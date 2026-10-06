"""Synthetic-only HTTP, tenant and shared quota regression checks; no model/network calls."""
import os
import sys
import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from api.app import create_app
from src.agent import agent_graph, chat_usage_store, tools
from src.agent.auth_session_store import issue_session, revoke_session, get_session
from src.agent.commerce_store import import_order_csv


class ChatSecurityTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "test.db"
        self.environment = patch.dict(os.environ, {
            "DATABASE_URL": "sqlite:///" + str(self.path), "USE_MANAGED_POSTGRES": "0",
            "SESSION_SIGNING_KEY": "synthetic-only-session-key-at-least-32-chars",
        })
        self.environment.start()
        self.clock = patch.object(chat_usage_store, "datetime")
        self.clock.start().now.return_value = datetime.now(timezone.utc).replace(second=0, microsecond=0)
        self.client = create_app().test_client()
        self.tokens = {owner: issue_session(owner, "operator") for owner in ("merchant-a", "merchant-b")}

    def tearDown(self):
        self.clock.stop()
        self.environment.stop()
        self.directory.cleanup()

    def headers(self, owner="merchant-a"):
        return {"Authorization": "Bearer " + self.tokens[owner]}

    def test_missing_forged_revoked_and_expired_sessions_do_not_call_ai(self):
        revoked = issue_session("revoked", "operator")
        revoke_session(get_session(revoked)["session_id"])
        expired = issue_session("expired", "operator")
        with closing(sqlite3.connect(self.path)) as conn, conn:
            conn.execute("UPDATE auth_sessions SET expires_at = '2000-01-01' WHERE username = 'expired'")
        with patch.object(agent_graph, "run_with_history") as model:
            for token in (None, "forged", revoked, expired):
                headers = {} if token is None else {"Authorization": "Bearer " + token}
                self.assertEqual(self.client.post("/v1/chat", json={"message": "trend"}, headers=headers).status_code, 401)
            model.assert_not_called()

    def test_http_owner_is_authenticated_and_queries_only_that_store(self):
        mapping = {"order_id": "id", "ordered_at": "date", "total_amount": "amount"}
        defaults = {"currency": "USD", "market": "US", "timezone": "UTC"}
        for owner, amount in (("merchant-a", 11), ("merchant-b", 99)):
            import_order_csv(f"id,date,amount\n{owner},2026-09-01T00:00:00Z,{amount}\n".encode(), owner, mapping, owner, defaults)

        def fake_agent(message, history, *, owner):
            return {"tool_results": [tools.query_sales_trend(owner=owner)]}

        with patch.object(agent_graph, "run_with_history", side_effect=fake_agent) as model:
            for owner, amount in (("merchant-a", 11), ("merchant-b", 99)):
                response = self.client.post("/v1/chat", json={"message": "trend", "owner": "someone-else"}, headers=self.headers(owner))
                self.assertEqual(response.status_code, 200)
                self.assertIn(f"{amount:,.2f}", response.json["evidence"][0]["summary"])
                self.assertEqual(model.call_args.kwargs["owner"], owner)
        with patch.object(tools, "get_connected_sales_trend") as query:
            self.assertFalse(tools.query_sales_trend()["success"])
            query.assert_not_called()

    def test_model_cannot_override_owner_and_missing_owner_does_not_call_model(self):
        fake = SimpleNamespace(invoke=lambda prompt: SimpleNamespace(content='[{"tool":"query_sales_trend","args":{"owner":"merchant-b","months":6}}]'))
        with patch.object(agent_graph, "_get_llm", return_value=fake) as model, patch.object(tools, "get_connected_sales_trend", return_value={"success": True, "data": [], "summary": "synthetic"}) as query:
            result = agent_graph.fetch_data_node({"user_query": "trend", "owner": "merchant-a"})
            self.assertIsNone(result["error"])
            query.assert_called_once_with(6, owner="merchant-a")
            model.reset_mock()
            self.assertTrue(agent_graph.fetch_data_node({"user_query": "trend"})["error"])
            model.assert_not_called()

    def test_rate_limits_survive_new_app_and_sessions_and_do_not_charge_denials(self):
        with patch.object(agent_graph, "run_with_history", return_value={}) as model:
            for _ in range(3):
                self.assertEqual(self.client.post("/v1/chat", json={"message": "trend"}, headers=self.headers()).status_code, 200)
            another = create_app().test_client()
            new_token = issue_session("merchant-a", "operator")
            denied = another.post("/v1/chat", json={"message": "trend"}, headers={"Authorization": "Bearer " + new_token})
            self.assertEqual(denied.status_code, 429)
            self.assertGreater(int(denied.headers["Retry-After"]), 0)
            self.assertEqual(model.call_count, 3)
            self.assertEqual(another.post("/v1/chat", json={"message": "trend"}, headers=self.headers("merchant-b")).status_code, 200)
        with closing(sqlite3.connect(self.path)) as conn, conn:
            self.assertEqual(conn.execute("SELECT used FROM chat_usage WHERE bucket LIKE 'day:merchant-a:%'").fetchone()[0], 3)

    def test_daily_and_global_limits_fail_closed(self):
        chat_usage_store._ensure_schema()
        for prefix, maximum in (("day:merchant-a:", 20), ("global:", 100)):
            with closing(sqlite3.connect(self.path)) as conn, conn:
                conn.execute("DELETE FROM chat_usage")
            chat_usage_store.reserve_chat_call("merchant-a")
            with closing(sqlite3.connect(self.path)) as conn, conn:
                conn.execute("UPDATE chat_usage SET used = ? WHERE bucket LIKE ?", (maximum, prefix + "%"))
            with patch.object(agent_graph, "run_with_history") as model:
                self.assertEqual(self.client.post("/v1/chat", json={"message": "trend"}, headers=self.headers()).status_code, 429)
                model.assert_not_called()
        with patch.object(chat_usage_store, "reserve_chat_call", side_effect=RuntimeError("synthetic outage")), patch.object(agent_graph, "run_with_history") as model:
            self.assertEqual(self.client.post("/v1/chat", json={"message": "trend"}, headers=self.headers()).status_code, 503)
            model.assert_not_called()

    def test_concurrent_calls_cannot_exceed_minute_limit(self):
        def call(_):
            try:
                chat_usage_store.reserve_chat_call("merchant-a")
                return True
            except chat_usage_store.ChatLimitExceeded:
                return False
        with ThreadPoolExecutor(max_workers=6) as executor:
            self.assertEqual(sum(executor.map(call, range(6))), 3)

    def test_invalid_input_never_spends_quota(self):
        with patch.object(chat_usage_store, "reserve_chat_call") as reserve:
            for payload in ({}, {"message": "x" * 1501}, ["invalid"]):
                self.assertEqual(self.client.post("/v1/chat", json=payload, headers=self.headers()).status_code, 400)
            reserve.assert_not_called()

    def test_cloud_model_has_output_timeout_and_retry_limits(self):
        with patch.dict(os.environ, {"LLM_PROVIDER": "openai", "OPENAI_API_KEY": "synthetic-not-a-real-key"}), patch("langchain_openai.ChatOpenAI") as model:
            agent_graph._get_llm()
            self.assertEqual(model.call_args.kwargs["max_tokens"], 1200)
            self.assertEqual(model.call_args.kwargs["timeout"], 30)
            self.assertEqual(model.call_args.kwargs["max_retries"], 0)


if __name__ == "__main__":
    unittest.main()

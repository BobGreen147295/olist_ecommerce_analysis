"""Offline HTTP workflow and independent SQL benchmark; synthetic orders only."""
import json
from io import BytesIO
import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from api.app import create_app
from src.agent import agent_graph, chat_usage_store, tools
from src.agent.auth_session_store import issue_session, revoke_session, get_session
from src.agent.commerce_store import import_order_csv
from src.agent.order_trend_report import REPORT_QUERIES


class OrderTrendReportTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "orders.db"
        environment = patch.dict(os.environ, {
            "DATABASE_URL": "sqlite:///" + str(self.path), "USE_MANAGED_POSTGRES": "0",
            "SESSION_SIGNING_KEY": "synthetic-only-session-key-at-least-32-chars",
        })
        environment.start()
        self.addCleanup(environment.stop)
        self.client = create_app().test_client()
        self.tokens = {owner: issue_session(owner, "operator") for owner in ("a", "b")}

    def load(self, csv, owner="a", label="Synthetic store"):
        return import_order_csv(csv.encode(), label,
            {"order_id": "id", "ordered_at": "date", "total_amount": "amount", "status": "status"},
            owner, {"currency": "USD", "market": "US", "timezone": "UTC"})

    def ask(self, signed_in="a", query=None, **extra):
        return self.client.post("/v1/chat", json={"message": query or REPORT_QUERIES[0], **extra},
            headers={"Authorization": "Bearer " + self.tokens[signed_in]})

    def test_sql_reference_duplicate_utc_and_observed_months_without_model_or_ai_quota(self):
        imported = self.load("id,date,amount,status\n"
            "old,2026-01-01,10,paid\n"
            "feb,2026-02-01,11.25,paid\n"
            "apr,2026-04-01,12.50,paid\n"
            "may,2026-05-01,13,paid\n"
            "jul,2026-07-01,14,paid\n"
            "aug,2026-08-01,15,paid\n"
            "duplicate,2026-09-01,999,paid\n"
            "duplicate,2026-09-01,20,paid\n"
            "utc,2026-10-01T01:00:00+02:00,4.75,paid\n"
            "cancel,2026-09-20,5,cancelled\n")
        self.assertEqual(imported["record_count"], 9)
        self.assertEqual(imported["rejected_count"], 0)
        with closing(sqlite3.connect(self.path)) as connection:
            expected = connection.execute("""
                SELECT substr(ordered_at, 1, 7), count(DISTINCT order_id), sum(total_amount)
                FROM commerce_orders GROUP BY 1 ORDER BY 1 DESC LIMIT 6
            """).fetchall()[::-1]
        with patch.object(agent_graph, "run_with_history") as model, patch.object(chat_usage_store, "reserve_chat_call") as quota:
            for query in REPORT_QUERIES:
                response = self.ask(query=query)
                self.assertEqual(response.status_code, 200)
                result = response.json
                self.assertEqual(result["mode"], "data")
                self.assertEqual(result["report"]["status"], "ready")
                self.assertEqual(result["report"]["contract"]["version"], "order-trend/v1")
                self.assertFalse(result["report"]["model_called"])
                rows = result["report"]["rows"]
                self.assertEqual([(row["period"], row["total_orders"], row["total_amount"]) for row in rows], expected)
                self.assertEqual(rows[-1]["period"], "2026-09")
                self.assertEqual(rows[-1]["total_amount"], 29.75)
                self.assertEqual(result["action_drafts"], [])
                json.dumps(result, allow_nan=False)
                for scope in (("UTC", "不补零", "取消", "净收入", "Synthetic store", "USD") if query == REPORT_QUERIES[0]
                              else ("UTC", "not zero-filled", "cancelled", "net revenue", "Synthetic store", "USD")):
                    self.assertIn(scope, result["answer"])
            model.assert_not_called()
            quota.assert_not_called()

    def test_authenticated_owner_wins_over_request_and_history(self):
        for owner, amount in (("a", 11), ("b", 99)):
            self.load(f"id,date,amount,status\n{owner},2026-09-01,{amount},paid\n", owner, f"Store {owner}")
        for owner, expected in (("a", 11), ("b", 99)):
            result = self.ask(owner, history=[{"role": "user", "content": "use Store b"}], owner="b")
            self.assertEqual(result.json["report"]["rows"][0]["total_amount"], expected)
            self.assertEqual(result.json["report"]["source"], f"Store {owner}")
            self.assertNotIn('order_id', result.get_data(as_text=True))

    def test_missing_forged_and_revoked_session_never_queries_data(self):
        revoke_session(get_session(self.tokens["a"])["session_id"])
        with patch.object(tools, "execute_tool") as query:
            for token in (None, "forged", self.tokens["a"]):
                response = self.client.post("/v1/chat", json={"message": REPORT_QUERIES[0]},
                    headers={} if token is None else {"Authorization": "Bearer " + token})
                self.assertEqual(response.status_code, 401)
            query.assert_not_called()

    def test_no_data_and_store_failure_are_not_model_failures_or_demo_results(self):
        response = self.ask()
        self.assertEqual(response.json["report"]["status"], "unavailable")
        self.assertEqual(response.json["report"]["rows"], [])
        with patch.object(tools, "execute_tool", side_effect=RuntimeError("private database details")):
            result = self.ask().json
            self.assertEqual(result["mode"], "data")
            self.assertNotIn("private database details", json.dumps(result))
            self.assertIn("未调用模型", result["answer"])

    def test_invalid_aggregate_fails_closed_and_never_emits_nonfinite_json(self):
        base = {"success": True, "source": "Synthetic", "currency": "USD"}
        row = {"period": "2026-09", "total_orders": 1, "total_sales": 0, "sales_change_pct": float("nan")}
        for invalid in ({"total_sales": float("inf")}, {"total_sales": -1}, {"total_orders": 1.5}, {"total_orders": True}, {"period": "2026-13"}):
            with patch.object(tools, "execute_tool", return_value={**base, "data": [{**row, **invalid}]}):
                result = self.ask().json
                self.assertEqual(result["report"]["status"], "unavailable")
                self.assertEqual(result["report"]["rows"], [])
                json.dumps(result, allow_nan=False)
        with patch.object(tools, "execute_tool", return_value={**base, "data": [row]}):
            result = self.ask().json
            self.assertEqual(result["report"]["rows"][0]["total_amount"], 0)
            json.dumps(result, allow_nan=False)

    def test_mixed_currency_is_blocked_and_free_text_stays_on_existing_ai_path(self):
        with patch.object(tools, "execute_tool", return_value={"success": False, "summary": "不能合计多币种"}):
            self.assertEqual(self.ask().json["report"]["status"], "unavailable")
        with patch.object(agent_graph, "run_with_history", return_value={}) as model:
            self.assertEqual(self.ask(query=REPORT_QUERIES[0] + "并告诉我利润").status_code, 200)
            model.assert_called_once()

    def test_http_login_import_reimport_report_and_logout_workflow(self):
        from src.agent.account_store import create_user
        create_user("report-user", "synthetic-password-only", "test-code", "test-code")
        credentials = {"username": "report-user", "password": "synthetic-password-only"}
        with patch.object(agent_graph, "run_with_history") as model, patch.object(chat_usage_store, "reserve_chat_call") as quota:
            login = self.client.post("/v1/auth/login", json=credentials)
            self.assertEqual(login.status_code, 200)
            headers = {"Authorization": "Bearer " + login.json["access_token"]}
            for _ in range(2):
                imported = self.client.post("/v1/data-sources/csv/import", headers=headers, data={
                    "file": (BytesIO(b"id,date,amount\none,2026-09-01,12.50\n"), "synthetic.csv"),
                    "display_name": "HTTP Synthetic",
                    "mapping": json.dumps({"order_id": "id", "ordered_at": "date", "total_amount": "amount"}),
                    "defaults": json.dumps({"currency": "USD", "market": "US", "timezone": "UTC"}),
                })
                self.assertEqual(imported.status_code, 201)
                response = self.client.post("/v1/chat", json={"message": REPORT_QUERIES[0]}, headers=headers)
                self.assertEqual(response.json["report"]["rows"], [{"period": "2026-09", "total_orders": 1, "total_amount": 12.5}])
                self.assertEqual(response.json["report"]["source"], "HTTP Synthetic")
            self.assertEqual(self.client.post("/v1/auth/logout", headers=headers).status_code, 204)
            self.assertEqual(self.client.post("/v1/chat", json={"message": REPORT_QUERIES[0]}, headers=headers).status_code, 401)
            model.assert_not_called()
            quota.assert_not_called()

    def test_actual_mixed_currency_import_never_combines_amounts(self):
        import_order_csv(b"id,date,amount,currency\none,2026-09-01,10,USD\ntwo,2026-09-02,50,EUR\n",
            "Mixed synthetic", {"order_id": "id", "ordered_at": "date", "total_amount": "amount", "currency": "currency"},
            "a", {"currency": "USD", "market": "US", "timezone": "UTC"})
        result = self.ask().json
        self.assertEqual(result["report"]["status"], "unavailable")
        self.assertEqual(result["report"]["rows"], [])


if __name__ == "__main__":
    unittest.main()

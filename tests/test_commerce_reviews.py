"""Synthetic-account facade and fixed-service transport boundaries. No real providers."""
import json
import os
import threading
import unittest
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest.mock import patch

import test_order_trend_report as fixture
from src.agent.research_gateway import request_review, owner_scope, ResearchRejected, ResearchUnavailable


class CommerceReviewTests(unittest.TestCase):
    setUp = fixture.OrderTrendReportTests.setUp
    load = fixture.OrderTrendReportTests.load

    def headers(self, owner="a"):
        return {"Authorization": "Bearer " + self.tokens[owner]}

    def test_session_controls_owner_and_only_server_report_crosses_the_bridge(self):
        self.load("id,date,amount,status\na,2026-08-01,60,paid\nb,2026-09-01,120,paid\n")
        self.load("id,date,amount,status\nx,2026-08-01,900,paid\ny,2026-09-01,999,paid\n", owner="b")
        with patch("api.commerce_reviews.request_review", return_value={"reviews": []}) as gateway:
            self.assertEqual(self.client.get("/v1/commerce").status_code, 401)
            gateway.assert_not_called()
            result = self.client.get("/v1/commerce", headers={**self.headers(), "X-Commerce-Owner": owner_scope("b")})
            self.assertEqual(result.status_code, 200)
            self.assertEqual(gateway.call_args.args, ("GET", "", "a"))
            self.assertIn("no-store", result.headers["Cache-Control"])
            self.client.get("/v1/commerce/report", headers=self.headers())
            self.assertEqual(gateway.call_args.args[3]["report"]["comparison"]["amount_delta"], 60)
            self.client.get("/v1/commerce/report", headers=self.headers("b"))
            self.assertEqual(gateway.call_args.args[3]["report"]["comparison"]["amount_delta"], 99)
            value = {"requestId": str(uuid.uuid4()), "snapshotId": "a" * 64, "decision": "no_action", "note": "先核对期间", "nextAction": "", "dueOn": None}
            self.assertEqual(self.client.post("/v1/commerce/reviews", headers=self.headers(), json={**value, "report": {"owner": "b"}}).status_code, 400)
            self.assertEqual(self.client.post("/v1/commerce/reviews", headers=self.headers(), json={**value, "owner": "b"}).status_code, 400)
            self.assertEqual(self.client.get("/v1/commerce?owner=b", headers=self.headers()).status_code, 400)
            self.assertEqual(self.client.post("/v1/commerce/reviews", headers=self.headers(), json=value).status_code, 200)
            sent = gateway.call_args.args
            self.assertEqual(sent[2], "a")
            self.assertEqual(sent[3]["report"]["comparison"]["amount_delta"], 60)
            self.assertNotIn("orders", sent[3]["report"])
            self.assertNotIn(self.tokens["a"], json.dumps(sent))

    def test_action_task_and_outcome_routes_are_fixed_and_authentication_failures_are_redacted(self):
        review, task = str(uuid.uuid4()), str(uuid.uuid4())
        with patch("api.commerce_reviews.request_review", return_value={"ok": True}) as gateway:
            for path, payload in [
                (f"/reviews/{review}/assistant", {"requestId": task, "question": "核对缺失覆盖", "platform": "综合"}),
                (f"/reviews/{review}/actions", {"taskId": task, "actionIndex": 0, "version": 1, "dueOn": "2026-11-01"}),
                (f"/reviews/{review}/assistant/{task}/retry", {}),
            ]:
                result = self.client.post("/v1/commerce" + path, headers=self.headers(), json=payload)
                self.assertEqual(result.status_code, 200)
                self.assertEqual(gateway.call_args.args[:3], ("POST", path, "a"))
            self.assertEqual(self.client.patch(f"/v1/commerce/reviews/{review}", headers=self.headers(), json={"outcome": "覆盖不足，仍需补数据", "version": 1}).status_code, 200)
            self.assertEqual(self.client.delete(f"/v1/commerce/reviews/{review}", headers=self.headers()).status_code, 204)
            count = gateway.call_count
            self.assertEqual(self.client.post("/v1/commerce/reviews/../assistant", headers=self.headers(), json={}).status_code, 404)
            self.assertEqual(gateway.call_count, count)
        with patch("api.commerce_reviews.request_review", side_effect=ResearchRejected(409, "数据已变化，请重新核对")):
            self.assertEqual(self.client.get("/v1/commerce", headers=self.headers()).status_code, 409)
        with patch("api.commerce_reviews.request_review", side_effect=ResearchUnavailable("private service key must not appear")):
            result = self.client.get("/v1/commerce", headers=self.headers())
            self.assertEqual(result.status_code, 503)
            self.assertNotIn("private", result.get_data(as_text=True))
        with patch("src.agent.auth_session_store.get_session", side_effect=RuntimeError("private database detail")):
            result = self.client.get("/v1/commerce", headers=self.headers())
            self.assertEqual(result.status_code, 503)
            self.assertNotIn("private", result.get_data(as_text=True))

    def test_cross_origin_preflight_supports_all_review_methods(self):
        with patch.dict(os.environ, {"ALLOWED_ORIGINS": "https://merchant.example"}):
            response = self.client.options("/v1/commerce/reviews/" + str(uuid.uuid4()), headers={"Origin": "https://merchant.example", "Access-Control-Request-Method": "PATCH"})
            self.assertEqual(response.status_code, 204)
            self.assertIn("PATCH", response.headers["Access-Control-Allow-Methods"])
            self.assertIn("DELETE", response.headers["Access-Control-Allow-Methods"])


class GatewayTests(unittest.TestCase):
    def test_service_key_is_backend_only_direct_bounded_and_never_follows_redirects(self):
        hits = []
        class Handler(BaseHTTPRequestHandler):
            mode = "normal"
            def do_GET(self):
                hits.append((self.path, self.headers.get("Authorization"), self.headers.get("X-Commerce-Owner")))
                self.send_response(302 if self.mode == "redirect" else 409 if self.mode == "conflict" else 200)
                if self.mode == "redirect": self.send_header("Location", "https://example.org/must-not-follow")
                self.end_headers()
                self.wfile.write(b'{"detail":"refresh evidence"}' if self.mode == "conflict" else b'{"reviews":[]}')
            def log_message(self, *_args): pass
        server = HTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        key = "test-fixed-service-key-at-least-32-characters"
        try:
            base = f"http://127.0.0.1:{server.server_port}"
            with patch.dict(os.environ, {"RESEARCH_SERVICE_URL": base, "RESEARCH_SERVICE_KEY": key, "HTTP_PROXY": "http://127.0.0.1:1"}):
                self.assertEqual(request_review("GET", "", "a"), {"reviews": []})
                self.assertEqual(hits[-1], ("/api/internal/research/commerce", "Bearer " + key, owner_scope("a")))
                Handler.mode = "redirect"
                with self.assertRaises(ResearchUnavailable): request_review("GET", "", "a")
                Handler.mode = "conflict"
                with self.assertRaises(ResearchRejected) as rejected: request_review("GET", "", "a")
                self.assertEqual(rejected.exception.status, 409)
                for url in ("http://example.org", base + "/other", base + "?owner=b", "https://user:password@example.org"):
                    with patch.dict(os.environ, {"RESEARCH_SERVICE_URL": url}):
                        with self.assertRaises(ResearchUnavailable): request_review("GET", "", "a")
                self.assertEqual(len(hits), 3)
        finally:
            server.shutdown(); server.server_close(); thread.join()

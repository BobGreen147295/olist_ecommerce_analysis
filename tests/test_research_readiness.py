"""Release checks exercise GETs only against an isolated local service."""
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

from scripts.check_research_integration import check, CheckFailed


class ReadinessTests(unittest.TestCase):
    def setUp(self):
        self.hits = []
        self.responses = {
            "/health": {"status": "ok"},
            "/v1/commerce": {"configured": True, "aiEnabled": False, "reviews": []},
            "/v1/commerce/report": {"snapshot": {"id": "a" * 64, "report": {"status": "ready"}}},
        }
        case = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                case.hits.append((self.command, self.path, self.headers.get("Authorization")))
                value = case.responses[self.path]
                self.send_response(value if isinstance(value, int) else 200)
                if value == 302:
                    self.send_header("Location", "/must-not-follow")
                self.end_headers()
                self.wfile.write(json.dumps(value).encode())

            def log_message(self, *_args):
                pass

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"
        self.addCleanup(self.thread.join)
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def test_manual_review_readiness_needs_no_model_and_uses_only_authenticated_gets(self):
        result = check(self.base, "synthetic-session")
        self.assertFalse(result["ai_access"])
        self.assertEqual(result["mutations"], 0)
        self.assertEqual(result["model_submissions"], 0)
        self.assertEqual(self.hits, [("GET", "/health", None), ("GET", "/v1/commerce", "Bearer synthetic-session"),
                                     ("GET", "/v1/commerce/report", "Bearer synthetic-session")])
        self.assertNotIn("synthetic-session", json.dumps(result))

    def test_unconfigured_expired_and_old_deployments_fail_instead_of_claiming_ready(self):
        for response, expected in [(503, "503"), (401, "401"), (302, "302"),
                                   ({"reviews": []}, "review_contract_not_ready")]:
            with self.subTest(response=response):
                self.responses["/v1/commerce"] = response
                self.hits.clear()
                with self.assertRaisesRegex(CheckFailed, expected):
                    check(self.base, "synthetic-session")
                self.assertEqual(len(self.hits), 2)
        self.responses["/v1/commerce"] = {"configured": True, "aiEnabled": True, "reviews": []}
        self.responses["/v1/commerce/report"]["snapshot"]["report"]["status"] = "unavailable"
        with self.assertRaisesRegex(CheckFailed, "order_data_not_ready"):
            check(self.base, "synthetic-session")

    def test_invalid_origins_and_tokens_never_make_a_request(self):
        for base, token in [("http://public.example", "token"), (self.base + "?owner=b", "token"),
                            (self.base + "/other", "token"), ("https://user:password@example.org", "token"),
                            (self.base, ""), (self.base, "token\r\nprivate")]:
            with self.assertRaises(CheckFailed):
                check(base, token)
        self.assertEqual(self.hits, [])

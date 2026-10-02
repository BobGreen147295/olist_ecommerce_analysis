"""Regression checks for acceptance gaps using synthetic data and temporary storage."""
from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from api.app import app, _shopify_opportunity_readiness, _shopify_store_opportunities, _shopify_order_trend
from scripts.evaluate_product import BASE, run_evaluation, synthetic_summary
from src.agent.evaluation import evaluate_experiment
from src.agent.observability import evaluate_response_quality
from src.agent.task_store import create_task, load_tasks, prepare_manual_execution


class EvaluationFixTests(unittest.TestCase):
    def test_original_acceptance_suite(self):
        for case in run_evaluation():
            with self.subTest(case=case["id"]):
                self.assertEqual(case["status"], "pass", case["detail"])

    def test_invalid_numbers_are_rejected(self):
        for field in BASE:
            for value in (float("nan"), float("inf"), -float("inf"), None, True, "10", 10**1000):
                with self.subTest(field=field, value_type=type(value).__name__), self.assertRaises(ValueError):
                    evaluate_experiment(**{**BASE, field: value})
        for field in ("treatment_users", "control_users", "treatment_orders", "control_orders"):
            with self.subTest(field=field), self.assertRaises(ValueError):
                evaluate_experiment(**{**BASE, field: 1.5})
        self.assertEqual(evaluate_experiment(**BASE)["warnings"], [])
        self.assertTrue(evaluate_experiment(**{**BASE, "treatment_users": 29})["warnings"])

    def test_invalid_trends_do_not_produce_signals(self):
        for field, value in (("date", "invalid"), ("date", "2026-02-30"), ("net_sales", None),
                             ("net_sales", float("nan")), ("gross_sales", -1), ("refunds", float("inf"))):
            summary = synthetic_summary()
            summary["order_trend"]["days"][0][field] = value
            with self.subTest(field=field, value=value):
                self.assertEqual(_shopify_opportunity_readiness(summary)["state"], "insufficient_data")
                self.assertEqual(_shopify_store_opportunities(summary), [])
        summary = synthetic_summary()
        summary["order_trend"]["days"][1]["date"] = summary["order_trend"]["days"][0]["date"]
        self.assertEqual(_shopify_store_opportunities(summary), [])
        summary = synthetic_summary()
        summary["order_trend"]["totals"]["gross_sales"] = 1
        self.assertEqual(_shopify_store_opportunities(summary), [])

    def test_sync_does_not_replace_missing_money_with_zero(self):
        for value in (None, {}, {"shopMoney": {}}, {"shopMoney": {"amount": "NaN"}},
                      {"shopMoney": {"amount": "Infinity"}}, {"shopMoney": {"amount": "-1"}},
                      {"shopMoney": {"amount": "1e999"}}):
            node = {"createdAt": "2026-09-01T00:00:00Z", "totalPriceSet": {"shopMoney": {"amount": "10"}},
                    "currentTotalPriceSet": value}
            with self.subTest(value=value), self.assertRaises(ValueError):
                _shopify_order_trend([node], 30, False)
        node["currentTotalPriceSet"] = {"shopMoney": {"amount": "0"}}
        self.assertEqual(_shopify_order_trend([node], 30, False)["totals"]["net_sales"], 0)

    def test_evidence_requires_matching_current_tool_data(self):
        result = {"tool_results": [{"tool": "trend", "success": True, "data": [{"sales": 120}]}],
                  "diagnosis": {"findings": [{"source": "trend", "evidence": [{"path": "0.sales", "value": 120}]}]}}
        score = evaluate_response_quality(result)
        self.assertEqual(score["evidence_coverage"], 1)
        self.assertEqual(score["source_citation_rate"], 1)
        for evidence in ([{"path": "0.sales", "value": 999}], [{"path": "1.sales", "value": 120}],
                         ["Sales = 120"], [{"path": "0.sales", "value": True}]):
            invalid = deepcopy(result)
            invalid["diagnosis"]["findings"][0]["evidence"] = evidence
            self.assertEqual(evaluate_response_quality(invalid)["evidence_coverage"], 0)
        result["tool_results"][0]["success"] = False
        self.assertEqual(evaluate_response_quality(result)["source_citation_rate"], 0)

    def test_route_rejects_fractional_counts_without_persisting_result(self):
        with tempfile.TemporaryDirectory() as directory, \
             patch("src.agent.task_store.TASKS_PATH", Path(directory) / "tasks.json"), \
             patch("src.agent.task_store._use_database", return_value=False), \
             patch("api.app._require_session", return_value={"username": "synthetic-eval"}):
            task = create_task({"title": "Synthetic", "audience": "Synthetic cohort"},
                               source_diagnosis={"source": "consented_reactivation_aggregate"}, owner="synthetic-eval")
            prepare_manual_execution(task["task_id"], channel="email", budget=200, market="US",
                                     locale="en-US", attribution_window_days=7, owner="synthetic-eval")
            client = app.test_client()
            for changes in ({"treatment_users": 100.5}, {"control_orders": 1.5}, {"cost": float("nan")}, {"treatment_revenue": None}):
                response = client.post(f"/v1/tasks/{task['task_id']}/observed-result", json={**BASE, **changes})
                self.assertEqual(response.status_code, 400)
                self.assertEqual(load_tasks()[0]["status"], "confirmed")
            response = client.post(f"/v1/tasks/{task['task_id']}/observed-result", json=BASE)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.get_json()["task"]["result"]["roi"], 4)

    def test_draft_persists_snapshot_and_blocked_input_cannot_create_task(self):
        summary = {**synthetic_summary(), "currency_code": "USD"}
        with tempfile.TemporaryDirectory() as directory, \
             patch("src.agent.task_store.TASKS_PATH", Path(directory) / "tasks.json"), \
             patch("src.agent.task_store._use_database", return_value=False), \
             patch("api.app._require_session", return_value={"username": "synthetic-eval"}), \
             patch("src.agent.merchant_connection_store.get_shopify_connection_status", return_value={"summary": summary}):
            client = app.test_client()
            for signal_id in ("net_sales_decline", "refund_pressure"):
                response = client.post("/v1/tasks/from-shopify-signal", json={"signal_id": signal_id})
                self.assertEqual(response.status_code, 201)
                source = response.get_json()["task"]["source_diagnosis"]
                self.assertEqual(source["provenance"]["currency"], "USD")
                self.assertEqual(source["provenance"]["observed_end"], "2026-09-14")
                self.assertEqual(len(source["summary_sha256"]), 64)
                self.assertEqual(load_tasks()[0]["source_diagnosis"], source)
            summary["order_trend"]["truncated"] = True
            self.assertEqual(client.post("/v1/tasks/from-shopify-signal", json={"signal_id": "net_sales_decline"}).status_code, 400)
            self.assertEqual(len(load_tasks()), 2)


if __name__ == "__main__":
    unittest.main()

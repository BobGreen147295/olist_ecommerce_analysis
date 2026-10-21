"""Deterministic acceptance: no network, no model, synthetic tenant data only."""
import json
import sqlite3
import unittest
from contextlib import closing
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import test_order_trend_report as fixture
from src.agent import agent_graph, chat_usage_store, tools
from src.agent.order_trend_report import COMPARISON_QUERIES


class OrderComparisonTests(unittest.TestCase):
    setUp = fixture.OrderTrendReportTests.setUp
    load = fixture.OrderTrendReportTests.load
    ask = fixture.OrderTrendReportTests.ask
    def test_two_period_difference_works_with_model_and_quota_unavailable(self):
        self.load("id,date,amount,status\na,2026-07-01,999,paid\nb,2026-08-01,10,paid\nc,2026-08-02,20,paid\nd,2026-08-03,30,paid\ne,2026-09-01,60,paid\nf,2026-09-02,60,paid\n")
        with patch.object(agent_graph, "run_with_history", side_effect=RuntimeError("model offline")) as model, patch.object(chat_usage_store, "reserve_chat_call", side_effect=RuntimeError("quota offline")) as quota:
            for query in (*COMPARISON_QUERIES, "核对近两期订单金额变化", "核对最近两个月订单金额？"):
                result = self.ask(query=query).json
                self.assertFalse(result["report"]["model_called"])
                c = result["report"]["comparison"]
                self.assertEqual((c["previous"]["total_amount"], c["current"]["total_amount"]), (60, 120))
                self.assertEqual((c["amount_delta"], c["change_pct"], c["orders_delta"]), (60, 100, -1))
                self.assertEqual(c["previous"]["start"], "2026-08-01")
                self.assertEqual(c["current"]["end_exclusive"], "2026-10-01")
                self.assertTrue(c["consecutive"])
                self.assertEqual(result["action_drafts"], [])
                self.assertNotIn("order_id", json.dumps(result))
            model.assert_not_called()
            quota.assert_not_called()

    def test_decimal_sum_and_decline_percentage_match_hand_calculation(self):
        self.load("id,date,amount,status\na,2026-08-01,0.1,paid\nb,2026-08-02,0.2,paid\nc,2026-09-01,0.1,paid\n")
        c = self.ask().json["report"]["comparison"]
        self.assertEqual(c["amount_delta"], -0.2)
        self.assertEqual(c["change_pct"], -66.67)

    def test_zero_baseline_has_no_percentage_and_gap_not_claimed_month_over_month(self):
        self.load("id,date,amount,status\na,2026-07-01,0,paid\nb,2026-09-01,20,paid\n")
        report = self.ask().json["report"]
        self.assertIsNone(report["comparison"]["change_pct"])
        self.assertEqual(report["comparison"]["percentage_status"], "zero_baseline")
        self.assertFalse(report["comparison"]["consecutive"])
        self.assertIn("period_gap", [i["code"] for i in report["issues"]])
        json.dumps(report, allow_nan=False)

    def test_one_period_never_invents_a_baseline(self):
        self.load("id,date,amount,status\na,2026-09-01,10,paid\n")
        report = self.ask().json["report"]
        self.assertIsNone(report["comparison"])
        self.assertIn("one_period", [i["code"] for i in report["issues"]])

    def test_stale_snapshot_and_missing_metadata_are_not_reported_as_live_sync(self):
        self.load("id,date,amount,status\na,2026-08-01,10,paid\nb,2026-09-01,20,paid\n")
        old = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
        with closing(sqlite3.connect(self.path)) as connection:
            connection.execute("UPDATE commerce_data_sources SET created_at=?", (old,))
            connection.commit()
        report = self.ask().json["report"]
        self.assertEqual(report["provenance"]["freshness"], "stale")
        self.assertEqual(report["provenance"]["imported_at"], old)
        self.assertIn("snapshot_stale", [i["code"] for i in report["issues"]])
        with patch.object(tools, "execute_tool", return_value={"success": True, "currency": "USD", "source": "Synthetic", "data": [{"period": "2026-09", "total_orders": 1, "total_sales": 1}]}):
            self.assertIn("metadata_unknown", [i["code"] for i in self.ask().json["report"]["issues"]])

    def test_corrupt_stored_rows_block_instead_of_silently_dropping_or_zeroing(self):
        self.load("id,date,amount,status\na,2026-09-01,10,paid\n")
        with closing(sqlite3.connect(self.path)) as connection:
            connection.execute("UPDATE commerce_orders SET ordered_at=?", ("invalid-date",))
            connection.commit()
        result = self.ask().json
        self.assertEqual(result["error_code"], "invalid_source_rows")
        self.assertEqual(result["report"]["rows"], [])

    def test_open_and_future_months_are_distinguished(self):
        current = datetime.now(timezone.utc).strftime("%Y-%m")
        base = {"success": True, "currency": "USD", "source": "Synthetic"}
        with patch.object(tools, "execute_tool", return_value={**base, "data": [{"period": "2020-01", "total_orders": 1, "total_sales": 1}, {"period": current, "total_orders": 1, "total_sales": 2}]}):
            self.assertIn("open_period", [i["code"] for i in self.ask().json["report"]["issues"]])
        with patch.object(tools, "execute_tool", return_value={**base, "data": [{"period": "9998-01", "total_orders": 1, "total_sales": 1}]}):
            self.assertEqual(self.ask().json["error_code"], "future_period")

    def test_no_source_is_actionable_not_an_ai_quota_error(self):
        result = self.ask().json
        self.assertEqual(result["error_code"], "source_required")
        self.assertIn("导入", result["answer"])

    def test_malformed_metadata_and_unrepresentable_percentage_fail_safely(self):
        base = {"success": True, "currency": "USD", "source": "Synthetic", "source_metadata": ["bad metadata"]}
        rows = [{"period": "2026-08", "total_orders": 1, "total_sales": 0.01},
                {"period": "2026-09", "total_orders": 1, "total_sales": 1e308}]
        with patch.object(tools, "execute_tool", return_value={**base, "data": rows}):
            result = self.ask().json
            self.assertEqual(result["error_code"], "invalid_aggregate")
            json.dumps(result, allow_nan=False)
        with patch.object(tools, "execute_tool", return_value={**base, "data": rows[:1]}):
            self.assertIn("metadata_unknown", [i["code"] for i in self.ask().json["report"]["issues"]])

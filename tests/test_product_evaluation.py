"""Check the acceptance harness itself, independently of product acceptance."""
import unittest
from copy import deepcopy
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.evaluate_product import BASE, check_signal_evidence, equal_metrics, sql_metrics, sql_signal_evidence, synthetic_summary


class AcceptanceHarnessTests(unittest.TestCase):
    def test_sql_matches_hand_calculated_answer(self):
        equal_metrics(sql_metrics(BASE), dict(treatment_conversion=.2, control_conversion=.1,
            conversion_uplift_pp=10, relative_lift=1, incremental_orders=10,
            incremental_revenue=1000, roi=4))

    def test_comparator_rejects_wrong_missing_and_nonfinite_numbers(self):
        for actual in ({"roi": 40}, {}, {"roi": float("nan")}, {"roi": float("inf")}):
            with self.subTest(actual=actual), self.assertRaises(AssertionError):
                equal_metrics(actual, {"roi": 4})

    def test_traceability_detects_tampered_evidence(self):
        evidence = sql_signal_evidence(synthetic_summary())
        self.assertEqual(evidence["net_sales_decline"], {"recent_net_sales": 420, "previous_net_sales": 700})
        self.assertEqual(evidence["refund_pressure"], {"gross_sales": 1680, "refunds": 560})
        signals = [dict(id=key, evidence=value) for key, value in evidence.items()]
        check_signal_evidence(signals, evidence)
        tampered = deepcopy(signals)
        tampered[0]["evidence"]["recent_net_sales"] = 999
        for invalid in (tampered, signals[:1], signals + signals[:1]):
            with self.subTest(invalid=invalid), self.assertRaises(AssertionError):
                check_signal_evidence(invalid, evidence)

    def test_zero_denominators_remain_undefined(self):
        reference = sql_metrics({**BASE, "control_orders": 0, "control_revenue": 0, "cost": 0})
        self.assertIsNone(reference["roi"])
        self.assertIsNone(reference["relative_lift"])


if __name__ == "__main__":
    unittest.main()

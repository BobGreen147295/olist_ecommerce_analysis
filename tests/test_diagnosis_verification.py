"""Bounded graph verification acceptance with synthetic data and scripted model responses."""
import copy
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from api.app import create_app, _format_agent_answer
from src.agent.auth_session_store import issue_session
from src.agent import agent_graph
from src.agent.observability import diagnosis_validation_errors


DATA = [{"total_sales": 11.5, "total_orders": 2}]
VALID = {"data_sufficient": True, "findings": [{"title": "期间销售额", "source": "query_sales_trend",
         "evidence": [{"path": "0.total_sales", "value": 11.5, "label": "销售额"}]}]}
ROUTE = '[{"tool":"query_sales_trend","args":{}}]'


class DiagnosisVerificationTests(unittest.TestCase):
    def run_graph(self, *outputs, data_success=True):
        responses = [RuntimeError("synthetic failure") if value is None else
                     SimpleNamespace(content=value if isinstance(value, str) else json.dumps(value)) for value in outputs]
        model = SimpleNamespace(invoke=Mock(side_effect=responses))
        with patch.object(agent_graph, "_get_llm", return_value=model), patch.object(agent_graph, "execute_tool", return_value={
            "tool": "query_sales_trend", "success": data_success, "data": DATA if data_success else None,
            "summary": "synthetic aggregates" if data_success else "no data",
        }), patch.object(agent_graph, "append_run_log"):
            result = agent_graph.run_with_history("我的店订单趋势", owner="synthetic-a")
        return result, model.invoke

    def test_correct_references_pass_without_repair(self):
        result, invoke = self.run_graph(ROUTE, VALID, {"action_drafts": [{"title": "人工核对", "actions": ["核对期间"]}]})
        self.assertEqual(result["verification"], {"status": "passed", "analysis_attempts": 1})
        self.assertEqual(invoke.call_count, 3)
        self.assertTrue(result["action_drafts"])

    def test_wrong_number_is_repaired_once_before_recommendation(self):
        wrong = copy.deepcopy(VALID)
        wrong["findings"][0]["evidence"][0]["value"] = 999
        result, invoke = self.run_graph(ROUTE, wrong, VALID, {"action_drafts": []})
        self.assertEqual(result["verification"], {"status": "passed", "analysis_attempts": 2})
        self.assertEqual(invoke.call_count, 4)
        self.assertIn("唯一一次修正机会", invoke.call_args_list[2].args[0])
        self.assertNotIn("999", result["analysis"])

    def test_format_error_can_repair_and_does_not_use_summary_as_diagnosis(self):
        result, invoke = self.run_graph(ROUTE, "not JSON", VALID, {"action_drafts": []})
        self.assertEqual(result["verification"]["status"], "passed")
        self.assertEqual(invoke.call_count, 4)

    def test_repeated_bad_source_path_value_or_shape_stops_without_leaking_diagnosis(self):
        variants = []
        for field, value in (("source", "forged-source"), ("title", ""), ("evidence", [])):
            wrong = copy.deepcopy(VALID)
            wrong["findings"][0][field] = value
            variants.append(wrong)
        for field, value in (("path", "0.missing"), ("path", "-1.total_sales"), ("value", 999), ("value", True)):
            wrong = copy.deepcopy(VALID)
            wrong["findings"][0]["evidence"][0][field] = value
            variants.append(wrong)
        variants.extend(({}, {"data_sufficient": "true", "findings": []}, "invalid JSON"))
        for wrong in variants:
            with self.subTest(wrong=wrong):
                result, invoke = self.run_graph(ROUTE, wrong, wrong)
                self.assertEqual(invoke.call_count, 3)
                self.assertEqual(result["verification"]["status"], "failed")
                self.assertEqual(result["diagnosis"]["findings"], [])
                self.assertEqual(result["action_drafts"], [])
                self.assertEqual(result["analysis"], "")
                self.assertIn("不能交付可靠结论", _format_agent_answer(result))

    def test_insufficient_data_stops_without_repair_or_recommendation(self):
        result, invoke = self.run_graph(ROUTE, {"data_sufficient": False, "findings": [{"title": "unverified"}]})
        self.assertEqual(invoke.call_count, 2)
        self.assertEqual(result["verification"]["status"], "insufficient")
        self.assertEqual(result["diagnosis"]["findings"], [])
        self.assertEqual(result["action_drafts"], [])
        result, invoke = self.run_graph(ROUTE, data_success=False)
        self.assertEqual(invoke.call_count, 1)
        self.assertEqual(result["verification"]["analysis_attempts"], 0)

    def test_model_failure_is_not_retried_and_exception_details_are_not_returned(self):
        result, invoke = self.run_graph(ROUTE, None)
        self.assertEqual(invoke.call_count, 2)
        self.assertEqual(result["verification"]["status"], "failed")
        self.assertNotIn("synthetic failure", json.dumps(result))

    def test_recommend_node_cannot_bypass_verification(self):
        with patch.object(agent_graph, "_get_llm") as model:
            result = agent_graph.recommend_node({"diagnosis": VALID})
            self.assertEqual(result["action_drafts"], [])
            model.assert_not_called()

    def test_non_finite_values_are_not_valid_evidence(self):
        wrong = copy.deepcopy(VALID)
        wrong["findings"][0]["evidence"][0]["value"] = float("nan")
        self.assertTrue(diagnosis_validation_errors(wrong, [{"success": True, "tool": "query_sales_trend", "data": DATA}]))

    def test_http_never_returns_failed_findings_or_actions(self):
        wrong = copy.deepcopy(VALID)
        wrong["findings"][0]["evidence"][0]["value"] = 999
        model = SimpleNamespace(invoke=Mock(side_effect=[SimpleNamespace(content=content) for content in
                                (ROUTE, json.dumps(wrong), json.dumps(wrong))]))
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
            "DATABASE_URL": "sqlite:///" + str(Path(directory) / "test.db"), "USE_MANAGED_POSTGRES": "0",
            "SESSION_SIGNING_KEY": "synthetic-verification-key-at-least-32-chars",
        }), patch.object(agent_graph, "_get_llm", return_value=model), patch.object(agent_graph, "execute_tool", return_value={
            "tool": "query_sales_trend", "success": True, "data": DATA, "summary": "synthetic aggregates",
        }), patch.object(agent_graph, "append_run_log"):
            token = issue_session("synthetic-a", "operator")
            response = create_app().test_client().post("/v1/chat", json={"message": "我的店订单趋势"},
                                                      headers={"Authorization": "Bearer " + token})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json["verification"], {"status": "failed", "analysis_attempts": 2})
            self.assertEqual(response.json["diagnosis"]["findings"], [])
            self.assertEqual(response.json["action_drafts"], [])
            self.assertNotIn("999", json.dumps(response.json))
            self.assertEqual(model.invoke.call_count, 3)


if __name__ == "__main__":
    unittest.main()

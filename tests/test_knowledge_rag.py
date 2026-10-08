"""Public, synthetic-only retrieval and Co-pilot acceptance; no network/model spend."""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from api.app import create_app, _format_agent_answer
from src.agent import agent_graph, knowledge
from src.agent.auth_session_store import issue_session


class KnowledgeRagTests(unittest.TestCase):
    def test_retrieval_is_bounded_and_returns_original_versioned_sources(self):
        cases = (("复购率是什么意思", "retention-readiness"), ("什么是 profit margin", "profit-data"),
                 ("ROI 如何计算", "roi-evidence"), ("sales definition", "order-sales"))
        for query, expected in cases:
            documents = knowledge.retrieve_knowledge(query)
            self.assertEqual(documents[0]["id"], expected)
            self.assertEqual(documents[0]["scope"], "public_product_rule")
            self.assertIn(documents[0]["text"], knowledge.render_knowledge(documents))
            self.assertEqual(documents[0]["version"], "2026-10-07")
        self.assertLessEqual(len(knowledge.retrieve_knowledge("销售额利润复购ROI")), 3)
        self.assertEqual(knowledge.retrieve_knowledge("美国关税政策是什么"), [])
        self.assertEqual(knowledge.retrieve_knowledge("costume design"), [])

    def test_definition_and_unknown_questions_never_call_model_or_merchant_tool(self):
        with patch.object(agent_graph, "_get_llm") as llm, patch.object(agent_graph, "execute_tool") as tool, patch.object(agent_graph, "append_run_log"):
            result = agent_graph.run_with_history("复购率是什么意思", owner="synthetic-a")
            answer = _format_agent_answer(result)
            self.assertIn("不能从订单总数推算", answer)
            self.assertIn("retention-readiness", answer)
            self.assertEqual(result["action_drafts"], [])
            unknown = agent_graph.run_with_history("什么是美国关税政策", owner="synthetic-a")
            self.assertIn("没有与问题匹配的依据", _format_agent_answer(unknown))
            self.assertEqual(unknown["knowledge_sources"], [])
            llm.assert_not_called()
            tool.assert_not_called()

    def test_missing_owner_rejected_before_retrieval(self):
        with patch.object(agent_graph, "retrieve_knowledge") as retrieval:
            self.assertTrue(agent_graph.fetch_data_node({"user_query": "ROI 如何计算"})["error"])
            retrieval.assert_not_called()

    def test_insufficient_diagnosis_does_not_generate_action_or_spend_model_call(self):
        with patch.object(agent_graph, "_get_llm") as llm:
            result = agent_graph.recommend_node({"diagnosis": {"data_sufficient": False}})
            self.assertEqual(result["action_drafts"], [])
            llm.assert_not_called()
        self.assertIn("本次不生成执行策略", _format_agent_answer({"diagnosis": {"data_sufficient": False}}))

    def test_method_context_reaches_analysis_and_recommendation(self):
        documents = knowledge.retrieve_knowledge("利润")
        state = {"owner": "synthetic-a", "user_query": "我的店利润如何", "knowledge_sources": documents,
                 "tool_results": [{"tool": "query_sales_trend", "success": True, "data": [], "summary": "synthetic"}]}
        fake = SimpleNamespace(invoke=lambda prompt: SimpleNamespace(content='{"findings": [], "data_sufficient": false}'))
        with patch.object(agent_graph, "_get_llm", return_value=fake):
            with patch.object(fake, "invoke", wraps=fake.invoke) as invoke:
                agent_graph.analyze_node(state)
                self.assertIn(documents[0]["text"], invoke.call_args.args[0])
                self.assertIn("不是商家事实", invoke.call_args.args[0])
                agent_graph.recommend_node({**state, "diagnosis_verified": True})
                self.assertIn(documents[0]["text"], invoke.call_args.args[0])

    def test_business_query_keeps_owner_and_separates_methods_from_store_evidence(self):
        fake = SimpleNamespace(invoke=lambda prompt: SimpleNamespace(content='[{"tool":"query_sales_trend","args":{"owner":"other"}}]'))
        with patch.object(agent_graph, "_get_llm", return_value=fake), patch.object(agent_graph, "execute_tool", return_value={"success": False, "summary": "no data"}) as tool:
            result = agent_graph.fetch_data_node({"user_query": "我的店利润如何", "owner": "synthetic-a"})
            tool.assert_called_once_with("query_sales_trend", owner="synthetic-a")
            self.assertFalse(result.get("knowledge_only"))
            answer = _format_agent_answer(result)
            self.assertIn("不能生成经营结论", answer)
            self.assertIn("不是店铺事实", answer)
            self.assertNotIn("建议先做一轮", answer)

    def test_http_uses_existing_auth_quota_and_exposes_matching_sources(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
            "DATABASE_URL": "sqlite:///" + str(Path(directory) / "test.db"),
            "USE_MANAGED_POSTGRES": "0", "SESSION_SIGNING_KEY": "synthetic-rag-key-at-least-32-characters",
        }), patch.object(agent_graph, "_get_llm") as llm, patch.object(agent_graph, "append_run_log"):
            client = create_app().test_client()
            self.assertEqual(client.post("/v1/chat", json={"message": "ROI 如何计算"}).status_code, 401)
            for owner in ("synthetic-a", "synthetic-b"):
                token = issue_session(owner, "operator")
                response = client.post("/v1/chat", json={"message": "ROI 如何计算", "owner": "other"}, headers={"Authorization": "Bearer " + token})
                self.assertEqual(response.status_code, 200)
                self.assertIn("roi-evidence", response.json["answer"])
                self.assertEqual(response.json["knowledge_sources"][0]["id"], "roi-evidence")
                self.assertEqual(response.json["action_drafts"], [])
            llm.assert_not_called()


if __name__ == "__main__":
    unittest.main()

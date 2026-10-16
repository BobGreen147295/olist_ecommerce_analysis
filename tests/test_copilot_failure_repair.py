"""Co-pilot shortcut and failure regressions; scripted models, no paid calls."""
import json
import os
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from api.app import _format_agent_answer
from src.agent import agent_graph, knowledge


class CopilotRepairTests(unittest.TestCase):
    def test_luna_uses_bounded_non_reasoning_chat_parameters(self):
        # Capture the actual SDK payload without making a provider request.
        with patch.dict(os.environ, {
            'LLM_PROVIDER': 'openai', 'OPENAI_MODEL': 'gpt-5.6-luna',
            'OPENAI_API_KEY': 'synthetic-not-a-key',
        }):
            model = agent_graph._get_llm()
        payload = model._get_request_payload('Reply OK')
        self.assertEqual(payload['model'], 'gpt-5.6-luna')
        self.assertEqual(payload['max_completion_tokens'], 1200)
        self.assertEqual(payload['reasoning_effort'], 'none')
        self.assertFalse(payload['store'])
        self.assertNotIn('temperature', payload)
        self.assertNotIn('max_tokens', payload)
        self.assertEqual(model.max_retries, 0)
        self.assertEqual(model.request_timeout, 30)

    def test_all_shipped_shortcuts_are_method_answers_without_model_or_store_access(self):
        queries = [
            '为什么要先做流失客户召回？', 'Why prioritize churn reactivation?',
            '当前 ROI 可以相信吗？', 'Can I trust the current ROI?',
            '还缺哪些数据连接？', 'Which data connections are missing?',
        ]
        with patch.object(agent_graph, '_get_llm') as model, \
             patch.object(agent_graph, 'execute_tool') as tool, \
             patch.object(agent_graph, 'append_run_log'):
            for query in queries:
                with self.subTest(query=query):
                    result = agent_graph.run_with_history(query, owner='synthetic-a')
                    self.assertTrue(result.get('knowledge_only'))
                    self.assertTrue(result['knowledge_sources'])
                    self.assertFalse(result['error'])
                    self.assertEqual(result['action_drafts'], [])
                    self.assertNotIn('分析服务不可用', _format_agent_answer(result))
            model.assert_not_called()
            tool.assert_not_called()

    def test_shortcut_explains_conditions_not_a_guaranteed_business_priority(self):
        with patch.object(agent_graph, '_get_llm') as model, patch.object(agent_graph, 'append_run_log'):
            result = agent_graph.run_with_history('为什么要先做流失客户召回？', owner='synthetic-a')
        self.assertIn('不一定', _format_agent_answer(result))
        self.assertNotIn('200 人', _format_agent_answer(result))
        model.assert_not_called()

    def test_real_measurements_and_mixed_questions_stay_on_data_path(self):
        for query in ['我的店本月复购率怎么算', 'Why prioritize churn reactivation for my store this month?',
                      '当前 ROI 可以相信吗？请核对我的订单', '昨天 ROI 如何计算', '还缺哪些数据连接？请分析本周订单']:
            with self.subTest(query=query):
                self.assertFalse(knowledge.is_knowledge_question(query))

    def test_model_failure_stops_at_every_stage_without_fabricated_actions(self):
        state = {'owner': 'synthetic-a', 'user_query': '我的店订单趋势', 'diagnosis_verified': True,
                 'diagnosis': {'data_sufficient': True, 'findings': []},
                 'tool_results': [{'tool': 'query_sales_trend', 'success': True, 'data': [{'total_sales': 10}]}]}
        for stage, handler in [('routing', agent_graph.fetch_data_node), ('analysis', agent_graph.analyze_node),
                               ('recommendation', agent_graph.recommend_node)]:
            for factory in [False, True]:
                with self.subTest(stage=stage, factory=factory):
                    model = SimpleNamespace(invoke=Mock(side_effect=TimeoutError('secret-synthetic-detail')))
                    kwargs = {'side_effect': TimeoutError('secret-synthetic-detail')} if factory else {'return_value': model}
                    with patch.object(agent_graph, '_get_llm', **kwargs), patch.object(agent_graph, 'execute_tool') as tool:
                        result = handler(state)
                    self.assertEqual(result['error_code'], 'model_timeout')
                    self.assertEqual(result['error_stage'], stage)
                    self.assertEqual(result['action_drafts'], [])
                    self.assertNotIn('secret-synthetic-detail', json.dumps(result))
                    tool.assert_not_called()

    def test_provider_errors_are_distinct_and_never_echo_provider_body(self):
        for status, provider_code, expected in [
            (401, None, 'model_authentication_failed'), (403, None, 'model_permission_denied'),
            (404, None, 'model_not_found'), (429, 'insufficient_quota', 'model_quota_exceeded'),
            (429, None, 'model_rate_limited'), (500, None, 'model_unavailable'),
        ]:
            error = RuntimeError('secret-synthetic-detail')
            error.status_code, error.code = status, provider_code
            with patch.object(agent_graph, '_get_llm', side_effect=error):
                result = agent_graph.analyze_node({'owner': 'synthetic-a', 'user_query': 'trend'})
            self.assertEqual(result['error_code'], expected)
            self.assertIn(expected, _format_agent_answer(result))
            self.assertNotIn('secret-synthetic-detail', json.dumps(result))

    def test_verification_failure_is_not_reported_as_a_model_outage(self):
        result = agent_graph.verify_node({'analysis_attempts': 2, 'diagnosis': {}})
        self.assertEqual(result['error_code'], 'evidence_verification_failed')
        self.assertIn('未通过证据核验', _format_agent_answer(result))

    def test_billing_429_is_not_misreported_as_temporary_throttling(self):
        for code in ('credit_balance_exhausted', 'organization_spend_limit_exceeded',
                     'project_spend_limit_exceeded'):
            with self.subTest(code=code):
                error = RuntimeError('private-provider-body')
                error.status_code, error.code = 429, code
                result = agent_graph._model_failure(error, 'routing')
                self.assertEqual(result['error_code'], 'model_quota_exceeded')
                self.assertEqual(result['provider_error_code'], code)
                self.assertNotIn('private-provider-body', json.dumps(result))
        error = RuntimeError('private-provider-body')
        error.status_code, error.code, error.type = 429, None, 'insufficient_quota'
        self.assertEqual(agent_graph._model_failure(error, 'routing')['error_code'], 'model_quota_exceeded')

    def test_provider_diagnostics_never_echo_unrecognized_codes(self):
        error = RuntimeError('private-provider-body')
        error.status_code, error.code, error.type = 429, 'private-token-value', 'private-account-value'
        result = agent_graph._model_failure(error, 'routing')
        self.assertEqual(result['provider_error_code'], 'unclassified')
        self.assertEqual(result['provider_status'], 429)
        self.assertNotIn('private-', json.dumps(result))

    def test_empty_recommendations_do_not_invent_a_generic_task(self):
        model = SimpleNamespace(invoke=Mock(return_value=SimpleNamespace(content='{"action_drafts": []}')))
        with patch.object(agent_graph, '_get_llm', return_value=model):
            result = agent_graph.recommend_node({'user_query': 'trend', 'diagnosis_verified': True})
        self.assertEqual(result['action_drafts'], [])


if __name__ == '__main__':
    unittest.main()

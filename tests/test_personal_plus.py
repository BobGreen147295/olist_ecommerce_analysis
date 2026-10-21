"""Synthetic personal transport and account boundary checks. Never calls a provider."""
import os
import secrets
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from scripts.personal_plus_app import create_personal_app, ORIGIN
from src.agent.personal_plus import PersonalPlusLLM, PersonalPlusError
from src.agent import agent_graph
from src.agent.auth_session_store import issue_session

ENV = {'LLM_PROVIDER': 'personal_plus', 'PERSONAL_PLUS_LOCAL': '1',
       'PERSONAL_PLUS_BRIDGE_URL': 'http://127.0.0.1:63100',
       'PERSONAL_PLUS_BRIDGE_SECRET': secrets.token_urlsafe(32), 'RENDER': ''}


class PersonalAdapterTests(unittest.TestCase):
    def test_fixed_loopback_and_local_flag_required_no_key_fallback(self):
        for overrides in ({'RENDER': 'true'}, {'PERSONAL_PLUS_LOCAL': ''},
                          {'PERSONAL_PLUS_BRIDGE_SECRET': ''},
                          *({'PERSONAL_PLUS_BRIDGE_URL': url} for url in (
                              'https://127.0.0.1:63100', 'http://localhost:63100', 'http://example.com',
                              'http://127.0.0.1:63100/redirect', 'http://user@127.0.0.1:63100',
                              'http://127.0.0.1:63100?secret=foo'))):
            with self.subTest(overrides=overrides), patch.dict(os.environ, {**ENV, **overrides, 'OPENAI_API_KEY': secrets.token_urlsafe(32)}):
                with self.assertRaises(PersonalPlusError):
                    agent_graph._get_llm()

    def test_adapter_contract_disables_proxies_redirects_and_does_not_send_api_key(self):
        response = SimpleNamespace(status_code=200, content=b'{}', json=lambda: {'content': 'completed synthetic'})
        with patch.dict(os.environ, ENV), patch('src.agent.personal_plus.requests.Session') as session:
            client = session.return_value.__enter__.return_value
            client.post.return_value = response
            model = agent_graph._get_llm()
            self.assertEqual(model.invoke('synthetic').content, 'completed synthetic')
            self.assertFalse(client.trust_env)
            args, kwargs = client.post.call_args
            self.assertEqual(args, ('http://127.0.0.1:63100/personal/invoke',))
            self.assertEqual(kwargs['json'], {'prompt': 'synthetic'})
            self.assertFalse(kwargs['allow_redirects'])
            self.assertEqual(kwargs['timeout'], (3, 50))
            with self.assertRaises(PersonalPlusError):
                model.invoke('x' * 24_001)
            self.assertEqual(client.post.call_count, 1)

    def test_failure_is_allowlisted_and_graph_never_recommends(self):
        for code in ('personal_authorization_required', 'personal_usage_stopped', 'personal_inference_failed'):
            model = SimpleNamespace(invoke=MagicMock(side_effect=PersonalPlusError(code)))
            with patch.object(agent_graph, '_get_llm', return_value=model):
                result = agent_graph.fetch_data_node({'owner': 'personal-owner', 'user_query': '本月订单趋势'})
            self.assertIn('不会', result['error'])
            self.assertEqual(result['action_drafts'], [])
            self.assertEqual(model.invoke.call_count, 1)

    def test_stream_failure_diagnostic_is_allowlisted_without_provider_text(self):
        with patch.dict(os.environ, ENV):
            result = agent_graph._model_failure(PersonalPlusError('personal_output_limit', 502, 'stream_too_large'), 'analysis')
            self.assertEqual(result['error_code'], 'personal_output_limit')
            self.assertEqual(result['provider_error_code'], 'stream_too_large')
            unsafe = agent_graph._model_failure(PersonalPlusError('personal_inference_failed', 502, 'untrusted-provider-text'), 'analysis')
            self.assertEqual(unsafe['provider_error_code'], 'unclassified')


class PersonalAppTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.environment = patch.dict(os.environ, {**ENV, 'USE_MANAGED_POSTGRES': '0',
            'DATABASE_URL': 'sqlite:///' + str(Path(self.directory.name) / 'personal.db'),
            'SESSION_SIGNING_KEY': secrets.token_urlsafe(32),
            'APP_ADMIN_USERNAME': 'personal-owner', 'APP_ADMIN_PASSWORD': secrets.token_urlsafe(24)})
        self.environment.start()
        Path(self.directory.name, 'data.html').write_text('synthetic local page', encoding='utf-8')
        segment = Path(self.directory.name, 'data/__next.data/__PAGE__.txt')
        segment.parent.mkdir(parents=True)
        segment.write_text('synthetic segment', encoding='utf-8')
        self.client = create_personal_app(Path(self.directory.name)).test_client()

    def tearDown(self):
        self.environment.stop()
        self.directory.cleanup()

    def send(self, path, method='GET', **kwargs):
        return self.client.open(path, method=method, base_url=ORIGIN, **kwargs)

    def test_host_cross_origin_mutations_registration_and_merchant_forms_blocked(self):
        self.assertEqual(self.client.get('/data').status_code, 403)
        for origin in (None, 'null', 'https://olist-revenueops.pages.dev'):
            self.assertEqual(self.send('/v1/auth/login', 'POST', headers={'Origin': origin} if origin else {}).status_code, 403)
        for path in ('/v1/auth/register', '/v1/pilot-applications', '/v1/integrations/shopify/authorize'):
            self.assertEqual(self.send(path, 'POST', headers={'Origin': ORIGIN}).status_code, 403)
        with self.send('/data') as page:
            self.assertEqual(page.data, b'synthetic local page')
        with self.send('/data/__next.data.__PAGE__.txt') as segment:
            self.assertEqual(segment.data, b'synthetic segment')
        self.assertEqual(self.send('/.env.personal-plus').status_code, 404)

    def test_existing_login_logout_and_account_isolation_stay_enforced(self):
        with patch.object(agent_graph, '_get_llm') as model:
            self.assertEqual(self.send('/v1/chat', 'POST', headers={'Origin': ORIGIN}, json={'message': '趋势'}).status_code, 401)
            other = issue_session('someone-else', 'admin')
            self.assertEqual(self.send('/v1/auth/me', headers={'Authorization': 'Bearer ' + other}).status_code, 403)
            login = self.send('/v1/auth/login', 'POST', headers={'Origin': ORIGIN}, json={'username': 'personal-owner', 'password': os.environ['APP_ADMIN_PASSWORD']})
            self.assertEqual(login.status_code, 200)
            headers = {'Origin': ORIGIN, 'Authorization': 'Bearer ' + login.json['access_token']}
            result = self.send('/v1/chat', 'POST', headers=headers, json={'message': '当前 ROI 可以相信吗？'})
            self.assertEqual(result.status_code, 200)
            self.assertEqual(result.json['mode'], 'knowledge')
            self.assertEqual(self.send('/v1/auth/logout', 'POST', headers=headers).status_code, 204)
            self.assertEqual(self.send('/v1/auth/me', headers=headers).status_code, 401)
            model.assert_not_called()


if __name__ == '__main__':
    unittest.main()

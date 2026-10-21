"""Authentication errors must not be confused with payload validation errors."""
import unittest
from unittest.mock import patch

from api.app import app


class SessionStatusTests(unittest.TestCase):
    def test_protected_routes_reject_missing_and_expired_sessions(self):
        routes = [
            ('GET', '/v1/tasks'), ('POST', '/v1/chat'),
            ('POST', '/v1/tasks/from-shopify-signal'), ('POST', '/v1/tasks/from-reactivation-signal'),
            ('POST', '/v1/tasks/probe/confirm'), ('POST', '/v1/tasks/probe/start'),
            ('GET', '/v1/tasks/probe/execution-package.csv'),
            ('POST', '/v1/tasks/probe/observed-result'), ('POST', '/v1/tasks/probe/diagnostic-review'),
            ('POST', '/v1/data-sources/csv/preview'), ('POST', '/v1/data-sources/csv/import'),
            ('DELETE', '/v1/data-sources/orders'), ('GET', '/v1/data-health'),
            ('GET', '/v1/integrations/shopify/status'), ('POST', '/v1/integrations/shopify/sync'),
            ('DELETE', '/v1/integrations/shopify'), ('GET', '/v1/opportunities/reactivation'),
        ]
        client = app.test_client()
        with patch('src.agent.auth_session_store.get_session', side_effect=ValueError('Expired synthetic session')):
            for headers in [{}, {'Authorization': 'Bearer expired-synthetic-token'}]:
                for method, path in routes:
                    with self.subTest(path=path, authenticated=bool(headers)):
                        response = client.open(path, method=method, headers=headers, json={})
                        self.assertEqual(response.status_code, 401)
                        self.assertIn('error', response.get_json())

    def test_authenticated_validation_error_remains_400(self):
        with patch('api.app._require_session', return_value={'username': 'synthetic'}):
            response = app.test_client().post('/v1/tasks/from-shopify-signal', json={})
        self.assertEqual(response.status_code, 400)


if __name__ == '__main__':
    unittest.main()

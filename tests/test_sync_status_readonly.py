"""Status reads must not implicitly sync, call a model or disguise outages as logout."""
import unittest
from unittest.mock import patch
import test_order_trend_report as fixture


class SyncStatusReadOnlyTests(unittest.TestCase):
    setUp = fixture.OrderTrendReportTests.setUp

    def status(self):
        return self.client.get('/v1/integrations/shopify/status', headers={'Authorization': 'Bearer ' + self.tokens['a']})

    def test_legacy_snapshot_is_disclosed_without_remote_sync_or_data_import(self):
        connection = {'status': 'synced', 'summary': {'orders': 2}, 'last_synced_at': '2026-09-01T00:00:00Z'}
        with patch('src.agent.merchant_connection_store.get_shopify_connection_status', return_value=connection) as read, patch('api.app.requests.post') as remote, patch('src.agent.commerce_store.import_order_csv') as imported:
            response = self.status()
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json['connection']['opportunity_readiness']['state'], 'trend_required')
            read.assert_called_once_with('a')
            remote.assert_not_called()
            imported.assert_not_called()

    def test_storage_outage_does_not_masquerade_as_expired_login_or_leak_exception(self):
        with patch('src.agent.merchant_connection_store.get_shopify_connection_status', side_effect=RuntimeError('private connection detail')):
            response = self.status()
            self.assertEqual(response.status_code, 503)
            self.assertNotIn('private connection detail', response.get_data(as_text=True))
        with patch('src.agent.merchant_connection_store.get_shopify_connection_status', return_value=None):
            self.assertEqual(self.status().status_code, 200)

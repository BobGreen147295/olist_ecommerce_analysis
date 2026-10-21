from copy import deepcopy
from datetime import datetime, timezone
import unittest
from unittest.mock import patch

from api.app import app, _shopify_opportunity_readiness, _shopify_store_opportunities, _shopify_signal_draft
from scripts.evaluate_product import synthetic_summary


class SnapshotFreshnessTests(unittest.TestCase):
    def test_existing_standalone_shopify_checks(self):
        from test_shopify_order_trend import main as aggregation
        from test_shopify_opportunity_readiness import main as readiness
        from test_shopify_store_opportunities import main as opportunities
        aggregation()
        readiness()
        opportunities()

    def test_old_missing_future_and_naive_snapshots_cannot_create_new_drafts(self):
        with patch('api.app._shopify_now', return_value=datetime(2026, 10, 15, tzinfo=timezone.utc)):
            for timestamp in ['2026-09-15T00:00:00Z', None, 'invalid',
                              '2026-10-16T00:00:00Z', '2026-10-15T00:00:00']:
                summary = synthetic_summary()
                summary['order_trend']['synced_at'] = timestamp
                with self.subTest(timestamp=timestamp):
                    self.assertNotEqual(_shopify_opportunity_readiness(summary)['state'], 'ready')
                    self.assertEqual(_shopify_store_opportunities(summary), [])
                    with self.assertRaises(ValueError):
                        _shopify_signal_draft(summary, 'net_sales_decline')

    def test_zero_order_days_use_sync_date_not_last_sale(self):
        summary = synthetic_summary()
        summary['order_trend']['synced_at'] = '2026-09-22T00:00:00Z'
        with patch('api.app._shopify_now', return_value=datetime(2026, 9, 22, 12, tzinfo=timezone.utc)):
            signals = _shopify_store_opportunities(summary)
        decline = next(signal for signal in signals if signal['id'] == 'net_sales_decline')
        self.assertEqual(decline['evidence'], {'recent_net_sales': 0, 'previous_net_sales': 420})
        self.assertEqual(decline['provenance']['observed_end'], '2026-09-21')
        self.assertIn('2026-09-21', decline['title'])

    def test_stale_http_draft_request_never_writes_a_task(self):
        with patch('api.app._shopify_now', return_value=datetime(2026, 10, 15, tzinfo=timezone.utc)), \
             patch('api.app._require_session', return_value={'username': 'synthetic'}), \
             patch('src.agent.merchant_connection_store.get_shopify_connection_status', return_value={'summary': synthetic_summary()}), \
             patch('src.agent.task_store.create_task') as create:
            response = app.test_client().post('/v1/tasks/from-shopify-signal', json={'signal_id': 'net_sales_decline'})
            self.assertEqual(response.status_code, 400)
            create.assert_not_called()

    def test_partial_current_day_does_not_change_comparison(self):
        summary = synthetic_summary()
        with patch('api.app._shopify_now', return_value=datetime(2026, 9, 15, 12, tzinfo=timezone.utc)):
            expected = _shopify_store_opportunities(summary)
            extra = deepcopy(summary['order_trend']['days'][-1])
            extra.update(date='2026-09-15', net_sales=10000, gross_sales=10000, refunds=0)
            summary['order_trend']['days'].append(extra)
            summary['order_trend']['orders_scanned'] += 2
            for key in ['orders', 'net_sales', 'gross_sales', 'refunds']:
                summary['order_trend']['totals'][key] += extra[key]
            self.assertEqual(_shopify_store_opportunities(summary), expected)

    def test_fresh_snapshot_still_rejects_future_order_dates(self):
        summary = synthetic_summary()
        summary['order_trend']['days'][-1]['date'] = '2026-09-16'
        with patch('api.app._shopify_now', return_value=datetime(2026, 9, 15, 12, tzinfo=timezone.utc)):
            self.assertEqual(_shopify_store_opportunities(summary), [])


if __name__ == '__main__':
    unittest.main()

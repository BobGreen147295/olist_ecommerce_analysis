"""Synthetic-only regression checks for the dormant-customer aggregate."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from src.agent import commerce_store


class ReactivationSafetyTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        environment = patch.dict(os.environ, {
            'DATABASE_URL': 'sqlite:///' + str(Path(self.directory.name) / 'orders.db'),
            'USE_MANAGED_POSTGRES': '0',
            'SESSION_SIGNING_KEY': 'synthetic-only-signing-key-at-least-32-chars',
        })
        environment.start()
        self.addCleanup(environment.stop)
        clock = patch.object(commerce_store, '_now', return_value='2026-10-15T12:00:00+00:00')
        clock.start()
        self.addCleanup(clock.stop)

    def import_rows(self, rows, owner='synthetic-a'):
        mapping = dict(order_id='id', ordered_at='date', total_amount='amount',
                       customer_id='customer', marketing_consent='consent')
        commerce_store.import_order_csv(
            ('id,date,amount,customer,consent\n' + rows).encode(), 'Synthetic', mapping, owner,
            dict(currency='USD', market='US', timezone='UTC'))

    def test_inactivity_uses_current_clock_not_last_order_in_export(self):
        self.import_rows('old,2026-01-01T00:00:00Z,100,anonymous-a,granted\n')
        result = commerce_store.get_reactivation_signal('synthetic-a')
        self.assertEqual(result['cutoff_date'], '2026-07-17')
        self.assertEqual(result['reference_at'], '2026-10-15T12:00:00+00:00')
        self.assertEqual(result['eligible_customers'], 1)

    def test_later_denied_or_unknown_consent_excludes_customer(self):
        for consent in ('denied', 'unknown'):
            with self.subTest(consent=consent):
                self.import_rows('old,2026-01-01T00:00:00Z,100,anonymous-a,granted\n'
                                 f'new,2026-02-01T00:00:00Z,10,anonymous-a,{consent}\n')
                result = commerce_store.get_reactivation_signal('synthetic-a')
                self.assertNotEqual(result['state'], 'ready')
                self.assertNotIn('anonymous-a', str(result))

    def test_conflicting_consent_at_same_latest_time_fails_closed(self):
        self.import_rows('a,2026-01-01T00:00:00Z,100,anonymous-a,granted\n'
                         'b,2026-01-01T00:00:00Z,1,anonymous-a,denied\n')
        self.assertNotEqual(commerce_store.get_reactivation_signal('synthetic-a')['state'], 'ready')

    def test_future_orders_do_not_generate_an_opportunity(self):
        self.import_rows('future,2027-01-01T00:00:00Z,100,anonymous-a,granted\n')
        self.assertNotEqual(commerce_store.get_reactivation_signal('synthetic-a')['state'], 'ready')


if __name__ == '__main__':
    unittest.main()

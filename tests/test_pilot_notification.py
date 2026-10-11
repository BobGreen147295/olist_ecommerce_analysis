"""Synthetic database and mocked HTTP; never sends actual mail."""
import hashlib
import hmac
import os
import secrets
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import requests
from api.app import create_app
from src.agent.pilot_notification import notify_owner
from src.agent.pilot_application_store import list_pilot_applications


class PilotNotificationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.secret = secrets.token_hex(32)
        self.environment = patch.dict(os.environ, {
            'DATABASE_URL': 'sqlite:///' + str(Path(self.directory.name) / 'pilot.db'),
            'USE_MANAGED_POSTGRES': '0',
            'PILOT_NOTIFICATION_URL': 'https://script.google.com/macros/s/synthetic/exec',
            'PILOT_NOTIFICATION_SECRET': self.secret,
        })
        self.environment.start()
        self.payload = {'contact_email': 'synthetic@example.com', 'shop_domain': 'synthetic.myshopify.com',
                        'monthly_orders': '50-199', 'challenge': 'other', 'terms_accepted': True}
        self.client = create_app().test_client()

    def tearDown(self):
        self.environment.stop()
        self.directory.cleanup()

    def test_unconfigured_or_untrusted_url_never_requests(self):
        for settings in ({'PILOT_NOTIFICATION_SECRET': ''}, {'PILOT_NOTIFICATION_URL': 'http://localhost/exec'},
                         {'PILOT_NOTIFICATION_URL': 'https://attacker.invalid/exec'}):
            with patch.dict(os.environ, settings), patch('src.agent.pilot_notification.requests.post') as send:
                self.assertEqual(notify_owner('a' * 16), 'not_configured')
                send.assert_not_called()

    def test_success_sends_only_signed_opaque_identifier(self):
        result = Mock(status_code=200)
        result.json.return_value = {'ok': True}
        with patch('src.agent.pilot_notification.requests.post', return_value=result) as send:
            response = self.client.post('/v1/pilot-applications', json=self.payload)
        self.assertEqual(response.status_code, 201)
        event = send.call_args.kwargs['json']
        self.assertEqual(set(event), {'application_id', 'timestamp', 'signature'})
        expected = hmac.new(self.secret.encode(), f"{event['application_id']}.{event['timestamp']}".encode(), hashlib.sha256).hexdigest()
        self.assertEqual(event['signature'], expected)
        self.assertNotIn('synthetic@example.com', str(event))
        self.assertNotIn('notification', response.json)
        self.assertEqual(list_pilot_applications()[0]['application_id'], event['application_id'])

    def test_failure_never_loses_application_or_retries(self):
        for exception in (requests.Timeout('synthetic-only'), RuntimeError('synthetic bug')):
            with patch('src.agent.pilot_notification.requests.post', side_effect=exception) as send:
                self.assertEqual(self.client.post('/v1/pilot-applications', json=self.payload).status_code, 201)
                self.assertEqual(send.call_count, 1)
        self.assertEqual(len(list_pilot_applications()), 2)

    def test_validation_honeypot_storage_failure_never_notify(self):
        with patch('src.agent.pilot_notification.requests.post') as send:
            self.assertEqual(self.client.post('/v1/pilot-applications', json={**self.payload, 'terms_accepted': False}).status_code, 400)
            self.assertEqual(self.client.post('/v1/pilot-applications', json={**self.payload, 'website': 'bot'}).status_code, 201)
            with patch('src.agent.pilot_application_store.create_pilot_application', side_effect=RuntimeError('synthetic')):
                self.assertEqual(self.client.post('/v1/pilot-applications', json=self.payload).status_code, 503)
            send.assert_not_called()

    def test_only_google_content_redirect_followed_without_reposting(self):
        redirect = Mock(status_code=302, headers={'Location': 'https://script.googleusercontent.com/macros/echo?synthetic=1'})
        success = Mock(status_code=200)
        success.json.return_value = {'ok': True}
        with patch('src.agent.pilot_notification.requests.post', return_value=redirect) as send, patch('src.agent.pilot_notification.requests.get', return_value=success) as read:
            self.assertEqual(notify_owner('a' * 16), 'accepted')
            self.assertEqual(send.call_count, 1)
            self.assertEqual(read.call_count, 1)
        redirect.headers = {'Location': 'https://attacker.invalid/secret'}
        with patch('src.agent.pilot_notification.requests.post', return_value=redirect), patch('src.agent.pilot_notification.requests.get') as read:
            self.assertEqual(notify_owner('a' * 16), 'failed')
            read.assert_not_called()

    def test_invalid_response_never_claims_delivery(self):
        for payload in ({'ok': False}, {'ok': 'true'}, [], {'unexpected': 'synthetic'}):
            response = Mock(status_code=200)
            response.json.return_value = payload
            with patch('src.agent.pilot_notification.requests.post', return_value=response):
                self.assertEqual(notify_owner('a' * 16), 'failed')


if __name__ == '__main__':
    unittest.main()

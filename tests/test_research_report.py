"""Aggregate-only report boundary, using synthetic accounts and no provider calls."""
import os
import sqlite3
import unittest
from unittest.mock import patch

import test_order_trend_report as fixture
from src.agent import agent_graph, chat_usage_store


class ResearchReportTests(unittest.TestCase):
    setUp = fixture.OrderTrendReportTests.setUp
    load = fixture.OrderTrendReportTests.load

    def get(self, owner=None, **kwargs):
        headers = kwargs.pop('headers', {})
        if owner:
            headers['Authorization'] = 'Bearer ' + self.tokens[owner]
        return self.client.get('/v1/reports/order-comparison', headers=headers, **kwargs)

    def test_authenticated_report_is_account_bound_and_has_no_model_dependency(self):
        self.load('id,date,amount,status\na,2026-08-01,60,paid\nb,2026-09-01,120,paid\n')
        self.load('id,date,amount,status\nx,2026-08-01,900,paid\ny,2026-09-01,999,paid\n', owner='b')
        self.assertEqual(self.get().status_code, 401)
        with patch.object(agent_graph, 'run_with_history', side_effect=AssertionError('no model')) as model, patch.object(chat_usage_store, 'reserve_chat_call', side_effect=AssertionError('no quota')) as quota:
            result = self.get('a')
            self.assertEqual(result.status_code, 200)
            self.assertEqual(set(result.json), {'report'})
            self.assertEqual(result.json['report']['comparison']['amount_delta'], 60)
            self.assertFalse(result.json['report']['model_called'])
            self.assertIn('no-store', result.headers['Cache-Control'])
            model.assert_not_called()
            quota.assert_not_called()
        self.assertEqual(self.get('a', query_string={'owner': 'b'}).status_code, 400)
        self.assertEqual(self.get(headers={'Authorization': 'Bearer invalid'}).status_code, 401)

    def test_local_service_key_is_read_only_and_pinned_to_one_configured_account(self):
        self.load('id,date,amount,status\na,2026-08-01,60,paid\nb,2026-09-01,120,paid\n')
        key = 'synthetic-read-only-key-at-least-32-characters'
        environment = {'PERSONAL_PLUS_LOCAL': '1', 'RESEARCH_REPORT_KEY': key,
                       'RESEARCH_REPORT_OWNER': 'a', 'APP_ADMIN_USERNAME': 'a', 'RENDER': ''}
        with patch.dict(os.environ, environment):
            headers = {'X-Research-Report-Key': key}
            result = self.get(headers=headers)
            self.assertEqual(result.status_code, 200)
            self.assertEqual(result.json['report']['comparison']['change_pct'], 100)
            self.assertEqual(self.get(headers={'X-Research-Report-Key': 'incorrect'}).status_code, 401)
            self.assertEqual(self.get(headers={'X-Research-Report-Key': 'é'}).status_code, 401)
            self.assertEqual(self.get(headers={**headers, 'Origin': 'http://localhost:3000'}).status_code, 401)
            self.assertEqual(self.get(headers=headers, environ_overrides={'REMOTE_ADDR': '203.0.113.5'}).status_code, 401)
            self.assertEqual(self.client.get('/v1/tasks', headers=headers).status_code, 401)
            with patch.dict(os.environ, {'RESEARCH_REPORT_OWNER': 'b'}):
                self.assertEqual(self.get(headers=headers).status_code, 401)
            with patch.dict(os.environ, {'PERSONAL_PLUS_LOCAL': '0'}):
                self.assertEqual(self.get(headers=headers).status_code, 401)
            with patch.dict(os.environ, {'RENDER': 'true'}):
                self.assertEqual(self.get(headers=headers).status_code, 401)

    def test_unavailable_data_remains_an_explicit_report_not_an_ai_error(self):
        response = self.get('a')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['report']['status'], 'unavailable')
        self.assertIn('source_required', [item['code'] for item in response.json['report']['issues']])
        self.assertIsNone(response.json['report']['comparison'])

    def test_auth_store_failure_is_unavailable_without_exposing_storage_details(self):
        with patch('src.agent.auth_session_store.get_session', side_effect=sqlite3.OperationalError('private storage details')):
            response = self.get('a')
        self.assertEqual(response.status_code, 503)
        self.assertNotIn('private storage details', response.get_data(as_text=True))

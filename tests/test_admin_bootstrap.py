"""Configured administrator recovery, using temporary synthetic accounts only."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from api.app import create_app
from src.agent.account_store import authenticate_user, create_user
from src.agent.task_store import _connect_database


class AdminBootstrapTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.environment = patch.dict(os.environ, {
            "DATABASE_URL": "sqlite:///" + str(Path(self.directory.name) / "admin.db"),
            "USE_MANAGED_POSTGRES": "0",
            "SESSION_SIGNING_KEY": "synthetic-only-session-key-at-least-32-characters",
            "APP_ADMIN_USERNAME": "synthetic-owner",
            "APP_ADMIN_PASSWORD": "synthetic-owner-password",
        })
        self.environment.start()
        self.client = create_app().test_client()
        self.credentials = {"username": "synthetic-owner", "password": "synthetic-owner-password"}

    def tearDown(self):
        self.environment.stop()
        self.directory.cleanup()

    def login(self, credentials=None):
        return self.client.post("/v1/auth/login", json=credentials or self.credentials)

    def test_configured_admin_can_login_without_public_registration(self):
        login = self.login()
        self.assertEqual(login.status_code, 200)
        headers = {"Authorization": "Bearer " + login.json["access_token"]}
        self.assertEqual(self.client.get("/v1/auth/me", headers=headers).json["role"], "admin")
        self.assertEqual(self.client.get("/v1/pilot-applications", headers=headers).status_code, 200)
        self.assertEqual(self.login({**self.credentials, "password": "wrong"}).status_code, 401)

    def test_recover_only_configured_matching_account_and_issue_fresh_role(self):
        create_user("synthetic-owner", self.credentials["password"], "invite", "invite")
        create_user("ordinary-user", "ordinary-password", "invite", "invite")
        from src.agent.auth_session_store import issue_session
        old_headers = {"Authorization": "Bearer " + issue_session("synthetic-owner", "operator")}
        login = self.login()
        self.assertEqual(login.status_code, 200)
        headers = {"Authorization": "Bearer " + login.json["access_token"]}
        self.assertEqual(self.client.get("/v1/auth/me", headers=headers).json["role"], "admin")
        self.assertEqual(self.client.get("/v1/pilot-applications", headers=headers).status_code, 200)
        self.assertEqual(self.client.get("/v1/pilot-applications", headers=old_headers).status_code, 403)
        ordinary = self.login({"username": "ordinary-user", "password": "ordinary-password"})
        ordinary_headers = {"Authorization": "Bearer " + ordinary.json["access_token"]}
        denied = self.client.get("/v1/pilot-applications", headers=ordinary_headers)
        self.assertEqual(denied.status_code, 403)
        self.assertNotIn("applications", denied.json)

    def test_mismatched_existing_password_cannot_gain_admin(self):
        create_user("synthetic-owner", "different-existing-password", "invite", "invite")
        self.assertEqual(self.login().status_code, 503)
        self.assertEqual(authenticate_user("synthetic-owner", "different-existing-password")["role"], "operator")
        self.assertIsNone(authenticate_user("synthetic-owner", self.credentials["password"]))

    def test_incorrect_login_does_not_restore_role(self):
        create_user("synthetic-owner", self.credentials["password"], "invite", "invite")
        self.assertEqual(self.login({**self.credentials, "password": "wrong"}).status_code, 401)
        self.assertEqual(authenticate_user("synthetic-owner", self.credentials["password"])["role"], "operator")

    def test_existing_admin_password_is_not_reset_by_configuration(self):
        from src.agent.account_store import ensure_admin_account
        ensure_admin_account("synthetic-owner", "existing-admin-password")
        self.assertEqual(self.login().status_code, 401)
        self.assertEqual(self.login({**self.credentials, "password": "existing-admin-password"}).status_code, 200)

    def test_disabled_account_stays_disabled(self):
        create_user("synthetic-owner", self.credentials["password"], "invite", "invite")
        conn, placeholder = _connect_database()
        try:
            conn.execute(f"UPDATE app_users SET enabled = FALSE WHERE username = {placeholder}", ("synthetic-owner",))
            conn.commit()
        finally:
            conn.close()
        self.assertEqual(self.login().status_code, 401)
        self.assertIsNone(authenticate_user("synthetic-owner", self.credentials["password"]))

    def test_missing_admin_configuration_keeps_operator_role(self):
        create_user("synthetic-owner", self.credentials["password"], "invite", "invite")
        with patch.dict(os.environ, {"APP_ADMIN_PASSWORD": ""}):
            login = self.login()
        self.assertEqual(login.status_code, 200)
        headers = {"Authorization": "Bearer " + login.json["access_token"]}
        self.assertEqual(self.client.get("/v1/auth/me", headers=headers).json["role"], "operator")


if __name__ == "__main__":
    unittest.main()

"""Real, disposable PostgreSQL acceptance. Never accepts an external database URL.

Run directly: python tests/integration/pg_acceptance.py --bin-dir <Postgres bin>
Requires psycopg2 and the existing API test dependencies. Missing binaries fail,
not skip. Only synthetic records; no email/model integrations are invoked.
"""
import argparse
from contextlib import closing
from copy import deepcopy
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import psycopg2
from psycopg2 import sql
from api.app import create_app
from scripts import migrate_postgres as migration
from src.agent import task_store as store
from src.agent.auth_session_store import issue_session
from src.agent import account_store, pilot_application_store

START = "2026-01-01T00:00:00+00:00"
END = "2026-01-15T00:00:00+00:00"
OPTIONS = dict(channel="email", budget=200, market="US", locale="en-US", attribution_window_days=14)
VALUES = dict(treatment_users=100, treatment_orders=20, treatment_revenue=2000,
              control_users=100, control_orders=10, control_revenue=1000,
              cost=200, currency="USD", revenue_net_of_refunds=True)


def native_path(path):
    """EDB Windows tools need an ASCII alias for non-ASCII user directories."""
    if os.name != "nt" or str(path).isascii():
        return path
    import ctypes
    from ctypes import wintypes
    short_path = ctypes.windll.kernel32.GetShortPathNameW
    short_path.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD]
    short_path.restype = wintypes.DWORD
    buffer = ctypes.create_unicode_buffer(32768)
    size = short_path(str(path), buffer, len(buffer))
    alias = buffer.value if 0 < size < len(buffer) else ""
    if not alias.isascii() or not alias:
        # The desktop runtime may preserve the long user component in WinAPI
        # results; cmd's read-only path expansion still exposes its ASCII alias.
        if any(char in str(path) for char in '"%\n\r'):
            raise RuntimeError("Unsafe characters in PostgreSQL test path")
        alias = subprocess.check_output(
            f'cmd.exe /d /c for %I in ("{path}") do @echo %~sI',
            timeout=10).decode("ascii").strip()
    if not alias or not alias.isascii():
        raise RuntimeError("PostgreSQL test directory needs a Windows ASCII short-path alias")
    return Path(alias)


class PostgreSQLAcceptance(unittest.TestCase):
    def setUp(self):
        self.databases = []
        url = self.new_database()
        self.environment = patch.dict(os.environ, {
            "DATABASE_URL": url, "USE_MANAGED_POSTGRES": "0",
            "MIGRATION_TARGET_DATABASE_URL": "", "APP_ADMIN_USERNAME": "",
            "APP_ADMIN_PASSWORD": "", "PILOT_NOTIFICATION_URL": "",
            "SESSION_SIGNING_KEY": SESSION_KEY, "REGISTRATION_CODE": REGISTRATION_CODE,
        })
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.addCleanup(self.drop_databases)
        self.client = create_app().test_client()

    def new_database(self):
        name = "revops_accept_" + uuid.uuid4().hex
        with closing(psycopg2.connect(ADMIN_URL)) as conn:
            conn.autocommit = True
            with conn.cursor() as cursor:
                cursor.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        self.databases.append(name)
        return ADMIN_URL.rsplit("/", 1)[0] + "/" + name

    def drop_databases(self):
        with closing(psycopg2.connect(ADMIN_URL)) as conn:
            conn.autocommit = True
            with conn.cursor() as cursor:
                for name in self.databases:
                    # Only exact names created by this test instance are eligible.
                    cursor.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))

    def create(self, source="consented_reactivation_aggregate", owner="synthetic-a"):
        return store.create_task({"title": "合成测试任务"}, owner=owner,
                                 source_diagnosis={"source": source, "evidence": {"recent": 420}})

    def headers(self, owner="synthetic-a"):
        return {"Authorization": "Bearer " + issue_session(owner, "user")}

    def seed_related_records(self):
        for owner in ("synthetic-a", "synthetic-b"):
            account_store.create_user(owner, os.environ["PGPASSWORD"], REGISTRATION_CODE, REGISTRATION_CODE)
        conversation = account_store.create_conversation("synthetic-a", "Synthetic recovery check")
        account_store.append_message(conversation["conversation_id"], "synthetic-a", "user", "Synthetic message only")
        pilot_application_store.create_pilot_application("synthetic@example.invalid",
            "synthetic-recovery.myshopify.com", "100-500", "Synthetic diagnosis question")
        return self.headers(), self.headers("synthetic-b"), conversation["conversation_id"]

    def test_01_readiness_does_not_create_tables(self):
        response = self.client.get("/readyz")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, {"status": "ok", "database": "ok"})
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        with closing(psycopg2.connect(os.environ["DATABASE_URL"])) as conn, conn.cursor() as cursor:
            cursor.execute("SELECT tablename FROM pg_tables WHERE schemaname='public'")
            self.assertEqual(cursor.fetchall(), [])

    def test_02_real_registration_login_and_account_isolation(self):
        password = os.environ["PGPASSWORD"]
        for owner in ("synthetic-a", "synthetic-b"):
            response = self.client.post("/v1/auth/register", json={"username": owner,
                "password": password, "registration_code": REGISTRATION_CODE})
            self.assertEqual(response.status_code, 201, response.json)
        self.assertEqual(self.client.post("/v1/auth/login", json={"username": "synthetic-a",
                         "password": "wrong"}).status_code, 401)
        login = self.client.post("/v1/auth/login", json={"username": "synthetic-a", "password": password})
        self.assertEqual(login.status_code, 200)
        headers = {"Authorization": "Bearer " + login.json["access_token"]}
        mine, other = self.create(), self.create(owner="synthetic-b")
        self.assertEqual([t["task_id"] for t in self.client.get("/v1/tasks", headers=headers).json["tasks"]], [mine["task_id"]])
        self.assertEqual(self.client.get("/v1/tasks").status_code, 401)
        self.assertEqual(self.client.post(f'/v1/tasks/{other["task_id"]}/confirm', headers=headers, json=OPTIONS).status_code, 404)

    def test_03_legacy_payload_format_and_unknown_fields_survive(self):
        task = self.create()
        task["legacy_extension"] = {"note": "保留旧扩展", "unknown": [1, 2]}
        with closing(psycopg2.connect(os.environ["DATABASE_URL"])) as conn, conn, conn.cursor() as cursor:
            cursor.execute("UPDATE operation_tasks SET payload=%s WHERE task_id=%s",
                           (json.dumps(task, ensure_ascii=True, indent=2, sort_keys=True), task["task_id"]))
        changed = store.update_task(task["task_id"], {"title": "已核对"}, owner="synthetic-a")
        self.assertEqual(changed["legacy_extension"], task["legacy_extension"])
        self.assertEqual(store.get_task(task["task_id"])["title"], "已核对")

    def test_04_real_http_start_window_and_no_overwrite(self):
        task = self.create()
        base = f'/v1/tasks/{task["task_id"]}'
        headers = self.headers()
        self.assertEqual(self.client.post(base + "/confirm", headers=headers, json=OPTIONS).status_code, 200)
        self.assertEqual(self.client.post(base + "/observed-result", headers=headers, json=VALUES).status_code, 400)
        with patch.object(store, "_now", return_value=START):
            started = self.client.post(base + "/start", headers=headers).json["task"]
        with patch.object(store, "_now", return_value="2026-01-14T23:59:59+00:00"):
            self.assertEqual(self.client.post(base + "/observed-result", headers=headers, json=VALUES).status_code, 400)
            self.assertEqual(self.client.post(base + "/start", headers=headers).json["task"]["execution"], started["execution"])
        self.assertEqual(self.client.post(base + "/confirm", headers=headers, json=OPTIONS).status_code, 400)
        self.assertEqual(self.client.post(base + "/observed-result", headers=self.headers("synthetic-b"), json=VALUES).status_code, 404)
        with patch.object(store, "_now", return_value=END):
            response = self.client.post(base + "/observed-result", headers=headers, json=VALUES)
            self.assertEqual(response.status_code, 200, response.json)
            self.assertEqual(response.json["task"]["result"]["observation_ends_at"], END)
            self.assertEqual(self.client.post(base + "/observed-result", headers=headers, json=VALUES).status_code, 400)

    def test_05_two_real_writers_only_one_can_win(self):
        task = self.create()
        previous = json.dumps(task, ensure_ascii=False)
        barrier = Barrier(2)
        def write(title):
            snapshot = deepcopy(task)
            snapshot["title"] = title
            barrier.wait(timeout=10)
            try:
                store._db_save_task(snapshot, previous)
                return "saved"
            except ValueError:
                return "conflict"
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(write, ["writer-a", "writer-b"]))
        self.assertCountEqual(results, ["saved", "conflict"])
        self.assertIn(store.get_task(task["task_id"])["title"], ["writer-a", "writer-b"])
        with self.assertRaises(ValueError):
            store._db_save_task(task, previous)

    def test_06_diagnostic_feedback_and_invalid_legacy_start(self):
        task = self.create("shopify_aggregate")
        base = f'/v1/tasks/{task["task_id"]}/diagnostic-review'
        self.assertEqual(self.client.post(base, headers=self.headers("synthetic-b"), json={"decision": "accepted"}).status_code, 404)
        for decision in ("accepted", "needs_information", "rejected"):
            response = self.client.post(base, headers=self.headers(), json={"decision": decision})
            self.assertEqual(response.status_code, 200)
        saved = store.get_task(task["task_id"])
        self.assertEqual(len(saved["diagnostic_reviews"]), 3)
        self.assertEqual(saved["source_diagnosis"], task["source_diagnosis"])
        self.assertNotIn("execution", saved)
        legacy = self.create()
        legacy.update(status="confirmed", attribution_window_days=14,
                      execution={"mode": "manual_handoff", "status": "in_progress"})
        store._db_save_task(legacy)
        with self.assertRaisesRegex(ValueError, "启动"):
            store.record_observed_result(legacy["task_id"], owner="synthetic-a", **VALUES)

    def test_07_full_schema_migration_content_verification(self):
        migration._initialize_target(os.environ["DATABASE_URL"])
        task = self.create()
        self.seed_related_records()
        target = self.new_database()
        with patch.dict(os.environ, {"MIGRATION_TARGET_DATABASE_URL": target}):
            copied = migration.migrate()
            self.assertEqual(set(copied), set(migration.TABLES))
            self.assertEqual(copied["operation_tasks"], 1)
            for table in ("app_users", "auth_sessions", "chat_conversations", "chat_messages", "pilot_applications"):
                self.assertGreater(copied[table], 0)
            self.assertEqual(migration.migrate(verify_only=True), copied)
            with self.assertRaisesRegex(RuntimeError, "不是空表"):
                migration.migrate()
            with closing(psycopg2.connect(target)) as conn, conn, conn.cursor() as cursor:
                cursor.execute("UPDATE operation_tasks SET status='rejected' WHERE task_id=%s", (task["task_id"],))
            with self.assertRaisesRegex(RuntimeError, "内容验证失败"):
                migration.migrate(verify_only=True)

    def test_08_dump_restore_and_verified_readback(self):
        task = self.create()
        headers_a, headers_b, conversation = self.seed_related_records()
        target = self.new_database()
        dump = CLUSTER_DIR / ("backup-" + uuid.uuid4().hex + ".dump")
        subprocess.run([str(BIN / "pg_dump.exe"), "-h", "127.0.0.1", "-p", str(PORT),
                        "-U", "revops_test", "-Fc", "-f", str(dump), self.databases[0]], check=True, timeout=30)
        subprocess.run([str(BIN / "pg_restore.exe"), "-h", "127.0.0.1", "-p", str(PORT),
                        "-U", "revops_test", "--exit-on-error", "-d", self.databases[1], str(dump)], check=True, timeout=30)
        with patch.dict(os.environ, {"MIGRATION_TARGET_DATABASE_URL": target}):
            self.assertEqual(migration.migrate(verify_only=True)["operation_tasks"], 1)
        with patch.dict(os.environ, {"DATABASE_URL": target}):
            self.assertEqual(store.get_task(task["task_id"]), task)
            self.assertEqual(self.client.get("/v1/auth/me", headers=headers_a).status_code, 200)
            self.assertEqual(self.client.get("/v1/tasks", headers=headers_b).json["tasks"], [])
            self.assertEqual(len(account_store.load_messages(conversation, "synthetic-a")), 1)
            self.assertEqual(account_store.load_messages(conversation, "synthetic-b"), [])
            self.assertEqual(len(pilot_application_store.list_pilot_applications()), 1)
            self.assertEqual(self.client.post("/v1/auth/login", json={"username": "synthetic-a",
                             "password": os.environ["PGPASSWORD"]}).status_code, 200)

    def test_09_verification_failure_rolls_back_real_transaction(self):
        migration._initialize_target(os.environ["DATABASE_URL"])
        self.create()
        self.seed_related_records()
        target = self.new_database()
        with patch.dict(os.environ, {"MIGRATION_TARGET_DATABASE_URL": target}), \
             patch.object(migration, "_verify_rows", side_effect=RuntimeError("synthetic verification failure")):
            with self.assertRaisesRegex(RuntimeError, "verification failure"):
                migration.migrate()
        with closing(psycopg2.connect(target)) as conn, conn.cursor() as cursor:
            for table in migration.TABLES:
                cursor.execute(sql.SQL("SELECT COUNT(*) FROM {}").format(sql.Identifier(table)))
                self.assertEqual(cursor.fetchone()[0], 0, table)

    def test_10_missing_database_is_unavailable_without_credentials(self):
        missing = ADMIN_URL.rsplit("/", 1)[0] + "/revops_missing_" + uuid.uuid4().hex
        with patch.dict(os.environ, {"DATABASE_URL": missing}):
            response = self.client.get("/readyz")
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.json, {"status": "unavailable", "database": "unavailable"})
            self.assertNotIn(os.environ["PGPASSWORD"], response.get_data(as_text=True))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bin-dir", required=True)
    args = parser.parse_args()
    BIN = native_path(Path(args.bin_dir).resolve())
    for binary in ("initdb.exe", "pg_ctl.exe", "pg_dump.exe", "pg_restore.exe"):
        if not (BIN / binary).is_file():
            parser.error(f"Missing PostgreSQL binary: {binary}")
    runtime = ROOT / ".venv" / "pg-acceptance"
    runtime.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="run-", dir=runtime) as directory:
        CLUSTER_DIR = native_path(Path(directory))
        with socket.socket() as port_probe:
            port_probe.bind(("127.0.0.1", 0))
            PORT = port_probe.getsockname()[1]
        password = secrets.token_urlsafe(32)
        SESSION_KEY, REGISTRATION_CODE = secrets.token_urlsafe(48), secrets.token_urlsafe(32)
        # Runtime-generated credentials live only in a git-ignored local env file.
        env_file = CLUSTER_DIR / ".env.pg-acceptance"
        env_file.write_text(f"PGPASSWORD={password}\nSESSION_SIGNING_KEY={SESSION_KEY}\nREGISTRATION_CODE={REGISTRATION_CODE}\n", encoding="utf-8")
        pw_file = CLUSTER_DIR / ".env.pg-password"
        pw_file.write_text(password + "\n", encoding="utf-8")
        ADMIN_URL = f"postgresql://revops_test@127.0.0.1:{PORT}/postgres"
        data = CLUSTER_DIR / "data"
        started = False
        with patch.dict(os.environ, {"PGPASSWORD": password}):
            try:
                subprocess.run([str(BIN / "initdb.exe"), "-D", str(data), "-U", "revops_test",
                                "-A", "scram-sha-256", "--pwfile", str(pw_file), "--encoding=UTF8", "--locale=C"], check=True, timeout=60)
                subprocess.run([str(BIN / "pg_ctl.exe"), "-D", str(data), "-l", str(CLUSTER_DIR / "server.log"),
                                "-o", f"-h 127.0.0.1 -p {PORT}", "-w", "-t", "30", "start"], check=True, timeout=40)
                started = True
                with closing(psycopg2.connect(ADMIN_URL)) as conn, conn.cursor() as cursor:
                    cursor.execute("SHOW server_version")
                    print("Real PostgreSQL:", cursor.fetchone()[0], flush=True)
                outcome = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(PostgreSQLAcceptance))
            finally:
                if started:
                    subprocess.run([str(BIN / "pg_ctl.exe"), "-D", str(data), "-m", "fast", "-w", "-t", "30", "stop"], check=True, timeout=40)
        sys.exit(0 if outcome.wasSuccessful() else 1)

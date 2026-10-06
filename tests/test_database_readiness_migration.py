"""Readiness and migration logic against synthetic SQLite-backed driver doubles."""
import os
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from api.app import create_app
from scripts import migrate_postgres as migration
from src.agent.task_store import _database_url, check_database_connection


class Cursor:
    def __init__(self, database):
        self.database = database
        self.cursor = database.connection.cursor()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.cursor.close()

    def execute(self, query, parameters=()):
        self.database.queries.append(query)
        if query == "SELECT to_regclass(%s)":
            return self.cursor.execute("SELECT name FROM sqlite_master WHERE name = ?", (parameters[0].split(".")[1],))
        return self.cursor.execute(query.replace("%s", "?"), parameters)

    def executemany(self, query, rows):
        self.database.queries.append(query)
        return self.cursor.executemany(query.replace("%s", "?"), rows)

    def fetchone(self):
        return self.cursor.fetchone() or (None,)

    def fetchall(self):
        return self.cursor.fetchall()

    @property
    def description(self):
        return [SimpleNamespace(name=value[0]) for value in self.cursor.description]


class Database:
    def __init__(self, tables):
        self.connection = sqlite3.connect(":memory:")
        self.queries = []
        self.readonly = None
        for table, rows in tables.items():
            self.connection.execute(f'CREATE TABLE "{table}" (id TEXT PRIMARY KEY, value TEXT)')
            self.connection.executemany(f'INSERT INTO "{table}" VALUES (?, ?)', rows)
        self.connection.commit()

    def __enter__(self):
        return self

    def __exit__(self, error_type, *args):
        if error_type:
            self.connection.rollback()
        else:
            self.connection.commit()

    def cursor(self):
        return Cursor(self)

    def set_session(self, *, readonly, isolation_level):
        self.readonly = readonly


class DatabaseTests(unittest.TestCase):
    def test_readiness_is_read_only_and_missing_database_is_not_created(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"USE_MANAGED_POSTGRES": "0"}):
            database = Path(directory) / "test.db"
            with patch.dict(os.environ, {"DATABASE_URL": "sqlite:///" + str(database)}):
                client = create_app().test_client()
                self.assertEqual(client.get("/health").status_code, 200)
                self.assertEqual(client.get("/readyz").status_code, 503)
                self.assertFalse(database.exists())
                sqlite3.connect(database).close()
                response = client.get("/readyz")
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json["database"], "ok")
                self.assertEqual(response.headers["Cache-Control"], "no-store")
                with closing(sqlite3.connect(database)) as conn:
                    self.assertEqual(conn.execute("SELECT name FROM sqlite_master").fetchall(), [])

    def test_postgres_failure_is_bounded_and_does_not_expose_credentials(self):
        with patch.dict(os.environ, {"USE_MANAGED_POSTGRES": "0", "DATABASE_URL": "postgresql://secret.invalid"}), patch("psycopg2.connect", side_effect=RuntimeError("secret.invalid password")) as connect:
            response = create_app().test_client().get("/readyz")
            self.assertEqual(response.status_code, 503)
            self.assertNotIn("secret", response.get_data(as_text=True))
            self.assertEqual(connect.call_args.kwargs["connect_timeout"], 5)
            self.assertIn("statement_timeout=5000", connect.call_args.kwargs["options"])

    def test_target_initialization_overrides_managed_routing_and_restores_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            target = "sqlite:///" + str(Path(directory) / "target.db")
            with patch.dict(os.environ, {"DATABASE_URL": "postgresql://source.invalid", "USE_MANAGED_POSTGRES": "1", "MIGRATION_TARGET_DATABASE_URL": "postgresql://wrong.invalid"}):
                migration._initialize_target(target)
                self.assertEqual(_database_url(), "postgresql://wrong.invalid")
                self.assertEqual(os.environ["DATABASE_URL"], "postgresql://source.invalid")
            with closing(sqlite3.connect(Path(directory) / "target.db")) as conn:
                tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
                self.assertTrue(set(migration.TABLES) <= tables)
                self.assertIn("pilot_applications", tables)
                self.assertIn("chat_usage", tables)

    def run_migration(self, source, target, *, verify_only=False):
        with patch.dict(os.environ, {"DATABASE_URL": "postgresql://source.invalid", "MIGRATION_TARGET_DATABASE_URL": "postgresql://target.invalid"}), patch.object(migration, "TABLES", ("operation_tasks", "pilot_applications")), patch.object(migration, "_initialize_target") as initialize, patch.object(migration.psycopg2, "connect", side_effect=[source, target]):
            result = migration.migrate(verify_only=verify_only)
            if verify_only:
                initialize.assert_not_called()
            return result

    def test_copy_and_verify_only_compare_content_not_just_count(self):
        source = Database({"operation_tasks": [("a", "synthetic")], "pilot_applications": [("b", "application")]})
        target = Database({"operation_tasks": [], "pilot_applications": []})
        try:
            self.assertEqual(self.run_migration(source, target), {"operation_tasks": 1, "pilot_applications": 1})
            self.assertTrue(source.readonly)
            target.queries.clear()
            self.run_migration(source, target, verify_only=True)
            self.assertTrue(target.readonly)
            self.assertTrue(all(query.startswith("SELECT") for query in target.queries))
            target.connection.execute("UPDATE operation_tasks SET value = 'different'")
            target.connection.commit()
            with self.assertRaisesRegex(RuntimeError, "内容验证失败"):
                self.run_migration(source, target, verify_only=True)
        finally:
            source.connection.close()
            target.connection.close()

    def test_missing_or_nonempty_target_is_rejected_before_any_insert(self):
        for target_tables in ({"operation_tasks": []}, {"operation_tasks": [], "pilot_applications": [("existing", "keep")]}):
            source = Database({"operation_tasks": [("a", "synthetic")], "pilot_applications": []})
            target = Database(target_tables)
            try:
                with self.assertRaises(RuntimeError):
                    self.run_migration(source, target)
                self.assertFalse(any(query.startswith("INSERT") for query in target.queries))
            finally:
                source.connection.close()
                target.connection.close()

    def test_verification_failure_rolls_back_all_copied_tables(self):
        source = Database({"operation_tasks": [("a", "synthetic")], "pilot_applications": [("b", "application")]})
        target = Database({"operation_tasks": [], "pilot_applications": []})
        try:
            with patch.object(migration, "_verify_rows", side_effect=RuntimeError("verification failed")), self.assertRaises(RuntimeError):
                self.run_migration(source, target)
            self.assertEqual(target.connection.execute("SELECT * FROM operation_tasks").fetchall(), [])
        finally:
            source.connection.close()
            target.connection.close()


if __name__ == "__main__":
    unittest.main()

import tempfile
import os
import json
import sqlite3
from copy import deepcopy
from contextlib import closing
import unittest
from pathlib import Path
from unittest.mock import patch

from api.app import create_app
from src.agent.task_store import (
    create_task, get_task, mark_manual_execution_started, prepare_manual_execution,
    record_observed_result, update_task,
)

START = "2026-01-01T00:00:00+00:00"
END = "2026-01-15T00:00:00+00:00"
VALUES = dict(treatment_users=100, treatment_orders=20, treatment_revenue=2000,
              control_users=100, control_orders=10, control_revenue=1000,
              cost=200, currency="USD", revenue_net_of_refunds=True)


class ExecutionWindowTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "tasks.json"
        self.task = create_task({}, source_diagnosis={"source": "consented_reactivation_aggregate"},
                                owner="synthetic-a", path=self.path)
        self.id = self.task["task_id"]
        self.options = dict(channel="email", budget=200, market="US", locale="en-US",
                            attribution_window_days=14, owner="synthetic-a", path=self.path)
        prepare_manual_execution(self.id, **self.options)

    def start(self):
        with patch("src.agent.task_store._now", return_value=START):
            return mark_manual_execution_started(self.id, owner="synthetic-a", path=self.path)

    def result(self, now=END, owner="synthetic-a"):
        with patch("src.agent.task_store._now", return_value=now):
            return record_observed_result(self.id, **VALUES, owner=owner, path=self.path)

    def test_approved_but_not_started_cannot_complete(self):
        with self.assertRaisesRegex(ValueError, "启动"):
            self.result()
        self.assertEqual(get_task(self.id, path=self.path)["status"], "confirmed")

    def test_window_boundary_is_enforced_and_recorded(self):
        self.start()
        with self.assertRaisesRegex(ValueError, "观察"):
            self.result("2026-01-14T23:59:59+00:00")
        completed = self.result()
        self.assertEqual(completed["status"], "completed")
        self.assertEqual(completed["result"]["observation_started_at"], START)
        self.assertEqual(completed["result"]["observation_ends_at"], END)
        self.assertEqual(completed["result"]["verification"], "self_reported")
        with self.assertRaises(ValueError):
            self.result()

    def test_duplicate_start_keeps_original_window(self):
        first = self.start()
        with patch("src.agent.task_store._now", return_value="2026-01-05T00:00:00+00:00"):
            second = mark_manual_execution_started(self.id, owner="synthetic-a", path=self.path)
        self.assertEqual(second["execution"], first["execution"])
        self.assertEqual(second["updated_at"], first["updated_at"])

    def test_running_parameters_cannot_be_reconfirmed_or_shortened(self):
        self.start()
        with self.assertRaises(ValueError):
            prepare_manual_execution(self.id, **{**self.options, "attribution_window_days": 1})
        with self.assertRaises(ValueError):
            update_task(self.id, {"attribution_window_days": 1}, path=self.path, owner="synthetic-a")
        self.assertEqual(get_task(self.id, path=self.path)["attribution_window_days"], 14)

    def test_other_account_cannot_start_or_return_results(self):
        self.assertIsNone(mark_manual_execution_started(self.id, path=self.path, owner="synthetic-b"))
        self.start()
        self.assertIsNone(self.result(owner="synthetic-b"))

    def test_missing_or_malformed_legacy_start_fails_closed(self):
        from src.agent.task_store import load_tasks, save_tasks
        for value in (None, "bad-date", "2026-01-01T00:00:00"):
            tasks = load_tasks(self.path)
            tasks[0]["execution"].update(status="in_progress", started_at=value)
            save_tasks(tasks, self.path)
            with self.assertRaises(ValueError):
                self.result()

    def test_approval_requires_finite_budget_and_integer_window(self):
        for field, value in (("budget", float("nan")), ("budget", float("inf")),
                             ("budget", True), ("attribution_window_days", 1.5),
                             ("attribution_window_days", True)):
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                prepare_manual_execution(self.id, **{**self.options, field: value})

    def test_http_blocks_unstarted_or_early_submission(self):
        client = create_app().test_client()
        snapshot = get_task(self.id, path=self.path)
        with patch("api.app._require_session", return_value={"username": "synthetic-a"}), \
             patch("src.agent.task_store.load_tasks", return_value=[snapshot]):
            # HTTP reaches the real state validator; failed cases never save.
            response = client.post(f"/v1/tasks/{self.id}/observed-result", json=VALUES)
            self.assertEqual(response.status_code, 400)
        snapshot = self.start()
        with patch("api.app._require_session", return_value={"username": "synthetic-a"}), \
             patch("src.agent.task_store.load_tasks", return_value=[snapshot]), \
             patch("src.agent.task_store._now", return_value=START):
            self.assertEqual(client.post(f"/v1/tasks/{self.id}/observed-result", json=VALUES).status_code, 400)

    def test_stale_database_writer_cannot_reset_start(self):
        url = "sqlite:///" + str(Path(self.directory.name) / "tasks.db")
        with patch.dict(os.environ, {"DATABASE_URL": url, "USE_MANAGED_POSTGRES": "0"}):
            task = create_task({}, source_diagnosis={"source": "consented_reactivation_aggregate"}, owner="synthetic-a")
            options = {key:value for key,value in self.options.items() if key != "path"}
            prepare_manual_execution(task["task_id"], **options)
            old = deepcopy(get_task(task["task_id"]))
            with patch("src.agent.task_store._now", return_value=START):
                mark_manual_execution_started(task["task_id"], owner="synthetic-a")
            with patch("src.agent.task_store.load_tasks", return_value=[old]), \
                 patch("src.agent.task_store._now", return_value="2026-01-05T00:00:00+00:00"):
                with self.assertRaisesRegex(ValueError, "更新"):
                    mark_manual_execution_started(task["task_id"], owner="synthetic-a")
            self.assertEqual(get_task(task["task_id"])["execution"]["started_at"], START)

    def test_generic_completion_cannot_bypass_observed_gate(self):
        from src.agent.task_store import complete_task
        with self.assertRaises(ValueError):
            complete_task(self.id, {"roi": 4}, path=self.path, owner="synthetic-a")

    def test_legacy_json_format_is_not_a_false_conflict(self):
        database = Path(self.directory.name) / "legacy.db"
        with patch.dict(os.environ, {"DATABASE_URL": "sqlite:///" + str(database), "USE_MANAGED_POSTGRES": "0"}):
            task = create_task({"title": "旧任务"}, owner="synthetic-a")
            task["legacy_extension"] = {"keep": [1, 2]}
            with closing(sqlite3.connect(database)) as connection, connection:
                connection.execute("UPDATE operation_tasks SET payload=? WHERE task_id=?",
                    (json.dumps(task, ensure_ascii=True, sort_keys=True, indent=2), task["task_id"]))
            changed = update_task(task["task_id"], {"title": "已核对"}, owner="synthetic-a")
            self.assertEqual(changed["legacy_extension"], task["legacy_extension"])
            self.assertEqual(get_task(task["task_id"])["title"], "已核对")


if __name__ == "__main__":
    unittest.main()

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from api.app import create_app
from src.agent.task_store import create_task, get_task, record_diagnostic_review, prepare_manual_execution


class DiagnosticReviewTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "tasks.json"
        self.source = {"source":"shopify_aggregate", "evidence":{"previous":700,"recent":420}}
        self.task = create_task({"title":"Synthetic store signal"}, source_diagnosis=self.source, owner="synthetic-a", path=self.path)
        self.id = self.task["task_id"]

    def test_feedback_preserves_evidence_and_history_without_marketing(self):
        for decision, status, action in [("accepted","confirmed","verify_business_cause"),
                                         ("needs_information","draft","clarify_definition"),
                                         ("rejected","rejected","stop_diagnosis")]:
            task = record_diagnostic_review(self.id, decision, owner="synthetic-a", path=self.path)
            self.assertEqual(task["status"], status)
            self.assertEqual(task["diagnostic_review"]["next_action"], action)
            self.assertEqual(task["source_diagnosis"], self.source)
            self.assertNotIn("execution",task)
            self.assertNotIn("result",task)
        self.assertEqual(len(task["diagnostic_reviews"]),3)
        with self.assertRaises(ValueError):
            prepare_manual_execution(self.id, channel="email", budget=0, market="US", locale="en", attribution_window_days=7, owner="synthetic-a", path=self.path)

    def test_foreign_account_and_unknown_decision_never_mutate(self):
        self.assertIsNone(record_diagnostic_review(self.id,"accepted",owner="synthetic-b",path=self.path))
        with self.assertRaises(ValueError):
            record_diagnostic_review(self.id,"launch",owner="synthetic-a",path=self.path)
        self.assertNotIn("diagnostic_review",get_task(self.id,path=self.path))

    def test_reactivation_task_cannot_use_diagnostic_feedback(self):
        task = create_task({}, source_diagnosis={"source":"consented_reactivation_aggregate"}, owner="synthetic-a",path=self.path)
        with self.assertRaises(ValueError):
            record_diagnostic_review(task["task_id"],"accepted",owner="synthetic-a",path=self.path)

    def test_http_requires_session_owner_and_structured_decision_only(self):
        client = create_app().test_client()
        url = f"/v1/tasks/{self.id}/diagnostic-review"
        with patch("api.app._require_session",side_effect=ValueError("expired")):
            self.assertEqual(client.post(url,json={"decision":"accepted"}).status_code,401)
        with patch("src.agent.task_store._use_database",return_value=False), \
             patch("src.agent.task_store.TASKS_PATH",self.path), \
             patch("api.app._require_session",return_value={"username":"synthetic-a"}):
            self.assertEqual(client.post(url,json={"decision":"accepted","customer_email":"synthetic@example.invalid"}).status_code,400)
            self.assertEqual(client.post(url,json={"decision":[]}).status_code,400)
            self.assertEqual(client.post(url,json={"decision":"accepted"}).status_code,200)
        with patch("src.agent.task_store._use_database",return_value=False), \
             patch("src.agent.task_store.TASKS_PATH",self.path), \
             patch("api.app._require_session",return_value={"username":"synthetic-b"}):
            self.assertEqual(client.post(url,json={"decision":"accepted"}).status_code,404)


if __name__ == "__main__":
    unittest.main()

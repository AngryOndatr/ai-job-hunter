import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from gmail_collector import GmailJobCollector


class GmailJobCollectorTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.processed_path = Path(self.temp_dir.name) / "processed_ids.json"
        self.collector = GmailJobCollector.__new__(GmailJobCollector)
        self.collector.target_labels = ["LinkedIn"]
        self.collector.max_age_days = 2
        self.collector.processed_ids_file = str(self.processed_path)
        self.collector.processed_ids = set()
        self.collector.service = Mock()
        users = self.collector.service.users.return_value
        users.labels.return_value.list.return_value.execute.return_value = {
            "labels": [{"name": "LinkedIn", "id": "label-1"}]
        }
        users.messages.return_value.list.return_value.execute.return_value = {
            "messages": [{"id": "message-1"}]
        }
        users.messages.return_value.get.return_value.execute.return_value = {
            "id": "message-1",
            "threadId": "thread-1",
            "payload": {
                "headers": [
                    {"name": "Subject", "value": "Java Engineer"},
                    {"name": "From", "value": "alerts@example.com"},
                ],
                "body": {},
            },
        }

    def test_deferred_fetch_does_not_mark_message_until_acknowledged(self):
        jobs = self.collector.fetch_new_job_emails(defer_processed=True)

        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["id"], "message-1")
        self.assertNotIn("message-1", self.collector.processed_ids)
        self.assertFalse(self.processed_path.exists())

        self.collector.mark_processed("message-1")

        self.assertEqual(json.loads(self.processed_path.read_text(encoding="utf-8")), ["message-1"])

    def test_default_fetch_preserves_immediate_deduplication_behavior(self):
        jobs = self.collector.fetch_new_job_emails()

        self.assertEqual(len(jobs), 1)
        self.assertIn("message-1", self.collector.processed_ids)
        self.assertEqual(json.loads(self.processed_path.read_text(encoding="utf-8")), ["message-1"])

    def test_reprocess_ids_override_local_processed_cache(self):
        self.collector.processed_ids = {"message-1"}

        jobs = self.collector.fetch_new_job_emails(
            defer_processed=True, reprocess_ids={"message-1"}
        )

        self.assertEqual([job["id"] for job in jobs], ["message-1"])
        self.assertIn("message-1", self.collector.processed_ids)

    def test_processed_id_file_is_written_in_stable_sorted_order(self):
        self.collector.processed_ids = {"message-z", "message-a"}

        self.collector._save_processed_ids()

        self.assertEqual(
            json.loads(self.processed_path.read_text(encoding="utf-8")),
            ["message-a", "message-z"],
        )


if __name__ == "__main__":
    unittest.main()

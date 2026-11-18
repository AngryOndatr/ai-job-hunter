import base64
import json
import re
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

    def test_digest_split_into_per_job_records(self):
        """A LinkedIn digest email splits into one record per job listing."""
        body = "\n".join([
            "Your job alert for Инженер-программист Java in Berlin",
            "Full-Stack Engineer (f/m/d)",
            "Zenjob",
            "Berlin, Germany",
            "",
            "This company is actively hiring",
            "View job: https://www.linkedin.com/comm/jobs/view/4489714169/?trackingId=abc",
            "",
            "---------------------------------------------------------",
            "  ",
            "            ",
            "Lead Developer Java / AI Insurance (all genders)",
            "adesso SE",
            "Berlin",
            "",
            "This company is actively hiring",
            "View job: https://www.linkedin.com/comm/jobs/view/4464891334/?trackingId=def",
            "",
            "---------------------------------------------------------",
            "  ",
            "            ",
            "Softwareentwickler Entwicklungsprojekte, all genders",
            "SALT AND PEPPER Group",
            "Berlin",
            "",
            "This company is actively hiring",
            "View job: https://www.linkedin.com/comm/jobs/view/4482674373/?trackingId=ghi",
            "",
            "See all jobs on LinkedIn:  https://www.linkedin.com/comm/jobs/search-results/?keywords=Java",
        ])
        parsed = {
            "id": "message-1",
            "threadId": "thread-1",
            "source": "LinkedIn",
            "subject": "You may be a fit for Zenjob's role",
            "sender": "jobalerts-noreply@linkedin.com",
            "date": "Mon, 16 Nov 2026 11:06:01 +0000",
            "body": body,
        }

        jobs = GmailJobCollector._split_digest(parsed)

        self.assertEqual(len(jobs), 3)
        self.assertEqual(jobs[0]["job_title"], "Full-Stack Engineer (f/m/d)")
        self.assertEqual(jobs[0]["company"], "Zenjob")
        self.assertEqual(jobs[0]["location"], "Berlin, Germany")
        self.assertEqual(jobs[0]["job_id"], "4489714169")
        self.assertEqual(jobs[0]["id"], "message-1:4489714169")
        self.assertEqual(jobs[1]["company"], "adesso SE")
        self.assertEqual(jobs[2]["company"], "SALT AND PEPPER Group")
        for job in jobs:
            self.assertIn(job["company"], job["body"])

    def test_non_digest_email_is_not_split(self):
        """A single-job email has one View job link and stays one record."""
        body = "Full-Stack Engineer (f/m/d)\nZenjob\nBerlin\nView job: https://www.linkedin.com/comm/jobs/view/4489714169/"
        parsed = {"id": "message-1", "body": body}

        self.assertEqual(GmailJobCollector._split_digest(parsed), [])

    def test_fetch_returns_split_records_for_digest(self):
        """fetch_new_job_emails returns per-job records for a digest message."""
        body = "\n".join([
            "Full-Stack Engineer (f/m/d)",
            "Zenjob",
            "Berlin, Germany",
            "This company is actively hiring",
            "View job: https://www.linkedin.com/comm/jobs/view/4489714169/?x=1",
            "---------------------------------------------------------",
            "Lead Developer Java / AI Insurance (all genders)",
            "adesso SE",
            "Berlin",
            "This company is actively hiring",
            "View job: https://www.linkedin.com/comm/jobs/view/4464891334/?x=2",
        ])
        users = self.collector.service.users.return_value
        users.messages.return_value.list.return_value.execute.return_value = {
            "messages": [{"id": "message-digest"}]
        }
        users.messages.return_value.get.return_value.execute.return_value = {
            "id": "message-digest",
            "threadId": "thread-digest",
            "payload": {
                "headers": [
                    {"name": "Subject", "value": "Digest"},
                    {"name": "From", "value": "jobalerts-noreply@linkedin.com"},
                ],
                "body": {"data": base64.urlsafe_b64encode(body.encode("utf-8")).decode("ascii")},
            },
        }

        jobs = self.collector.fetch_new_job_emails(defer_processed=True)

        self.assertEqual(len(jobs), 2)
        self.assertEqual(jobs[0]["company"], "Zenjob")
        self.assertEqual(jobs[1]["company"], "adesso SE")


if __name__ == "__main__":
    unittest.main()

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

import yaml

from main import run_pipeline


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.config_path = Path(self.temp_dir.name) / "config.yaml"
        self.config_path.write_text(
            yaml.safe_dump({"limits": {"max_jobs_per_run": 5}}), encoding="utf-8"
        )
        self.job = {
            "id": "gmail-message-1",
            "subject": "Senior Java Engineer",
            "body": "Java and Spring Boot experience required.",
            "application_email": "jobs@example.com",
            "company": "Example GmbH",
        }
        self.collector = Mock()
        self.collector.fetch_new_job_emails.return_value = [self.job]
        self.analyzer = Mock()
        self.analyzer.analyze_job.return_value = {
            "match_score": 88,
            "eligible_for_draft": True,
            "matching_skills": ["Java"],
            "missing_keywords": [],
            "summary": "Strong match.",
        }
        self.analyzer.generate_tailored_sections.return_value = {
            "{{SUMMARY}}": "Java engineer with Spring experience."
        }
        self.analyzer.generate_cover_letter.return_value = "Dear Hiring Team, ..."
        self.drive = Mock()
        self.drive.load_master_profile.return_value = "Java engineer factual profile"
        self.drive.load_resume_template.return_value = {
            "text": "Output template {{SUMMARY}}",
            "placeholders": ["{{SUMMARY}}"],
        }
        self.drive.create_tailored_resume.return_value = {
            "pdf_bytes": b"%PDF-mock",
            "pdf": {"name": "Resume.pdf"},
        }
        self.draft_executor = Mock()
        self.draft_executor.create_draft.return_value = {
            "draft_id": "draft-1",
            "url": "https://mail.google.com/mail/u/0/#drafts/draft-1",
        }
        self.notifier = Mock()

    def run_with_components(self):
        return run_pipeline(
            config_path=str(self.config_path),
            collector=self.collector,
            analyzer=self.analyzer,
            drive_manager=self.drive,
            draft_executor=self.draft_executor,
            notifier=self.notifier,
        )

    def test_runs_eligible_job_through_draft_and_notification(self):
        report = self.run_with_components()

        self.assertEqual(report["fetched"], 1)
        self.assertEqual(report["attempted"], 1)
        self.assertEqual(report["drafts_created"], 1)
        self.assertEqual(report["notifications_sent"], 1)
        self.assertEqual(report["errors"], [])
        self.assertEqual(report["skipped"], [])
        self.collector.fetch_new_job_emails.assert_called_once_with(defer_processed=True)
        self.drive.load_master_profile.assert_called_once_with()
        self.drive.load_resume_template.assert_called_once_with()
        self.analyzer.analyze_job.assert_called_once_with(
            self.job, "Java engineer factual profile"
        )
        self.analyzer.generate_tailored_sections.assert_called_once_with(
            self.job,
            "Java engineer factual profile",
            self.analyzer.analyze_job.return_value,
            ["{{SUMMARY}}"],
        )
        self.drive.create_tailored_resume.assert_called_once_with(
            "Senior Java Engineer", self.analyzer.generate_tailored_sections.return_value
        )
        self.draft_executor.create_draft.assert_called_once_with(
            self.job,
            self.analyzer.generate_cover_letter.return_value,
            self.drive.create_tailored_resume.return_value,
        )
        self.collector.mark_processed.assert_called_once_with("gmail-message-1")
        self.notifier.send_notification.assert_called_once_with(
            self.job,
            self.analyzer.analyze_job.return_value,
            self.draft_executor.create_draft.return_value,
        )

    def test_dry_run_analyzes_and_tailors_without_external_writes_or_acknowledging(self):
        report = run_pipeline(
            config_path=str(self.config_path),
            collector=self.collector,
            analyzer=self.analyzer,
            drive_manager=self.drive,
            draft_executor=self.draft_executor,
            notifier=self.notifier,
            dry_run=True,
        )

        self.assertTrue(report["dry_run"])
        self.assertEqual(report["drafts_created"], 0)
        self.assertEqual(report["notifications_sent"], 0)
        self.assertEqual(
            report["would_create_drafts"],
            [{"job_id": "gmail-message-1", "title": "Senior Java Engineer", "recipient": "jobs@example.com"}],
        )
        self.analyzer.generate_tailored_sections.assert_called_once()
        self.analyzer.generate_cover_letter.assert_called_once()
        self.drive.create_tailored_resume.assert_not_called()
        self.draft_executor.create_draft.assert_not_called()
        self.notifier.send_notification.assert_not_called()
        self.collector.mark_processed.assert_not_called()

    def test_marks_below_threshold_and_missing_recipient_jobs_as_skipped(self):
        second_job = {**self.job, "id": "gmail-message-2", "application_email": ""}
        self.collector.fetch_new_job_emails.return_value = [self.job, second_job]
        self.analyzer.analyze_job.side_effect = [
            {"match_score": 40, "eligible_for_draft": False, "summary": "Low match."},
            {"match_score": 90, "eligible_for_draft": True, "summary": "Strong match."},
        ]

        report = self.run_with_components()

        self.assertEqual(report["drafts_created"], 0)
        self.assertEqual(
            [entry["reason"] for entry in report["skipped"]],
            ["below_match_threshold", "missing_application_recipient"],
        )
        self.assertEqual(
            self.collector.mark_processed.call_args_list,
            [unittest.mock.call("gmail-message-1"), unittest.mock.call("gmail-message-2")],
        )
        self.draft_executor.create_draft.assert_not_called()
        self.notifier.send_notification.assert_not_called()

    def test_continues_after_a_job_failure_and_retries_failed_job_next_run(self):
        second_job = {**self.job, "id": "gmail-message-2", "subject": "Backend Engineer"}
        self.collector.fetch_new_job_emails.return_value = [self.job, second_job]
        self.analyzer.generate_tailored_sections.side_effect = [
            RuntimeError("model unavailable"),
            {"{{SUMMARY}}": "Backend engineer."},
        ]

        report = self.run_with_components()

        self.assertEqual(report["drafts_created"], 1)
        self.assertEqual(report["notifications_sent"], 1)
        self.assertEqual(len(report["errors"]), 1)
        self.assertEqual(report["errors"][0]["job_id"], "gmail-message-1")
        self.assertEqual(report["errors"][0]["stage"], "resume_tailoring")
        self.collector.mark_processed.assert_called_once_with("gmail-message-2")

    def test_records_notification_failure_without_recreating_a_draft(self):
        self.notifier.send_notification.side_effect = RuntimeError("Telegram unavailable")

        report = self.run_with_components()

        self.assertEqual(report["drafts_created"], 1)
        self.assertEqual(report["notifications_sent"], 0)
        self.assertEqual(report["errors"][0]["stage"], "telegram_notification")
        self.assertEqual(
            report["errors"][0]["draft_url"],
            "https://mail.google.com/mail/u/0/#drafts/draft-1",
        )
        self.collector.mark_processed.assert_called_once_with("gmail-message-1")

    def test_respects_max_jobs_per_run_without_acknowledging_queued_jobs(self):
        self.config_path.write_text(
            yaml.safe_dump({"limits": {"max_jobs_per_run": 1}}), encoding="utf-8"
        )
        second_job = {**self.job, "id": "gmail-message-2"}
        self.collector.fetch_new_job_emails.return_value = [self.job, second_job]

        report = self.run_with_components()

        self.assertEqual(report["fetched"], 2)
        self.assertEqual(report["attempted"], 1)
        self.collector.mark_processed.assert_called_once_with("gmail-message-1")


if __name__ == "__main__":
    unittest.main()

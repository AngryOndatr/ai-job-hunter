import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import yaml

from main import _error_record, run_pipeline
from gmail_executor import GmailDraftExecutor


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.config_path = Path(self.temp_dir.name) / "config.yaml"
        self.config_path.write_text(
            yaml.safe_dump(
                {
                    "gmail": {
                        "target_labels": ["Jobs"],
                        "max_email_age_days": 2,
                        "processed_ids_file": "processed_ids.json",
                    },
                    "ai_policy": {
                        "provider": "google",
                        "model": "gemini-test-model",
                        "language": "en",
                        "min_match_score_to_draft": 75,
                    },
                    "google_docs": {
                        "master_profile_doc_id": "profile-id",
                        "resume_template_doc_id": "template-id",
                        "output_folder_id": "output-folder-id",
                    },
                    "paths": {
                        "credentials_file": "credentials.json",
                        "token_file": "token.json",
                    },
                    "limits": {"max_jobs_per_run": 5},
                }
            ),
            encoding="utf-8",
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
        self.draft_executor.idempotency_message_id.side_effect = (
            GmailDraftExecutor.idempotency_message_id
        )
        self.draft_executor.create_draft.return_value = {
            "draft_id": "draft-1",
            "url": "https://mail.google.com/mail/u/0/#drafts/draft-1",
        }
        self.notifier = Mock()
        self.state_store = Mock()
        self.state_store.get_terminal_ids.return_value = set()
        self.state_store.get_job_state.return_value = None

    def run_with_components(self):
        return run_pipeline(
            config_path=str(self.config_path),
            collector=self.collector,
            analyzer=self.analyzer,
            drive_manager=self.drive,
            draft_executor=self.draft_executor,
            notifier=self.notifier,
            state_store=self.state_store,
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
            "Senior Java Engineer", self.analyzer.generate_tailored_sections.return_value,
            idempotency_key="ai-job-hunter-" + hashlib.sha256(b"gmail-message-1").hexdigest(),
        )
        self.draft_executor.create_draft.assert_called_once_with(
            self.job,
            self.analyzer.generate_cover_letter.return_value,
            self.drive.create_tailored_resume.return_value,
            idempotency_message_id=GmailDraftExecutor.idempotency_message_id("gmail-message-1"),
        )
        self.collector.mark_processed.assert_called_once_with("gmail-message-1")
        self.notifier.send_notification.assert_called_once_with(
            self.job,
            self.analyzer.analyze_job.return_value,
            self.draft_executor.create_draft.return_value,
        )

    def test_dry_run_analyzes_and_tailors_without_external_writes_or_acknowledging(self):
        with (
            patch("main.GmailDraftExecutor") as draft_factory,
            patch("main.TelegramNotifier") as notifier_factory,
        ):
            report = run_pipeline(
                config_path=str(self.config_path),
                collector=self.collector,
                analyzer=self.analyzer,
                drive_manager=self.drive,
                state_store=self.state_store,
                dry_run=True,
            )

        self.assertTrue(report["dry_run"])
        self.assertEqual(report["drafts_created"], 0)
        self.assertEqual(report["notifications_sent"], 0)
        self.assertEqual(
            report["would_create_drafts"],
            [{"job_id": "gmail-message-1", "title": "Senior Java Engineer"}],
        )
        self.analyzer.generate_tailored_sections.assert_called_once()
        self.analyzer.generate_cover_letter.assert_called_once()
        self.drive.create_tailored_resume.assert_not_called()
        self.draft_executor.create_draft.assert_not_called()
        self.notifier.send_notification.assert_not_called()
        draft_factory.assert_not_called()
        notifier_factory.assert_not_called()
        self.collector.mark_processed.assert_not_called()
        self.state_store.mark_status.assert_not_called()

    def test_dry_run_does_not_mark_skipped_jobs_processed(self):
        second_job = {**self.job, "id": "gmail-message-2", "application_email": ""}
        self.collector.fetch_new_job_emails.return_value = [self.job, second_job]
        self.analyzer.analyze_job.side_effect = [
            {"match_score": 40, "eligible_for_draft": False, "summary": "Low match."},
            {"match_score": 90, "eligible_for_draft": True, "summary": "Strong match."},
        ]

        report = run_pipeline(
            config_path=str(self.config_path),
            collector=self.collector,
            analyzer=self.analyzer,
            drive_manager=self.drive,
            state_store=self.state_store,
            dry_run=True,
        )

        self.assertEqual(
            [entry["reason"] for entry in report["skipped"]],
            ["below_match_threshold", "missing_application_recipient"],
        )
        self.collector.mark_processed.assert_not_called()

    def test_dry_run_report_omits_application_recipient(self):
        report = run_pipeline(
            config_path=str(self.config_path),
            collector=self.collector,
            analyzer=self.analyzer,
            drive_manager=self.drive,
            state_store=self.state_store,
            dry_run=True,
        )

        self.assertEqual(
            report["would_create_drafts"],
            [{"job_id": "gmail-message-1", "title": "Senior Java Engineer"}],
        )

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

    def test_filters_jobs_already_terminal_in_durable_state(self):
        second_job = {**self.job, "id": "gmail-message-done"}
        self.collector.fetch_new_job_emails.return_value = [self.job, second_job]
        self.state_store.get_terminal_ids.return_value = {"gmail-message-done"}

        report = self.run_with_components()

        self.assertEqual(report["fetched"], 2)
        self.assertEqual(report["attempted"], 1)
        self.analyzer.analyze_job.assert_called_once_with(
            self.job, "Java engineer factual profile"
        )

    def test_recovers_draft_pending_message_without_creating_another_resume_or_draft(self):
        self.state_store.get_job_state.return_value = {
            "status": "draft_pending",
            "draft_message_id": "<stable@example.invalid>",
        }
        self.draft_executor.find_existing_draft.return_value = {
            "draft_id": "draft-recovered",
            "url": "https://mail.google.com/mail/u/0/#drafts/draft-recovered",
        }

        report = self.run_with_components()

        self.assertEqual(report["drafts_created"], 1)
        self.drive.create_tailored_resume.assert_not_called()
        self.draft_executor.create_draft.assert_not_called()
        self.draft_executor.find_existing_draft.assert_called_once()
        self.collector.mark_processed.assert_called_once_with("gmail-message-1")

    def test_missing_secrets_fail_before_gmail_collector_is_initialized(self):
        with patch.dict("os.environ", {}, clear=True):
            with patch("main.GmailJobCollector") as collector_factory:
                with self.assertRaisesRegex(ValueError, "GEMINI_API_KEY"):
                    run_pipeline(config_path=str(self.config_path))

        collector_factory.assert_not_called()

    def test_oauth_preflight_happens_before_gmail_collector_initialization(self):
        events = []
        collector_instance = Mock()
        collector_instance.fetch_new_job_emails.return_value = []

        def oauth_preflight(_config):
            events.append("oauth")

        def create_collector(**_kwargs):
            events.append("collector")
            return collector_instance

        with patch.dict(
            "os.environ",
            {
                "GEMINI_API_KEY": "gemini-test-secret",
                "TELEGRAM_BOT_TOKEN": "telegram-test-secret",
                "TELEGRAM_CHAT_ID": "12345",
            },
            clear=True,
        ):
            with patch("main.preflight_google_oauth", side_effect=oauth_preflight):
                with patch("main.GmailJobCollector", side_effect=create_collector):
                    run_pipeline(config_path=str(self.config_path))

        self.assertEqual(events, ["oauth", "collector"])

    def test_unexpected_job_error_details_are_redacted(self):
        secret = "private-token-and-job-content"
        error = _error_record("gmail-1", "Engineer", "analysis", RuntimeError(secret))

        self.assertNotIn(secret, error["error"])
        self.assertIn("Details redacted", error["error"])

    def test_respects_max_jobs_per_run_without_acknowledging_queued_jobs(self):
        self.config_path.write_text(
            yaml.safe_dump(
                {
                    "gmail": {"target_labels": ["Jobs"], "max_email_age_days": 2, "processed_ids_file": "processed_ids.json"},
                    "ai_policy": {"provider": "google", "model": "gemini-test-model", "language": "en", "min_match_score_to_draft": 75},
                    "google_docs": {"master_profile_doc_id": "profile-id", "resume_template_doc_id": "template-id", "output_folder_id": "output-folder-id"},
                    "paths": {"credentials_file": "credentials.json", "token_file": "token.json"},
                    "limits": {"max_jobs_per_run": 1},
                }
            ), encoding="utf-8"
        )
        second_job = {**self.job, "id": "gmail-message-2"}
        self.collector.fetch_new_job_emails.return_value = [self.job, second_job]

        report = self.run_with_components()

        self.assertEqual(report["fetched"], 2)
        self.assertEqual(report["attempted"], 1)
        self.collector.mark_processed.assert_called_once_with("gmail-message-1")


if __name__ == "__main__":
    unittest.main()

import base64
import tempfile
import unittest
from email import policy
from email.parser import BytesParser
from pathlib import Path
from unittest.mock import Mock

import yaml

from gmail_executor import GmailDraftError, GmailDraftExecutor


class GmailDraftExecutorTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.config_path = Path(self.temp_dir.name) / "config.yaml"
        self.config_path.write_text(
            yaml.safe_dump(
                {
                    "paths": {
                        "credentials_file": "credentials.json",
                        "token_file": "token.json",
                    }
                }
            ),
            encoding="utf-8",
        )
        self.service = Mock()
        self.service.users.return_value.drafts.return_value.create.return_value.execute.return_value = {
            "id": "draft-123",
            "message": {"id": "message-456", "threadId": "thread-789"},
        }
        self.executor = GmailDraftExecutor(config_path=str(self.config_path), service=self.service)
        self.job = {
            "job_title": "Senior Java Engineer",
            "company": "Example GmbH",
            "application_email": "Hiring Team <jobs@example.com>",
            "sender": "alerts@job-board.example",
        }
        self.cover_letter = "Dear Hiring Team,\nI am applying for the Java role."
        self.resume = {
            "pdf_bytes": b"%PDF-1.7\nmock resume content",
            "pdf": {"name": "Tailored Resume.pdf"},
        }

    def test_creates_gmail_draft_with_cover_letter_and_pdf_attachment(self):
        result = self.executor.create_draft(self.job, self.cover_letter, self.resume)

        self.assertEqual(result["draft_id"], "draft-123")
        self.assertEqual(result["message_id"], "message-456")
        self.assertEqual(result["thread_id"], "thread-789")
        self.assertEqual(result["recipient"], "Hiring Team <jobs@example.com>")
        self.assertEqual(result["subject"], "Application: Senior Java Engineer at Example GmbH")
        self.assertEqual(
            result["url"], "https://mail.google.com/mail/u/0/#drafts/draft-123"
        )

        request = self.service.users.return_value.drafts.return_value.create
        request.assert_called_once()
        self.assertEqual(request.call_args.kwargs["userId"], "me")
        raw = request.call_args.kwargs["body"]["message"]["raw"]
        message_bytes = base64.urlsafe_b64decode(raw.encode("ascii"))
        parsed = BytesParser(policy=policy.default).parsebytes(message_bytes)
        self.assertEqual(str(parsed["To"]), "Hiring Team <jobs@example.com>")
        self.assertEqual(
            str(parsed["Subject"]), "Application: Senior Java Engineer at Example GmbH"
        )
        parts = list(parsed.iter_parts())
        body_text = parts[0].get_content().replace("\r\n", "\n").rstrip("\n")
        self.assertEqual(body_text, self.cover_letter)
        self.assertEqual(parts[1].get_filename(), "Tailored Resume.pdf")
        self.assertEqual(parts[1].get_content_type(), "application/pdf")
        self.assertEqual(parts[1].get_payload(decode=True), self.resume["pdf_bytes"])

    def test_does_not_use_job_alert_sender_as_application_recipient(self):
        job_without_application_email = {"job_title": self.job["job_title"], "sender": self.job["sender"]}

        with self.assertRaisesRegex(ValueError, "application_email or recipient"):
            self.executor.create_draft(job_without_application_email, self.cover_letter, self.resume)

        self.service.users.return_value.drafts.return_value.create.assert_not_called()

    def test_rejects_invalid_pdf_before_calling_gmail(self):
        invalid_resume = {"pdf_bytes": b"not a pdf"}

        with self.assertRaisesRegex(ValueError, "valid PDF bytes"):
            self.executor.create_draft(self.job, self.cover_letter, invalid_resume)

        self.service.users.return_value.drafts.return_value.create.assert_not_called()

    def test_wraps_gmail_api_failure_without_exposing_request_details(self):
        self.service.users.return_value.drafts.return_value.create.return_value.execute.side_effect = (
            RuntimeError("sensitive API response")
        )

        with self.assertRaisesRegex(GmailDraftError, "Gmail API failed") as error:
            self.executor.create_draft(self.job, self.cover_letter, self.resume)

        self.assertIsInstance(error.exception.__cause__, RuntimeError)
        self.assertNotIn("sensitive API response", str(error.exception))

    def test_requires_valid_recipient_and_job_title(self):
        with self.assertRaisesRegex(ValueError, "valid email address"):
            self.executor.create_draft(
                {"job_title": "Engineer", "recipient": "not-an-email"},
                self.cover_letter,
                self.resume,
            )

        with self.assertRaisesRegex(ValueError, "job_title, title, or subject"):
            self.executor.create_draft(
                {"recipient": "jobs@example.com"}, self.cover_letter, self.resume
            )

        self.service.users.return_value.drafts.return_value.create.assert_not_called()

    def test_requires_id_in_gmail_response(self):
        self.service.users.return_value.drafts.return_value.create.return_value.execute.return_value = {
            "message": {"id": "message-456"}
        }

        with self.assertRaisesRegex(GmailDraftError, "without an ID"):
            self.executor.create_draft(self.job, self.cover_letter, self.resume)


if __name__ == "__main__":
    unittest.main()

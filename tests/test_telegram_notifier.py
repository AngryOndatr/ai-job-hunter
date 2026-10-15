import os
import unittest
from unittest.mock import Mock, patch

import requests

from telegram_notifier import TelegramNotificationError, TelegramNotifier


class TelegramNotifierTests(unittest.TestCase):
    def setUp(self):
        self.session = Mock()
        self.response = self.session.post.return_value
        self.response.json.return_value = {
            "ok": True,
            "result": {"message_id": 321, "chat": {"id": 987654}},
        }
        self.token = "test-secret-bot-token"
        self.notifier = TelegramNotifier(
            bot_token=self.token,
            chat_id="987654",
            session=self.session,
        )
        self.job = {"job_title": "Senior Java Engineer", "company": "Example GmbH"}
        self.analysis = {"match_score": 86, "summary": "Strong match based on Java experience."}
        self.draft = {"url": "https://mail.google.com/mail/u/0/#drafts/draft-123"}

    def test_sends_job_analysis_and_gmail_draft_link_to_configured_chat(self):
        result = self.notifier.send_notification(self.job, self.analysis, self.draft)

        self.assertEqual(result, {"message_id": 321, "chat_id": "987654"})
        self.session.post.assert_called_once()
        call = self.session.post.call_args
        self.assertEqual(
            call.args[0],
            f"https://api.telegram.org/bot{self.token}/sendMessage",
        )
        self.assertEqual(call.kwargs["timeout"], 15)
        self.assertEqual(call.kwargs["json"]["chat_id"], "987654")
        message = call.kwargs["json"]["text"]
        self.assertIn("Senior Java Engineer", message)
        self.assertIn("Example GmbH", message)
        self.assertIn("86/100", message)
        self.assertIn("Strong match based on Java experience.", message)
        self.assertIn(self.draft["url"], message)
        self.assertNotIn(self.token, message)

    def test_sends_document_only_notification_with_both_drive_links(self):
        resume_url = "https://drive.google.com/file/d/resume-pdf/view"
        cover_letter_url = "https://drive.google.com/file/d/letter-pdf/view"

        result = self.notifier.send_document_only_notification(
            self.job, resume_url, cover_letter_url
        )

        self.assertEqual(result, {"message_id": 321, "chat_id": "987654"})
        message = self.session.post.call_args.kwargs["json"]["text"]
        self.assertIn(resume_url, message)
        self.assertIn(cover_letter_url, message)
        self.assertNotIn("Gmail draft", message)

    def test_rejects_non_google_links_for_document_only_notification(self):
        with self.assertRaisesRegex(ValueError, "Google Drive HTTPS"):
            self.notifier.send_document_only_notification(
                self.job,
                "https://example.com/resume.pdf",
                "https://drive.google.com/file/d/letter/view",
            )

        self.session.post.assert_not_called()

    def test_requires_bot_token_and_chat_id(self):
        with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "", "TELEGRAM_CHAT_ID": ""}):
            with self.assertRaisesRegex(ValueError, "TELEGRAM_BOT_TOKEN"):
                TelegramNotifier()

        with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "token", "TELEGRAM_CHAT_ID": ""}):
            with self.assertRaisesRegex(ValueError, "TELEGRAM_CHAT_ID"):
                TelegramNotifier()

    def test_rejects_invalid_job_analysis_or_draft_before_http_request(self):
        invalid_cases = [
            ({}, self.analysis, self.draft, "job_title"),
            (self.job, {"match_score": 101, "summary": "Summary"}, self.draft, "match_score"),
            (self.job, {"match_score": 86, "summary": " "}, self.draft, "summary"),
            (self.job, self.analysis, {"url": "https://example.com/draft"}, "Gmail HTTPS"),
        ]

        for job, analysis, draft, message in invalid_cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(ValueError, message):
                    self.notifier.send_notification(job, analysis, draft)

        self.session.post.assert_not_called()

    def test_handles_telegram_api_rejection(self):
        self.response.json.return_value = {"ok": False, "description": "chat not found"}

        with self.assertRaisesRegex(TelegramNotificationError, "rejected"):
            self.notifier.send_notification(self.job, self.analysis, self.draft)

    def test_rejects_malformed_success_response(self):
        self.response.json.return_value = {"ok": True, "result": {}}

        with self.assertRaisesRegex(TelegramNotificationError, "without a message ID"):
            self.notifier.send_notification(self.job, self.analysis, self.draft)

    def test_sanitizes_request_errors_that_may_contain_the_bot_token(self):
        self.session.post.side_effect = requests.HTTPError(
            f"request failed at https://api.telegram.org/bot{self.token}/sendMessage"
        )

        with self.assertRaises(TelegramNotificationError) as error:
            self.notifier.send_notification(self.job, self.analysis, self.draft)

        self.assertNotIn(self.token, str(error.exception))
        self.assertIsNone(error.exception.__cause__)

    def test_rejects_message_beyond_telegram_length_limit(self):
        oversized_analysis = {"match_score": 86, "summary": "x" * 4100}

        with self.assertRaisesRegex(ValueError, "character limit"):
            self.notifier.send_notification(self.job, oversized_analysis, self.draft)

        self.session.post.assert_not_called()


if __name__ == "__main__":
    unittest.main()

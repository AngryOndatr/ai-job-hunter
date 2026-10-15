"""Send application-ready notifications to Telegram."""

import os
from collections.abc import Mapping
from typing import Any

import requests
from dotenv import load_dotenv


class TelegramNotificationError(RuntimeError):
    """Raised when a Telegram notification cannot be delivered."""


class TelegramNotifier:
    """Send a concise job summary with a link to its Gmail draft."""

    API_BASE_URL = "https://api.telegram.org"
    MAX_MESSAGE_LENGTH = 4096

    def __init__(
        self,
        bot_token: str | None = None,
        chat_id: str | None = None,
        session: Any = None,
    ):
        load_dotenv()
        self.bot_token = bot_token or os.getenv("TELEGRAM_BOT_TOKEN")
        self.chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID")
        if not self.bot_token:
            raise ValueError("TELEGRAM_BOT_TOKEN is not set in the environment.")
        if not self.chat_id:
            raise ValueError("TELEGRAM_CHAT_ID is not set in the environment.")
        self.session = session or requests.Session()

    def send_notification(
        self,
        job: Mapping[str, Any],
        job_analysis: Mapping[str, Any],
        draft: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Send a Telegram message and return its message ID and chat ID."""
        text = self._build_message(job, job_analysis, draft)
        endpoint = f"{self.API_BASE_URL}/bot{self.bot_token}/sendMessage"

        try:
            response = self.session.post(
                endpoint,
                json={"chat_id": self.chat_id, "text": text},
                timeout=15,
            )
            response.raise_for_status()
            result = response.json()
        except Exception:
            # Request exceptions may contain the API URL, which includes the bot token.
            raise TelegramNotificationError("Telegram API request failed.") from None

        if not isinstance(result, dict) or result.get("ok") is not True:
            raise TelegramNotificationError("Telegram API rejected the notification.")

        message = result.get("result") or {}
        if not isinstance(message, dict):
            raise TelegramNotificationError("Telegram API returned an invalid notification result.")
        message_id = message.get("message_id")
        if message_id is None:
            raise TelegramNotificationError("Telegram API returned a result without a message ID.")
        chat = message.get("chat") or {}
        if not isinstance(chat, dict):
            chat = {}
        return {
            "message_id": message_id,
            "chat_id": str(chat.get("id", self.chat_id)),
        }

    @classmethod
    def _build_message(
        cls,
        job: Mapping[str, Any],
        job_analysis: Mapping[str, Any],
        draft: Mapping[str, Any],
    ) -> str:
        if not isinstance(job, Mapping):
            raise TypeError("job must be a mapping containing job details.")
        if not isinstance(job_analysis, Mapping):
            raise TypeError("job_analysis must be a mapping containing the analysis result.")
        if not isinstance(draft, Mapping):
            raise TypeError("draft must be a mapping returned by GmailDraftExecutor.")

        title = job.get("job_title") or job.get("title") or job.get("subject")
        if not isinstance(title, str) or not title.strip():
            raise ValueError("Job data must include a job_title, title, or subject.")

        score = job_analysis.get("match_score")
        if type(score) is not int or not 0 <= score <= 100:
            raise ValueError("job_analysis.match_score must be an integer from 0 to 100.")
        summary = job_analysis.get("summary")
        if not isinstance(summary, str) or not summary.strip():
            raise ValueError("job_analysis.summary must be non-empty text.")

        draft_url = draft.get("url")
        if not isinstance(draft_url, str) or not draft_url.startswith(
            "https://mail.google.com/"
        ):
            raise ValueError("draft.url must be a Gmail HTTPS link.")

        lines = ["Application materials ready", f"Position: {title.strip()}"]
        employer = job.get("employer") or job.get("company")
        if isinstance(employer, str) and employer.strip():
            lines.append(f"Company: {employer.strip()}")
        lines.extend(
            [
                f"Match: {score}/100",
                f"Analysis: {summary.strip()}",
                f"Gmail draft: {draft_url}",
            ]
        )
        text = "\n".join(lines)
        if len(text) > cls.MAX_MESSAGE_LENGTH:
            raise ValueError(
                f"Notification is longer than Telegram's {cls.MAX_MESSAGE_LENGTH}-character limit."
            )
        return text

"""Create Gmail drafts containing a cover letter and tailored resume PDF."""

import base64
import re
from collections.abc import Mapping
from email import policy
from email.message import EmailMessage
from email.utils import parseaddr
from typing import Any

import yaml
from googleapiclient.discovery import build

from google_auth import get_google_credentials


class GmailDraftError(RuntimeError):
    """Raised when a Gmail draft cannot be created."""


class GmailDraftExecutor:
    """Create reviewable Gmail drafts from job details and generated materials."""

    def __init__(self, config_path: str = "config.yaml", service: Any = None):
        try:
            with open(config_path, "r", encoding="utf-8") as config_file:
                config = yaml.safe_load(config_file) or {}
        except OSError as exc:
            raise FileNotFoundError(f"Could not read configuration file '{config_path}'.") from exc

        if service is None:
            paths = config.get("paths", {})
            credentials_file = paths.get("credentials_file", "credentials.json")
            token_file = paths.get("token_file", "token.json")
            credentials = get_google_credentials(credentials_file, token_file)
            service = build("gmail", "v1", credentials=credentials, cache_discovery=False)

        self.service = service

    def create_draft(
        self,
        job: Mapping[str, Any],
        cover_letter: str,
        tailored_resume: Mapping[str, Any],
    ) -> dict[str, str]:
        """Create a draft and return IDs and a Gmail URL for downstream notifications.

        The recipient must be explicitly present as ``application_email`` or
        ``recipient``. The collector's ``sender`` is a job-alert source and is
        deliberately never used as the application recipient.
        """
        if not isinstance(job, Mapping):
            raise TypeError("job must be a mapping containing job details.")
        if not isinstance(cover_letter, str) or not cover_letter.strip():
            raise ValueError("cover_letter must be a non-empty string.")
        if not isinstance(tailored_resume, Mapping):
            raise TypeError("tailored_resume must be the result from GoogleDriveManager.")

        recipient = job.get("application_email") or job.get("recipient")
        recipient = self._validate_recipient(recipient)
        title = self._job_title(job)
        employer = str(job.get("employer") or job.get("company") or "").strip()
        subject = f"Application: {title} at {employer}" if employer else f"Application: {title}"

        pdf_bytes = tailored_resume.get("pdf_bytes")
        if not isinstance(pdf_bytes, bytes) or not pdf_bytes.startswith(b"%PDF"):
            raise ValueError("tailored_resume must contain valid PDF bytes in 'pdf_bytes'.")
        pdf_metadata = tailored_resume.get("pdf")
        suggested_name = pdf_metadata.get("name") if isinstance(pdf_metadata, Mapping) else None
        filename = self._pdf_filename(suggested_name, title)

        message = EmailMessage(policy=policy.SMTP)
        message["To"] = recipient
        message["Subject"] = subject
        message.set_content(cover_letter.strip(), subtype="plain", charset="utf-8")
        message.add_attachment(
            pdf_bytes,
            maintype="application",
            subtype="pdf",
            filename=filename,
        )
        raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")

        try:
            draft = (
                self.service.users()
                .drafts()
                .create(userId="me", body={"message": {"raw": raw_message}})
                .execute()
            )
        except Exception as exc:
            raise GmailDraftError("Gmail API failed to create the application draft.") from exc

        draft_id = draft.get("id")
        if not isinstance(draft_id, str) or not draft_id:
            raise GmailDraftError("Gmail API returned a draft without an ID.")

        sent_message = draft.get("message") or {}
        message_id = sent_message.get("id", "")
        thread_id = sent_message.get("threadId", "")
        return {
            "draft_id": draft_id,
            "message_id": message_id,
            "thread_id": thread_id,
            "url": f"https://mail.google.com/mail/u/0/#drafts/{draft_id}",
            "recipient": recipient,
            "subject": subject,
        }

    @staticmethod
    def _validate_recipient(recipient: Any) -> str:
        if not isinstance(recipient, str) or not recipient.strip():
            raise ValueError(
                "Job data must include an application_email or recipient address."
            )
        display_name, address = parseaddr(recipient.strip())
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", address):
            raise ValueError("The application recipient must be a valid email address.")
        return f"{display_name} <{address}>" if display_name else address

    @staticmethod
    def _job_title(job: Mapping[str, Any]) -> str:
        title = job.get("job_title") or job.get("title") or job.get("subject")
        if not isinstance(title, str) or not title.strip():
            raise ValueError("Job data must include a job_title, title, or subject.")
        return title.strip()

    @staticmethod
    def _pdf_filename(suggested_name: Any, job_title: str) -> str:
        filename = suggested_name if isinstance(suggested_name, str) else ""
        filename = filename.replace("\\", "/").rsplit("/", 1)[-1]
        filename = re.sub(r'[\x00-\x1f<>:"|?*]', "_", filename).strip(" .")
        if not filename:
            filename = f"{job_title} - Tailored Resume.pdf"
        if not filename.lower().endswith(".pdf"):
            filename += ".pdf"
        return filename[:180]

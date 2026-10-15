"""Google Drive and Docs operations for tailoring and exporting resumes."""

import io
import os
import re
from collections.abc import Mapping
from typing import Any

import yaml
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

from google_auth import get_google_credentials


class GoogleDriveServiceError(RuntimeError):
    """Raised when a resume cannot be copied, tailored, or exported."""


class GoogleDriveManager:
    """Copy a Google Docs resume template, replace placeholders, and save a PDF.

    Template placeholders use double braces, for example `{{SUMMARY}}` and
    `{{EXPERIENCE}}`. The `tailored_sections` mapping may use either the full
    placeholder or its bare name as a key.
    """

    def __init__(
        self,
        config_path: str = "config.yaml",
        drive_service: Any = None,
        docs_service: Any = None,
    ):
        try:
            with open(config_path, "r", encoding="utf-8") as config_file:
                config = yaml.safe_load(config_file) or {}
        except OSError as exc:
            raise FileNotFoundError(f"Could not read configuration file '{config_path}'.") from exc

        drive_config = config.get("google_docs", {})
        self.template_id = drive_config.get("master_resume_doc_id")
        self.output_folder_id = drive_config.get("output_folder_id")
        if not self.template_id or not self.output_folder_id:
            raise ValueError(
                "config.yaml must define google_docs.master_resume_doc_id and "
                "google_docs.output_folder_id."
            )

        paths = config.get("paths", {})
        credentials_file = paths.get("credentials_file", "credentials.json")
        token_file = paths.get("token_file", "token.json")

        if drive_service is None or docs_service is None:
            credentials = get_google_credentials(credentials_file, token_file)
            drive_service = drive_service or build(
                "drive", "v3", credentials=credentials, cache_discovery=False
            )
            docs_service = docs_service or build(
                "docs", "v1", credentials=credentials, cache_discovery=False
            )

        self.drive = drive_service
        self.docs = docs_service

    def create_tailored_resume(
        self,
        job_title: str,
        tailored_sections: Mapping[str, str],
        output_name: str | None = None,
    ) -> dict[str, Any]:
        """Create a tailored Google Doc and PDF in the configured Drive folder.

        Returns document metadata, PDF metadata, and PDF bytes for downstream
        Gmail attachment handling.
        """
        if not isinstance(job_title, str) or not job_title.strip():
            raise ValueError("job_title must be a non-empty string.")
        replacements = self._normalize_replacements(tailored_sections)
        base_name = self._safe_file_name(output_name or f"{job_title} - Tailored Resume")

        document = None
        pdf_file = None
        try:
            document = self.drive.files().copy(
                fileId=self.template_id,
                body={"name": base_name, "parents": [self.output_folder_id]},
                fields="id,name,mimeType,webViewLink",
                supportsAllDrives=True,
            ).execute()
            document_id = document["id"]

            replacement_requests = [
                {
                    "replaceAllText": {
                        "containsText": {"text": placeholder, "matchCase": True},
                        "replaceText": text,
                    }
                }
                for placeholder, text in replacements.items()
            ]
            update_response = self.docs.documents().batchUpdate(
                documentId=document_id,
                body={"requests": replacement_requests},
            ).execute()

            replies = update_response.get("replies", [])
            if len(replies) != len(replacements):
                raise GoogleDriveServiceError(
                    "Google Docs returned an incomplete placeholder replacement response."
                )
            replacement_counts = {}
            for (placeholder, _), reply in zip(replacements.items(), replies):
                count = reply.get("replaceAllText", {}).get("occurrencesChanged", 0)
                replacement_counts[placeholder] = count
                if count == 0:
                    raise GoogleDriveServiceError(
                        f"Template placeholder {placeholder!r} was not found."
                    )

            pdf_bytes = self.drive.files().export(
                fileId=document_id,
                mimeType="application/pdf",
            ).execute()
            if not isinstance(pdf_bytes, bytes) or not pdf_bytes.startswith(b"%PDF"):
                raise GoogleDriveServiceError("Google Drive returned invalid PDF data.")

            pdf_name = f"{base_name}.pdf"
            pdf_file = self.drive.files().create(
                body={
                    "name": pdf_name,
                    "mimeType": "application/pdf",
                    "parents": [self.output_folder_id],
                },
                media_body=MediaIoBaseUpload(
                    io.BytesIO(pdf_bytes),
                    mimetype="application/pdf",
                    resumable=False,
                ),
                fields="id,name,mimeType,webViewLink,size",
                supportsAllDrives=True,
            ).execute()

            return {
                "document": document,
                "pdf": pdf_file,
                "pdf_bytes": pdf_bytes,
                "replacement_counts": replacement_counts,
            }
        except Exception as exc:
            self._trash_if_created(pdf_file)
            self._trash_if_created(document)
            if isinstance(exc, GoogleDriveServiceError):
                raise
            raise GoogleDriveServiceError(
                f"Failed to create the tailored resume for {job_title!r}."
            ) from exc

    @staticmethod
    def _normalize_replacements(tailored_sections: Mapping[str, str]) -> dict[str, str]:
        if not isinstance(tailored_sections, Mapping) or not tailored_sections:
            raise ValueError("tailored_sections must be a non-empty mapping of placeholders to text.")

        replacements = {}
        for key, value in tailored_sections.items():
            if not isinstance(key, str) or not key.strip():
                raise ValueError("Every tailored section must have a non-empty placeholder name.")
            if not isinstance(value, str):
                raise TypeError(f"Replacement for {key!r} must be text.")

            placeholder = key.strip()
            if not (placeholder.startswith("{{") and placeholder.endswith("}}")):
                placeholder = "{{" + placeholder.strip("{} ") + "}}"
            if placeholder == "{{}}":
                raise ValueError("Placeholder names cannot be empty.")
            replacements[placeholder] = value
        return replacements

    @staticmethod
    def _safe_file_name(name: str) -> str:
        safe_name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", name).strip(" .")
        if not safe_name:
            raise ValueError("The output file name is empty after removing invalid characters.")
        return safe_name[:180]

    def _trash_if_created(self, file_metadata: dict[str, Any] | None) -> None:
        if not file_metadata or not file_metadata.get("id"):
            return
        try:
            self.drive.files().update(
                fileId=file_metadata["id"],
                body={"trashed": True},
                supportsAllDrives=True,
            ).execute()
        except Exception:
            # Preserve the original API failure; cleanup errors should not hide it.
            pass

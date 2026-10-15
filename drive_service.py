"""Google Drive and Docs operations for tailoring and exporting resumes."""

import io
import os
import re
from collections.abc import Mapping
from typing import Any

import yaml
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

from google_auth import BASE_SCOPES, get_google_credentials


class GoogleDriveServiceError(RuntimeError):
    """Raised when a resume cannot be copied, tailored, or exported."""


class GoogleDriveManager:
    """Read a factual profile and copy a separate resume template to generate a PDF.

    Template placeholders use double braces, for example `{{SUMMARY}}` and
    `{{EXPERIENCE}}`. The `tailored_sections` mapping may use either the full
    placeholder or its bare name as a key. Only the template document is copied;
    the profile document is used as source material for AI generation.
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
        self.profile_id = drive_config.get("master_profile_doc_id")
        self.resume_template_id = drive_config.get("resume_template_doc_id")
        self.output_folder_id = drive_config.get("output_folder_id")
        if not self.profile_id or not self.resume_template_id or not self.output_folder_id:
            raise ValueError(
                "config.yaml must define google_docs.master_profile_doc_id, "
                "google_docs.resume_template_doc_id, and google_docs.output_folder_id."
            )
        if self.profile_id == self.resume_template_id:
            raise ValueError(
                "google_docs.master_profile_doc_id and resume_template_doc_id "
                "must refer to different Google Docs."
            )
        if self.resume_template_id == "REPLACE_WITH_RESUME_TEMPLATE_DOC_ID":
            raise ValueError(
                "Set google_docs.resume_template_doc_id to the ID of a separate "
                "Google Docs resume template."
            )

        paths = config.get("paths", {})
        credentials_file = paths.get("credentials_file", "credentials.json")
        token_file = paths.get("token_file", "token.json")

        if drive_service is None or docs_service is None:
            credentials = get_google_credentials(
                credentials_file, token_file, scopes=BASE_SCOPES
            )
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
        *,
        idempotency_key: str | None = None,
        output_folder_id: str | None = None,
    ) -> dict[str, Any]:
        """Create a tailored Google Doc and PDF in the configured Drive folder.

        Returns document metadata, PDF metadata, and PDF bytes for downstream
        Gmail attachment handling.
        """
        if not isinstance(job_title, str) or not job_title.strip():
            raise ValueError("job_title must be a non-empty string.")
        replacements = self._normalize_replacements(tailored_sections)
        base_name = self._safe_file_name(output_name or f"{job_title} - Tailored Resume")

        output_folder_id = output_folder_id or self.output_folder_id
        document = None
        pdf_file = None
        document_created = False
        pdf_created = False
        try:
            if idempotency_key:
                document = self._find_idempotent_file(idempotency_key, "document", output_folder_id)
            document_reused = bool(document)
            if not document:
                copy_body = {"name": base_name, "parents": [output_folder_id]}
                if idempotency_key:
                    copy_body["appProperties"] = {
                        "aiJobHunterKey": idempotency_key,
                        "aiJobHunterArtifact": "document",
                    }
                document = self.drive.files().copy(
                    fileId=self.resume_template_id,
                    body=copy_body,
                    fields=(
                        "id,name,mimeType,webViewLink,appProperties"
                        if idempotency_key
                        else "id,name,mimeType,webViewLink"
                    ),
                    supportsAllDrives=True,
                ).execute()
                document_created = True
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
            replacement_counts = {}
            if document_reused:
                current_doc = self.docs.documents().get(documentId=document_id).execute()
                existing_text = self._extract_document_text(current_doc)
                replacement_requests = [
                    request for request in replacement_requests
                    if request["replaceAllText"]["containsText"]["text"] in existing_text
                ]
            if replacement_requests:
                update_response = self.docs.documents().batchUpdate(
                    documentId=document_id,
                    body={"requests": replacement_requests},
                ).execute()
                replies = update_response.get("replies", [])
                if len(replies) != len(replacement_requests):
                    raise GoogleDriveServiceError(
                        "Google Docs returned an incomplete placeholder replacement response."
                    )
                for request, reply in zip(replacement_requests, replies):
                    placeholder = request["replaceAllText"]["containsText"]["text"]
                    count = reply.get("replaceAllText", {}).get("occurrencesChanged", 0)
                    replacement_counts[placeholder] = count
                    if count == 0:
                        raise GoogleDriveServiceError(
                            f"Template placeholder {placeholder!r} was not found."
                        )
            if document_reused:
                replacement_counts.update(
                    {key: 0 for key in replacements if key not in replacement_counts}
                )

            pdf_bytes = self.drive.files().export(
                fileId=document_id,
                mimeType="application/pdf",
            ).execute()
            if not isinstance(pdf_bytes, bytes) or not pdf_bytes.startswith(b"%PDF"):
                raise GoogleDriveServiceError("Google Drive returned invalid PDF data.")

            pdf_name = f"{base_name}.pdf"
            media = MediaIoBaseUpload(
                io.BytesIO(pdf_bytes), mimetype="application/pdf", resumable=False
            )
            if idempotency_key:
                pdf_file = self._find_idempotent_file(idempotency_key, "pdf", output_folder_id)
            if pdf_file:
                pdf_file = self.drive.files().update(
                    fileId=pdf_file["id"], media_body=media,
                    fields="id,name,mimeType,webViewLink,size", supportsAllDrives=True,
                ).execute()
            else:
                pdf_body = {
                    "name": pdf_name,
                    "mimeType": "application/pdf",
                    "parents": [output_folder_id],
                }
                if idempotency_key:
                    pdf_body["appProperties"] = {
                        "aiJobHunterKey": idempotency_key,
                        "aiJobHunterArtifact": "pdf",
                    }
                pdf_file = self.drive.files().create(
                    body=pdf_body, media_body=media,
                    fields="id,name,mimeType,webViewLink,size,appProperties",
                    supportsAllDrives=True,
                ).execute()
                pdf_created = True

            return {
                "document": document,
                "pdf": pdf_file,
                "pdf_bytes": pdf_bytes,
                "replacement_counts": replacement_counts,
            }
        except Exception as exc:
            if pdf_created:
                self._trash_if_created(pdf_file)
            if document_created:
                self._trash_if_created(document)
            if isinstance(exc, GoogleDriveServiceError):
                raise
            raise GoogleDriveServiceError(
                "Failed to create the tailored resume in Google Drive."
            ) from exc

    def _find_idempotent_file(
        self, idempotency_key: str, artifact: str, folder_id: str | None = None
    ) -> dict[str, Any] | None:
        folder_id = folder_id or self.output_folder_id
        escaped_key = idempotency_key.replace("\\", "\\\\").replace("'", "\\'")
        response = self.drive.files().list(
            q=(
                f"'{folder_id}' in parents and trashed = false and "
                "appProperties has { "
                f"key='aiJobHunterKey' and value='{escaped_key}' }} and "
                "appProperties has { "
                f"key='aiJobHunterArtifact' and value='{artifact}' }}"
            ),
            pageSize=10,
            fields="files(id,name,mimeType,webViewLink,appProperties)",
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        ).execute()
        files = response.get("files", [])
        if len(files) > 1:
            raise GoogleDriveServiceError(
                f"Multiple Drive {artifact} artifacts exist for the same source message."
            )
        return files[0] if files else None

    def create_document_only_application(
        self,
        job: Mapping[str, Any],
        job_title: str,
        tailored_sections: Mapping[str, str],
        cover_letter: str,
        *,
        idempotency_key: str,
    ) -> dict[str, Any]:
        """Save tailored resume and cover letter Docs/PDFs under the company folder."""
        if not isinstance(cover_letter, str) or not cover_letter.strip():
            raise ValueError("cover_letter must be non-empty text.")
        folder_key = f"{idempotency_key}-company"
        folder_id = self.get_or_create_company_folder(job, idempotency_key=folder_key)
        resume = self.create_tailored_resume(
            job_title,
            tailored_sections,
            output_name=f"{job_title} - Tailored Resume",
            idempotency_key=f"{idempotency_key}-resume",
            output_folder_id=folder_id,
        )
        cover = self._create_cover_letter(
            job_title, cover_letter, folder_id,
            idempotency_key=f"{idempotency_key}-cover-letter",
        )
        return {
            "folder": {"id": folder_id},
            "resume": resume,
            "cover_letter": cover,
            "idempotency_keys": {
                "company_folder": folder_key,
                "resume": f"{idempotency_key}-resume",
                "cover_letter": f"{idempotency_key}-cover-letter",
            },
        }

    def get_or_create_company_folder(
        self, job: Mapping[str, Any], *, idempotency_key: str | None = None
    ) -> str:
        """Find or create a safely named company folder beneath the output folder."""
        name = self._company_folder_name(job)
        escaped_name = name.replace("\\", "\\\\").replace("'", "\\'")
        folders = []
        if idempotency_key:
            response = self.drive.files().list(
                q=(
                    f"'{self.output_folder_id}' in parents and trashed = false and "
                    "appProperties has { "
                    f"key='aiJobHunterCompanyKey' and value='{idempotency_key}' }}"
                ),
                pageSize=10,
                fields="files(id,name)",
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
            ).execute()
            folders = response.get("files", [])
        if not folders:
            response = self.drive.files().list(
                q=(
                    f"'{self.output_folder_id}' in parents and name = '{escaped_name}' "
                    "and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
                ),
                pageSize=10,
                fields="files(id,name)",
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
            ).execute()
            folders = response.get("files", [])
        if len(folders) > 1:
            raise GoogleDriveServiceError("Multiple company folders have the same name.")
        if folders:
            return folders[0]["id"]
        folder = self.drive.files().create(
            body={
                "name": name,
                "mimeType": "application/vnd.google-apps.folder",
                "parents": [self.output_folder_id],
                **(
                    {"appProperties": {"aiJobHunterCompanyKey": idempotency_key}}
                    if idempotency_key
                    else {}
                ),
            },
            fields="id,name",
            supportsAllDrives=True,
        ).execute()
        if not folder.get("id"):
            raise GoogleDriveServiceError("Google Drive created a company folder without an ID.")
        return folder["id"]

    @classmethod
    def _company_folder_name(cls, job: Mapping[str, Any]) -> str:
        raw_name = job.get("company") or job.get("employer")
        if not isinstance(raw_name, str) or not raw_name.strip():
            raw_name = "Unknown Company"
        safe_name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", raw_name).strip(" .")
        safe_name = re.sub(r"\s+", " ", safe_name)[:100].strip(" .")
        return safe_name if safe_name.strip("_") else "Unknown Company"

    def _create_cover_letter(
        self,
        job_title: str,
        text: str,
        folder_id: str,
        *,
        idempotency_key: str,
    ) -> dict[str, Any]:
        """Create/reuse a cover-letter Google Doc and exported PDF."""
        doc = self._find_idempotent_file(idempotency_key, "cover-letter-document", folder_id)
        created_doc = False
        created_pdf = False
        pdf = None
        try:
            if not doc:
                doc = self.drive.files().create(
                    body={
                        "name": self._safe_file_name(f"{job_title} - Cover Letter"),
                        "mimeType": "application/vnd.google-apps.document",
                        "parents": [folder_id],
                        "appProperties": {
                            "aiJobHunterKey": idempotency_key,
                            "aiJobHunterArtifact": "cover-letter-document",
                        },
                    },
                    fields="id,name,mimeType,webViewLink,appProperties",
                    supportsAllDrives=True,
                ).execute()
                created_doc = True
                self.docs.documents().batchUpdate(
                    documentId=doc["id"],
                    body={
                        "requests": [
                            {"insertText": {"location": {"index": 1}, "text": text}}
                        ]
                    },
                ).execute()
            pdf_bytes = self.drive.files().export(
                fileId=doc["id"], mimeType="application/pdf"
            ).execute()
            if not isinstance(pdf_bytes, bytes) or not pdf_bytes.startswith(b"%PDF"):
                raise GoogleDriveServiceError(
                    "Google Drive returned invalid cover-letter PDF data."
                )
            pdf_key = f"{idempotency_key}-pdf"
            pdf = self._find_idempotent_file(pdf_key, "cover-letter-pdf", folder_id)
            media = MediaIoBaseUpload(
                io.BytesIO(pdf_bytes), mimetype="application/pdf", resumable=False
            )
            if pdf:
                pdf = self.drive.files().update(
                    fileId=pdf["id"], media_body=media,
                    fields="id,name,mimeType,webViewLink,size", supportsAllDrives=True,
                ).execute()
            else:
                pdf = self.drive.files().create(
                    body={
                        "name": self._safe_file_name(f"{job_title} - Cover Letter.pdf"),
                        "mimeType": "application/pdf", "parents": [folder_id],
                        "appProperties": {
                            "aiJobHunterKey": pdf_key,
                            "aiJobHunterArtifact": "cover-letter-pdf",
                        },
                    },
                    media_body=media,
                    fields="id,name,mimeType,webViewLink,size,appProperties",
                    supportsAllDrives=True,
                ).execute()
                created_pdf = True
            return {"document": doc, "pdf": pdf, "pdf_bytes": pdf_bytes}
        except Exception as exc:
            if created_pdf:
                self._trash_if_created(pdf)
            if created_doc:
                self._trash_if_created(doc)
            if isinstance(exc, GoogleDriveServiceError):
                raise
            raise GoogleDriveServiceError(
                "Failed to create the cover letter in Google Drive."
            ) from exc

    def load_master_profile(self) -> str:
        """Read factual candidate information from the master profile document."""
        try:
            document = self.docs.documents().get(documentId=self.profile_id).execute()
        except Exception as exc:
            raise GoogleDriveServiceError("Failed to read the master profile Google Doc.") from exc

        text = self._extract_document_text(document).strip()
        if not text:
            raise GoogleDriveServiceError("The master profile Google Doc contains no readable text.")
        return text

    def load_resume_template(self) -> dict[str, Any]:
        """Read the output template and discover its double-brace placeholders."""
        try:
            document = self.docs.documents().get(documentId=self.resume_template_id).execute()
        except Exception as exc:
            raise GoogleDriveServiceError("Failed to read the resume template Google Doc.") from exc

        text = self._extract_document_text(document).strip()
        placeholders = list(dict.fromkeys(re.findall(r"\{\{\s*[A-Za-z0-9_ -]+\s*\}\}", text)))
        if not text:
            raise GoogleDriveServiceError("The resume template Google Doc contains no readable text.")
        if not placeholders:
            raise GoogleDriveServiceError(
                "The resume template Google Doc contains no {{PLACEHOLDER}} sections to tailor."
            )
        return {"text": text, "placeholders": placeholders}

    @classmethod
    def _extract_document_text(cls, document: Mapping[str, Any]) -> str:
        """Extract text from Google Docs paragraphs, tables, and table of contents."""
        body = document.get("body") or {}
        content = body.get("content") or []
        if not content:
            tabs = document.get("tabs") or []
            for tab in tabs:
                tab_body = (tab.get("documentTab") or {}).get("body") or {}
                content.extend(tab_body.get("content") or [])
        return cls._extract_content_text(content)

    @classmethod
    def _extract_content_text(cls, content: list[Mapping[str, Any]]) -> str:
        pieces = []
        for element in content:
            paragraph = element.get("paragraph")
            if paragraph:
                for paragraph_element in paragraph.get("elements") or []:
                    text_run = paragraph_element.get("textRun") or {}
                    run_text = text_run.get("content")
                    if isinstance(run_text, str):
                        pieces.append(run_text)

            table = element.get("table")
            if table:
                for row in table.get("tableRows") or []:
                    for cell in row.get("tableCells") or []:
                        pieces.append(cls._extract_content_text(cell.get("content") or []))

            table_of_contents = element.get("tableOfContents")
            if table_of_contents:
                pieces.append(
                    cls._extract_content_text(table_of_contents.get("content") or [])
                )
        return "".join(pieces)

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

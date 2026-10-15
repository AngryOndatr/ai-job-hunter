"""Durable job-processing state stored as a private JSON file in Google Drive."""

import io
import json
from datetime import datetime, timezone
from typing import Any

import yaml
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload

from google_auth import get_google_credentials


class ProcessingStateError(RuntimeError):
    """Raised when durable processing state cannot be read or persisted safely."""


class GoogleDriveProcessingState:
    """Persist non-sensitive job statuses in a JSON file in the configured Drive folder."""

    FILE_NAME = "ai-job-hunter-processing-state.json"
    VERSION = 1
    TERMINAL_STATUSES = {"skipped", "draft_created"}
    VALID_STATUSES = TERMINAL_STATUSES | {
        "processing",
        "resume_pending",
        "resume_created",
        "draft_pending",
    }
    METADATA_FIELDS = {
        "reason",
        "resume_document_id",
        "resume_pdf_id",
        "resume_idempotency_key",
        "draft_message_id",
        "draft_id",
        "draft_url",
        "notification_status",
    }

    def __init__(
        self,
        config_path: str = "config.yaml",
        drive_service: Any = None,
    ):
        try:
            with open(config_path, "r", encoding="utf-8") as config_file:
                config = yaml.safe_load(config_file) or {}
        except OSError as exc:
            raise FileNotFoundError(
                f"Could not read configuration file '{config_path}'."
            ) from exc

        self.output_folder_id = (config.get("google_docs") or {}).get("output_folder_id")
        if not isinstance(self.output_folder_id, str) or not self.output_folder_id.strip():
            raise ValueError("config.yaml must define google_docs.output_folder_id.")

        if drive_service is None:
            paths = config.get("paths", {})
            credentials = get_google_credentials(
                paths.get("credentials_file", "credentials.json"),
                paths.get("token_file", "token.json"),
            )
            drive_service = build(
                "drive", "v3", credentials=credentials, cache_discovery=False
            )

        self.drive = drive_service
        self.file_id: str | None = None
        self.state: dict[str, Any] = {"version": self.VERSION, "jobs": {}}
        self._load()

    def get_terminal_ids(self) -> set[str]:
        """Return source message IDs that should not be processed again."""
        return {
            message_id
            for message_id, record in self.state["jobs"].items()
            if record.get("status") in self.TERMINAL_STATUSES
        }

    def get_job_state(self, message_id: str) -> dict[str, Any] | None:
        """Return a copy of one message's saved state, if present."""
        record = self.state["jobs"].get(message_id)
        return dict(record) if record else None

    def mark_status(self, message_id: str, status: str, **metadata: str) -> None:
        """Persist a state transition and a small allowlist of non-sensitive metadata."""
        if not isinstance(message_id, str) or not message_id:
            raise ValueError("message_id must be a non-empty string.")
        if status not in self.VALID_STATUSES:
            raise ValueError(f"Unsupported processing status: {status!r}.")
        unexpected_fields = set(metadata) - self.METADATA_FIELDS
        if unexpected_fields:
            raise ValueError("Processing state cannot store arbitrary metadata fields.")
        if not all(isinstance(value, str) for value in metadata.values()):
            raise TypeError("Processing state metadata values must be strings.")

        record = self.state["jobs"].setdefault(message_id, {})
        record.update(metadata)
        record.update(
            {
                "status": status,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        self._save()

    def _load(self) -> None:
        try:
            response = (
                self.drive.files()
                .list(
                    q=(
                        f"name = '{self.FILE_NAME}' and "
                        f"'{self.output_folder_id}' in parents and trashed = false"
                    ),
                    pageSize=10,
                    fields="files(id,name)",
                    supportsAllDrives=True,
                    includeItemsFromAllDrives=True,
                )
                .execute()
            )
            files = response.get("files", [])
            if len(files) > 1:
                raise ProcessingStateError(
                    "Multiple processing-state files were found in the configured Drive folder."
                )
            if not files:
                return

            self.file_id = files[0].get("id")
            if not self.file_id:
                raise ProcessingStateError("The processing-state file has no Drive ID.")

            buffer = io.BytesIO()
            downloader = MediaIoBaseDownload(
                buffer, self.drive.files().get_media(fileId=self.file_id)
            )
            done = False
            while not done:
                _, done = downloader.next_chunk()

            loaded = json.loads(buffer.getvalue().decode("utf-8"))
            if (
                not isinstance(loaded, dict)
                or loaded.get("version") != self.VERSION
                or not isinstance(loaded.get("jobs"), dict)
            ):
                raise ProcessingStateError("The processing-state file has an unsupported format.")
            self.state = loaded
        except ProcessingStateError:
            raise
        except Exception as exc:
            raise ProcessingStateError(
                "Could not safely read the durable processing-state file from Google Drive."
            ) from exc

    def _save(self) -> None:
        content = json.dumps(
            self.state, ensure_ascii=False, indent=2, sort_keys=True
        ).encode("utf-8")
        media = MediaIoBaseUpload(
            io.BytesIO(content), mimetype="application/json", resumable=False
        )
        try:
            if self.file_id:
                response = (
                    self.drive.files()
                    .update(
                        fileId=self.file_id,
                        media_body=media,
                        fields="id",
                        supportsAllDrives=True,
                    )
                    .execute()
                )
            else:
                response = (
                    self.drive.files()
                    .create(
                        body={
                            "name": self.FILE_NAME,
                            "mimeType": "application/json",
                            "parents": [self.output_folder_id],
                        },
                        media_body=media,
                        fields="id",
                        supportsAllDrives=True,
                    )
                    .execute()
                )
                self.file_id = response.get("id")
            if not response.get("id"):
                raise ProcessingStateError(
                    "Google Drive did not return an ID for the processing-state file."
                )
        except ProcessingStateError:
            raise
        except Exception as exc:
            raise ProcessingStateError(
                "Could not persist durable processing state to Google Drive."
            ) from exc

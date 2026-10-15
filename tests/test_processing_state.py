import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import yaml

from processing_state import GoogleDriveProcessingState, ProcessingStateError


class ProcessingStateTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.config_path = Path(self.temp_dir.name) / "config.yaml"
        self.config_path.write_text(
            yaml.safe_dump({"google_docs": {"output_folder_id": "output-folder"}}),
            encoding="utf-8",
        )
        self.drive = Mock()
        self.drive.files.return_value.list.return_value.execute.return_value = {"files": []}

    def make_store(self):
        return GoogleDriveProcessingState(
            config_path=str(self.config_path), drive_service=self.drive
        )

    def test_loads_as_empty_and_persists_terminal_status_in_drive(self):
        store = self.make_store()

        store.mark_status("gmail-1", "skipped", reason="below_match_threshold")

        self.assertEqual(store.get_terminal_ids(), {"gmail-1"})
        create = self.drive.files.return_value.create
        create.assert_called_once()
        self.assertEqual(
            create.call_args.kwargs["body"]["parents"], ["output-folder"]
        )
        self.assertEqual(
            create.call_args.kwargs["body"]["name"], store.FILE_NAME
        )

    def test_rejects_sensitive_or_unapproved_metadata(self):
        store = self.make_store()

        with self.assertRaisesRegex(ValueError, "arbitrary metadata"):
            store.mark_status("gmail-1", "processing", recipient="person@example.com")

        self.drive.files.return_value.create.assert_not_called()

    def test_rejects_multiple_state_files_in_drive(self):
        self.drive.files.return_value.list.return_value.execute.return_value = {
            "files": [{"id": "one"}, {"id": "two"}]
        }

        with self.assertRaisesRegex(ProcessingStateError, "Multiple processing-state"):
            self.make_store()

    def test_loads_existing_terminal_state(self):
        self.drive.files.return_value.list.return_value.execute.return_value = {
            "files": [{"id": "state-file", "name": GoogleDriveProcessingState.FILE_NAME}]
        }
        contents = json.dumps(
            {
                "version": 1,
                "jobs": {"gmail-done": {"status": "draft_created"}},
            }
        ).encode("utf-8")

        class Downloader:
            def __init__(self, buffer, _request):
                self.buffer = buffer
                self.done = False

            def next_chunk(self):
                if not self.done:
                    self.buffer.write(contents)
                    self.done = True
                return None, self.done

        with patch("processing_state.MediaIoBaseDownload", Downloader):
            store = self.make_store()

        self.assertEqual(store.get_terminal_ids(), {"gmail-done"})
        self.assertEqual(store.file_id, "state-file")

    def test_legacy_missing_recipient_skips_are_reprocessable(self):
        store = self.make_store()
        store.state["jobs"] = {
            "gmail-recipient-missing": {
                "status": "skipped",
                "reason": "missing_application_recipient",
            },
            "gmail-low-match": {
                "status": "skipped",
                "reason": "below_match_threshold",
            },
            "gmail-in-progress": {"status": "processing"},
        }

        self.assertEqual(store.get_reprocessable_ids(), {
            "gmail-recipient-missing", "gmail-in-progress"
        })
        self.assertEqual(store.get_terminal_ids(), {"gmail-low-match"})

    def test_document_only_application_is_terminal_only_after_notification_succeeds(self):
        store = self.make_store()
        store.state["jobs"] = {
            "gmail-notified": {
                "status": "document_only_created",
                "notification_status": "sent",
            },
            "gmail-notification-pending": {
                "status": "document_only_created",
                "notification_status": "failed",
            },
            "gmail-artifact-pending": {"status": "document_only_pending"},
        }

        self.assertEqual(store.get_terminal_ids(), {"gmail-notified"})
        self.assertEqual(
            store.get_reprocessable_ids(),
            {"gmail-notification-pending", "gmail-artifact-pending"},
        )

    def test_persists_document_only_artifact_ids_links_and_idempotency_metadata(self):
        store = self.make_store()

        store.mark_status(
            "gmail-doc-only",
            "document_only_created",
            document_only_idempotency_key="stable-job-key",
            company_folder_key="stable-company-key",
            company_folder_id="folder-id",
            resume_document_id="resume-doc-id",
            resume_pdf_id="resume-pdf-id",
            resume_pdf_link="https://drive.google.com/file/d/resume/view",
            cover_letter_document_id="letter-doc-id",
            cover_letter_pdf_id="letter-pdf-id",
            cover_letter_pdf_link="https://drive.google.com/file/d/letter/view",
            notification_status="pending",
        )

        self.assertEqual(store.get_job_state("gmail-doc-only")["status"], "document_only_created")
        self.drive.files.return_value.create.assert_called_once()


if __name__ == "__main__":
    unittest.main()

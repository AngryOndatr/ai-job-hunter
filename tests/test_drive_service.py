import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

import yaml

from drive_service import GoogleDriveManager, GoogleDriveServiceError


class GoogleDriveManagerTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.config_path = Path(self.temp_dir.name) / "config.yaml"
        self.config_path.write_text(
            yaml.safe_dump(
                {
                    "google_docs": {
                        "master_resume_doc_id": "template-id",
                        "output_folder_id": "output-folder-id",
                    },
                    "paths": {
                        "credentials_file": "credentials.json",
                        "token_file": "token.json",
                    },
                }
            ),
            encoding="utf-8",
        )

        self.drive = Mock()
        self.docs = Mock()
        self.document = {
            "id": "tailored-doc-id",
            "name": "Senior Java Engineer - Tailored Resume",
            "mimeType": "application/vnd.google-apps.document",
            "webViewLink": "https://docs.google.com/document/d/tailored-doc-id/edit",
        }
        self.pdf_file = {
            "id": "tailored-pdf-id",
            "name": "Senior Java Engineer - Tailored Resume.pdf",
            "mimeType": "application/pdf",
            "webViewLink": "https://drive.google.com/file/d/tailored-pdf-id/view",
            "size": "14",
        }
        self.pdf_bytes = b"%PDF-1.7\nmock-pdf-data"

        self.drive.files.return_value.copy.return_value.execute.return_value = self.document
        self.drive.files.return_value.export.return_value.execute.return_value = self.pdf_bytes
        self.drive.files.return_value.create.return_value.execute.return_value = self.pdf_file
        self.docs.documents.return_value.batchUpdate.return_value.execute.return_value = {
            "replies": [{"replaceAllText": {"occurrencesChanged": 1}}]
        }

        self.manager = GoogleDriveManager(
            config_path=str(self.config_path),
            drive_service=self.drive,
            docs_service=self.docs,
        )

    def test_loads_master_profile_and_discovers_placeholders_in_document_content(self):
        self.docs.documents.return_value.get.return_value.execute.return_value = {
            "body": {
                "content": [
                    {
                        "paragraph": {
                            "elements": [
                                {"textRun": {"content": "Profile text\n{{SUMMARY}}\n"}},
                            ]
                        }
                    },
                    {
                        "table": {
                            "tableRows": [
                                {
                                    "tableCells": [
                                        {
                                            "content": [
                                                {
                                                    "paragraph": {
                                                        "elements": [
                                                            {"textRun": {"content": "{{EXPERIENCE}}\n"}}
                                                        ]
                                                    }
                                                }
                                            ]
                                        }
                                    ]
                                }
                            ]
                        }
                    },
                ]
            }
        }

        result = self.manager.load_master_resume_profile()

        self.assertIn("Profile text", result["text"])
        self.assertEqual(result["placeholders"], ["{{SUMMARY}}", "{{EXPERIENCE}}"])
        self.docs.documents.return_value.get.assert_called_once_with(
            documentId="template-id"
        )

    def test_copies_replaces_exports_and_saves_pdf(self):
        result = self.manager.create_tailored_resume(
            "Senior Java Engineer",
            {"SUMMARY": "Java engineer with Spring Boot experience."},
        )

        self.assertEqual(result["document"], self.document)
        self.assertEqual(result["pdf"], self.pdf_file)
        self.assertEqual(result["pdf_bytes"], self.pdf_bytes)
        self.assertEqual(result["replacement_counts"], {"{{SUMMARY}}": 1})

        self.drive.files.return_value.copy.assert_called_once_with(
            fileId="template-id",
            body={
                "name": "Senior Java Engineer - Tailored Resume",
                "parents": ["output-folder-id"],
            },
            fields="id,name,mimeType,webViewLink",
            supportsAllDrives=True,
        )
        update_call = self.docs.documents.return_value.batchUpdate.call_args.kwargs
        self.assertEqual(update_call["documentId"], "tailored-doc-id")
        self.assertEqual(
            update_call["body"]["requests"][0]["replaceAllText"]["containsText"]["text"],
            "{{SUMMARY}}",
        )
        self.drive.files.return_value.export.assert_called_once_with(
            fileId="tailored-doc-id",
            mimeType="application/pdf",
        )
        self.drive.files.return_value.create.assert_called_once()

    def test_trashes_copy_when_template_placeholder_is_missing(self):
        self.docs.documents.return_value.batchUpdate.return_value.execute.return_value = {
            "replies": [{"replaceAllText": {"occurrencesChanged": 0}}]
        }

        with self.assertRaisesRegex(GoogleDriveServiceError, "placeholder.*not found"):
            self.manager.create_tailored_resume("Java Engineer", {"SUMMARY": "New summary"})

        self.drive.files.return_value.update.assert_called_once_with(
            fileId="tailored-doc-id",
            body={"trashed": True},
            supportsAllDrives=True,
        )
        self.drive.files.return_value.export.assert_not_called()

    def test_trashes_copy_when_docs_update_fails(self):
        self.docs.documents.return_value.batchUpdate.return_value.execute.side_effect = OSError(
            "Docs API unavailable"
        )

        with self.assertRaisesRegex(GoogleDriveServiceError, "Failed to create"):
            self.manager.create_tailored_resume("Java Engineer", {"SUMMARY": "New summary"})

        self.drive.files.return_value.update.assert_called_once_with(
            fileId="tailored-doc-id",
            body={"trashed": True},
            supportsAllDrives=True,
        )

    def test_trashes_copy_when_exported_content_is_not_a_pdf(self):
        self.drive.files.return_value.export.return_value.execute.return_value = b"not a pdf"

        with self.assertRaisesRegex(GoogleDriveServiceError, "invalid PDF"):
            self.manager.create_tailored_resume("Java Engineer", {"SUMMARY": "New summary"})

        self.drive.files.return_value.update.assert_called_once_with(
            fileId="tailored-doc-id",
            body={"trashed": True},
            supportsAllDrives=True,
        )
        self.drive.files.return_value.create.assert_not_called()

    def test_rejects_invalid_sections_before_calling_google_apis(self):
        with self.assertRaisesRegex(ValueError, "non-empty mapping"):
            self.manager.create_tailored_resume("Java Engineer", {})

        self.drive.files.return_value.copy.assert_not_called()

    def test_sanitizes_invalid_characters_in_output_name(self):
        result = self.manager._safe_file_name("Java/Platform: Engineer?")

        self.assertEqual(result, "Java_Platform_ Engineer_")


if __name__ == "__main__":
    unittest.main()

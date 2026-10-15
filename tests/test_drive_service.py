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
                        "master_profile_doc_id": "profile-id",
                        "resume_template_doc_id": "template-id",
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
        self.drive.files.return_value.update.return_value.execute.return_value = self.pdf_file
        self.drive.files.return_value.create.return_value.execute.return_value = self.pdf_file
        self.docs.documents.return_value.batchUpdate.return_value.execute.return_value = {
            "replies": [{"replaceAllText": {"occurrencesChanged": 1}}]
        }

        self.manager = GoogleDriveManager(
            config_path=str(self.config_path),
            drive_service=self.drive,
            docs_service=self.docs,
        )

    def test_loads_profile_and_template_from_separate_documents(self):
        profile_document = {
            "body": {
                "content": [
                    {"paragraph": {"elements": [{"textRun": {"content": "FACTUAL PROFILE TEXT\n"}}]}}
                ]
            }
        }
        template_document = {
            "body": {
                "content": [
                    {
                        "paragraph": {
                            "elements": [
                                {"textRun": {"content": "Template layout\n{{SUMMARY}}\n"}},
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
        self.docs.documents.return_value.get.return_value.execute.side_effect = [
            profile_document,
            template_document,
        ]

        profile = self.manager.load_master_profile()
        template = self.manager.load_resume_template()

        self.assertEqual(profile, "FACTUAL PROFILE TEXT")
        self.assertIn("Template layout", template["text"])
        self.assertEqual(template["placeholders"], ["{{SUMMARY}}", "{{EXPERIENCE}}"])
        self.assertEqual(
            self.docs.documents.return_value.get.call_args_list,
            [
                unittest.mock.call(documentId="profile-id"),
                unittest.mock.call(documentId="template-id"),
            ],
        )

    def test_rejects_same_document_for_profile_and_output_template(self):
        config = yaml.safe_load(self.config_path.read_text(encoding="utf-8"))
        config["google_docs"]["resume_template_doc_id"] = "profile-id"
        self.config_path.write_text(yaml.safe_dump(config), encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "different Google Docs"):
            GoogleDriveManager(
                config_path=str(self.config_path),
                drive_service=self.drive,
                docs_service=self.docs,
            )

    def test_requires_configured_separate_resume_template_id(self):
        config = yaml.safe_load(self.config_path.read_text(encoding="utf-8"))
        config["google_docs"]["resume_template_doc_id"] = (
            "REPLACE_WITH_RESUME_TEMPLATE_DOC_ID"
        )
        self.config_path.write_text(yaml.safe_dump(config), encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "Set google_docs.resume_template_doc_id"):
            GoogleDriveManager(
                config_path=str(self.config_path),
                drive_service=self.drive,
                docs_service=self.docs,
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

    def test_reuses_existing_resume_artifacts_for_same_idempotency_key(self):
        document = {
            **self.document,
            "appProperties": {
                "aiJobHunterKey": "stable-key",
                "aiJobHunterArtifact": "document",
            },
        }
        pdf = {
            **self.pdf_file,
            "appProperties": {
                "aiJobHunterKey": "stable-key",
                "aiJobHunterArtifact": "pdf",
            },
        }
        self.drive.files.return_value.list.return_value.execute.side_effect = [
            {"files": [document]},
            {"files": [pdf]},
        ]
        self.docs.documents.return_value.get.return_value.execute.return_value = {
            "body": {"content": [{"paragraph": {"elements": [{"textRun": {"content": "Already tailored"}}]}}]}
        }
        self.drive.files.return_value.export.return_value.execute.return_value = self.pdf_bytes
        self.drive.files.return_value.update.return_value.execute.return_value = self.pdf_file

        result = self.manager.create_tailored_resume(
            "Senior Java Engineer", {"{{SUMMARY}}": "Java engineer"},
            idempotency_key="stable-key",
        )

        self.assertEqual(result["document"]["id"], self.document["id"])
        self.assertEqual(result["pdf"]["id"], self.pdf_file["id"])
        self.drive.files.return_value.copy.assert_not_called()
        self.docs.documents.return_value.batchUpdate.assert_not_called()
        self.drive.files.return_value.create.assert_not_called()
        self.drive.files.return_value.update.assert_called_once()


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

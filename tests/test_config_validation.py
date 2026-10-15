import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import yaml

from config_validation import (
    ConfigurationError,
    load_validated_config,
    preflight_google_oauth,
    validate_required_secrets,
)
from google_auth import BASE_SCOPES, SCOPES


class ConfigValidationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.config_path = Path(self.temp_dir.name) / "config.yaml"
        self.config = {
            "gmail": {
                "target_labels": ["Jobs"],
                "max_email_age_days": 7,
                "processed_ids_file": "processed_ids.json",
            },
            "ai_policy": {
                "provider": "google",
                "model": "gemini-test-model",
                "language": "en",
                "min_match_score_to_draft": 75,
            },
            "google_docs": {
                "master_profile_doc_id": "profile-id",
                "resume_template_doc_id": "template-id",
                "output_folder_id": "output-folder-id",
            },
            "paths": {"credentials_file": "credentials.json", "token_file": "token.json"},
            "limits": {"max_jobs_per_run": 5},
        }
        self.write_config()

    def write_config(self):
        self.config_path.write_text(yaml.safe_dump(self.config), encoding="utf-8")

    def test_accepts_valid_project_configuration(self):
        validated = load_validated_config(str(self.config_path))
        self.assertEqual(validated["limits"]["max_jobs_per_run"], 5)

    def test_rejects_invalid_limits_before_use(self):
        self.config["limits"]["max_jobs_per_run"] = 0
        self.write_config()

        with self.assertRaisesRegex(ConfigurationError, "limits.max_jobs_per_run"):
            load_validated_config(str(self.config_path))

    def test_rejects_placeholder_template_id(self):
        self.config["google_docs"]["resume_template_doc_id"] = (
            "REPLACE_WITH_RESUME_TEMPLATE_DOC_ID"
        )
        self.write_config()

        with self.assertRaisesRegex(ConfigurationError, "resume_template_doc_id"):
            load_validated_config(str(self.config_path))

    def test_missing_secret_error_names_variable_but_never_value(self):
        secret_value = "sensitive-api-key-value"

        with self.assertRaises(ConfigurationError) as caught:
            validate_required_secrets(
                dry_run=False,
                environ={"GEMINI_API_KEY": "", "TELEGRAM_BOT_TOKEN": secret_value},
            )

        self.assertIn("GEMINI_API_KEY", str(caught.exception))
        self.assertIn("TELEGRAM_CHAT_ID", str(caught.exception))
        self.assertNotIn(secret_value, str(caught.exception))

    def test_dry_run_does_not_require_telegram_credentials(self):
        validate_required_secrets(
            dry_run=True,
            environ={"GEMINI_API_KEY": "gemini-key"},
        )

    def test_rejects_oauth_credentials_without_required_scopes_safely(self):
        credentials = Mock()
        credentials.has_scopes.return_value = False

        with patch("config_validation.get_google_credentials", return_value=credentials):
            with self.assertRaises(ConfigurationError) as caught:
                preflight_google_oauth(self.config)

        credentials.has_scopes.assert_called_once_with(SCOPES)
        self.assertIn(
            "required Gmail compose, Gmail read, Drive, or Docs scopes",
            str(caught.exception),
        )

    def test_document_only_preflight_does_not_require_gmail_compose_scope(self):
        credentials = Mock()
        credentials.has_scopes.return_value = True

        with patch("config_validation.get_google_credentials", return_value=credentials):
            preflight_google_oauth(self.config, require_gmail_compose=False)

        credentials.has_scopes.assert_called_once_with(BASE_SCOPES)

    def test_redacts_unexpected_oauth_exception_details(self):
        secret_value = "private-refresh-token"

        with patch(
            "config_validation.get_google_credentials",
            side_effect=RuntimeError(f"OAuth failed with {secret_value}"),
        ):
            with self.assertRaises(ConfigurationError) as caught:
                preflight_google_oauth(self.config)

        self.assertNotIn(secret_value, str(caught.exception))


if __name__ == "__main__":
    unittest.main()

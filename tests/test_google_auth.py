import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from google_auth import BASE_SCOPES, SCOPES, get_google_credentials


class GoogleAuthTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.token_path = Path(self.temp_dir.name) / "token.json"
        self.credentials_path = Path(self.temp_dir.name) / "credentials.json"
        self.credentials_path.write_text("{}", encoding="utf-8")

    @staticmethod
    def make_credentials(scopes):
        creds = Mock()
        creds.valid = True
        creds.expired = False
        creds.refresh_token = "refresh-token"
        creds.to_json.return_value = json.dumps({"scopes": scopes, "token": "updated-token"})
        return creds

    def test_reuses_token_when_it_has_all_required_scopes(self):
        self.token_path.write_text(json.dumps({"scopes": SCOPES}), encoding="utf-8")
        creds = self.make_credentials(SCOPES)

        with patch("google_auth.Credentials.from_authorized_user_file", return_value=creds) as load:
            with patch("google_auth.InstalledAppFlow.from_client_secrets_file") as oauth_flow:
                result = get_google_credentials(str(self.credentials_path), str(self.token_path))

        self.assertIs(result, creds)
        load.assert_called_once_with(str(self.token_path), SCOPES)
        oauth_flow.assert_not_called()
        saved_token = json.loads(self.token_path.read_text(encoding="utf-8"))
        self.assertEqual(saved_token["token"], "updated-token")

    def test_reauthorizes_old_token_that_lacks_required_google_api_scopes(self):
        self.token_path.write_text(
            json.dumps(
                {
                    "scopes": [
                        scope
                        for scope in SCOPES
                        if scope != "https://www.googleapis.com/auth/gmail.compose"
                    ]
                }
            ),
            encoding="utf-8",
        )
        creds = self.make_credentials(SCOPES)
        flow = Mock()
        flow.run_local_server.return_value = creds

        with patch(
            "google_auth.InstalledAppFlow.from_client_secrets_file", return_value=flow
        ) as create_flow:
            result = get_google_credentials(str(self.credentials_path), str(self.token_path))

        self.assertIs(result, creds)
        create_flow.assert_called_once_with(str(self.credentials_path), SCOPES)
        flow.run_local_server.assert_called_once_with(port=0)

    def test_reuses_read_and_drive_token_without_gmail_compose_scope(self):
        self.token_path.write_text(
            json.dumps({"scopes": BASE_SCOPES}), encoding="utf-8"
        )
        creds = self.make_credentials(BASE_SCOPES)

        with patch("google_auth.Credentials.from_authorized_user_file", return_value=creds) as load:
            with patch("google_auth.InstalledAppFlow.from_client_secrets_file") as oauth_flow:
                result = get_google_credentials(
                    str(self.credentials_path), str(self.token_path), scopes=BASE_SCOPES
                )

        self.assertIs(result, creds)
        load.assert_called_once_with(str(self.token_path), BASE_SCOPES)
        oauth_flow.assert_not_called()

    def test_preserves_granted_compose_scope_when_loading_token_for_document_only_use(self):
        self.token_path.write_text(json.dumps({"scopes": SCOPES}), encoding="utf-8")
        creds = self.make_credentials(BASE_SCOPES)

        with patch("google_auth.Credentials.from_authorized_user_file", return_value=creds):
            get_google_credentials(
                str(self.credentials_path), str(self.token_path), scopes=BASE_SCOPES
            )

        saved_token = json.loads(self.token_path.read_text(encoding="utf-8"))
        self.assertEqual(saved_token["scopes"], SCOPES)

    def test_requires_oauth_client_file_when_existing_token_has_insufficient_scopes(self):
        self.token_path.write_text(json.dumps({"scopes": []}), encoding="utf-8")
        self.credentials_path.unlink()

        with self.assertRaisesRegex(FileNotFoundError, "Credentials file"):
            get_google_credentials(str(self.credentials_path), str(self.token_path))


if __name__ == "__main__":
    unittest.main()

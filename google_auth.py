"""Shared OAuth credentials for Gmail, Google Drive, and Google Docs."""

import json
import os

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow


GMAIL_READ_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
GMAIL_COMPOSE_SCOPE = "https://www.googleapis.com/auth/gmail.compose"
DRIVE_SCOPE = "https://www.googleapis.com/auth/drive"
DOCS_SCOPE = "https://www.googleapis.com/auth/documents"
BASE_SCOPES = [GMAIL_READ_SCOPE, DRIVE_SCOPE, DOCS_SCOPE]
DRAFT_SCOPES = [*BASE_SCOPES, GMAIL_COMPOSE_SCOPE]
SCOPES = DRAFT_SCOPES


def get_google_credentials(
    credentials_file: str,
    token_file: str,
    scopes: list[str] | None = None,
) -> Credentials:
    """Load, refresh, or obtain OAuth credentials with all project scopes.

    Older token files are re-authorized when they do not record all requested
    scopes; refresh tokens cannot grant scopes that were not originally approved.
    """
    requested_scopes = SCOPES if scopes is None else scopes
    granted_scopes = requested_scopes
    creds = None
    if os.path.exists(token_file):
        with open(token_file, "r", encoding="utf-8") as token_handle:
            token_info = json.load(token_handle)

        stored_scopes = token_info.get("scopes") or []
        if isinstance(stored_scopes, str):
            stored_scopes = stored_scopes.split()

        if set(requested_scopes).issubset(set(stored_scopes)):
            creds = Credentials.from_authorized_user_file(token_file, requested_scopes)
            granted_scopes = stored_scopes

    if creds and not creds.valid:
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            creds = None

    if not creds:
        if not os.path.exists(credentials_file):
            raise FileNotFoundError(
                f"Credentials file '{credentials_file}' not found. "
                "Download an OAuth client file from Google Cloud Console."
            )
        flow = InstalledAppFlow.from_client_secrets_file(credentials_file, requested_scopes)
        creds = flow.run_local_server(port=0)

    credential_data = json.loads(creds.to_json())
    credential_data["scopes"] = granted_scopes
    with open(token_file, "w", encoding="utf-8") as token_handle:
        json.dump(credential_data, token_handle)

    return creds

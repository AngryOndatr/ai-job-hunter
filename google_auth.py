"""Shared OAuth credentials for Gmail, Google Drive, and Google Docs."""

import json
import os

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow


SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/documents",
]


def get_google_credentials(credentials_file: str, token_file: str) -> Credentials:
    """Load, refresh, or obtain OAuth credentials with all project scopes.

    Older token files are re-authorized when they do not record all requested
    scopes; refresh tokens cannot grant scopes that were not originally approved.
    """
    creds = None
    if os.path.exists(token_file):
        with open(token_file, "r", encoding="utf-8") as token_handle:
            token_info = json.load(token_handle)

        stored_scopes = token_info.get("scopes") or []
        if isinstance(stored_scopes, str):
            stored_scopes = stored_scopes.split()

        if set(SCOPES).issubset(set(stored_scopes)):
            creds = Credentials.from_authorized_user_file(token_file, SCOPES)

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
        flow = InstalledAppFlow.from_client_secrets_file(credentials_file, SCOPES)
        creds = flow.run_local_server(port=0)

    with open(token_file, "w", encoding="utf-8") as token_handle:
        token_handle.write(creds.to_json())

    return creds

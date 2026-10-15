"""Validate configuration and runtime prerequisites before touching Gmail."""

import os
from collections.abc import Mapping
from typing import Any

import yaml
from dotenv import load_dotenv

from google_auth import BASE_SCOPES, DRAFT_SCOPES, get_google_credentials


SUPPORTED_LANGUAGES = {"en", "de", "uk"}
MAX_JOBS_PER_RUN = 10  # Matches typical config.yaml default
MAX_EMAIL_AGE_DAYS = 365


class ConfigurationError(ValueError):
    """Raised when configuration or runtime prerequisites are incomplete."""


def load_validated_config(config_path: str) -> dict[str, Any]:
    """Load YAML and validate fields and ranges without echoing config values."""
    try:
        with open(config_path, "r", encoding="utf-8") as config_file:
            config = yaml.safe_load(config_file)
    except OSError:
        raise ConfigurationError(
            f"Cannot read configuration file '{config_path}'. Check the configured path."
        ) from None
    except yaml.YAMLError:
        raise ConfigurationError(
            f"Configuration file '{config_path}' is not valid YAML."
        ) from None

    if not isinstance(config, dict):
        raise ConfigurationError("The configuration root must be a YAML mapping.")

    gmail = _mapping(config, "gmail")
    labels = gmail.get("target_labels")
    if (
        not isinstance(labels, list)
        or not labels
        or not all(isinstance(label, str) and label.strip() for label in labels)
    ):
        raise ConfigurationError("gmail.target_labels must be a non-empty list of label names.")
    _bounded_integer(
        gmail.get("max_email_age_days"),
        "gmail.max_email_age_days",
        1,
        MAX_EMAIL_AGE_DAYS,
    )
    _non_empty_string(gmail.get("processed_ids_file"), "gmail.processed_ids_file")

    ai_policy = _mapping(config, "ai_policy")
    if ai_policy.get("provider") != "google":
        raise ConfigurationError("ai_policy.provider must be 'google'.")
    _non_empty_string(ai_policy.get("model"), "ai_policy.model")
    language = ai_policy.get("language")
    if not isinstance(language, str) or language not in SUPPORTED_LANGUAGES:
        raise ConfigurationError("ai_policy.language must be one of: de, en, uk.")
    threshold = ai_policy.get("min_match_score_to_draft")
    if type(threshold) not in (int, float) or not 0 <= threshold <= 100:
        raise ConfigurationError(
            "ai_policy.min_match_score_to_draft must be a number from 0 to 100."
        )

    google_docs = _mapping(config, "google_docs")
    profile_id = _non_empty_string(
        google_docs.get("master_profile_doc_id"), "google_docs.master_profile_doc_id"
    )
    template_id = _non_empty_string(
        google_docs.get("resume_template_doc_id"), "google_docs.resume_template_doc_id"
    )
    output_folder_id = _non_empty_string(
        google_docs.get("output_folder_id"), "google_docs.output_folder_id"
    )
    if template_id == "REPLACE_WITH_RESUME_TEMPLATE_DOC_ID":
        raise ConfigurationError(
            "Set google_docs.resume_template_doc_id to the separate resume template document ID."
        )
    if profile_id == template_id:
        raise ConfigurationError(
            "google_docs.master_profile_doc_id and resume_template_doc_id must be different."
        )
    if output_folder_id in {profile_id, template_id}:
        raise ConfigurationError(
            "google_docs.output_folder_id must identify a folder, not either Google Doc."
        )

    paths = _mapping(config, "paths")
    _non_empty_string(paths.get("credentials_file"), "paths.credentials_file")
    _non_empty_string(paths.get("token_file"), "paths.token_file")

    limits = _mapping(config, "limits")
    _bounded_integer(
        limits.get("max_jobs_per_run"), "limits.max_jobs_per_run", 1, MAX_JOBS_PER_RUN
    )

    filters = config.get("filters", {})
    if not isinstance(filters, Mapping):
        raise ConfigurationError("filters must be a YAML mapping.")
    for key in ("keywords", "blacklisted_keywords"):
        if key in filters:
            values = filters[key]
            if not isinstance(values, list) or not all(
                isinstance(value, str) and value.strip() for value in values
            ):
                raise ConfigurationError(f"filters.{key} must be a list of non-empty strings.")

    return config


def validate_required_secrets(
    *,
    dry_run: bool,
    require_gemini: bool = True,
    require_telegram: bool = True,
    environ: Mapping[str, str] | None = None,
) -> None:
    """Fail before ingestion when required environment variables are missing."""
    load_dotenv()
    env = os.environ if environ is None else environ
    required = []
    if require_gemini:
        required.append("GEMINI_API_KEY")
    if require_telegram and not dry_run:
        required.extend(("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"))
    missing = [
        name
        for name in required
        if not isinstance(env.get(name), str) or not env[name].strip()
    ]
    if missing:
        names = ", ".join(missing)
        raise ConfigurationError(f"Missing required environment variable(s): {names}.")


def preflight_google_oauth(
    config: Mapping[str, Any], *, require_gmail_compose: bool = True
) -> None:
    """Refresh or obtain the Google scopes required by the selected application path."""
    paths = config["paths"]
    scopes = DRAFT_SCOPES if require_gmail_compose else BASE_SCOPES
    try:
        credentials = get_google_credentials(
            paths["credentials_file"], paths["token_file"], scopes=scopes
        )
        if not credentials.has_scopes(scopes):
            missing_scope_context = (
                "Gmail compose, Gmail read, Drive, or Docs"
                if require_gmail_compose
                else "Gmail read, Drive, or Docs"
            )
            raise ConfigurationError(
                f"Google OAuth token is missing required {missing_scope_context} scopes. "
                "Reauthorize the account with the scopes required by this application path."
            )
    except ConfigurationError:
        raise
    except Exception:
        raise ConfigurationError(
            "Google OAuth preflight failed. Check the OAuth client/token files, account access, "
            "and the required Gmail, Drive, and Docs scopes."
        ) from None


def _mapping(config: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = config.get(key)
    if not isinstance(value, Mapping):
        raise ConfigurationError(f"{key} must be a YAML mapping.")
    return value


def _non_empty_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConfigurationError(f"{field} must be a non-empty string.")
    return value.strip()


def _bounded_integer(value: Any, field: str, minimum: int, maximum: int) -> None:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ConfigurationError(f"{field} must be an integer from {minimum} to {maximum}.")

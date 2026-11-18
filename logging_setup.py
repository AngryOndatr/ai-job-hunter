"""Shared logging configuration for the AI Job Hunter pipeline.

Design rules (see CLAUDE.md "AI input safety" and report redaction policy):

- Logs are operational telemetry: stage names, message/document/draft IDs,
  counts, durations, and safe error types. They must never contain secret
  values, job-alert bodies, profile text, or recipient addresses.
- Unexpected exception details are redacted at the call sites; this module
  only formats what callers already chose to log.
"""

import logging
import os
import sys
from datetime import datetime, timezone

LOG_LEVEL_ENV = "AI_JOB_HUNTER_LOG_LEVEL"
DEFAULT_LOG_LEVEL = "INFO"
_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"


def _resolve_level() -> int:
    raw = os.getenv(LOG_LEVEL_ENV, DEFAULT_LOG_LEVEL).upper()
    return getattr(logging, raw, logging.INFO)


def configure_logging(*, log_file: str | None = None, level: int | None = None) -> logging.Logger:
    """Configure the root pipeline logger; returns the 'ai_job_hunter' logger.

    Always emits to stdout (captured by GitHub Actions). When ``log_file`` is
    given, the same records are appended to that file for local debugging.
    """
    level = level if level is not None else _resolve_level()

    root = logging.getLogger("ai_job_hunter")
    root.setLevel(level)
    root.handlers.clear()
    root.propagate = False

    formatter = logging.Formatter(_LOG_FORMAT)

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    stream_handler.setLevel(level)
    root.addHandler(stream_handler)

    if log_file:
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(formatter)
        file_handler.setLevel(level)
        root.addHandler(file_handler)

    return root


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_logger(name: str) -> logging.Logger:
    """Return a child logger of the pipeline root."""
    return logging.getLogger("ai_job_hunter").getChild(name)

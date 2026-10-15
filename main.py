"""Orchestrate the end-to-end job application preparation pipeline."""

import json
from collections.abc import Mapping
from typing import Any

import yaml

from ai_tailor import GeminiJobAnalyzer
from drive_service import GoogleDriveManager
from gmail_collector import GmailJobCollector
from gmail_executor import GmailDraftExecutor
from telegram_notifier import TelegramNotifier


def run_pipeline(
    config_path: str = "config.yaml",
    *,
    collector: Any = None,
    analyzer: Any = None,
    drive_manager: Any = None,
    draft_executor: Any = None,
    notifier: Any = None,
) -> dict[str, Any]:
    """Run one batch and return a report; dependencies can be injected for tests."""
    try:
        with open(config_path, "r", encoding="utf-8") as config_file:
            config = yaml.safe_load(config_file) or {}
    except OSError as exc:
        raise FileNotFoundError(f"Could not read configuration file '{config_path}'.") from exc

    limits = config.get("limits", {})
    max_jobs = limits.get("max_jobs_per_run", 5)
    if type(max_jobs) is not int or max_jobs < 1:
        raise ValueError("limits.max_jobs_per_run must be a positive integer.")

    collector = collector or GmailJobCollector(config_path=config_path)
    jobs = collector.fetch_new_job_emails(defer_processed=True)
    batch = jobs[:max_jobs]
    report = {
        "fetched": len(jobs),
        "attempted": len(batch),
        "drafts_created": 0,
        "notifications_sent": 0,
        "skipped": [],
        "errors": [],
    }
    if not batch:
        return report

    analyzer = analyzer or GeminiJobAnalyzer(config_path=config_path)
    drive_manager = drive_manager or GoogleDriveManager(config_path=config_path)
    draft_executor = draft_executor or GmailDraftExecutor(config_path=config_path)
    notifier = notifier or TelegramNotifier()

    profile = drive_manager.load_master_resume_profile()
    master_profile = profile.get("text")
    placeholders = profile.get("placeholders")
    if not isinstance(master_profile, str) or not master_profile.strip():
        raise ValueError("The master resume profile is empty or invalid.")
    if not isinstance(placeholders, list) or not placeholders:
        raise ValueError("The master resume has no replaceable sections.")

    for job in batch:
        message_id = job.get("id") if isinstance(job, Mapping) else None
        title = _job_title(job) if isinstance(job, Mapping) else "Unknown job"
        stage = "analysis"
        draft = None
        try:
            if not isinstance(message_id, str) or not message_id:
                raise ValueError("Collected job is missing its Gmail message ID.")

            analysis = analyzer.analyze_job(job, master_profile)
            if not analysis.get("eligible_for_draft"):
                collector.mark_processed(message_id)
                report["skipped"].append(
                    {"job_id": message_id, "title": title, "reason": "below_match_threshold"}
                )
                continue

            recipient = job.get("application_email") or job.get("recipient")
            if not recipient:
                collector.mark_processed(message_id)
                report["skipped"].append(
                    {"job_id": message_id, "title": title, "reason": "missing_application_recipient"}
                )
                continue

            stage = "resume_tailoring"
            tailored_sections = analyzer.generate_tailored_sections(
                job, master_profile, analysis, placeholders
            )
            cover_letter = analyzer.generate_cover_letter(job, master_profile, analysis)

            stage = "resume_document"
            tailored_resume = drive_manager.create_tailored_resume(title, tailored_sections)

            stage = "gmail_draft"
            draft = draft_executor.create_draft(job, cover_letter, tailored_resume)
            report["drafts_created"] += 1

            # A created draft is a completed application artifact. Persist its source ID
            # before notification so a Telegram outage does not create duplicate drafts.
            stage = "processed_id_persistence"
            collector.mark_processed(message_id)

            stage = "telegram_notification"
            try:
                notifier.send_notification(job, analysis, draft)
                report["notifications_sent"] += 1
            except Exception as exc:
                report["errors"].append(
                    _error_record(message_id, title, stage, exc, draft=draft)
                )
        except Exception as exc:
            report["errors"].append(
                _error_record(message_id, title, stage, exc, draft=draft)
            )

    return report


def _job_title(job: Mapping[str, Any]) -> str:
    title = job.get("job_title") or job.get("title") or job.get("subject")
    return title.strip() if isinstance(title, str) and title.strip() else "Untitled job"


def _error_record(
    message_id: Any,
    title: str,
    stage: str,
    error: Exception,
    *,
    draft: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    record = {
        "job_id": message_id,
        "title": title,
        "stage": stage,
        "error": f"{type(error).__name__}: {error}",
    }
    if draft and draft.get("url"):
        record["draft_url"] = draft["url"]
    return record


def main() -> int:
    report = run_pipeline()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())

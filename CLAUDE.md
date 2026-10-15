# 🤖 AI Job Hunter

AI Job Hunter prepares job applications through a Python pipeline. `main.py` connects Gmail ingestion, Google Gemini analysis and resume tailoring, Google Docs/PDF generation, Gmail draft creation, and Telegram notifications. It creates drafts for human review and never sends application emails.

The system operates on a **Human-in-the-Loop** model: the agent automates all tedious preparation tasks while leaving final review and email dispatch to you.

## 📐 System Architecture

`main.py` orchestrates these steps:

1. `GmailJobCollector` fetches unseen messages from configured Gmail labels.
2. `GoogleDriveManager` reads factual candidate information from the master profile Google Doc and discovers `{{PLACEHOLDER}}` sections in the separate resume template.
3. `GeminiJobAnalyzer` scores each job against the profile and, for eligible jobs, generates tailored resume sections and a cover letter.
4. `GoogleDriveManager` copies the template, replaces the requested sections, and exports a PDF.
5. `GmailDraftExecutor` creates a draft with the cover letter and PDF attachment.
6. `TelegramNotifier` sends the job summary and Gmail draft link.

## ⚙️ Dynamic Configuration (`config.yaml`)

The system reads processing settings from `config.yaml`:

- **Gmail settings:** target labels, maximum message age, and local `processed_ids.json` path. Durable processing state is stored in `ai-job-hunter-processing-state.json` in the configured Google Drive output folder; local IDs are acknowledged after a job is skipped or a draft is created.
- **AI policy:** model, response language, and minimum score (`min_match_score_to_draft`).
- **Google Docs:** factual master profile document ID, separate resume template document ID, and output folder ID.
- **Run limit:** `limits.max_jobs_per_run` caps jobs attempted in one run.
- `filters.keywords` and `filters.blacklisted_keywords` are present in the configuration but are not currently applied by `GmailJobCollector` or `main.py`.
- `main.py` validates configuration, required run-mode secrets, and Google OAuth scopes before scanning Gmail. Dry-run requires Gemini credentials but not Telegram credentials. Keep configuration/preflight errors actionable and never include secret values or full job/profile content in reports.

## 🛠️ Platform Responsibilities

1. **Windows — Development and debugging**
   - IDE: IntelliJ IDEA Community Edition with the Python plugin.
   - Purpose: writing code, running `python main.py`, local module testing, virtual environment (`venv`) management, and debugging.
   - Local files excluded from Git via `.gitignore`: `credentials.json`, `token.json`, `processed_ids.json`, and `.env`.
2. **Cloud runner — GitHub Actions**
   - Runs `main.py` on a scheduled cron without requiring a local machine to stay powered on.
   - Sensitive API tokens and credentials are stored in GitHub Repository Secrets; `token.json` is generated at runtime.
3. **Android — Mobile control center**
   - **Telegram Bot:** sends push notifications with match scores and quick-action links.
   - **Gmail app:** lets you review the draft email and tailored PDF resume before sending.

## Pipeline Behavior

- Candidate facts are read from `google_docs.master_profile_doc_id`. The generated resume is copied from the separate `google_docs.resume_template_doc_id`, which must contain one or more double-brace placeholders such as `{{SUMMARY}}` or `{{EXPERIENCE}}`. The IDs must be different; profile-only content is never copied into the output document.
- A job is eligible only when its match score meets `ai_policy.min_match_score_to_draft`.
- A Gmail draft requires an explicit `application_email` or `recipient` value in the job mapping. The job alert's `sender` is never treated as the application address. Jobs without a recipient are reported as skipped.
- Jobs that fail before draft creation are not marked processed and can be retried. After a draft is created, the message ID is persisted before Telegram notification to avoid creating duplicate drafts if Telegram is unavailable; the run report includes the draft URL when notification fails.
- `main.py` prints a JSON run report and exits with a non-zero status if any job or notification failed.
- `python main.py --dry-run` reads Gmail and the configured profile/template Docs, then performs Gemini analysis/content generation. It does not initialize draft or Telegram clients, create Google Docs or Gmail drafts, send Telegram notifications, or update processed IDs. The `would_create_drafts` report omits recipient addresses. This mode needs Google OAuth and Gemini credentials, but not Telegram secrets.

## 🔑 Required Credentials and Token Acquisition

1. **Google Docs profile, resume template, and output folder IDs (`config.yaml`)**
   - Set `google_docs.master_profile_doc_id` to the Google Doc containing factual skills, career history, achievements, and baseline summary.
   - Set `google_docs.resume_template_doc_id` to a different Google Doc containing the final resume layout and double-brace placeholders.
   - Set `google_docs.output_folder_id` to the destination folder. The older `master_resume_doc_id` setting must be migrated: retain its document as the profile source and provide a separate output template ID.
   - Open the export folder in Google Drive and copy its ID from the URL: `/drive/folders/YOUR_FOLDER_ID`. Set `google_docs.output_folder_id` in `config.yaml`.
2. **Google OAuth credentials (`credentials.json` and `token.json`)**
   - In Google Cloud Console, enable **Gmail API**, **Google Drive API**, and **Google Docs API**.
   - Create an **OAuth 2.0 Client ID** for a Desktop Application.
   - Download the JSON file, rename it to `credentials.json`, and place it in the project root.
   - On first Google API use, authorize the requested Gmail read-only, Gmail compose, Drive, and Docs scopes in the browser. Existing tokens without any required scope trigger re-authorization.
   - After re-authorization, update the GitHub `GOOGLE_TOKEN_JSON` secret with the new `token.json` content.
3. **Telegram bot token and chat ID**
   - Create a bot via [@BotFather](https://t.me/BotFather) to get `TELEGRAM_BOT_TOKEN`.
   - Send a message to your bot, then open `https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates` to find your numerical `TELEGRAM_CHAT_ID`.

## 🔑 GitHub Secrets Configuration

Configure these secrets under **Settings → Secrets and variables → Actions** in your GitHub repository:

| Secret name | Description | Example value |
|---|---|---|
| `GEMINI_API_KEY` | Google Gemini API key | `your-gemini-api-key` |
| `TELEGRAM_BOT_TOKEN` | Telegram bot token from @BotFather | `123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ` |
| `TELEGRAM_CHAT_ID` | Your numerical chat ID | `987654321` |
| `GOOGLE_TOKEN_JSON` | Full content of your local `token.json` file | `{"token":"...","refresh_token":"..."}` |

## 🚀 GitHub Actions Workflow (`.github/workflows/run_agent.yml`)

- Runs daily at 08:00 UTC and can be started manually with `workflow_dispatch`.
- Uses Python 3.11, installs dependencies from `requirements.txt`, and runs `main.py`.
- Requires the `GEMINI_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, and `GOOGLE_TOKEN_JSON` repository secrets.
- Writes the Google token from the environment without echoing its contents to the log.
- Stores the durable processing manifest in Google Drive, independent of the GitHub Actions cache and runner lifetime.
- Tracks jobs through `processing`, `resume_pending`, `resume_created`, `draft_pending`, `draft_created`, and `skipped`. Drive artifacts and pending Gmail drafts use deterministic idempotency keys so an interrupted run reuses existing artifacts.
- Stores only message/document/draft IDs, status, timestamps, and notification status; do not add job content or recipient details to the manifest.
- Serializes workflow runs across refs because all runs share the same Drive manifest.

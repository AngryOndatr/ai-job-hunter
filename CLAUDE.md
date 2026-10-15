# 🤖 AI Job Hunter

AI Job Hunter prepares job applications through a Python pipeline. `main.py` connects Gmail ingestion, Google Gemini analysis and resume tailoring, Google Docs/PDF generation, Gmail draft creation, and Telegram notifications. It creates drafts for human review and never sends application emails.

The system operates on a **Human-in-the-Loop** model: the agent automates all tedious preparation tasks while leaving final review and email dispatch to you.

## 📐 System Architecture

`main.py` orchestrates these steps:

1. `GmailJobCollector` fetches unseen messages from configured Gmail labels.
2. `GoogleDriveManager` reads the master Google Doc text and discovers its `{{PLACEHOLDER}}` sections.
3. `GeminiJobAnalyzer` scores each job against the profile and, for eligible jobs, generates tailored resume sections and a cover letter.
4. `GoogleDriveManager` copies the template, replaces the requested sections, and exports a PDF.
5. `GmailDraftExecutor` creates a draft with the cover letter and PDF attachment.
6. `TelegramNotifier` sends the job summary and Gmail draft link.

## ⚙️ Dynamic Configuration (`config.yaml`)

The system reads processing settings from `config.yaml`:

- **Gmail settings:** target labels, maximum message age, and `processed_ids.json` path. During orchestration, IDs are acknowledged after a job is skipped or a draft is created; failures before draft creation remain eligible for retry.
- **AI policy:** model, response language, and minimum score (`min_match_score_to_draft`).
- **Google Docs:** master resume document ID and output folder ID.
- **Run limit:** `limits.max_jobs_per_run` caps jobs attempted in one run.
- `filters.keywords` and `filters.blacklisted_keywords` are present in the configuration but are not currently applied by `GmailJobCollector` or `main.py`.

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

- The master profile is read from the configured Google Doc. The document must contain one or more double-brace placeholders such as `{{SUMMARY}}` or `{{EXPERIENCE}}` for sections to tailor.
- A job is eligible only when its match score meets `ai_policy.min_match_score_to_draft`.
- A Gmail draft requires an explicit `application_email` or `recipient` value in the job mapping. The job alert's `sender` is never treated as the application address. Jobs without a recipient are reported as skipped.
- Jobs that fail before draft creation are not marked processed and can be retried. After a draft is created, the message ID is persisted before Telegram notification to avoid creating duplicate drafts if Telegram is unavailable; the run report includes the draft URL when notification fails.
- `main.py` prints a JSON run report and exits with a non-zero status if any job or notification failed.

## 🔑 Required Credentials and Token Acquisition

1. **Google Drive template ID and folder ID (`config.yaml`)**
   - Open your master resume in Google Docs and copy its ID from the URL: `/document/d/YOUR_TEMPLATE_ID/edit`. Set `google_docs.master_resume_doc_id` in `config.yaml`.
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
- Restores and saves `processed_ids.json` through the Actions cache. The cache is best-effort state: if it is absent or evicted, messages still within the configured age window may be processed again.
- Serializes runs on the same ref to avoid concurrent updates to the processed-ID cache.

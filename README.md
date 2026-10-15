# 🤖 AI Job Hunter

**AI Job Hunter** is an autonomous multi-agent pipeline built with Python to streamline and automate the job application process. The agent scans incoming job notifications in Gmail, evaluates role compatibility using Google Gemini `gemini-3.8-flash`, tailors key resume sections for Applicant Tracking Systems (ATS), dynamically generates updated PDF resumes via the Google Docs API, creates ready-to-send Gmail drafts, and dispatches real-time push alerts to Telegram.

The system adheres to a **Human-in-the-Loop** architecture: the agent automates all tedious preparation tasks while reserving final review and submission control for you.

---

## 📐 System Architecture

```text
┌──────────────┐     ┌─────────────────────┐     ┌──────────────────────┐
│  Gmail API   │ --> │ GmailJobCollector   │ --> │  JobAnalyzerAgent    │
│  (Incoming)  │     │ (Scan & Deduplicate)│     │  (LLM / Gemini API)  │
└──────────────┘     └─────────────────────┘     └──────────────────────┘
                                                            │
                                                            ▼
┌──────────────┐     ┌─────────────────────┐     ┌──────────────────────┐
│ Telegram Bot │ <-- │  Gmail Executor     │ <-- │ GoogleDriveManager   │
│(Notification)│     │  (Create Draft)     │     │ (Clone, Tailor, PDF) │
└──────────────┘     └─────────────────────┘     └──────────────────────┘
```
## System Architecture Overview

1. **Gmail Ingestion:** Scans targeted folders/labels and filters completed messages using a durable processing manifest in the configured Google Drive output folder.
2. **AI Job Analysis:** Google Gemini `gemini-3.8-flash` compares job requirements with the factual master profile and applies the configured match threshold.
3. **Document Generation:** Gemini tailors the resume template's `{{PLACEHOLDER}}` sections using profile evidence. The pipeline clones the separate template Google Doc, updates those sections, and exports a PDF.
4. **Gmail Execution:** Creates a draft email in Gmail containing the cover letter and attached PDF resume.
5. **Notification:** Sends an immediate digest alert with direct links via Telegram Bot.

---

## 🚀 Key Features

* **Targeted Ingestion & Deduplication:** Scans designated Gmail labels (`Glassdoor`, `LinkedIn`, `Michael Page`, `Stepstone.de`) and stores durable job statuses in a JSON manifest in Google Drive.
* **Flexible Configuration (`config.yaml`):** Manage Gmail labels, target keywords, blacklists, match thresholds, and language preferences (`en`/`de`/`uk`) without modifying code.
* **Intelligent ATS Analysis (LLM):** Evaluates job specs against your profile (Java / Spring Boot / Full-Stack), computes a `match_score`, and extracts missing keywords.
* **Dynamic Resume Tailoring (Google Docs):** Clones your Google Docs resume template, updates relevant sections via Google Docs API while preserving styling, and exports a PDF.
* **Cover Letter Generation:** Drafts personalized cover letters tailored to specific role requirements in your configured language.
* **Safe Delivery (Gmail Drafts):** Automatically attaches the tailored PDF resume and populates the cover letter in a Gmail draft.
* **Telegram Notifications:** Dispatches structured summary alerts with direct deep-links to Gmail drafts.

## 🔒 AI Input and Content Safety

Email content, job descriptions, profile text, and prior analysis are sent to Gemini as untrusted data, separate from trusted system instructions. Job-ad text may guide relevance but is never treated as evidence of candidate qualifications. Generated cover letters and resume sections receive a second, structured grounding review; the pipeline rejects the output if the review is malformed, identifies unsupported claims, or cannot provide exact evidence quotations found in the master profile. This review is an additional model-based safeguard and is not a guarantee of perfect semantic verification.
---

## 🛠️ Project Structure

```text
ai-job-hunter/
├── main.py                   # Main pipeline orchestrator
├── gmail_collector.py        # Email scanner and deduplication engine
├── ai_tailor.py              # LLM job analyzer & Cover Letter generator
├── drive_service.py          # Google Drive & Docs API manager (Document cloning & PDF export)
├── google_auth.py            # Shared Google OAuth scopes and token handling
├── gmail_executor.py         # Gmail draft creation engine
├── telegram_notifier.py      # Telegram bot notification interface
├── config.yaml               # Central configuration file.
├── credentials.json          # Google OAuth 2.0 Client credentials (Git-ignored)
├── token.json                # Persisted OAuth session token (Git-ignored)
├── processed_ids.json        # Local fast-path cache of processed email IDs (Git-ignored)
├── .env.example              # Environment variables template
├── requirements.txt          # Python project dependencies
├── README.md                 # Main project documentation
└── CLAUDE.md                 # Hybrid Cloud & Mobile architecture guide
```

---

## 📦 Setup & Installation

### 1. Repository Setup & Dependencies
```bash
git clone https://github.com/AngryOndatr/ai-job-hunter.git
cd ai-job-hunter

python -m venv venv
# On Windows:
venv\Scripts\activate
# On Linux/macOS:
source venv/bin/activate

pip install -r requirements.txt
```
### 2. Configure Parameters (config.yaml)
1. Update config.yaml with your criteria:
2. Specify target Gmail labels.
3. Provide the Google Docs master profile ID, separate resume template ID, and target Google Drive output folder ID.
4. Define technical keywords, blacklisted terms, and response language.

### 3. Google Workspace Credentials (credentials.json & token.json)
1. Navigate to the [Google Cloud Console](https://console.cloud.google.com/).
2. Enable the **Gmail API**, **Google Drive API** и **Google Docs API**.
3. Create an **OAuth 2.0 Client ID** (Тип приложения: *Desktop App* / *Рабочий стол*).
4. Download the JSON credential file, rename it to `credentials.json`, and place it in the root directory.
5. При первом использовании Google APIs пройдите авторизацию в браузере. Приложение запрашивает Gmail read-only, Gmail compose, Google Drive и Google Docs scopes. Если `token.json` не содержит все необходимые scopes, повторная авторизация запустится автоматически.
After re-authorization, update the GitHub secret `GOOGLE_TOKEN_JSON` with the new `token.json` content.

Configure two different Google Docs in `config.yaml`:
- `google_docs.master_profile_doc_id` points to a factual source document containing the candidate's skills, career history, achievements, and baseline summary. Gemini reads this document for evidence; it is never copied into the generated resume.
- `google_docs.resume_template_doc_id` points to the output layout. Put double-brace placeholders such as `{{SUMMARY}}`, `{{SKILLS}}`, or `{{EXPERIENCE}}` where generated sections should appear. `drive_service.py` copies this document, replaces its placeholders, and saves the tailored Google Doc and PDF in `google_docs.output_folder_id`.

The profile and template IDs must refer to different documents. To migrate from the previous single-document setup, keep the old `master_resume_doc_id` value as `master_profile_doc_id`, create or choose a separate Google Docs resume layout with placeholders, and set its ID as `resume_template_doc_id`. The sample config contains a `REPLACE_WITH_RESUME_TEMPLATE_DOC_ID` marker that must be replaced before running the pipeline.

`gmail_executor.py` creates a Gmail draft from the generated cover letter and PDF. Job data must include an explicit application address in `application_email` or `recipient`; the sender of a job alert is never treated as the employer's application address. The executor creates drafts only and does not send email.

`telegram_notifier.py` sends a plain-text notification with the role, company, match score, analysis summary, and Gmail draft link using `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` from the environment.

### 4. Gemini API Key (GEMINI_API_KEY)
1. Перейдите в [Google AI Studio](https://aistudio.google.com/).
2. Нажмите **Get API key** -> **Create API key**.
3. Скопируйте сгенерированный ключ и добавьте его:
    - Для локальной разработки: в файл `.env` как `GEMINI_API_KEY=AIzaSy...`
    - Для GitHub Actions: в секреты репозитория (`Settings -> Secrets and variables -> Actions`) с именем `GEMINI_API_KEY`.

### 5. Environment Variables Configuration
Copy `.env.example` to create your local `.env` file and populate it with your keys:
```bash
GEMINI_API_KEY=your_gemini_api_key_here
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here
TELEGRAM_CHAT_ID=your_telegram_chat_id_here
```

---

## 🏃 Running the Pipeline

Execute the pipeline locally:
```bash
python main.py
```
*Note: On initial execution, a browser window will open requesting Google API authorization. Upon approval, `token.json` will be generated automatically.*

Before scanning Gmail, startup validates the required configuration fields and ranges, checks the secrets needed for the selected run mode, and verifies that Google OAuth credentials include the required Gmail, Drive, and Docs scopes. Preflight errors identify the setting to fix without printing secret values. A normal run requires Gemini and Telegram credentials; `--dry-run` requires Gemini credentials but does not require Telegram credentials.

To verify ingestion and AI analysis without creating Google Docs, Gmail drafts, Telegram notifications, or marking messages as processed, run:
```bash
python main.py --dry-run
```
The JSON report lists eligible applications under `would_create_drafts` without including recipient addresses. Dry runs read Gmail and the two configured Google Docs and call Gemini, so they require valid Google OAuth credentials and `GEMINI_API_KEY`; Telegram secrets are not required.

### Run automated tests

Run the unit test suite locally from the repository root:
```bash
python -m unittest discover -s tests -v
```
GitHub Actions runs the same command on pushes and pull requests using Python 3.11. The test workflow needs no Google, Gemini, or Telegram secrets.

The orchestrator processes up to `limits.max_jobs_per_run` messages per run. The durable `ai-job-hunter-processing-state.json` manifest in `google_docs.output_folder_id` tracks each Gmail message as `processing`, `resume_pending`, `resume_created`, `draft_pending`, `draft_created`, or `skipped`. It stores IDs, deterministic Drive/Gmail idempotency keys, timestamps, and notification status; it does not store job content or recipient addresses. Pending Drive artifacts and drafts are reconciled by their idempotency keys after an interrupted run. The local `processed_ids.json` remains a convenience cache only. Each run lists and downloads the manifest once, then reuploads the full JSON file at each state transition (several writes per handled job); Drive API usage and transfer size therefore grow with the manifest history. The manifest remains in the output folder until manually removed, so it should be periodically reviewed and pruned if the application is used long term.

### Scheduled GitHub Actions runs

`.github/workflows/run_agent.yml` runs daily at 08:00 UTC and supports manual runs from the repository's **Actions** tab. Configure the `GEMINI_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, and `GOOGLE_TOKEN_JSON` repository secrets first. Processing state is persisted to Google Drive and survives runner replacement and Actions cache eviction. Workflow runs are serialized across refs because they share one manifest. The manifest remains in the configured output folder until manually removed and grows by one compact record per handled Gmail message.

---

## 📝 License
MIT License

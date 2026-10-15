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

1. **Gmail Ingestion:** Scans targeted folders/labels for new job notification emails and filters out duplicates using `processed_ids.json`.
2. **AI Job Analysis:** Google Gemini `gemini-3.8-flash` compares job requirements with the profile read from your master resume and applies the configured match threshold.
3. **Document Generation:** Gemini tailors the template's `{{PLACEHOLDER}}` sections using profile evidence. The pipeline clones the master Google Doc, updates those sections, and exports a PDF.
4. **Gmail Execution:** Creates a draft email in Gmail containing the cover letter and attached PDF resume.
5. **Notification:** Sends an immediate digest alert with direct links via Telegram Bot.

---

## 🚀 Key Features

* **Targeted Ingestion & Deduplication:** Scans designated Gmail labels (`Glassdoor`, `LinkedIn`, `Michael Page`, `Stepstone.de`) by message age and keywords, maintaining processed IDs in `processed_ids.json`.
* **Flexible Configuration (`config.yaml`):** Manage Gmail labels, target keywords, blacklists, match thresholds, and language preferences (`en`/`de`/`uk`) without modifying code.
* **Intelligent ATS Analysis (LLM):** Evaluates job specs against your profile (Java / Spring Boot / Full-Stack), computes a `match_score`, and extracts missing keywords.
* **Dynamic Resume Tailoring (Google Docs):** Clones your Google Docs resume template, updates relevant sections via Google Docs API while preserving styling, and exports a PDF.
* **Cover Letter Generation:** Drafts personalized cover letters tailored to specific role requirements in your configured language.
* **Safe Delivery (Gmail Drafts):** Automatically attaches the tailored PDF resume and populates the cover letter in a Gmail draft.
* **Telegram Notifications:** Dispatches structured summary alerts with direct deep-links to Gmail drafts.
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
├── processed_ids.json        # Database of processed email IDs (Git-ignored)
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
3. Provide your Google Docs master resume template ID and target Google Drive output folder ID.
4. Define technical keywords, blacklisted terms, and response language.

### 3. Google Workspace Credentials (credentials.json & token.json)
1. Navigate to the [Google Cloud Console](https://console.cloud.google.com/).
2. Enable the **Gmail API**, **Google Drive API** и **Google Docs API**.
3. Create an **OAuth 2.0 Client ID** (Тип приложения: *Desktop App* / *Рабочий стол*).
4. Download the JSON credential file, rename it to `credentials.json`, and place it in the root directory.
5. При первом использовании Google APIs пройдите авторизацию в браузере. Приложение запрашивает Gmail read-only, Gmail compose, Google Drive и Google Docs scopes. Если `token.json` не содержит все необходимые scopes, повторная авторизация запустится автоматически.
After re-authorization, update the GitHub secret `GOOGLE_TOKEN_JSON` with the new `token.json` content.

The master resume template should contain double-brace placeholders for sections to replace, such as `{{SUMMARY}}` or `{{EXPERIENCE}}`. `drive_service.py` replaces these placeholders in a copy of the template and saves both the tailored Google Doc and exported PDF in the configured output folder.

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

The orchestrator processes up to `limits.max_jobs_per_run` messages per run. It only creates a draft when the job data contains an explicit `application_email` or `recipient`; job alerts without an application address are recorded as skipped. Errors before draft creation leave the Gmail message eligible for retry. If Telegram fails after a draft is created, the report includes the draft link and the message is not reprocessed into a duplicate draft.

### Scheduled GitHub Actions runs

`.github/workflows/run_agent.yml` runs daily at 08:00 UTC and supports manual runs from the repository's **Actions** tab. Configure the `GEMINI_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, and `GOOGLE_TOKEN_JSON` repository secrets first. The workflow restores and saves `processed_ids.json` through the Actions cache so scheduled runs can retain Gmail deduplication state; a cold or evicted cache can cause recent messages to be processed again.

---

## 📝 License
MIT License

# 🤖 AI Job Hunter

**AI Job Hunter** is a Python pipeline that scans job alerts in Gmail, evaluates role compatibility with Google Gemini, and prepares tailored application materials. For eligible jobs with an application address, it creates a Gmail draft with the cover letter and PDF resume. For eligible jobs without an application address, it saves the resume and cover letter as Google Docs and PDFs in a company-specific Google Drive folder. Telegram links you to the prepared materials; the pipeline never sends an application email.

The system adheres to a **Human-in-the-Loop** architecture: the agent automates all tedious preparation tasks while reserving final review and submission control for you.

---

## 📐 System Architecture

```text
Gmail → collect and deduplicate → Gemini analysis and tailoring → route by application address
    address available     → resume PDF + Gmail draft → Telegram draft link
    no address            → company Drive folder with resume/cover-letter Docs and PDFs → Telegram file links
```
## System Architecture Overview

1. **Gmail Ingestion:** Scans targeted folders/labels and filters completed messages using a durable processing manifest in the configured Google Drive output folder.
2. **AI Job Analysis:** Google Gemini compares job requirements with the factual master profile and applies the configured match threshold. The model is configured via `ai_policy.model` in `config.yaml` (currently `gemini-2.5-flash-lite`).
3. **Document Generation:** Gemini tailors the resume template's `{{PLACEHOLDER}}` sections using profile evidence and generates a cover letter.
4. **Application preparation:** With a recipient, creates a Gmail draft containing the cover letter and PDF resume. Without one, stores both documents and their PDFs under `Output Folder/<Company Name>`; missing or unsafe company names are handled safely.
5. **Notification:** Sends a Telegram alert with a Gmail draft link or links to the document-only PDFs, depending on the route.

---

## 🚀 Key Features

* **Targeted Ingestion & Deduplication:** Scans designated Gmail labels (`Glassdoor`, `LinkedIn`, `Michael Page`, `Stepstone.de`) and stores durable job statuses in a JSON manifest in Google Drive.
* **Flexible Configuration (`config.yaml`):** Manage Gmail labels, match thresholds, and language preferences (`en`/`de`/`uk`) without modifying code. Keyword and blacklist filters are defined in configuration but are not yet applied by the ingestion or matching logic.
* **LLM Job Analysis:** Evaluates job specs against your profile (Java / Spring Boot / Full-Stack), computes a `match_score`, and extracts missing keywords.
* **Dynamic Resume Tailoring (Google Docs):** Clones your Google Docs resume template, updates relevant sections via Google Docs API while preserving styling, and exports a PDF.
* **Cover Letter Generation:** Drafts personalized cover letters tailored to specific role requirements in your configured language.
* **Two application paths:** Creates Gmail drafts when an application address is available, or company-folder documents when it is not.
* **Telegram Notifications:** Links to the Gmail draft or to both PDFs in the company Drive folder.

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
5. При первом использовании Google APIs пройдите авторизацию в браузере. Приложение запрашивает Gmail read-only, Google Drive и Google Docs scopes; Gmail compose запрашивается только если в обрабатываемой пачке есть подходящая вакансия с адресом для заявки. Если `token.json` не содержит scopes для выбранного сценария, повторная авторизация запустится автоматически.
After re-authorization, update the GitHub secret `GOOGLE_TOKEN_JSON` with the new `token.json` content.

Configure two different Google Docs in `config.yaml`:
- `google_docs.master_profile_doc_id` points to a factual source document containing the candidate's skills, career history, achievements, and baseline summary. Gemini reads this document for evidence; it is never copied into the generated resume.
- `google_docs.resume_template_doc_id` points to the output layout. Put double-brace placeholders such as `{{SUMMARY}}`, `{{SKILLS}}`, or `{{EXPERIENCE}}` where generated sections should appear. `drive_service.py` copies this document, replaces its placeholders, and saves the tailored Google Doc and PDF in `google_docs.output_folder_id`.

The profile and template IDs must refer to different documents. To migrate from the previous single-document setup, keep the old `master_resume_doc_id` value as `master_profile_doc_id`, create or choose a separate Google Docs resume layout with placeholders, and set its ID as `resume_template_doc_id`. The sample config contains a `REPLACE_WITH_RESUME_TEMPLATE_DOC_ID` marker that must be replaced before running the pipeline.

`gmail_executor.py` creates a Gmail draft from the generated cover letter and PDF when job data includes an explicit application address in `application_email` or `recipient`; the sender of a job alert is never treated as the employer's application address. Without a recipient, the pipeline saves both documents and PDFs under a sanitized company folder and does not initialize the Gmail draft executor. Neither path sends application email.

`telegram_notifier.py` sends a plain-text notification using `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`. Draft notifications include the role, company, match score, analysis summary, and Gmail draft link. Document-only notifications include the role, company, and links to the resume and cover-letter PDFs.

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

Before processing, startup validates configuration and required secrets. Gmail read-only, Drive, and Docs scopes are needed for ingestion and document access; Gmail compose is required only when the batch contains a job with an application recipient. A normal run requires Gemini and Telegram credentials; `--dry-run` requires Gemini credentials but does not require Telegram or Gmail compose access.

To verify ingestion and AI analysis without creating Google Docs, Gmail drafts, Telegram notifications, or marking messages as processed, run:
```bash
python main.py --dry-run
```
The JSON report lists email-based applications under `would_create_drafts` and document-only applications under `would_create_documents`, without including recipient addresses. Dry runs read Gmail and the two configured Google Docs and call Gemini, so they require valid Google OAuth credentials and `GEMINI_API_KEY`; Telegram secrets and Gmail compose access are not required.

Eligible jobs without an application email are prepared without creating a Gmail draft. The tailored resume and cover letter are saved as Google Docs and PDFs under `Output Folder/<Company Name>`; unsafe company-name characters are replaced, and missing company names use `Unknown Company`. The run summary counts completed document-only applications separately from Gmail drafts.

### Run automated tests

Run the unit test suite locally from the repository root:
```bash
python -m unittest discover -s tests -v
```
GitHub Actions runs the same command on pushes and pull requests using Python 3.11. The test workflow needs no Google, Gemini, or Telegram secrets.

The orchestrator processes up to `limits.max_jobs_per_run` messages per run. The durable `ai-job-hunter-processing-state.json` manifest in `google_docs.output_folder_id` tracks each Gmail message as `processing`, `resume_pending`, `resume_created`, `draft_pending`, `draft_created`, `document_only_pending`, `document_only_created`, or `skipped`. It stores artifact IDs and links, deterministic Drive/Gmail idempotency keys, timestamps, and notification status; it does not store job content or recipient addresses. Pending Drive artifacts and drafts are reconciled by their idempotency keys after an interrupted run. Document-only applications become terminal only after the Telegram notification succeeds; a failed notification is retried from saved artifact links without regenerating documents. The local `processed_ids.json` remains a convenience cache only. Each run lists and downloads the manifest once, then reuploads the full JSON file at each state transition (several writes per handled job); Drive API usage and transfer size therefore grow with the manifest history. The manifest remains in the output folder until manually removed, so it should be periodically reviewed and pruned if the application is used long term.

### Scheduled GitHub Actions runs

`.github/workflows/run_agent.yml` is scheduled daily at 08:00 UTC, but the scheduled job is gated off unless the repository variable `ENABLE_SCHEDULED_RUNS` is exactly `true`. Keep it unset/false until the Phase 7.7 live pilot and recovery review are complete. Manual runs support `dry-run` (default) and a capped `pilot`; the manual job cap cannot exceed `limits.max_jobs_per_run` and should initially be set to one. Configure `GEMINI_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, and `GOOGLE_TOKEN_JSON` repository secrets before running. Processing state is persisted to Google Drive and survives runner replacement and Actions cache eviction. Workflow runs are serialized across refs because they share one manifest. The manifest remains in the configured output folder until manually removed and grows by one compact record per handled Gmail message. See [RUNBOOK.md](RUNBOOK.md) for the controlled verification sequence.

Each CLI run emits a JSON report with a run ID, timestamps, duration, aggregate counts, outcome, and per-job error stage. GitHub Actions writes a compact summary and fails the workflow when a job or notification error is recorded. See [RUNBOOK.md](RUNBOOK.md) for triage, retry, and draft recovery procedures; inspect Gmail Drafts before retrying after a failure that may have occurred after draft creation.

---

## 📝 License
MIT License

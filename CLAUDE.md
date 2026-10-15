# 🤖 AI Job Hunter

AI Job Hunter is an autonomous multi-agent Python system designed to automate the job search and application pipeline. The agent scans incoming job alert emails in specific Gmail folders (Glassdoor, LinkedIn, Michael Page, Stepstone.de), analyzes requirements using Google Gemini `gemini-3.8-flash`, matches them against your master resume, adapts key resume sections for ATS optimization, generates a PDF via Google Docs API, creates a draft email with the attachment in Gmail, and sends a notification to Telegram.

The system operates on a **Human-in-the-Loop** model: the agent automates all tedious preparation tasks while leaving final review and email dispatch to you.

## 📐 System Architecture

```text
┌──────────────┐     ┌─────────────────────┐     ┌──────────────────────┐
│  Gmail API   │ --> │ GmailJobCollector   │ --> │  JobAnalyzerAgent    │
│ (Target      │     │ (Scan Labels &      │     │  (Gemini API)       │
│  Labels)     │     │  Deduplicate)       │     │                      │
└──────────────┘     └─────────────────────┘     └──────────────────────┘
                                                            │
                                                            ▼
┌──────────────┐     ┌─────────────────────┐     ┌──────────────────────┐
│ Telegram Bot │ <-- │  Gmail Executor     │ <-- │ GoogleDriveManager   │
│(Notification)│     │  (Create Draft)     │     │ (Clone, Tailor, PDF) │
└──────────────┘     └─────────────────────┘     └──────────────────────┘
```

## ⚙️ Dynamic Configuration (`config.yaml`)

The system reads scan rules, keyword filters, and AI behavior policies from `config.yaml`:

- **Gmail target labels:** Glassdoor, LinkedIn, Michael Page, and Stepstone.de.
- **Keyword filter:** Java, Spring Boot, Full-Stack, Microservices, Angular, and TypeScript.
- **AI policy:** response language (`en`), minimum match score (`min_match_score_to_draft`), and blacklisted keywords.

## 🛠️ Platform Responsibilities

1. **Windows — Development and debugging**
   - IDE: IntelliJ IDEA Community Edition with the Python plugin.
   - Purpose: writing code, local module testing, virtual environment (`venv`) management, and debugging.
   - Local files excluded from Git via `.gitignore`: `credentials.json`, `token.json`, `processed_ids.json`, and `.env`.
2. **Cloud runner — GitHub Actions**
   - Runs `main.py` on a scheduled cron without requiring a local machine to stay powered on.
   - Sensitive API tokens and credentials are stored in GitHub Repository Secrets; `token.json` is generated at runtime.
3. **Android — Mobile control center**
   - **Telegram Bot:** sends push notifications with match scores and quick-action links.
   - **Gmail app:** lets you review the draft email and tailored PDF resume before sending.

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

```yaml
name: AI Job Hunter Cloud Runner

on:
  schedule:
    - cron: '0 8 * * *'
  workflow_dispatch:

jobs:
  run-pipeline:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout repository
        uses: actions/checkout@v3

      - name: Set up Python 3.10
        uses: actions/setup-python@v4
        with:
          python-version: '3.10'

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt

      - name: Inject Google Token Secret
        run: |
          echo '${{ secrets.GOOGLE_TOKEN_JSON }}' > token.json

      - name: Execute Main Pipeline
        env:
          GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
          TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
          TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}
        run: python main.py
```

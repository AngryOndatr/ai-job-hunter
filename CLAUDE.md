🤖 AI Job Hunter
AI Job Hunter is an autonomous multi-agent Python system designed to automate the job search and application pipeline. The agent scans incoming job alert emails in specific Gmail folders (Glassdoor, LinkedIn, Michael Page, Stepstone.de), analyzes requirements using Claude 3.5 Sonnet, matches them against your master resume, adapts key resume sections for ATS optimization, generates a PDF via Google Docs API, creates a draft email with the attachment in Gmail, and sends a notification to Telegram.

The system operates on a Human-in-the-Loop model: the agent automates all tedious preparation tasks while leaving final review and email dispatch to you.


📐 System Architecture
┌──────────────┐     ┌─────────────────────┐     ┌──────────────────────┐
│  Gmail API   │ --> │ GmailJobCollector   │ --> │  JobAnalyzerAgent    │
│ (Target      │     │ (Scan Labels &      │     │  (LLM / Claude API)  │
│  Labels)     │     │  Deduplicate)       │     │                      │
└──────────────┘     └─────────────────────┘     └──────────────────────┘

                                                            │

                                                            ▼

┌──────────────┐     ┌─────────────────────┐     ┌──────────────────────┐
│ Telegram Bot │ <-- │  Gmail Executor     │ <-- │ GoogleDriveManager   │
│(Notification)│     │  (Create Draft)     │     │ (Clone, Tailor, PDF) │
└──────────────┘     └─────────────────────┘     └──────────────────────┘


⚙️ Dynamic Configuration (config.yaml)
The system reads scan rules, keyword filters, and AI behavior policies from config.yaml:

Gmail Target Labels: Scans specified aggregator labels (Glassdoor, LinkedIn, Michael Page, Stepstone.de).
Keywords Filter: Primary filtering based on tech stack (Java, Spring Boot, Full-Stack, Microservices, Angular, TypeScript).
AI Policy: Output response language (en), cutoff threshold (min_match_score_to_draft), and blacklisted keywords.


🛠️ Platform Responsibilities
1. Windows (Development & Debugging Environment)
   IDE: IntelliJ IDEA Community Edition with the Python plugin.
   Purpose: Writing code, local module testing, virtual environment (venv) management, and debugging.
   Local Files (Excluded from Git via .gitignore): credentials.json, token.json, processed_ids.json, .env.
2. Cloud Runner (Cloud Execution)
   Platform: GitHub Actions.
   Purpose: Executing the main orchestrator script (main.py) on a scheduled cron basis without requiring a local machine to stay powered on.
   Security (Secrets): Sensitive API tokens and credentials are securely stored within GitHub Repository Secrets, and token.json is dynamically generated at runtime.
3. Android (Mobile Control Center)
   Interface 1 (Telegram Bot): Instant push notifications delivered straight to your Android device, complete with match scores and quick-action links.
   Interface 2 (Gmail App): Reviewing the pre-generated draft email containing your ATS-optimized PDF resume and cover letter before giving the final tap to Send.


🔑 Required Credentials & Token Acquisition Guide
1. Google Drive Template ID & Folder ID
   Google Docs Resume Template ID: Open your master resume in Google Docs. Copy the ID from the browser URL: /document/d/YOUR_TEMPLATE_ID/edit.
   Google Drive Target Folder ID: Open the target export folder in Google Drive. Copy the ID from the URL: /drive/folders/YOUR_FOLDER_ID.
2. Google OAuth Credentials (credentials.json & token.json)
   In Google Cloud Console, enable Gmail API, Google Drive API, and Google Docs API.
   Create an OAuth 2.0 Client ID for Desktop Application.
   Download the JSON, rename it to credentials.json, and place it in the project root.
   Run python main.py locally once to authenticate in the browser and auto-generate token.json.
3. Telegram Bot Token & Chat ID
   Create a new bot via @BotFather to get the TELEGRAM_BOT_TOKEN.
   Send a message to your bot, then open https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates to find your numerical TELEGRAM_CHAT_ID.
4. Anthropic API Key
   Generate an API key from the Anthropic Console dashboard and save it as ANTHROPIC_API_KEY.


🔑 GitHub Secrets Configuration
To allow the cloud pipeline to authenticate with Google APIs and notify you, configure the following secrets under your GitHub repository settings (Settings -> Secrets and variables -> Actions):

| Secret Name | Description | Example Value |
|-------------|-------------|---------------|
| ANTHROPIC_API_KEY | Anthropic Claude API Key | sk-ant-api03-... |
| TELEGRAM_BOT_TOKEN | Telegram Bot Token from @BotFather | 123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ |
| TELEGRAM_CHAT_ID | Your personal numerical chat ID | 987654321 |
| GOOGLE_TOKEN_JSON | Full content of your local token.json file | {"token": "...", "refresh_token": "...", ...} |



🚀 GitHub Actions Workflow (.github/workflows/run_agent.yml)
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

          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}

          TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}

          TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}

        run: |

          python main.py

# 🗺️ AI Job Hunter: Project Implementation Plan

This document outlines the step-by-step roadmap for implementing the **AI Job Hunter** project. Each phase corresponds to a specific GitHub Issue/Task.

---

## 📌 Phase 1: Environment Setup & Core Documentation (Completed)
- [x] Define hybrid architecture (Windows dev + GitHub Actions cloud runner).
- [x] Create and clean project documentation (`README.md`, `CLAUDE.md`).
- [x] Define Gmail target labels (`Glassdoor`, `LinkedIn`, `Michael Page`, `Stepstone.de`) and platform responsibilities.

## ⚙️ Phase 2: Configuration & Core Data Structures
- [ ] **Task #1:** Create `config.yaml` for dynamic configuration (labels, keywords, match thresholds, language settings).
- [ ] **Task #2:** Create `.env.example` template for environment secrets (`GEMINI_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`).
- [ ] **Task #3:** Set up `requirements.txt` with essential dependencies (`google-api-python-client`, `google-auth-oauthlib`, `google-genai`, `python-dotenv`, `requests`, `pyyaml`).

## 📥 Phase 3: Ingestion Module (`gmail_collector.py`) (Completed)
- [x] **Task #4:** Implement Gmail API authentication and service initialization (`credentials.json` / `token.json`).
- [x] **Task #5:** Develop `GmailJobCollector` to scan targeted labels by message age (`max_email_age_days`) and keywords.
- [x] **Task #6:** Implement deduplication logic via `processed_ids.json` to prevent reprocessing the same job alert.

## 🤖 Phase 4: AI Analysis & Tailoring Module (`ai_tailor.py` & `drive_service.py`)
- [x] **Task #7:** Integrate Google Gemini `gemini-3.8-flash` to analyze job descriptions against the user's master profile (Java, Spring Boot, Full-Stack), using `GEMINI_API_KEY` and the configured language and match threshold.
- [x] **Task #8:** Implement Google Drive & Docs API manager to clone the master resume template, inject tailored content, and export as PDF.
- [x] **Task #9:** Generate dynamic, context-aware Cover Letters in the configured language.

## 📤 Phase 5: Executor & Notification Module (`gmail_executor.py` & `telegram_notifier.py`)
- [x] **Task #10:** Implement Gmail draft creation, attaching the tailored PDF resume and inserting the generated cover letter.
- [x] **Task #11:** Build the Telegram notification sender to dispatch instant success/summary alerts with deep links.

## 🚀 Phase 6: Orchestration & Cloud Deployment (`main.py` & CI/CD)
- [x] **Task #12:** Implement `main.py` pipeline orchestrator connecting all modules.
- [x] **Task #13:** Configure GitHub Actions workflow (`.github/workflows/run_agent.yml`) with automated cron triggers and secret injection.
- [ ] **Task #14:** End-to-end dry run and verification in the hybrid environment (local dry-run mode implemented; live verification pending credentials/API access).

## 🛡️ Phase 7: Production Readiness

Prepare the pipeline for reliable, secure, and observable operation before enabling unattended scheduled runs. Keep human review as the final step: the system may create application drafts but must never send them.

- [ ] **Phase 7.1 (#22):** Add automated CI quality gates for pull requests.
  - CI workflow and local test instructions are implemented; first GitHub Actions run is pending push/PR.
  - Run the unit test suite on the supported Python version for pushes and pull requests.
  - Fail the workflow on test errors and document the local verification command.
- [ ] **Phase 7.2 (#21):** Make dry-run execution independent of write-only integrations.
  - Run ingestion and analysis without requiring Telegram credentials or initializing draft/notification clients.
  - Keep dry-run output useful while excluding unnecessary personal data and preserving processed-message state.
- [ ] **Phase 7.3 (#20):** Replace best-effort cached processing state with durable, duplicate-safe processing.
  - Preserve processing state across GitHub runner/cache eviction and deploys.
  - Define recovery behavior for failures between document creation, draft creation, and state persistence; retries must not silently create duplicate application drafts.
- [ ] **Phase 7.4 (#19):** Validate configuration and runtime secrets before processing.
  - Validate required fields, types, ranges, OAuth scopes, and secrets with actionable errors before scanning messages.
  - Ensure logs and failure reports never expose credentials or full job/resume content.
- [ ] **Phase 7.5 (#18):** Harden AI input handling and generated application content.
  - Treat email content as untrusted input, constrain prompt-injection influence, and require resume claims to be supported by the master profile.
  - Add tests for malicious instructions, malformed model output, and unsupported claims.
- [ ] **Phase 7.6 (#17):** Add production diagnostics and an operator runbook.
  - Produce actionable per-run and per-job status, document retry/incident procedures, and make scheduled-run failures visible.
  - Record enough information to troubleshoot without logging sensitive content.
- [ ] **Phase 7.7 (#16):** Complete controlled live verification and pilot.
  - Verify dry-run against the configured Google/Gemini accounts, then run a small capped live pilot that creates drafts only.
  - Confirm generated documents, Gmail drafts, processed-state recovery, Telegram alerts, and that no email is sent; record results and rollback steps.

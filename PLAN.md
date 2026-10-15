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
- [ ] **Task #7:** Integrate Google Gemini `gemini-3.8-flash` to analyze job descriptions against the user's master profile (Java, Spring Boot, Full-Stack), using `GEMINI_API_KEY` and the configured language and match threshold.
- [ ] **Task #8:** Implement Google Drive & Docs API manager to clone the master resume template, inject tailored content, and export as PDF.
- [ ] **Task #9:** Generate dynamic, context-aware Cover Letters in the configured language.

## 📤 Phase 5: Executor & Notification Module (`gmail_executor.py` & `telegram_notifier.py`)
- [ ] **Task #10:** Implement Gmail draft creation, attaching the tailored PDF resume and inserting the generated cover letter.
- [ ] **Task #11:** Build the Telegram notification sender to dispatch instant success/summary alerts with deep links.

## 🚀 Phase 6: Orchestration & Cloud Deployment (`main.py` & CI/CD)
- [ ] **Task #12:** Implement `main.py` pipeline orchestrator connecting all modules.
- [ ] **Task #13:** Configure GitHub Actions workflow (`.github/workflows/run_agent.yml`) with automated cron triggers and secret injection.
- [ ] **Task #14:** End-to-end dry run and verification in the hybrid environment.

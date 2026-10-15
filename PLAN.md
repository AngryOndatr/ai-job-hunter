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
  - Dry-run skips draft/Telegram client initialization, leaves all processed IDs unchanged, and omits recipient addresses; automated coverage added.
  - Run ingestion and analysis without requiring Telegram credentials or initializing draft/notification clients.
  - Keep dry-run output useful while excluding unnecessary personal data and preserving processed-message state.
- [x] **Phase 7.3 (#20):** Replace best-effort cached processing state with durable, duplicate-safe processing.
  - Preserve processing state across GitHub runner/cache eviction and deploys.
  - Store a recoverable state machine in a Google Drive JSON manifest and reconcile generated documents and Gmail drafts with deterministic idempotency keys.
  - Document retention and Google Drive API usage; serialize scheduled/manual workflow runs across refs.
  - Define recovery behavior for failures between document creation, draft creation, and state persistence; retries must not silently create duplicate application drafts.
- [x] **Phase 7.4 (#19):** Validate configuration and runtime secrets before processing.
  - Validate required fields, types, ranges, OAuth scopes, and run-mode secrets before scanning messages.
  - Keep preflight and per-job error reporting actionable without exposing secret values or full job/resume content; cover these paths with automated tests.
- [x] **Phase 7.5 (#18):** Harden AI input handling and generated application content.
  - Pass trusted directives as Gemini system instructions and serialize emails, job descriptions, analysis, and profile text as untrusted source data.
  - Fail closed when a structured grounding review is malformed, identifies unsupported claims, or lacks exact generated-claim and master-profile evidence quotations; cover these cases with automated tests.
- [x] **Phase 7.6 (#17):** Add production diagnostics and an operator runbook.
  - Add run IDs, UTC timestamps, duration, overall status, aggregate counts, and stage-level error records to CLI reports; redact unexpected startup details.
  - Write a compact GitHub Actions step summary while retaining non-zero workflow exits for preflight and job failures.
  - Document failure triage, retries, draft recovery, and safe verification in `RUNBOOK.md` without logging credentials, message bodies, or profile content.
- [ ] **Phase 7.7 (#16):** Complete controlled live verification and pilot.
  - Manual workflow modes, one-job pilot cap, default-off scheduled-run gate, and a safe pilot record template are implemented; real-account verification is pending configured credentials and resume-template ID.
  - Verify dry-run against the configured Google/Gemini accounts, then run a small capped live pilot that creates documents and drafts only.
  - Confirm generated documents, Gmail drafts, processed-state recovery, Telegram alerts, and that no email is sent; record results and rollback steps before enabling scheduled execution.
- [ ] **Phase 7.8 (#23):** Separate factual profile source from resume output template.
  - Code, configuration schema, tests, and migration docs are implemented; configure the separate template ID before live use.
  - Read candidate facts from a dedicated master profile document and use a separate Google Doc as the output layout with replaceable placeholders.
  - Complete and verify this migration before the Phase 7.7 live pilot.
- [ ] **Phase 7.9 (#24, low priority):** Configure Gemini prompts at runtime.
  - Store editable analysis, resume-tailoring, and cover-letter instructions in Google Docs loaded at the start of each run.
  - Keep output schemas and profile-grounding safeguards enforced by code, and record prompt revisions for traceability and rollback.

## 🧰 Phase 8: Engineering Quality & Portfolio Readiness

Polish the repository so its claims, verification evidence, and operational behavior are clear and credible to engineers reviewing the project. Complete the production-readiness safeguards in Phase 7 before calling the application production-ready; Phase 8 improves the engineering quality and presentation of the repository.

- [ ] **Phase 8.1 (#25):** Reconcile documentation and implementation status.
  - Describe the current architecture accurately as a modular single-process pipeline unless the system is actually split into independently acting agents.
  - Scope ATS and other capability claims to behavior the code demonstrates; keep model/provider details consistent with configuration.
  - Audit phase and task checkboxes against merged code, CI results, and pending account-specific/live verification; distinguish implemented work from verified operation.
  - Acceptance: README, `CLAUDE.md`, and `PLAN.md` contain no contradictory architecture, capability, or completion claims.
- [ ] **Phase 8.2 (#26):** Add automated code-quality checks to CI.
  - Adopt and configure a Python formatter and linter, then run them alongside unit tests on pushes and pull requests.
  - Document the same commands for local development and keep CI failures actionable.
  - Acceptance: CI rejects formatting or lint violations and the existing codebase passes the configured checks.
- [ ] **Phase 8.3 (#27):** Add integration and recovery verification beyond isolated mocks.
  - Add deterministic API-boundary/contract tests for the Gmail, Drive, and Docs requests and for recovery after interruption at each persisted side-effect boundary.
  - Keep ordinary CI independent of personal Google credentials; define an explicitly gated verification path for tests requiring real Google services.
  - Acceptance: automated checks cover state reload, ambiguous API outcomes, duplicate artifact reconciliation, and state-write failures; live checks are clearly identified separately.
- [ ] **Phase 8.4 (#28):** Harden durable-state integrity and long-term growth.
  - Evaluate whole-manifest rewrites, concurrent writers, Drive revision conflicts, and the cost of retaining every processed message indefinitely.
  - Implement a bounded and concurrency-safe persistence/retention strategy with versioned migration behavior and recovery for malformed or incompatible state.
  - Acceptance: concurrent updates cannot silently overwrite one another, retention behavior is documented, and recovery/migration behavior has automated coverage.
- [ ] **Phase 8.5 (#29):** Make the repository license declaration complete.
  - Add the license text matching the MIT declaration in `README.md`, including the appropriate copyright notice.
  - Acceptance: repository license metadata and README agree, and the license file is present at the repository root.
- [ ] **Phase 8.6 (#30):** Establish clear project-level contribution and verification guidance.
  - Document supported Python version, setup, test and quality-check commands, configuration expectations, and how contributors can run changes without production credentials.
  - Link to the Phase 7.6 operator runbook and Phase 7.7 live-pilot evidence rather than duplicating their operational procedures here.
  - Acceptance: a new contributor can install dependencies, run the full local checks, and understand which behaviors still require controlled live verification.

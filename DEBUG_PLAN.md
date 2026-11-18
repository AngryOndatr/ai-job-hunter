# Debug Plan — AI Job Hunter Pipeline

**Date:** 2026-11-17
**Branch:** dev
**Goal:** локально, модуль за модулем, проверить и при необходимости починить четыре
этапа конвейера: (1) распознавание вакансий в письмах, (2) сбор информации о
вакансии, (3) модификация изменяемых частей резюме, (4) компоновка и сохранение
резюме + cover letter в папку компании.

## Environment & inputs

- Real `GEMINI_API_KEY` and Google OAuth (`credentials.json`, `token.json`) are
  available locally → live smoke tests are allowed after isolated unit checks.
- Sample emails will be provided by the user when Stage 1 begins (chat or file).
- Use project `venv`; run everything from the repo root.
- Existing test suite is the baseline: `pytest tests/ -v`.
- Secrets must never appear in logs, reports, or test output (see `CLAUDE.md`).

## Stage 1 — Job recognition in emails

**Module:** `gmail_collector.py` → `GmailJobCollector`

- [x] Verify label discovery against `gmail.target_labels` (`label_map` lookup,
      warning when a label is missing).
- [x] Verify date cutoff `after:{int(cutoff.timestamp())}` from
      `gmail.max_email_age_days`.
- [x] Verify dedup via `processed_ids` + `discovered_ids`, and
      `defer_processed=True` path used by `main.py`.
- [x] Verify `_parse_message` extracts `id, threadId, source, subject, sender,
      date, body`.
- [x] Verify `_extract_body` walks `multipart/mixed` and nested `parts` for
      `text/plain`, and handles body without `parts`.
- [x] Unit tests: extended `tests/test_gmail_collector.py` with digest-splitting
      tests (3 new tests, all passing).
- [x] Implemented `_split_digest()` in `gmail_collector.py`: LinkedIn-style
      digests are split into one record per job with extracted `job_title`,
      `company`, `location`, `job_url`, `job_id`, and synthetic ID
      `<message_id>:<job_id>`.
- [x] Verified on the real sample email (`Zenjob's Full-Stack Engineer` digest):
      3 jobs extracted with correct titles, companies, locations, URLs, IDs.
- [ ] Live smoke: `python gmail_collector.py` against real Gmail (deferred —
      modifies `processed_ids.json`; requires explicit user confirmation).

**Done when:** collector returns correct parsed records for the sample emails,
and the existing/new unit tests pass. ✅ (live smoke deferred)

## Stage 2 — Collecting job information

**Module:** `ai_tailor.py` → `GeminiJobAnalyzer.analyze_job`

- [x] Verify `__init__` validates `ai_policy.model`, `language`,
      `min_match_score_to_draft`, and requires `GEMINI_API_KEY` when no client
      is injected.
- [x] Verify `_normalize_job` accepts both a raw description string and a
      collector mapping with `subject`, `sender`, `source`, `body`.
- [x] Verified digest-split records normalize correctly: `company` → `employer`,
      job block → `description`.
- [x] Verify `_build_prompt` produces JSON with `task`, `language`, `job_data`,
      `master_profile`.
- [x] Verify output schema: `match_score` (int 0–100), `matching_skills`,
      `missing_keywords`, `summary`, `eligible_for_draft` based on threshold.
- [x] Verify failure paths raise `GeminiAnalysisError`: empty response, invalid
      JSON, score out of range, non-int score, empty summary, non-list skills.
- [x] Unit tests: extended `tests/test_ai_tailor.py` with a digest-split record
      test (17 tests passing).
- [ ] Live smoke: one `analyze_job()` call against a real sample email + the
      master profile text; inspect the returned analysis.
      (blocked transiently by sandbox classifier; retry)

**Done when:** analysis is returned with all required fields and the
eligibility flag matches the configured threshold.

## Stage 3 — Modifying mutable parts of the resume

**Modules:** `ai_tailor.py` → `generate_tailored_sections` / `_verify_grounding`
and `drive_service.py` → `GoogleDriveManager.create_tailored_resume`

- [ ] Verify `generate_tailored_sections` prompt includes `requested_placeholders`,
      `job_data`, `job_analysis`, `master_profile`.
- [ ] Verify response validation: every requested placeholder present exactly
      once, no unrequested placeholders, no empty content, no duplicates.
- [ ] Verify `_verify_grounding` fails closed on unsupported claims, missing
      quotes, or quotes not present verbatim in the master profile.
- [ ] Verify `create_tailored_resume`:
  - copies the template into `output_folder_id` with correct `appProperties`,
  - issues `replaceAllText` for each `{{PLACEHOLDER}}` (matchCase),
  - checks `occurrencesChanged > 0`,
  - exports a PDF starting with `%PDF`,
  - reuses prior artifacts via `_find_idempotent_file` on re-run.
- [ ] Unit tests: extend `tests/test_ai_tailor.py` and
      `tests/test_drive_service.py` with mocks for the Docs/Drive services.
- [ ] Live smoke: run once against the real Drive (sandbox company or trash
      after); verify the document text contains replacements and the PDF is
      valid; re-run and verify no duplicates appear.

**Done when:** every template placeholder is replaced with tailored content,
grounding passes, and a valid PDF is exported idempotently.

## Stage 4 — Composing and saving resume + cover letter per company folder

**Module:** `drive_service.py` → `create_document_only_application`,
`get_or_create_company_folder`, `_create_cover_letter`

- [ ] Verify `_company_folder_name` sanitizes `\/:*?"<>|` and control chars,
      strips trailing dots/spaces, truncates to 100 chars, and falls back to
      `Unknown Company` when the job has no company/employer.
- [ ] Verify `get_or_create_company_folder` prefers the idempotency key
      (`aiJobHunterCompanyKey`) and falls back to name match; raises on
      multiple matches.
- [ ] Verify `_create_cover_letter` creates a Docs file with `insertText` at
      index 1, exports PDF, and is idempotent via
      `aiJobHunterKey` / `aiJobHunterArtifact`.
- [ ] Verify `create_document_only_application` returns `{folder, resume,
      cover_letter, idempotency_keys}` with all four artifacts under the
      company folder.
- [ ] Unit tests: extend `tests/test_drive_service.py` with mocks.
- [ ] Live smoke: run with a sample job + tailored sections + cover letter;
      verify `Output Folder/<Company Name>/` contains resume Doc/PDF and
      cover-letter Doc/PDF; re-run and verify no duplicates.

**Done when:** the four artifacts appear under the correct company folder and
re-runs reuse them.

## Orchestration sanity check

- [ ] After all four stages pass, run `python main.py --dry-run` to confirm
      ingestion + analysis + tailoring without creating documents/drafts.
- [ ] Confirm existing `tests/test_main.py` still passes.

## Cross-cutting checks

- [ ] No secret values, job content, or profile content appear in logs,
      reports, or test output.
- [ ] Grounding review is documented as model-based, not a semantic guarantee
      (per `CLAUDE.md`).
- [ ] `processed_ids.json` and the Drive processing manifest are updated only
      on terminal outcomes; failures leave jobs retryable.
- [ ] Document-only jobs become terminal only after Telegram notification
      succeeds.

## Execution order

1. Confirm environment, run `pytest tests/ -v` as baseline.
2. Stage 1 → Stage 2 → Stage 3 → Stage 4.
3. Orchestration sanity check (`--dry-run`).
4. Record findings and any code fixes in this file.

## Open items

- Sample emails: user will provide them when Stage 1 starts.

---

## Stage 1 findings — LinkedIn digest email

**Sample:** `You may be a fit for Zenjob’s Full-Stack Engineer (f_m_d) role - Actively recruiting.eml`
(from `C:\Users\user\Downloads\`)

**What the sample reveals:**

The email is a **LinkedIn job alert digest** containing **three distinct jobs**:

| # | Title | Company | Location | LinkedIn job ID |
|---|-------|---------|----------|-----------------|
| 1 | Full-Stack Engineer (f/m/d) | Zenjob | Berlin, Germany | 4489714169 |
| 2 | Lead Developer Java / AI Insurance (all genders) | adesso SE | Berlin | 4464891334 |
| 3 | Softwareentwickler Entwicklungsprojekte, all genders | SALT AND PEPPER Group | Berlin | 4482674373 |

Plus a "See all jobs" link to the full LinkedIn search results page.

Each job entry has:
- A job title line
- A company name line
- A location line
- A `View job: https://www.linkedin.com/comm/jobs/view/{jobId}/...` link
- No actual job description in the email body — only title/company/location/link

**Problem with current collector:**

`GmailJobCollector._parse_message()` returns **one record per email** with the entire
body as a single `body` string. For a digest like this:

- `subject` = "You may be a fit for Zenjob's Full-Stack Engineer (f/m/d) role - Actively recruiting"
- `sender` = "LinkedIn Job Alerts <jobalerts-noreply@linkedin.com>"
- `body` = full text containing all three jobs + "See all jobs" link

`GeminiJobAnalyzer.analyze_job()` receives this as one `job` mapping with the whole
body as `description`. Gemini may not know where one job ends and another begins,
and there is no `company`/`employer` field extracted, so the cover letter / resume
cannot be tailored to a specific role.

**Proposed fix (to implement during Stage 1 debugging):**

Add digest parsing in `gmail_collector.py` to split a LinkedIn-style digest into
per-job records before returning from `fetch_new_job_emails()`:

1. Detect digest pattern (e.g., repeated `View job: https://www.linkedin.com/comm/jobs/view/{id}/` lines).
2. For each job block, extract:
   - `job_title` — the title line above the company
   - `company` / `employer` — the company line
   - `location` — optional location line
   - `job_url` — the `View job` URL
   - `job_id` — the numeric ID from the URL
   - `body` / `description` — the block's text (title + company + location)
   - `subject` — original email subject
   - `sender` — original email sender
3. Return a list of per-job records instead of one record for the email.

This makes Stage 2 (`analyze_job`) work per-job, and Stages 3–4 generate tailored
resume + cover letter for each job individually, saving into `<Company Name>` folders.

**Done when:** collector splits the digest into N per-job records with extracted
`job_title`, `company`, `job_url`, `body`, and `pytest` passes for new tests.
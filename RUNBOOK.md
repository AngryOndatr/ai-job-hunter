# Operator Runbook

This runbook covers the scheduled GitHub Actions job and local execution. Eligible jobs with an application address produce a Gmail draft; eligible jobs without one produce review-ready files in Google Drive. Neither route sends an application email.

## Check a run

1. Open **Actions → AI Job Hunter** and select the scheduled or manually dispatched run.
2. Check the **AI Job Hunter run** summary for status, run ID, counts, duration, and failed stages. `success` means the run had no recorded job errors; it does not assert that a person reviewed a draft.
3. Open the failed **Run job application pipeline** step and inspect the JSON report. It distinguishes `would_create_drafts` from `would_create_documents`; errors identify a processing stage, including `document_only_application` and `telegram_notification`. Reports intentionally omit message bodies, profile text, and recipient addresses.
4. For draft applications, check Gmail Drafts. For document-only applications, open `google_docs.output_folder_id` in Drive and find the sanitized company folder (or `Unknown Company` if the alert did not identify a company). Telegram links to the resume and cover-letter PDFs.

## Phase 7.7 controlled verification

Scheduled executions are disabled unless the repository variable `ENABLE_SCHEDULED_RUNS` is exactly `true`. Keep it unset/false until the real-account pilot has been reviewed. Manual workflow dispatch offers `dry-run` (default) and `pilot`; the pilot accepts an explicit job cap that cannot exceed `limits.max_jobs_per_run`. Start with a cap of one.

1. Complete the credential and template setup listed in `README.md`; confirm the factual profile and resume template are different documents and that the template has valid placeholders.
2. Dispatch **AI Job Hunter** in `dry-run` mode with a cap of one. Confirm Gmail fetching, Gemini analysis, and that the eligible job appears under `would_create_drafts` or `would_create_documents`, as appropriate. Verify that no company folder, Docs/PDFs, Gmail draft, Telegram message, or durable processing-state write was created.
3. Review the candidate job and configuration. Dispatch `pilot` with cap one. A job with an application address creates a Gmail draft and resume PDF. A job without one creates resume and cover-letter Docs/PDFs under `Output Folder/<Company Name>` and sends Telegram links. Neither route sends application email.
4. Verify the correct route: for drafts, check recipient, draft body and attachment in Gmail; for document-only jobs, check all four files under the company folder. Confirm the Telegram notification and terminal durable state. Confirm any Gmail draft remains unsent. Record outcome/run IDs in `PILOT_RESULTS_TEMPLATE.md` in a private location without personal content.
5. Do not enable scheduled execution until recovery behavior and rollback are reviewed. If the pilot is approved, set `ENABLE_SCHEDULED_RUNS=true`; to disable scheduled runs, unset it or set it to `false`. Manual dispatch remains available for `dry-run` and capped `pilot`.

Recovery verification must use an approved test message/artifact. Do not edit production manifest state or delete Drive/Gmail artifacts to simulate an interruption. If there is no safe test case, record recovery verification as deferred and leave scheduled runs disabled.

## Common failures

| Stage / symptom | First checks | Safe next action |
|---|---|---|
| `preflight_failed` | Review the named configuration field, missing secret name, or OAuth scope requirement in the report. | Correct the GitHub Actions secret/configuration and reauthorize Google locally if the OAuth token lacks scopes; update `GOOGLE_TOKEN_JSON` with the refreshed token. Rerun after validation. |
| `startup_failed` | Review the workflow step logs immediately before the pipeline step, including token JSON validation. The report redacts unexpected exception details. | Fix the reported setup issue. Do not paste credentials into logs or issue comments. |
| `analysis` / `resume_tailoring` | Check Gemini availability, API key configuration, quota, and model response. | Retry on a later run or dispatch manually after the underlying transient issue is resolved. Failed pre-draft jobs remain eligible for retry. |
| `resume_document` | Check Drive/Docs permissions, output folder access, and whether a document with the deterministic idempotency key already exists. | Retry through the normal pipeline; Drive reconciliation is designed to reuse matching artifacts. Do not delete artifacts until the matching job state has been inspected. |
| `document_only_application` | Check Drive/Docs permissions and the company folder under the configured output folder. Inspect the durable state for the saved idempotency keys and artifact IDs. | Retry normally. The deterministic company-folder, resume, and cover-letter keys reconcile partial output; matching artifacts are reused. |
| `gmail_draft` / `draft_recovery` | Check Gmail compose scope and Gmail Drafts. Inspect the durable job state in the configured Drive output folder. | Allow the next run to reconcile `draft_pending`. Do not manually create a replacement draft until confirming that no matching draft exists. |
| `processed_id_persistence` | Check Drive access and the durable manifest. A draft may already have been created before this failure. | Inspect Gmail Drafts and the manifest before retrying. Idempotency/recovery should reconcile an existing draft; never assume the operation had no side effects. |
| `telegram_notification` | Check Telegram token, chat ID, bot access, and network/API status. Inspect the durable manifest to determine whether this is a Gmail draft or document-only application. | Retry through the normal pipeline after fixing Telegram. Draft notifications reuse the existing draft. Document-only notifications retry from saved Drive links without regenerating files. Do not clear processing state manually. |
| No jobs / zero outputs | Check fetched/attempted counts, Gmail labels and age filters, match threshold, route-specific candidate counts, and skip reasons. | Adjust source/configuration only if the input set is unexpectedly empty. A successful run with no eligible outputs is not an execution failure. |

## Retry and recovery rules

- Prefer a normal scheduled or manually dispatched workflow rerun after correcting the underlying cause. Workflow concurrency prevents two runs from writing the shared manifest at the same time.
- Failures before a terminal outcome remain retryable. The durable manifest and idempotency keys reconcile resume documents, cover letters, company folders, and Gmail drafts after interruptions.
- If the last recorded state is `draft_pending`, inspect Gmail Drafts and let the recovery path search for the existing deterministic draft before attempting a new one.
- `document_only_pending` indicates that file creation may be partial; rerun normally so Drive can reuse files by deterministic keys. `document_only_created` with a failed or pending notification retries Telegram from the saved PDF links. It becomes terminal after notification status is saved as `sent`.
- If a draft exists, treat it as an external side effect even when the run is red or Telegram failed. Verify recipient, content, and attachment in Gmail; the application remains unsent until a human chooses to send it.
- Do not manually edit/delete the durable manifest or matching Drive/Gmail artifacts as a first response. Preserve the run ID, stage, state record, and relevant artifact IDs for investigation.
- For repeated failures, stop dispatching retries, capture the workflow run URL and run ID, and review configuration/scopes and Drive/Gmail state before resuming.

## Local diagnostics

Run the same pipeline locally with `python main.py` or the read-only mode with `python main.py --dry-run`. The command prints a JSON report with run timestamps, duration, outcome, aggregate counts, and per-job stage errors. Unexpected setup errors are redacted. Dry-run still reads Gmail and profile/template Docs and calls Gemini, but it does not create company folders, Docs/PDFs, Gmail drafts, Telegram notifications, or durable/local processing-state writes. It lists eligible draft and document-only candidates separately.

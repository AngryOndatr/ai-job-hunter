# Phase 7.7 Pilot Record

Complete after each real-account verification. Do not record secrets, Gmail subjects/bodies, candidate profile text, recipient addresses, or generated application content in this file. Store this record in a private operational location unless the referenced run and artifact metadata are approved for the public repository.

## Environment

- Date/time (UTC):
- Repository commit:
- GitHub Actions run URL:
- GitHub Actions run ID:
- Mode: `dry-run` / `pilot`
- Effective job cap:
- Schedule gate (`ENABLE_SCHEDULED_RUNS`): `false` / `true`

## Dry-run verification

- Outcome and pipeline run ID:
- Gmail fetch completed: yes / no
- Gemini analysis completed: yes / no
- Candidate draft count reported:
- Confirmed no documents/drafts/notifications/state writes: yes / no
- Follow-up (describe only configuration or stage names):

## Capped live pilot

- Outcome and pipeline run ID:
- Jobs attempted / drafts created / notifications sent:
- Resume document and PDF verified in Drive: yes / no
- Draft and attachment verified in Gmail: yes / no
- Recipient and content manually reviewed: yes / no
- Confirmed no email was sent: yes / no
- Durable state verified as terminal: yes / no
- Recovery behavior verified: yes / no / deferred
- Follow-up (no personal content):

## Rollback / schedule decision

- Schedule remains disabled pending review: yes / no
- Any pilot artifacts to retain or remove (record IDs only in a private location):
- Disable procedure confirmed: set repository variable `ENABLE_SCHEDULED_RUNS` to `false` or unset it; cancel an active workflow run if necessary.
- Decision and reviewer:

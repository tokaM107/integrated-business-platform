# Security remediation log

Every change made by the security audit of 10 Nov 2026, on branch `security/full-audit-2026-11-10`. Finding
numbers refer to [FULL_SECURITY_AUDIT.md](FULL_SECURITY_AUDIT.md). Paths are under `apps/imed_erp/imed_erp/`
unless they start with `deploy/` or `scripts/`. Nothing was pushed, merged or deployed.

Tests named below are in `imederp/tests/test_security_server_fields.py` (S) and
`imederp/tests/test_security_audit.py` (A).

## Commit `04fa30e`: documents and sessions

| Finding | Change | Files | Evidence |
|---|---|---|---|
| D1, D5 | Cash Handover: the entry, custody account, receiver and cancel fields are kept as stored (`keep`); the person saving or submitting is `handed_over_by`; cancelling reverses only the stored entry of a Received hand-over | `imederp/server_fields.py`, `imederp/doctype/cash_handover/cash_handover.py` | S: 3 tests, all failed before |
| D2 | App Payment: `journal_entry` kept as stored, so submission always posts | `imederp/doctype/app_payment/app_payment.py` | S: 1 test, failed before |
| D3 | Cash Discrepancy: 16 decision fields change only under `flags.by_action` | `imederp/doctype/cash_discrepancy/cash_discrepancy.py` | S: 1 test, failed before |
| D7 | Treasury Close: discrepancy and review marks kept as stored; `amended_from` must be the reopened close of the same box and day; `withdraw()` refuses another close's discrepancy | `treasury_close.py`, `cash_discrepancy.py` | S: 2 tests, failed before. `amended_from`: no attack test |
| D4 | `validate` hook on every document: the right to write or submit is checked on the stored values | `imederp/server_fields.py`, `hooks.py` | S: 2 tests (attack refused; own draft still saved) |
| D8 | Posted-document links kept as stored on Inter Business Transfer, Damaged Stock Sale, Stock Count, Studio Hour Package; typed usage rows dropped on a manual package | the four controllers | Full suite passes; no attack test |
| D9 | Inter Business Transfer `confirm_receipt` reloads the stored document before posting | `inter_business_transfer.py` | Full suite passes |
| D6 (part) | Printer Reading recognises the day's screen by a flag the screen sets, not by a link in the request | `printer_reading.py`, `daily_counter_reading.py` | Full suite passes; no attack test |
| S1 | Session policy as an `auth_hooks` hook: 30 min idle and 12 h total; 15 min and 8 h for privileged roles; configurable; cache entry dropped on logout | `imederp/session_policy.py`, `hooks.py` | A: 8 tests; HTTP checks (audit report, section E) |

## Commit `8d2d7c6`: endpoints, integrations, assistant

| Finding | Change | Files | Evidence |
|---|---|---|---|
| X3 | POST only: `library_sync.receive`, XStudio `sync_now`, `test_connection`, `dry_run`, material request `request_approval`, `approve`, `reject`, booking `record_payment`, `make_booking_invoice` | `imederp/library_sync/sync.py`, `imederp/xstudio/sync.py`, `imederp/material_issue.py`, `imederp/booking_accounts.py` | A: 1 test; HTTP: GET answers 403 |
| A1 | Who took a booking payment is written in the Payment Entry's remarks and a comment on the booking | `imederp/booking_accounts.py` | Booking tests pass; no dedicated test |
| A2 | Request id cleaned, at most 64 characters, and refused when it belongs to another booking | `imederp/booking_accounts.py` | A: 2 tests |
| A3 | The rejection reason is appended after formatting | `imederp/material_issue.py` | A: 1 test |
| A8 | Doctor Debts and Doctor Statement call the ledger permission check | `imederp/report/doctor_debts/`, `doctor_statement/` | A: 1 test |
| X1 | A customer outside the sync's group keeps its name; the difference is listed for review; names stored as plain text | `imederp/xstudio/sync.py` | 1 test in `test_xstudio_sync.py` |
| X5 | XStudio's error text and hall names are escaped | `imederp/xstudio/client.py`, `sync.py` | A: 1 test |
| X6 | http accepted only for a loopback host (parsed, not a prefix); the login does not follow redirects | `imederp/doctype/xstudio_settings/xstudio_settings.py`, `imederp/xstudio/client.py` | A: 2 tests |
| X7 | At most 500 documents a batch and 1,000 lines a document; a malformed element fails alone | `imederp/library_sync/sync.py` | A: 2 tests |
| X4 | `source_payload`, `file_content` and the payload hashes are never readable by the assistant | `assistant/tools/records.py` | A: 1 test |
| X9 (part) | A data block's tags are neutralised whatever their case or spacing | `assistant/core/prompts.py` | A: 1 test |
| X8 | Per-user budget: 20 messages a minute, 500 a day (`imed_assistant_daily_messages`) | `assistant/api.py` | A: 1 test |
| — | A malformed `messages` value is refused instead of a server error | `assistant/api.py` | A: 1 test |

## Commit `889c24c`: deployment scripts

| Finding | Change | Files | Evidence |
|---|---|---|---|
| I-backup | The backup script is copied into the image at the path the Coolify task runs | `deploy/Containerfile`, `.dockerignore` | Local build: file present, parses |
| I3 | One iptables rule per port; rules removed by their comment; port list validated | `deploy/vps_harden.sh` | `bash -n` only. Not run on Linux |
| I8 (part) | Old staging sets cleaned in every year | `deploy/offsite_backup_host.sh` | Code reading |
| X10 (part) | The connector refuses an ERP address that is not https (http only to the PC itself) | `scripts/library_connector/tanmya_connector.py` | Compiles; not run |

## What users and integrations will notice

- A browser idle for 30 minutes (15 for the owner, the accountant and administrators) is signed out; so is any
  session after 12 hours (8). Change the values in the site configuration if they do not fit the work.
- A hand-over submitted by someone other than its drafter records the submitter as the person handing over.
- The Integration Status report lists a row "to look at" when XStudio names an existing customer differently.
- The assistant refuses more than 500 messages a day from one user.
- A library batch over 500 documents is refused; the connector's batches are far smaller.
- A script calling the nine endpoints above with GET gets 403.
- The library connector no longer runs against an `http://` ERP address other than the PC itself.
- XStudio login fails, instead of following, if its address answers with a redirect.

## Not changed, on purpose

- Who may withdraw a recovery or write off a pending shortage (K1, K2): owner decisions.
- Whether any branch manager may record an app subscription (D6): owner decision.
- The default of `vps_harden.sh` (which ports to close): the owner's decision of 29 Oct 2026 stands until changed.
- `compose.coolify.yaml` (secrets in containers, image digests, container limits): changes how production starts,
  so it needs approval and a rehearsal.
- No dependency was upgraded.
- `apps/imed_erp/imed_erp/public/js/imed_assistant.js` had an uncommitted change before the audit. It is still
  uncommitted and untouched.

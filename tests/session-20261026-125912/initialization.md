# Test Session Initialization

- **Session:** tests/session-20261026-125912/
- **Started:** 2026-10-26 12:59:12 local
- **Tested plan:** `docs/plan-clients-frontend-ui.md` (all implementation rows verified as `Executed = [x]`)
- **Tester agent run:** full CRUD + validations E2E via Playwright MCP + PostgreSQL DB verification

## Scope (user request)

1. Complete CRUD and validations for the Clients frontend plan.
2. Playwright MCP browser E2E over all pages/actions.
3. All matrix test cases (plan §4 Testing strategy items 1–15).
4. Field validations: client-side (required/email/maxlength) and server-side (400 shapes, 409 dup, maxlength).
5. Verify all changes actually land in the PostgreSQL database.

## Environment

- Django dev server: `uv run python manage.py runserver 127.0.0.1:8010` (rebuilt per stage)
- Live PostgreSQL via `src/document_generator/.env` (credentials not printed; loaded with python-dotenv)
- Browser: Playwright MCP (Chromium), same-origin only

## Test data conventions

- All sandbox rows named with prefix `E2E Sandbox ...` (unique names per test; includes punctuation/XSS/length probes).
- Every created sandbox row is soft-deleted (confirmed in DB as `is_active=false`) or, per item, verified as never-inserted.
- No schema/dependency/config/application-code changes; scripts live in this session dir only.

## Artifacts

- `e2e_http.py` — HTTP-level end-to-end of the full API contract the UI depends on
- `db_check.py` — read-only PostgreSQL row verifications per stage
- `shots/` — Playwright screenshots at each UI state
- `RESULTS.md` — final pass/fail ledger (written at session end)

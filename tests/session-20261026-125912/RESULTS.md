# Test Results — Clients Frontend E2E, Validations & DB Verification

- **Session:** `tests/session-20261026-125912/` (started 2026-10-26 12:59:12 local)
- **Plan:** `docs/plan-clients-frontend-ui.md` — all implementation rows `Executed = [x]`
- **Scope (user request):** complete CRUD + validations; all matrix cases; Playwright MCP browser E2E; complete E2E implementation (HTTP test runner); field validation checks; DB change verification.
- **Verdict: ALL requested coverage PASSED. 3 minor observations recorded (report-only; no fixes applied). Application source untouched by this session.**

## 1. Automated unit suites (run from `src/document_generator`)

| Suite | Result | Evidence |
|---|---|---|
| `manage.py test frontend` | **10/10 pass** | `OUT-frontend-tests.txt` |
| `manage.py test clients` (regression) | **21/22** — 1 fail = documented pre-existing `test_create_readonly_fields_ignored` (`AssertionError: 5 != 1`; file untouched by this task) | `OUT-clients-tests.txt` |

## 2. HTTP-contract E2E — `e2e_http.py` vs live `runserver 127.0.0.1:8010`

**25/25 steps PASS** (`OUT-e2e-http-v3.txt`; v1/v2 logs kept showing the runner's own two script bugs — duplicate-name probe and cascading missing-rival — which were fixed in the runner, not the app):

- Create 201 + echo + server timestamps; list-first ordering
- Duplicate case-insensitive → **409** `{"client_name": "A client with this name (case-insensitive) already exists."}`
- 400 shapes: missing required field, invalid email, `industries` as string, list member non-string, whitespace-only name (`may not be blank`), 300-char name (`no more than 255`), null name
- POST with `client_id`/`is_active` set → ignored, fresh id, active
- PUT full → 200; PUT missing key → 400 `list_of_entities`; PATCH → **405**; PUT unknown id → 404
- Rename to *other* row's UPPER name → 409; rename to own UPPER name → 200 (self-exclusion)
- DELETE 204 → DELETE again 404 → GET detail 404 → list excludes id → PUT on deleted id 404
- `updated_at` advanced after PUT; every created row soft-deleted (cleanup 204)

## 3. Playwright browser E2E (MCP, Chromium) + evidence

| # | Item | Result | Evidence |
|---|---|---|---|
| A/B | navbar (brand, `Clients`→`/`), footer, empty state `No clients yet — add your first client.` | PASS | `shots/A1-home-empty-state.png`, `shots/B1-empty-state.png` |
| A | vendored assets served: bootstrap.min.css, styles.css, bundle js, clients.js (4 same-origin static, 0 external refs) | PASS | stage-A resource list + §5 grep |
| C | add form: `maxlength 255/100/–/255/254–`, required×3, `novalidate`, Cancel→`/` | PASS | `shots/C0-add-form.png` |
| C | typed 300 chars → input holds **255** (client-side truncation) | PASS | typingProbe |
| C | valid create → redirect `/` → row `[name, E2EA, Alpha SPOC, EditDelete]` | PASS | `shots/C1-list-after-add.png` + DB id 25 |
| D0 | all-blank submit → 3 inline "Please fill out this field." + **0 network POSTs** | PASS | `shots/D0-blank-errors.png` |
| D1 | ws-only name → server **400** → inline "This field may not be blank." postDelta=1 | PASS | `shots/D1-ws-name-server-400.png` |
| D2 | programmatic 300-char name → server **400** → inline "Ensure this field has no more than 255 characters." | PASS | `shots/D2-long-name-server-400.png` |
| D3 | invalid email → client-side block, **0 POSTs**, inline "@" message | PASS | `shots/D3-bad-email-client-block.png` |
| D4 | case-variant duplicate → server **409** inline, stays on form | PASS | `shots/D4-duplicate-409.png` |
| E | edit prefill exact (all six incl. joined lists) → PUT **200** → list shows `E2EA-UPD` | PASS | `shots/E1-...png`, `E2-...png` + DB |
| F1 | delete confirm → **204** → row gone, empty state; GET detail 404 | PASS | `shots/F1-...png` + DB id 25 |
| G | XSS probe `<img onerror>`/`<script>`/`<b>` → cells render **text-only**; 0 img/script elements in tbody; no dialog | PASS | `shots/G1-...png`, `G2-...png` + DB id 26 |
| F2 | two-tab stale delete → DELETE **404** → exact banner captured by MutationObserver (t=30719 visible → t=30805 hidden) → list refreshed | PASS | `shots/F2-5-stale-404-after.png` + observer transcript below |
| H | admin-cookie: login (sessionid set) → UI create+delete OK, no 403 → DB row inactive | PASS | id 30 + logs |
| 15 | offline-capability: zero external refs; computed navbar bg `rgb(33, 37, 41)` (vendored CSS applied) | PASS | §5 grep + stage-A data |

**Observer transcript (item 13):** mutator log on `#clients-error`: `[t=30077 hidden ""] → [t=30719 visible "Client no longer active — the list has been refreshed."] → [t=30805 hidden ""]`; DELETE response status captured `[404]`; rows after: empty state.

## 4. Database verification (`db_check.py`, psycopg, read-only — OUT db files)

- Created rows cross-checked **per stage** with expected values per column + `is_active` + `created_at`/`updated_at` (ids 25–30 this session).
- UI deactivations: `is_active=false`, `updated_at` advanced, other columns preserved (25/26/27/28/29/30).
- Rejected payloads never inserted: ws-only name, 300-char name, duplicate case-variant (case-lock count exactly 1).
- Finalstate sweep: `{"sandbox_total": 12, "sandbox_active": 0}` — **0 active rows remain; DB left exactly as found (was 0 active).**
- `logs/app.log` shows matching `CLIENT_CREATED/UPDATED/DEACTIVATED` lifecycle lines for every id (25–30) — app-level logging verified.

## 5. Offline/grep check

`Select-String https?://` over all frontend templates+static (minus 127/localhost/w3/data): **NONE** — all references local/vendor-packed (also matrix 15 plus frames from stage A).

## 6. Findings (report-only; NOT fixed per tester constraints)

| # | Severity | Finding | Repro/reach |
|---|---|---|---|
| O1 | cosmetic | `/favicon.ico` auto-request → 404 (no `<link rel=icon>`; no favicon planned) | Every page load; browser default request |
| O2 | minor | Nested DRF list-type error shape `{"field": {"field": "…"}}` → `applyApiErrors` → `String(object)` → `[object Object]` inline string | API-level only (E6/E7); unreachable through the UI (form always sends arrays) |
| O3 | minor | 404-branch delete banner visible ≈86 ms then cleared by auto-refresh's `hideError()` — matrix 13 "message + refresh" technically works but effectively invisible | Stale delete 404 flow (Observer transcript O3) |

## 7. Environment/tooling integrity

- No application source, config, dependency, schema or migration change made during testing (scripts live only under `tests/session-20261026-125912/`).
- Dev server stopped at session end; browser tabs closed; `.playwright-mcp/` artifacts removed.
- Previous user changes preserved (uncommitted git state verified).

## 8. Matrix cross-check (plan §4 items 1–15)

| Item (plan §4) | This session |
|---|---|
| 1–4 (smoke, templates, plumbing) | PASS (frontend 10/10) |
| 5 rows render / name-shortname-spoc | PASS (C) |
| 6 empty state | PASS (A/B) |
| 7 add flow + log | PASS (C + logs) |
| 8 duplicate 409 inline | PASS (D4 + E16) |
| 9 required/email blocking | PASS (D0/D3 + E5/D2) |
| 10 edit prefill + all-keys PUT + updated_at | PASS (E) |
| 11 edit of deleted id → banner + disabled | PASS (prev session; re-verified API paths E20/E22) |
| 12 delete confirm text + 204 + DB | PASS (F1 + DB) |
| 13 stale delete 404 + refresh | PASS (F2; banner transient — O3) |
| 14 admin cookie regression | PASS (H) |
| 15 offline styling | PASS (A + grep + computed style) |

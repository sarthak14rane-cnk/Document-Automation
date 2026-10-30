# Final Report — template_master E2E Test Session (2026-10-28)

Session: `tests/session-20261028-153500/` · Plan: `docs/plan-template-master-backend.md`

## Verdict

**The backend fulfills the plan's functional contract on all 4 endpoints.** All product-level
checks pass; the run surfaced **4 defects** (2 severe, environment/content-fidelity), all
reproduced with minimal cases and reported — no application code was modified.

## Evidence by area

| Area | Result | Evidence |
| :--- | :--- | :--- |
| Baseline unit+API suite (63 tests) | **PASS** (exit 0) | `baseline_rerun.txt` |
| GET /templates/ (list, exclusions, shape) | **PASS** (test client + live HTTP) | `e2e_run2.log`, HTTP smoke |
| GET /templates/{id}/schema/ (9 groups, 3 ai_sections, prompts, requires) | **PASS** | `schema_{client}.json` artifacts |
| POST /ai/generate-section/ REAL opencode (10 real calls: 9 E2E + 1 live HTTP) | **PASS** (with .exe OPENCODE_BIN) | `ai_content_{client}.json`, `ai_http_greenleaf.txt` |
| POST /templates/{id}/preview/ REAL render (test client + live HTTP) | **PASS** | `preview_{client}.docx`, `preview_http_acme.docx` |
| Error contracts (404/409/400/502 incl. codes) — 16 checks | **PASS** 16/16 | `e2e_run2.log` |
| Content correctness, 3 industries (NGO eye-care / steel manufacturing / fintech) + organic-food over HTTP | **PASS** — industry-appropriate, valid shapes, no debris | `ai_content_*.json`, `extracted_*.txt` |
| Golden structural coverage (Acme render vs Mission_for_Vision golden, 20 markers) | **PASS** | `recheck.md` |
| SmartArt (client name, sparse roles, partner gating on/off, weekly cadence) | **PASS** | per-client data2/data3 checks |
| Phase toggles incl. `optional`+disclaimer and phase_4 off blanking (TOC-aware) | **PASS** | `recheck.md` |
| Registry/DB hygiene (all test rows rolled back/deleted; DB as found: 0 rows) | **PASS** | final `manage.py shell` probe |

Totals: E2E 125 checks (116 PASS / 9 FAIL → 7 confirmed harness bugs re-verified PASS, 2 = defect D4),
error contracts 16/16, recheck 11 checks, live-HTTP smoke 4/4 endpoints.

## Defects found (reported, NOT fixed — Tester scope)

### D1 (medium) — default `OPENCODE_BIN='opencode'` unresolvable by the bridge on this server
`subprocess.run(shell=False)` cannot resolve the npm shims (`opencode.cmd`/`opencode.ps1`,
no `.exe` on PATH) → `WinError 2` on every AI call with default settings.
Mitigation used: `OPENCODE_BIN` env override (the plan's designed swap point).

### D3 (SEVERE) — multi-line prompts lose all CLI flags through the `.cmd` shim
With `OPENCODE_BIN=opencode.cmd`, cmd.exe re-parses the command line; the bridge places the
(multi-line) prompt BEFORE `--format`/`--model`, so cmd splits at newlines and the flags are
lost → opencode silently falls back to the subscription-gated default (`kimi-k3`) →
**every real config prompt fails 502** ("An active OpenCode Go subscription is required").
Repro: single-line quote-only prompt → OK; same prompt + newlines → kimi-k3 fallback (captured).
Working config: `OPENCODE_BIN=...\nodejs\node_modules\@opencode\cli\bin\opencode.exe`
(the real exe the shim forwards to) — with it, all 10 real generations succeeded.
Suggested fixes (Planner/Executor): resolve the binary via `shutil.which` honoring PATHEXT /
prefer the `.exe`; and/or move `--format`/`--model` flags BEFORE the prompt in argv.

### D2 (low) — model can leak `<tool_use>` debris into `text` output
Observed on a trivial prompt (`PONG` + tool-use transcript appended). `bullets`/`categories`
are protected by JSON validation; `text` has no debris check → junk could silently reach
documents. Not observed on the 10 real schema prompts this session.

### D4 (SEVERE) — bare `&` silently dropped from every rendered value (docxtpl 0.20.2)
`DocxTemplate.render()` unconditionally runs `fix_tables()`, which re-parses the rendered XML
with `etree.XMLParser(recover=True)` (`docxtpl/template.py:520`); values containing bare `&`
are invalid XML and the recover parser silently deletes the character.
- Minimal repro saved: `probe_in.docx`/`probe_out.docx` — `'Employee & Workforce'` → `'Employee  Workforce'`.
- Affects **AI content AND static config text**: phase titles like
  "Governance, Policy & Compliance Framework Design" render as "Policy  Compliance".
- Breaks golden parity: the golden document preserves `&` ("STANDARD TERMS & CONDITIONS").
Suggested fixes: pre-escape `&`/`<`/`>` in string context values before `render()` (and
avoid double-escaping), or post-process; alternatively pin/patch docxtpl.

## Artifacts in this session
`initialization.md`, `baseline_rerun.txt`, `spike_bridge.py`, `e2e_full.py`, `e2e_run.log` (D1/D3 evidence),
`e2e_run2.log`, `recheck.py`, `recheck.md`, `results.md`, `schema_*.json`, `ai_content_*.json`,
`ai_http_greenleaf.txt`, `preview_*.docx` (3 clients + HTTP), `extracted_*.txt`, `extracted_golden.txt`,
`probe_in.docx`/`probe_out.docx` (D4 repro), `bad_config.yaml`, `server.pid`.

## Notes
- Test-environment configuration used (not code changes): `OPENCODE_BIN` → real `opencode.exe`;
  `testserver` added to ALLOWED_HOSTS inside the session script only.
- Rendered Word files are saved for human inspection (plan's "Word inspection" step);
  programmatic golden comparison was performed instead of a manual GUI open.

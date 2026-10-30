# Test Session — template_master E2E

- Session dir: `tests/session-20261028-153500/`
- Started: 2026-10-28 15:36
- Plan under test: `docs/plan-template-master-backend.md` (all To-Do Matrix rows `Executed = [x]`; only "Manual smoke" row remained unchecked — this session covers it)
- Scope (user request): complete end-to-end test of ALL 4 endpoints + real (unmocked) AI generation via opencode with clients from DIFFERENT industries to validate generated content correctness.

## Environment

- Workdir: `C:\Users\LT-IS-07\PycharmProjects\Document-Automation`
- Django app dir: `src/document_generator/` (test label: `template_master.tests`)
- DB: Postgres `cnk` (test DB created per run, destroyed after)
- Documents: `documents/config_v2.yaml`, `documents/master_dpdpa_ia_v2.docx`, golden `documents/Mission_for_Vision-DPDPA_IA_Proposal_V1.docx`
- opencode: settings default `OPENCODE_MODEL = opencode/mimo-v2.6-flash-free`

## Test matrix (planned)

| # | Area | Method | Real/mocked |
|---|------|--------|-------------|
| 1 | Baseline unit+API suite (63 tests) | `manage.py test template_master.tests` | mocked AI |
| 2 | opencode bridge liveness spike | one real `generate_section` call | REAL |
| 3 | E2E: list -> schema -> 3x AI -> preview, x3 industry clients | Django test client (full middleware stack), DB tx rolled back | REAL AI + REAL render |
| 4 | Error contracts live (404/409/400/502) | test client | REAL |
| 5 | Live HTTP smoke via runserver (true HTTP) | Invoke-WebRequest | REAL render + REAL AI |
| 6 | Rendered docx content verification vs golden | programmatic text extraction/diff | REAL artifacts |

## Constraints (Tester rules)

- No application source code modified; no production config changes; no commits.
- Any test scripts live ONLY in this session directory.
- DB rows created for E2E are rolled back / deleted — DB left as found.

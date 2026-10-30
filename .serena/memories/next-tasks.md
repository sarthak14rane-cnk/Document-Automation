# Next tasks

## 1. ~~template_master backend~~ DONE — built + E2E verified 2026-10-28/30
Model + 4 endpoints + engine/ package all implemented and running. Full API reference:
see `mem:template-master/api-reference`. E2E battery + unit suite green; see
`mem:template-master/e2e-verification`. Plan: `docs/plan-template-master-backend.md`.

## 2. ~~Document generation core~~ DONE — engine/ package implemented
`src/document_generator/engine/` (manifest, schema_builder, computed, context_builder,
renderer, smartart, ai_bridge) built + validated. Config contract:
`mem:template-master/config-contract`.

## 3. E2E defect fixes D1-D4 — DONE 2026-10-30 (plan `docs/plan-fix-template-ai-e2e-defects.md`)
- D1/D3: Windows-safe opencode binary resolution + flags-before-prompt argv.
- D2: tool-debris strip. D4: docxtpl bare-`&` XML-escape (renderer).
- All 4 fixed + regression-tested (12 new unit tests; suite 75/75). No regressions on re-run.
Details: `mem:template-master/e2e-verification`.

## 4. Template artifacts relocated to media/ — DONE 2026-10-30
Config + master docx moved `documents/` -> `src/document_generator/media/DPDP_IA/` (service-scoped
subfolder). DB row template_id=40 paths updated; app verified to resolve/render from new location.
NOTE: E2E harnesses in `tests/session-*/` still reference old `documents/` fixture paths — update
before any re-run.

## 5. Clients-app D3 — still open (test-only)
`clients/tests.py` `test_create_readonly_fields_ignored` asserts hardcoded `client_id == 1` —
change to `!= 999`. NOT to be touched during template work.

## 6. Auth / hardening pass
API surfaces run with AllowAny and `REST_FRAMEWORK['DEFAULT_AUTHENTICATION_CLASSES'] = []`.
Revisit with frontend fetch CSRF/credential handling when auth lands.

## 7. Housekeeping
- Work remains uncommitted/pushed unless asked (engine/, media/, tests/, docs/plan-*.md untracked).
- 13 soft-deleted TEST-* rows remain in cnk.clients_client (purge optional).
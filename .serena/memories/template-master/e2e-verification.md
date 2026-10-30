# template_master — E2E verification + defect-fix state (2026-10-30)

## Unit suite
`uv run python manage.py test template_master.tests` (from src/document_generator/) -> **75/75 OK**
(63 old + 12 new regression tests for D1-D4).

## Full E2E battery (post-fix)
- Run 1 + completion run: **138 checks, 0 FAIL** (acme 33/33, bharat 28/28, technova 37/37 incl.
  3 live AI calls, error contracts 16/16, D4 acceptance 8/8, golden markers, DB hygiene).
- Later re-run: 113 checks, 2 FAIL — both transient provider JSON-output quality on
  `processing_bullets` (model emitted non-JSON) correctly surfaced as 502 ai_generation_failed.
  NOT regressions. Free-tier quota (provider.quota) is an environment limit, not a defect.

## D1-D4 fixes (files: engine/ai_bridge.py, engine/renderer.py, template_master/tests.py)
- D1: default OPENCODE_BIN='opencode' unresolvable on Windows (npm installs only .cmd/.ps1 shims)
  -> resolve_opencode_bin (explicit path -> PATH .exe -> shutil.which -> npm-shim target-exe parse).
  Always logs AI_BRIDGE_BIN / AI_BRIDGE_BIN_RESOLVED.
- D3: .cmd shim re-parsed cmdline, split multi-line prompt, dropped --format/--model -> silent
  kimi-k3 fallback. Fix: flags BEFORE prompt in argv: [bin,'run','--format','json','--model',M,prompt].
- D2: model can leak <tool_use> transcripts into text -> _strip_tool_debris in _validate (all
  schemas). Debris-only output -> empty-retry -> 502.
- D4: docxtpl 0.20.2 drops bare & from rendered context -> _xml_escape_context escapes &<> string
  leaves for the docxtpl render only (SmartArt keeps raw). Golden parity restored.
- AI_BRIDGE_MODEL_MISMATCH warning = best-effort no-op (spike C: served model not exposed in
  NDJSON/stderr).

## Live-HTTP smoke (D1/D3 proof over real sockets)
runserver 127.0.0.1:8765 --noreload, fresh env, NO OPENCODE_BIN -> 10/10 PASS: list/schema/
real-AI (19.7s, no debris)/preview (1.04MB)/D4-&-verbatim over the wire.

## Env facts
- opencode direct exe: C:\Users\LT-IS-07\AppData\Local\Programs\nodejs\node_modules\@opencode\cli\bin\opencode.exe
- Default model: opencode/mimo-v2.6-flash-free (OPENCODE_MODEL). Timeout 180s.
- DB left as found: TemplateMaster rows = 0 after every E2E run (transaction rollback).
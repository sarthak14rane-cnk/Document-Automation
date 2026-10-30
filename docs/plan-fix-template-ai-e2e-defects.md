# Fix E2E Test-Session Defects (opencode Invocation, AI Debris, Ampersand Dropping)

## 1. Objective

Fix the four defects (D1–D4) found by the 2026-10-28 end-to-end test session
(`tests/session-20261028-153500/FINAL_REPORT.md`) against the `template_master`
backend / `document_generator.engine` package:

| ID | Severity | Defect |
| :--- | :--- | :--- |
| D1 | Medium | Default `OPENCODE_BIN='opencode'` cannot be executed by `subprocess.run(shell=False)` on this Windows server (npm installs only `.cmd`/`.ps1` shims) → `WinError 2` on every AI call with default settings. |
| D3 | **Severe** | With `OPENCODE_BIN=opencode.cmd`, cmd.exe re-parses the command line and splits multi-line prompts at newlines; because the bridge places the prompt **before** `--format`/`--model`, all flags are lost → opencode silently falls back to the subscription-gated default (`kimi-k3`) → **every real (multi-line) config prompt fails with 502**. Only pointing `OPENCODE_BIN` at the real `opencode.exe` works today. |
| D2 | Low | The model can leak `<tool_use>…</tool_use>` transcripts into assistant text. `bullets`/`categories` are protected by JSON validation, but `output_schema: text` has no debris handling → junk could reach documents. |
| D4 | **Severe** | docxtpl 0.20.2 drops every **bare `&`** from any rendered context value (AI content *and* static config text, e.g. "Governance, Policy & Compliance Framework Design" renders as "Policy  Compliance"), breaking golden parity (the golden document preserves `&`). |

Final outcome: real AI generation works with **default settings** on this server (no
env var required), model invocation is hardened and observable, text outputs are
debris-free, and every `&`/`<`/`>` in user/AI/config content renders verbatim in
generated documents.

User-confirmed design choices (2026-10-28): D2 = **strip + log**; D1/D3 = **full
hardening** (binary resolution + flags-before-prompt argv + model-mismatch warning);
D4 = **engine-level escaping** (no dependency change).

---

## 2. Context

### Confirmed repository facts

- `src/document_generator/engine/ai_bridge.py` (read in full):
  - `generate_section(prompt, output_schema, model=None, timeout=None, cwd=None)` (line 162) builds argv at lines 173–182 as `[OPENCODE_BIN, "run", prompt, "--format", "json"]` + `["--model", resolved_model]` — **prompt before flags** (D3 factor).
  - `_run_once(argv, timeout, cwd)` (line 140): `subprocess.run(..., shell=False, ...)`; `OSError` → `AIError` (lines 155–156).
  - `_extract_assistant_text(stdout)` (line 67) → `(text, errors)`; `_validate(text, output_schema)` (line 97) → `(parsed, reason)`; `_strip_fences` (line 59); `normalize_model` (line 47); `DEFAULT_PROVIDER = "opencode"` (line 42).
  - Settings reads: `getattr(settings, "OPENCODE_BIN", "opencode")` (line 174), `OPENCODE_TIMEOUT` (169), `DOCUMENTS_ROOT` (171), `OPENCODE_MODEL` (180).
  - Retry loop: one full retry (lines 185–202); `AI_BRIDGE_OK` / `AI_BRIDGE_FAILED` loguru events.
- `src/document_generator/engine/renderer.py` (read in full): `render_document(config, template_path, context)` — `template.render(context, autoescape=False)` (line 26), then `smartart.patch_smartart(rendered, config, context)` (line 36) receives the **raw** context (SmartArt does its own lxml-safe text assignment — must NOT receive escaped values).
- `src/document_generator/backend/settings.py` lines 172–186: `DOCUMENTS_ROOT` (177), `OPENCODE_BIN = os.getenv('OPENCODE_BIN', 'opencode')` (180), `OPENCODE_MODEL = 'opencode/mimo-v2.6-flash-free'` (185), `OPENCODE_TIMEOUT` (186).
- `src/document_generator/template_master/tests.py` test classes: `ComputedTests` (144), `ManifestTests` (184), `SchemaBuilderTests` (256), `ContextBuilderTests` (306), `AIBridgeTests` (473), `SmartArtTests` (567), `RendererTests` (616), `TemplateAPITests` (652).
- docxtpl 0.20.2 (installed at `.venv/Lib/site-packages/docxtpl/template.py`): `render()` calls `fix_tables(xml_src)` **unconditionally** (line 492); `fix_tables` re-parses with `etree.XMLParser(recover=True)` (lines 520–521) — the recover parser silently deletes bare `&` from text (invalid XML). This is the D4 root cause. Upstream `clean_tags` (lines 289–301) does not help.
- npm shim on this server: `C:\Users\LT-IS-07\AppData\Local\Programs\nodejs\opencode.cmd` contains `"%dp0%\node_modules\@opencode\cli\bin\opencode.exe"   %*` — a formulaic npm shim forwarding to a real exe. `opencode.ps1` is the same target. **No `opencode.exe` on PATH itself.**
- The A1 envelope (pinned in the module docstring + live runs): NDJSON events; assistant text in `{"type":"text","part":{"text":…}}`; errors in `{"type":"error","error":{…}}`. Observed `step_start` events show no obvious model field; a defensive scan for `modelID`/`model` keys is required (spike) for D3's mismatch warning.

### Confirmed test-session evidence

- `tests/session-20261028-153500/`: `e2e_run.log` (D1 WinError 2 + D3 kimi-k3 stderr), `e2e_run2.log` (working runs with `.exe`), `spike_bridge.py`, `probe_in.docx`/`probe_out.docx` (D4 minimal repro: `'Employee & Workforce'` → `'Employee  Workforce'`), `extracted_golden.txt` (golden preserves `&`, e.g. `STANDARD TERMS & CONDITIONS`), `FINAL_REPORT.md`.
- Empirical: single-line prompt with quotes through the `.cmd` shim → `--model` honored; same prompt + newlines → `kimi-k3` fallback. Multi-line prompts + flags through the **real `.exe`** → all 10 real generations succeeded.
- Default model in effect: `opencode/mimo-v2.6-flash-free` (settings line 185); the `opencode-go` default (`kimi-k3`) 403s without a Go subscription.

### Assumptions

- **A1 (fix)**: opencode v2.0.28 accepts `run --format json [--model X] <prompt>` (flags before the positional). To be spike-verified before the argv reorder is kept. If rejected, keep prompt-first order — binary resolution alone already fixes D1/D3 for the `.exe` path.
- **A2 (fix)**: npm `.cmd` shims encountered in the wild follow the `"%dp0%\node_modules\…\*.exe" %*` convention. Parse is best-effort with a loud fallback warning (argv order provides degraded-mode mitigation).
- **A3 (fix)**: the NDJSON envelope may expose the served model somewhere in event/message fields; if it never does, the mismatch warning simply never fires (no behavior change).

### Dependencies

- opencode v2.0.28 installed + authenticated (unchanged).
- No new packages. docxtpl stays pinned at 0.20.2.

### Blockers

- None known. (D2 policy, D3 scope, D4 approach were confirmed by the user.)

---

## 3. What / Why / How to Build

### 3.1 D1 + D3 — opencode binary resolution and invocation hardening (`engine/ai_bridge.py`)

**What**
1. Add `resolve_opencode_bin(raw) -> str` and call it from `generate_section` instead of using `getattr(settings, "OPENCODE_BIN", "opencode")` verbatim.
2. Reorder argv to put flags before the positional prompt.
3. Add a best-effort served-model mismatch warning.

**Why**
- D1: `subprocess.run(shell=False)` uses CreateProcess, which only auto-appends `.exe`; npm installs `opencode` as `.cmd`/`.ps1`, so the bare name fails with `WinError 2`.
- D3: with a `.cmd` shim, cmd.exe re-parses the command line and splits multi-line argv at newlines; prompt-before-flags loses the flags → silent fallback to the subscription-gated default model. Resolving the real `.exe` removes the cmd layer entirely; flags-before-prompt keeps the model correct even in degraded `.cmd` mode (truncated prompt → validation failure → visible retry/502 instead of silently charging the Go subscription).

**How**
- `resolve_opencode_bin(raw)` logic (Windows-aware, POSIX-safe pass-through):
  1. If `raw` contains a path separator or `os.path.isfile(raw)` → return as-is (explicit override, absolute or relative; existing files win).
  2. Bare name: manual PATH scan preferring `<dir>/<name>.exe` (iterate `os.environ.get("PATH", "").split(os.pathsep)`).
  3. Else `shutil.which(raw)` (honors PATHEXT; may return `.cmd`/`.bat`).
  4. If the resolved file ends with `.cmd`/`.bat`: read its text and extract the first quoted `...\.exe` target (npm shim convention, e.g. `"%dp0%\node_modules\@opencode\cli\bin\opencode.exe" %*`); if that exe exists, return it and `logger.info("AI_BRIDGE_BIN_RESOLVED shim={} exe={}", …)`.
  5. If nothing resolves → raise `AIError("opencode binary '<raw>' not found; set OPENCODE_BIN to the full path of opencode.exe")` (visible failure, consistent with the module contract).
  6. Always log the finally chosen binary: `logger.info("AI_BRIDGE_BIN path={}", resolved)` (fires once per `generate_section` call — cheap, makes silent environment differences visible).
- Argv order (line 173–182) becomes: `[resolved_bin, "run", "--format", "json"]` + `["--model", resolved_model]` (when set) + `[str(prompt)]`. Guarded by the A1 spike (§4): if the CLI rejects flags-before-prompt, revert to prompt-first and record the result in the module docstring (binary resolution alone still fixes D1/D3 for the `.exe` path).
- Served-model mismatch warning: extend `_extract_assistant_text` to also return any `modelID`/`model` string values found anywhere in the parsed events (defensive scan, first hit wins). In `generate_section`, after a successful validation, if a served model was detected and it differs from `resolved_model`, `logger.warning("AI_BRIDGE_MODEL_MISMATCH requested={} served={}", …)`. Log-only (no retry/hard fail). Best-effort per A3.

### 3.2 D2 — tool-debris stripping (`engine/ai_bridge.py`)

**What**: strip opencode tool-call transcripts from assistant text before validation; log when debris is removed.

**Why**: the model can emit `<tool_use>…</tool_use>` (with nested `<tool_name>`, `<tool_input>`, `<tool_use_error>`) into text events; `text` schema currently passes debris straight through into documents.

**How**
- New `_strip_tool_debris(text) -> str` (module-private, applied inside `_validate` to the raw assistant text **before** `_strip_fences`, for **all** schemas):
  - `re.sub(r"<tool_use\b.*?</tool_use>", "", text, flags=re.DOTALL)` (removes whole blocks).
  - Also strip stray fragments: `<tool_name>…</tool_name>`, `<tool_input>…</tool_input>`, `<tool_use_error>…</tool_use_error>` (same DOTALL pattern).
  - Collapse 3+ blank lines; `.strip()`.
  - If anything was removed → `logger.warning("AI_BRIDGE_DEBRIS_STRIPPED bytes={}", removed_len)` (user choice: strip + log, keep availability).
- Placement guarantees the existing retry semantics: debris-only output → empty after strip → existing `"empty assistant text"` retry → 502 if persistent (visible-failure contract preserved). For `bullets`/`categories`, stripping before fence/JSON handling can also rescue valid JSON that was wrapped in debris (currently a guaranteed 502).

### 3.3 D4 — XML-escape context values for the docxtpl render (`engine/renderer.py`)

**What**: escape `&`, `<`, `>` in every string leaf of the context **for the docxtpl render only**; SmartArt continues to receive raw values.

**Why**: docxtpl 0.20.2 re-parses the rendered XML with `recover=True` (`template.py:520`), silently dropping bare `&` (and mangling other invalid-XML fragments) from values. Pre-escaping makes every value valid XML; the document then displays the literal characters. No dependency change (user choice).

**How**
- New `_xml_escape_context(context) -> dict`:
  - Recursively walk dicts (including `_Bunch`, a `dict` subclass — plain-dict copies are fine: Jinja resolves `client.name` via item lookup), lists, and tuples.
  - For every `str` leaf: `xml.sax.saxutils.escape(value)` (`&`→`&amp;`, `<`→`&lt;`, `>`→`&gt;`; quotes untouched — values never land in attributes in this master).
  - Non-string leaves (`bool`, `int`, `float`, `None`, `datetime`) pass through unchanged.
  - Return a fresh plain-dict structure (never mutate the caller's context).
- In `render_document`: `render_context = _xml_escape_context(context)`; `template.render(render_context, autoescape=False)`; line 36 unchanged (`smartart.patch_smartart(rendered, config, context)` keeps the **raw** context — lxml escapes SmartArt text correctly on serialization already).
- Document in the module docstring: the recover-parser rationale, and the documented edge case — values that already contain literal `&amp;`/`&lt;` render as that literal text (safest interpretation; values are plain text, never markup).

### 3.4 Regression tests (`template_master/tests.py`)

**What/Why**: lock the fixes in; keep the existing 63 tests green (escaping must be a no-op for special-char-free values).

**How** (extend `AIBridgeTests` at line 473 and `RendererTests` at line 616; use `tempfile.TemporaryDirectory` + `os.environ` monkeypatching via `unittest.mock.patch.dict` for PATH):
- `AIBridgeTests`:
  - `test_resolve_bin_prefers_exe_on_path` — temp dir with `fakeopencode.exe` + `fakeopencode.cmd` on PATH → resolution returns the `.exe`.
  - `test_resolve_bin_parses_npm_shim` — temp `opencode.cmd` with the npm-convention line pointing at a created `.exe` → resolves to the exe (and logs `AI_BRIDGE_BIN_RESOLVED`).
  - `test_resolve_bin_missing_raises_aierror` — empty PATH → `AIError` with the `OPENCODE_BIN` hint.
  - `test_resolve_bin_explicit_path_wins` — existing absolute path returned unchanged.
  - `test_argv_puts_flags_before_prompt` — mock `_run_once` to capture argv; assert `[..., "run", "--format", "json", "--model", <model>, <prompt>]`.
  - `test_text_debris_stripped_and_logged` — fake stdout whose text event contains `PONG\n\n<tool_use>…</tool_use>` → parsed content is clean; warning logged (assert via `logger` capture or side-effect list).
  - `test_debris_around_json_still_parses` — bullets JSON wrapped in `<tool_use>` debris → parsed successfully.
  - `test_model_mismatch_warns` — event containing `modelID: "other/model"` while requesting `opencode/mimo-v2.6-flash-free` → warning logged, call still succeeds.
- `RendererTests`:
  - `test_ampersand_value_survives_render` — build context via `build_context` with an AI category title containing `&` (e.g. `"Employee & Workforce Data"`), render, assert the title appears verbatim in the extracted document text (`&amp;` in raw `word/document.xml`).
  - `test_angle_bracket_value_renders_literally` — an input containing `"< 500 records"` renders as literal text (`&lt; 500 records` in raw XML), not swallowed markup.
  - `test_config_ampersand_phase_titles_survive` — render and assert `"Governance, Policy & Compliance Framework Design"` appears verbatim (static config text, D4's worst case).
  - `test_smartart_receives_raw_context` — stakeholder role containing `&` (e.g. `"R&D Head"`) appears in `word/diagrams/data2.xml` serialized as `R&amp;D Head` (proves SmartArt got the raw value and lxml escaped it properly).

---

## 4. Technical Specification

### Architecture changes
`None.` (No new modules; two engine modules modified; test file extended.)

### Data flow
- AI: view → `generate_section` → `resolve_opencode_bin` → `_run_once(argv: flags-before-prompt)` → `_extract_assistant_text` (+ model scan) → `_validate` (with `_strip_tool_debris`) → retry/`AIError` unchanged.
- Render: view → `build_context` (raw values) → `render_document` → `_xml_escape_context` copy → docxtpl → `patch_smartart(rendered, raw context)` → bytes.

### API changes
`None.` (Request/response contracts unchanged; only success-rate and content fidelity change.)

### Database/schema changes
`Not applicable.`

### Backend changes
- `engine/ai_bridge.py`: new imports (`os`, `shutil`, `pathlib`), new helpers `resolve_opencode_bin`, `_strip_tool_debris`; modified `_extract_assistant_text` (model scan), `_validate` (debris strip), `generate_section` (resolution call, argv order, mismatch warning); updated module docstring (A1-order spike result, shim resolution, debris policy, mismatch warning).
- `engine/renderer.py`: new `_xml_escape_context` + `render_document` uses the escaped copy for docxtpl; docstring update.

### Frontend changes
`Not applicable.`

### Configuration changes
`None.` — `OPENCODE_BIN` default stays `'opencode'` (now resolvable via the bridge); explicit absolute-path override continues to win. No settings edits required.

### Security considerations
- `resolve_opencode_bin` only *searches* PATH / parses a local shim file — no shell execution, no request-controlled input (binary name comes from settings only). Keep argv list form (`shell=False`).
- Shim parsing must only accept targets that exist as files; never `eval`/execute shim content.
- Escaping strengthens output integrity (prevents values from being silently mangled); it does not enable injection (docxtpl template tags come only from the master file).

### Error handling
- Unresolvable binary → `AIError` with an actionable message (visible failure, maps to 502 as today).
- Debris-only text → existing empty-retry → 502 (unchanged contract).
- Everything else unchanged (`AI_BRIDGE_FAILED` logging preserved).

### Validation
- In-schema inputs: unchanged.
- Engine: `RendererTests` new cases prove `&`/`<`/`>` fidelity incl. static config text and SmartArt raw-context behavior.

### Performance considerations
- `resolve_opencode_bin` runs once per `generate_section` (PATH scan is trivial vs. a 10–120 s model call). `shutil.which` fallback acceptable.
- `_xml_escape_context` deep-copies the context once per render (~ms at this document size).

### Compatibility considerations
- POSIX: manual `.exe` preference is Windows-only behavior; on POSIX `shutil.which(raw)` resolves normally (guard the `.cmd`-parse branch with `os.name == "nt"` or simply by file extension).
- docxtpl pinned at 0.20.2 — the fix targets its known behavior; re-run `RendererTests` if docxtpl is ever upgraded.
- The mismatch warning is envelope-dependent (A3) — absence of model fields degrades to no-op.

### Testing strategy
1. **Unit**: full suite `uv run python manage.py test template_master.tests` (workdir `src/document_generator`) — 63 existing + ~12 new, all green.
2. **Live bridge spikes** (real opencode, workdir repo root, `.venv` via `uv run`):
   - Spike A (before committing argv order): `run --format json --model opencode/mimo-v2.6-flash-free "Reply PONG"` — flags-before-prompt accepted? Record in module docstring.
   - Spike B (D1+D3 acceptance): with **no `OPENCODE_BIN` env override**, call the real multi-line `client_profile` prompt through `generate_section` — must succeed with `mimo-v2.6-flash-free` (resolution via npm shim parse).
   - Spike C (mismatch scan): run a trivial call and inspect captured NDJSON for `modelID`/`model` fields to confirm/deny A3; record.
3. **D4 acceptance**: render with an `&`-bearing category title and assert verbatim presence; re-check the saved-session golden markers (`STANDARD TERMS & CONDITIONS`, `BROAD METHODOLOGY & KEY STEPS`, phase-2a/2b titles) in a fresh render.
4. **Full E2E rerun**: new session dir `tests/session-<date>/`, rerun the prior battery (`e2e_full.py`-style: 3 industries, error contracts) **without any `OPENCODE_BIN` override** + live-HTTP smoke (runserver + Invoke-WebRequest). All previous PASS checks must remain PASS; the 2 former D4 FAIL checks (verbatim `&` titles) must now PASS.
5. `uv run python manage.py check`.

### Deployment considerations
- After merge: no migration, no dependency change, no settings change; `uv sync` unnecessary. Server needs nothing new — resolution works with default settings on npm-shim installs; explicit `OPENCODE_BIN` overrides still take precedence.

---

## 5. Change Template

| File | Change Type | Proposed Change | Reason |
| :--- | :--- | :--- | :--- |
| `src/document_generator/engine/ai_bridge.py` | Modify | Add `resolve_opencode_bin` (PATH `.exe` preference → `shutil.which` → npm-shim parse → precise `AIError`), flags-before-prompt argv (spike-guarded), `_strip_tool_debris` applied in `_validate`, served-model scan in `_extract_assistant_text` + `AI_BRIDGE_MODEL_MISMATCH` warning, `AI_BRIDGE_BIN`/`AI_BRIDGE_BIN_RESOLVED` logging, docstring update | Fixes D1, D2, D3 |
| `src/document_generator/engine/renderer.py` | Modify | Add `_xml_escape_context` (recursive `&`/`<`/`>` escaping of string leaves) and use the escaped copy for the docxtpl render only; SmartArt keeps raw context; docstring rationale + entity edge case | Fixes D4 |
| `src/document_generator/template_master/tests.py` | Modify | New unit tests: 5× binary resolution/argv (in `AIBridgeTests`), 3× debris/mismatch, 4× renderer escaping fidelity (in `RendererTests`) | Regression protection for D1–D4 |

**Explicitly out of scope**: `backend/settings.py` (defaults unchanged and now functional); docxtpl upgrade; frontend; auth; lint execution; opencode HTTP-API swap; changes to endpoint contracts or views/serializers/urls/models.

---

## 6. To-Do Matrix

| File / Change | Proposed Action | Executed | Tested | Deployed |
| :--- | :--- | :---: | :---: | :---: |
| `src/document_generator/engine/ai_bridge.py` | D1/D3 binary resolution + argv order + mismatch warning; D2 debris strip | [x] | [x] | [ ] |
| `src/document_generator/engine/renderer.py` | D4 `_xml_escape_context` for docxtpl render (SmartArt raw) | [x] | [x] | [ ] |
| `src/document_generator/template_master/tests.py` | New unit tests for resolution/argv/debris/mismatch + renderer escaping | [x] | [x] | [ ] |
| Spike A (live) | verify flags-before-prompt accepted by opencode v2.0.28; record in docstring | [x] | [x] | [ ] |
| Spike B (live) | real multi-line config prompt succeeds with NO `OPENCODE_BIN` override (D1+D3 acceptance) | [x] | [x] | [ ] |
| Spike C (live) | confirm/deny NDJSON model fields (A3); record | [x] | [x] | [ ] |
| Unit suite | full `template_master.tests` green (63 old + ~12 new) | [x] | [x] | [ ] |
| D4 acceptance | verbatim `&` in fresh render + golden markers re-check | [x] | [x] | [ ] |
| E2E rerun | new session battery without env override + live-HTTP smoke; D4 FAILs now PASS | [x] | [x] | [ ] |

**Execution evidence (2026-10-28 session `tests/session-20261028-171000/`, completed 2026-10-30):**
- Unit suite: 75/75 green (63 old + 12 new), exit 0. Run via `uv run python manage.py test template_master.tests`.
- Spike A PASS (opencode v2.0.28 accepts `run --format json --model <id> <prompt>`); Spike C: no model field in NDJSON/stderr (mismatch warning = best-effort no-op, recorded in docstring); Spike B 8/8 PASS with NO `OPENCODE_BIN` (`AI_BRIDGE_BIN_RESOLVED shim=…nodejs\opencode.CMD exe=…bin\opencode.exe`, `AI_BRIDGE_OK model=opencode/mimo-v2.6-flash-free`).
- Combined E2E (`e2e_rerun.log` run 1 + `complete_technova.py` after free-tier quota recovery): **138 checks, 0 FAIL** (`results.md`) — acme 33/33, bharat 28/28, technova 37/37 (3 live AI calls + preview + content/SmartArt checks), error contracts 16/16, D4 acceptance 8/8 (incl. both former-FAIL `&` titles), golden markers, DB hygiene. Interruption note: run 1's technova AI section hit `provider.quota` (free-tier, non-defect) and was completed on quota recovery.
- Live-HTTP smoke (`http_smoke.py 33`, `runserver 127.0.0.1:8765 --noreload`, fresh env, no `OPENCODE_BIN`): **10/10 PASS** (`http_smoke.md`) — real AI over HTTP (19.7 s, no debris), preview 1,042,903 bytes, D4 `&` verbatim over the wire; server log shows `AI_BRIDGE_BIN_RESOLVED` + `AI_BRIDGE_OK`.
- DB left as found: `TemplateMaster` rows = 0 after every run (transaction rollback + smoke-row deletion verified).
- `Deployed` remains `[ ]`: no deployment is in scope for this plan (local dev validation only).

---

## 7. Sources

Repository:
- `src/document_generator/engine/ai_bridge.py` — full read (argv build lines 173–182, `_run_once` 140–159, `_validate` 97–137, `_extract_assistant_text` 67–94, settings reads 169–182).
- `src/document_generator/engine/renderer.py` — full read (render 26, smartart raw context 36).
- `src/document_generator/backend/settings.py` lines 172–186 — OPENCODE_*/DOCUMENTS_ROOT defaults.
- `src/document_generator/template_master/tests.py` — class inventory (lines 144–652).
- `.venv/Lib/site-packages/docxtpl/template.py` — lines 492 (`render` → `fix_tables`), 519–521 (`XMLParser(recover=True)`), 289–301 (`clean_tags`) — D4 root cause.
- `C:\Users\LT-IS-07\AppData\Local\Programs\nodejs\opencode.cmd` — npm shim content forwarding to `node_modules\@opencode\cli\bin\opencode.exe` (D1/D3 basis).
- Test session `tests/session-20261028-153500/` — `FINAL_REPORT.md` (defect definitions), `e2e_run.log`/`e2e_run2.log` (D1/D3 stderr evidence), `probe_in.docx`/`probe_out.docx` (D4 minimal repro), `extracted_golden.txt` (golden `&` parity), `spike_bridge.py`.

External:
`None.` (All evidence is local: repository files, installed-package source, and the recorded test session. No web research was required.)

---

## 8. Summary

Fix the four E2E-found defects with the smallest correct changes, all inside two engine modules plus tests: (1) the opencode bridge gains Windows-safe binary resolution (PATH `.exe` preference → `shutil.which` → npm-shim target extraction → actionable `AIError`), spike-verified flags-before-prompt argv ordering, tool-debris stripping with logging for all output schemas, and a best-effort served-model mismatch warning — making real AI generation work with default settings on this server; (2) the renderer XML-escapes string context values for the docxtpl render only, so `&`/`<`/`>` render verbatim and golden parity is restored, while SmartArt continues to receive raw values. Validation: ~12 new unit tests, full-suite green, three live spikes (argv order, no-env-override acceptance, envelope model fields), a D4 acceptance render against golden markers, and a full E2E rerun + live-HTTP smoke without any environment override. Key risks are the npm-shim convention assumption (mitigated by loud fallback + argv ordering) and the argv-order spike (guarded; binary resolution alone already fixes the defect).

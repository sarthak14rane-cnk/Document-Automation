# template_master Backend — Template Registry, Schema, Preview & AI Section Generation

## 1. Objective

Build the backend for the `template_master` application of the Document-Automation project:

1. **One table** `template_masters` (template name, path to config file, path to template master file, is_active, created_at).
2. **Three template endpoints**:
   - List **active** templates whose config AND template-master files both exist on the server (user's `get_active_templates`).
   - Given a template id: verify both files exist, then return the **JSON inputs structure** (form schema) derived from that template's config file (user's `get_template/<id>`).
   - Given a template id and JSON inputs: **render the Word document** using the config + template master + inputs and return it (user's `preview_template/<id>`).
3. **One generalized AI endpoint**: takes JSON input (prompt, section structure/output schema, industries list) and returns the AI-generated section as JSON. The intended frontend flow is: AI sections are generated **first**, then their content is passed as part of the preview request.
4. AI section generation must go through the **opencode application installed on the server**, via a **separate dedicated module** (user requirement).

**User-decided design choices (confirmed 2026-10-26):**

| Decision | Choice |
| :--- | :--- |
| opencode invocation | `opencode run` headless CLI (subprocess), **not** TUI automation |
| AI prompt ownership | **Frontend-supplied prompt** (generalized endpoint takes the prompt; `get_template`-equivalent returns the prompts) |
| Preview output | `.docx` streamed back as a file response (no storage) |
| SmartArt patching | **Included in v1** |
| AI request flow | Synchronous per section (no job queue) |
| URL naming | RESTful (`/templates/…`, `/ai/…`) |

---

## 2. Context

### Existing architecture (confirmed from repository)

- **Stack**: Django 6.1.2 + DRF 3.18, PostgreSQL (`cnk` database, port 2478, IPv4-forced), loguru logging, `python-dotenv`, uv package manager. Settings: `src/document_generator/backend/settings.py` (`BASE_DIR` = `src/document_generator/`).
- **App conventions** (from `clients` app, the reference implementation):
  - DRF `ViewSet`/`APIView` with `permission_classes = [AllowAny]` (no auth this iteration; `REST_FRAMEWORK['DEFAULT_AUTHENTICATION_CLASSES'] = []` — settings.py lines 111-121).
  - `SimpleRouter` registration with numeric `lookup_field`/`lookup_value_regex` (`clients/urls.py`).
  - `loguru` structured info logs (`CLIENT_CREATED …` style) in `perform_*`/actions.
  - Models: `BigAutoField` explicit PK, `is_active` soft-delete flag, `created_at`/`updated_at` auto timestamps, lowercase unique constraint, `JSONField` for lists/dicts (`clients/models.py`).
  - `backend/urls.py`: API includes first, **frontend include kept LAST** (page routes share prefixes with API).
- **`template_master` app**: already in `INSTALLED_APPS` (settings.py line 55); empty startapp skeleton (`models.py`, `views.py`, `tests.py`, `admin.py`, `apps.py`, `migrations/__init__.py` all default stubs).
- **Document assets** at **repo root** (`C:\...\Document-Automation\documents\` — outside `BASE_DIR`):
  - `documents/config_v2.yaml` — the single document map (1,175 lines; restructured per `docs/plan-config-restructure-industries-ai-toggles-version.md`): `version: 2`, `inputs:` groups (incl. inline toggle items with `default`, e.g. `phase_4: optional`), `computed:` function declarations, `smartart:` node maps (`word/diagrams/data2.xml`, `data3.xml`), `lint:`, `library:` (verbatim content pool), `sections:` (33 sections, 3 AI blocks with `output_schema: text|bullets|categories`, prompts with Jinja, **AI-ONLY — no fallbacks**, visible-failure contract).
  - `documents/master_dpdpa_ia_v2.docx` — the Jinja master template (docxtpl syntax: `{%p for blk in sections.X.blocks %}`, `{%tr for m in milestones %}`, `{{ sections.data_categories.heading }}`, `{{ phases.phase_X.title }}`, inline `{% if %}`; TOC field; footer; 3 SmartArt parts `data1–data3.xml`).
  - `documents/Mission_for_Vision-DPDPA_IA_Proposal_V1.docx` — golden reference output.
- **Dependencies NOT yet installed** (`pyproject.toml`): `pyyaml` (config parsing) and `docxtpl` (docx rendering) are absent. `docxtpl` brings `python-docx`, `jinja2`, `lxml` transitively.
- **Config-declared engine conventions** (config_v2.yaml header): the engine modules are *named* in the header (`engine/manifest.py`, `engine/schema_builder.py`, `engine/computed.py`) — the engine should live as a plain package under `src/document_generator/engine/` matching that contract. Render context namespaces declared in the header: `client, cnk, commercials, timeline, retention, narrative, ai (ai.industries + ai.industries_phrase), computed, library, phases (bridge context), sections (per-section heading/blocks payloads)`.
- **Git state**: `documents/` is untracked; the files must be present on the server at the paths stored in the DB for anything to work.

### opencode facts (verified on this machine, v2.0.28)

- Background service already running (`opencode service status` → `http://127.0.0.1:49374`); authenticated provider `opencode-go`, default model `kimi-k3` (`opencode api get /api/model/default`).
- `opencode run "<message>"` is the documented automation entry point. Confirmed flags: `--model provider/model#variant`, `--format json`, `--agent`, `--file`, `--session`, `--auto`, `--standalone`, `--server`.
- V2 HTTP API also offers session routes + one-shot `POST /api/experimental/generate` (not used in v1; the bridge module isolates this swap point).

### docxtpl facts (Context7: /elapouya/python-docx-template)

- `{%p tag %}`, `{%tr tag %}`, `{%tc tag %}`, `{%r tag %}` are docxtpl's documented special tags; the tag-bearing paragraph/row/column/run is removed and the real Jinja tag placed appropriately. The master template uses exactly this syntax.
- `DocxTemplate.render(context, jinja_env=None, autoescape=False)`; `DocxTemplate.save(path)`. No SmartArt support — SmartArt parts must be patched by direct OOXML surgery after render.

### Assumptions (must be verified during implementation)

- **A1**: `opencode run --format json` output shape is not documented in the fetched pages; the first implementation step is a one-call spike (trivial prompt) to pin the JSON envelope and the assistant-text extraction path. The bridge must parse defensively.
- **A2**: `opencode run` inherits the project context of its `cwd` (project config/instructions). Default `cwd` = repo root (`DOCUMENTS_ROOT`); if repository instructions visibly pollute generation, switch to a neutral scratch cwd. Record the choice in the bridge.
- **A3**: Test runner conventions follow `clients/tests.py` (Django test runner against Postgres). Existing suite has one known test-only failure (`test_create_readonly_fields_ignored`); new tests must not depend on it.
- **A4**: Computed value formats (ordinal date, Indian financial year, Indian number format) must be matched against the golden document during implementation (e.g. "5th June 2025", "Rs. 12,34,567").
- **A5**: The template DB row's paths are admin-managed data (not user input); endpoints treat them as trusted but still validate resolution under `DOCUMENTS_ROOT`.

### Dependencies / blockers

- `uv add pyyaml docxtpl` requires network/uv cache (standard).
- opencode must remain installed + authenticated on the server; its background service must be running for `opencode run` (it auto-starts the shared service when absent).
- `documents/` files must exist on the server at the paths recorded in `template_masters`.

---

## 3. What / Why / How to Build

### 3.1 Model — `TemplateMaster`

**What**: one table with the user's columns (+ `updated_at` for consistency with `Client`).

**Why**: registry mapping a template name to its two on-server artifact paths; `is_active` gates availability.

**How**: in `src/document_generator/template_master/models.py` (replace stub):

```python
class TemplateMaster(models.Model):
    template_id = models.BigAutoField(primary_key=True)
    template_name = models.CharField(max_length=255, unique=True)
    config_path = models.CharField(max_length=500)     # repo-root-relative, e.g. "documents/config_v2.yaml"
    template_path = models.CharField(max_length=500)   # e.g. "documents/master_dpdpa_ia_v2.docx"
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self): return self.template_name
```

- Relative paths (not absolute) so the registry survives server moves; resolution happens against the `DOCUMENTS_ROOT` setting (§3.8). Unique `template_name` (case-sensitive DB constraint is enough; admin-managed data).
- Migration: `python manage.py makemigrations template_master` → `template_master/migrations/0001_initial.py`, then `python manage.py migrate`.

### 3.2 Engine package — `src/document_generator/engine/`

**What**: a plain (non-Django) Python package implementing the config-declared contract.

**Why**: the config header names `engine/manifest.py`, `engine/schema_builder.py`, `engine/computed.py` as the intended layout; views stay thin and the engine stays testable and reusable for the future real-generation flow.

**How**: new package `src/document_generator/engine/` with modules (all new files):

| Module | Responsibility |
| :--- | :--- |
| `__init__.py` | package marker (empty) |
| `errors.py` | exception hierarchy: `EngineError` → `ConfigError` (manifest), `RenderError`, `AIError` (bridge), `MissingAIContentError` |
| `manifest.py` | `load_config(config_path)` — `yaml.safe_load`, path safety check, structural validation (required top keys `version/inputs/computed/sections/library`; every section has `id/group/blocks`; AI blocks have `prompt` + `output_schema` + **no `fallback`**; `enabled_when` shape; anti-dead-key: every top-level `library` key referenced by ≥1 block via `path`/`config_default`). Raises `ConfigError` with precise messages. |
| `schema_builder.py` | `build_form_schema(config)` → the JSON returned by the schema endpoint: template identity + `groups` (from config `inputs:`, each field normalized: `key, label, type, required, default, hint, options, enabled_when, items, meta, validation`) + **fixed identity base fields** (`service`, `version`, `client_id`, `created_by` marked `validation: base`, `fixed: true` where constants) + `ai_sections` descriptors (see §3.4). Also computes per-AI-section `requires` (variables referenced by the prompt) via `jinja2.meta.find_undeclared_variables`. |
| `computed.py` | pure functions per config `computed:` declarations: `ordinal_date(value)`, `financial_year(value)`, `indian_format(value, prefix)`, `milestone_amounts(total_fee, milestones)`, `list_phrase(list, fallback)` ("A, B and C"). Formats matched to golden doc (A4). |
| `context_builder.py` | `build_context(config, inputs, ai_content)` → full render context: validates/coerces inputs against the schema (required keys, types), builds namespaces `client, cnk, commercials, timeline, retention, narrative, ai, computed (executed), phases, sections` — incl. toggle gating (`enabled_when` forms `{toggle: scope.phases, key: …}` and `{input: …, equals: …}`), `filter_by_toggle`, `gate_by_flag` (drop `requires_flag` items when flag absent/false), `overrides_from` (scope.bullet_overrides remove/add), `override_input` precedence (user value wins over block default when non-empty), phase bridge contexts (incl. `phase_4` optional → `treat_optional_as: enabled`), and `sections.<id>.heading` + `sections.<id>.blocks` payloads. Raises `MissingAIContentError` listing block ids for AI-only blocks with no user content (visible-failure contract). |
| `renderer.py` | `render_document(config, template_path, context) -> bytes`: `DocxTemplate(template_path)` → `render(context, autoescape=False)` → SmartArt patch (§3.5) → `save` to `BytesIO` → return bytes. Cleans up temp file handles; raises `RenderError` on failure. |
| `smartart.py` | `patch_smartart(docx_bytes, config, context) -> bytes`: reopen the rendered package as zip; for each `word/diagrams/*.xml` part declared in config `smartart:`, locate the diagram XML, patch the **text runs of the mapped nodes** per node map (`nodes: [..]`, `source: {input|input+format|skip_if_empty}`, `sparse: true`, `when: {input, equals}`), leave all other nodes and all other package entries byte-identical, rewrite the zip (deflate, preserve part order). Raises `RenderError` on structure mismatch. |
| `ai_bridge.py` | **The only module that shells out to opencode** (user's "separate file" requirement). See §3.6. |

### 3.3 Settings + URLs wiring

**What**: settings additions and URL includes.

**Why**: path resolution base, opencode tunables, route mounting.

**How**:
- `backend/settings.py` — append:
  ```python
  # Document template root (repo root by default; documents/ lives outside BASE_DIR).
  DOCUMENTS_ROOT = Path(os.getenv('DOCUMENTS_ROOT', str(BASE_DIR.parent.parent)))
  # opencode headless bridge
  OPENCODE_BIN = os.getenv('OPENCODE_BIN', 'opencode')
  OPENCODE_MODEL = os.getenv('OPENCODE_MODEL', '')   # '' = opencode default (currently opencode-go/kimi-k3)
  OPENCODE_TIMEOUT = int(os.getenv('OPENCODE_TIMEOUT', '180'))
  ```
- `backend/urls.py` — insert `path('', include('template_master.urls'))` **after** the clients include and **before** the frontend include (preserve the "frontend LAST" invariant).

### 3.4 Endpoint 1 + 2 — active list and schema (`template_master/views.py`)

**What**:
- `GET /templates/` — active templates whose two files both exist on the server.
- `GET /templates/<int:template_id>/schema/` — inputs JSON structure from the config.

**Why**: the user's `get_active_templates` and `get_template/<id>`; the schema is the contract the future frontend renders the form from.

**How**:
- `TemplateActiveListView(APIView)` (`AllowAny`): filter `is_active=True`; for each row resolve both paths under `DOCUMENTS_ROOT`; include only rows where both files exist (log skipped rows with loguru at warning). Response 200: list of `{template_id, template_name, config_path, template_path, created_at}`.
- `TemplateSchemaView(APIView)`: fetch row (404 if missing or inactive → `{"detail": "Template not found or inactive."}`); resolve + verify both files (409 + `code: "config_file_missing"` / `"template_file_missing"` if absent); `manifest.load_config` (400 `code: "invalid_config"` on `ConfigError`); `schema_builder.build_form_schema(config)`; return 200:
  ```json
  {
    "template": {"template_id": 1, "template_name": "DPDPA IA", "service": "DPDPA_IA",
                  "display_name": "…", "version": 2},
    "groups": [ {"group": "client", "title": "Client Details",
                 "fields": [ {"key": "client.name", "label": "Client Name", "type": "text",
                               "required": true, "default": "", "hint": null, "options": null,
                               "enabled_when": null, "items": null, "meta": {"rows": 8},
                               "validation": null, "fixed": false}, … ]}, … ],
    "ai_sections": [
      {"section_id": "entity_coverage", "block_id": "client_profile",
       "label": "Client Profile (AI-generated — click Generate, then edit)",
       "output_schema": "text", "editable": true,
       "prompt": "<raw Jinja prompt from config>",
       "requires": ["client.name", "client.website", "computed.entities_phrase",
                     "ai.industries_phrase", "client.profile"]}
    ]
  }
  ```
  - `groups` mirror config `inputs:` 1:1 (labels/types/defaults/hints/options/`enabled_when`/inline toggle `items` incl. `phase_4: optional`) so the frontend stays config-driven.
  - Identity base fields (`service`, `version` fixed; `client_id`, `created_by` user-supplied) appear as `validation: base` fields; `service`/`version` carry `fixed: true` + values so the frontend hides them.
  - `ai_sections` = ALL blocks with `source: ai` (3 for DPDPA: `client_profile`, `categories`, `processing_bullets`), each with raw prompt + `output_schema` + `requires` — this is what enables the frontend-supplied-prompt flow (decision #2).

### 3.5 Endpoint 3 — preview (`POST /templates/<int:template_id>/preview/`)

**What**: render the real .docx from config + master + JSON inputs and stream it back.

**How**:
- `TemplatePreviewView(APIView)`; request body:
  ```json
  {
    "inputs": { "<schema key>": value, … },            // every field key from groups (client.*, scope.*, commercials.*, timeline.*, retention.*, narrative.*, ai.industries, reference_number, proposal_date, validity_days, client_id, created_by, …)
    "ai_content": { "client_profile": "…text…",
                     "categories": [ {"id": "…", "title": "…", "summary": "…", "bullets": ["…"]}, … ],
                     "processing_bullets": ["…", …] }
  }
  ```
- Flow: fetch row (404) → files (409) → `manifest.load_config` (400) → `context_builder.build_context` (400 on validation errors; **400 `code: "missing_ai_content"` listing block ids** if an AI block has no content — visible-failure contract) → `renderer.render_document` (500 `code: "render_failed"` on engine errors, details logged) → `FileResponse(bytes, content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document', filename="<slug>_<reference_number or timestamp>.docx")` with `Content-Disposition: attachment`.
- TOC page numbers remain a Word-side field update (standard docx behaviour; documented caveat).

### 3.6 Endpoint 4 — AI section generation (`POST /ai/generate-section/`)

**What**: generalized, frontend-supplied-prompt AI generation (decision #2).

**How** — `AISectionView(APIView)`; request:
```json
{
  "prompt": "<Jinja-templated prompt text as delivered by the schema endpoint>",
  "output_schema": "text | bullets | categories",
  "industries": ["Eye-care / Not-for-profit", "…"],
  "client_context": { "name": "…", "short_name": "…", "website": "…",
                       "entities": ["…"], "profile": "…" }
}
```
- Backend **renders the prompt with Jinja2 server-side** (the frontend never renders Jinja): context = `{"client": client_context, "ai": {"industries": industries, "industries_phrase": list_phrase(industries, "the organisation")}, "computed": {"entities_phrase": list_phrase(entities, "its operating entities")}}`. Strict undefined handling: any remaining unrendered `{{ … }}`/`{% … %}` → 400 `code: "unresolved_prompt_vars"` listing the variable names (visible failure, never silently sent raw).
- `engine/ai_bridge.py`:
  - `generate_section(prompt, output_schema, timeout=OPENCODE_TIMEOUT)`: build argv list — `[OPENCODE_BIN, "run", prompt, "--format", "json"]` + `["--model", OPENCODE_MODEL]` when set — `subprocess.run(argv, shell=False, capture_output=True, text=True, timeout=…, cwd=DOCUMENTS_ROOT)` (A2 note in module docstring). Kill on timeout; cap captured output.
  - Parse the `--format json` envelope (A1 spike first), extract assistant text, strip code fences, `json.loads`, validate against `output_schema`: `text` → non-empty str; `bullets` → list of non-empty str; `categories` → list of dicts with `id/title/summary/bullets[str]`. One **full retry** on parse/validation failure; then raise `AIError` (visible failure contract — never empty content).
- Response 200: `{"output_schema": "text", "content": <parsed content>}` (key name `content` for all schemas; frontend stores it under the block id).
- Errors: 400 invalid request / unresolved vars; **502 `code: "ai_generation_failed"`** on opencode failure/timeout/invalid output (retryable by design); loguru `AI_SECTION_GENERATED`/`AI_SECTION_FAILED`.

### 3.7 Serializers, exceptions, admin

- `template_master/serializers.py`: `TemplateMasterSerializer` (list output); `AISectionRequestSerializer` (`prompt` required non-empty str, `output_schema` ChoiceField text/bullets/categories, `industries` ListField(child=CharField, allow_empty=True, required=False), `client_context` DictField optional); `PreviewRequestSerializer` (`inputs` DictField required, `ai_content` DictField optional). Deep input validation lives in the engine (schema-driven), not DRF fields.
- `template_master/exceptions.py`: `FilesMissing(APIException)` (409), `AIGenerationFailed(APIException)` (502), `RenderFailed(APIException)` (500) — following the `clients/exceptions.py` precedent.
- `template_master/admin.py`: register `TemplateMaster` (list display: name, is_active, created_at).

### 3.8 Path resolution & safety

- `engine/paths.py`-style helpers live in `manifest.py`: `resolve_under_documents_root(rel_path) -> Path` — reject absolute paths, `..` escapes, and paths resolving outside `DOCUMENTS_ROOT` (A5). All file access goes through it.

---

## 4. Technical Specification

### Architecture changes

```
HTTP
 → template_master.views (4 APIViews, thin)
    → engine.manifest (config load/validate)
    → engine.schema_builder (form schema + ai_sections)
    → engine.context_builder (inputs → render context)
    → engine.renderer (docxtpl) + engine.smartart (OOXML patch)
    → engine.ai_bridge (opencode run subprocess)   [separate file, user requirement]
 → Postgres (template_masters via Django ORM)
```

### Data flow (frontend contract, for the later frontend build)

1. `GET /templates/` → user picks a template.
2. `GET /templates/{id}/schema/` → form groups + `ai_sections` (prompts + `requires`).
3. User fills the form (client fields may be prefilled from the existing `clients` module) and triggers each AI section: `POST /ai/generate-section/` with that section's prompt + `output_schema` + `industries` + `client_context` → JSON content per section.
4. `POST /templates/{id}/preview/` with `inputs` + `ai_content` → `.docx` download.

### API changes

| Method & path | Purpose | Success | Errors |
| :--- | :--- | :--- | :--- |
| `GET /templates/` | active templates with both files present | 200 list | — |
| `GET /templates/{id}/schema/` | inputs JSON structure from config | 200 schema | 404 inactive/unknown; 409 `config_file_missing`/`template_file_missing`; 400 `invalid_config` |
| `POST /templates/{id}/preview/` | render + return .docx | 200 file | 404; 409 files; 400 validation / `missing_ai_content`; 500 `render_failed` |
| `POST /ai/generate-section/` | generalized AI section generation | 200 `{output_schema, content}` | 400 validation/`unresolved_prompt_vars`; 502 `ai_generation_failed` |

### Database/schema changes

- New table `template_masters` (§3.1) in the existing `cnk` Postgres DB via `template_master` migration `0001_initial`. No changes to existing tables.

### Backend changes

- As per §3. Dependency additions via `uv add pyyaml docxtpl` (pyproject.toml + uv.lock).

### Frontend changes

`Not applicable.` (Backend plan; the schema/AI contracts above are the frontend's future integration surface.)

### Configuration changes

- `backend/settings.py`: `DOCUMENTS_ROOT`, `OPENCODE_BIN`, `OPENCODE_MODEL`, `OPENCODE_TIMEOUT` (env-overridable; `.env` is user-owned).
- `pyproject.toml`/`uv.lock`: + `pyyaml`, `docxtpl`.

### Security considerations

- Endpoints are unauthenticated (consistent with the current no-auth iteration — **documented accepted risk**, revisit with the deferred auth pass). `POST /ai/generate-section/` in particular can consume opencode quota — acceptable for MVP on an internal server.
- Path safety: all artifact access resolves under `DOCUMENTS_ROOT`; absolute/`..` paths rejected (A5). Paths come from DB (admin-managed), never from request bodies.
- Subprocess: argv list (no `shell=True`), fixed timeout with kill, output capped; opencode binary name from settings, not from requests.
- Prompt-injection via user-supplied fields (e.g. `client.profile`) into AI prompts is inherent to the feature — noted, not mitigated in v1.
- YAML loaded with `yaml.safe_load` only.

### Error handling

- Precedent: `clients` app — DRF `ValidationError` → 400 field-keyed; custom `APIException` subclasses → 409/502/500 with `{"detail", "code"}`. Engine raises typed errors (`ConfigError`, `RenderError`, `AIError`, `MissingAIContentError`); views map them to the statuses in the API table. loguru logs every failure with context ids.

### Validation

- Schema endpoint validates the config structurally (manifest) before serving; preview validates inputs against the same schema (required/type coercion; unknown keys → 400; missing required → 400; missing AI content → 400 `missing_ai_content`).
- AI bridge validates model output against `output_schema` after each call (retry once → visible 502).

### Performance considerations

- Preview render is synchronous and fast (seconds); AI section generation synchronous ~10–60 s (accepted per decision #5 — the frontend shows per-section spinners). `opencode run` connects to the persistent background service, so no model-load cold start per call.
- No pagination on the templates list (small registry, consistent with clients list).

### Compatibility considerations

- Windows server: subprocess argv quoting handled by `subprocess` list args; opencode on PATH (`OPENCODE_BIN` override for non-PATH installs).
- Django 6.1 `FileResponse`/`BytesIO` streaming.
- Postgres test DB: new migration must apply cleanly; no existing-table changes.

### Testing strategy

- **Unit** (`template_master/tests.py`, engine tests in `template_master/tests.py` or `engine/tests` imported there — keep a single `tests.py` per app convention):
  - `computed.py`: ordinal_date/financial_year/indian_format/milestone_amounts/list_phrase (golden-format cases).
  - `manifest.py`: valid config loads; missing key / bad AI block (fallback present) / dead library key → `ConfigError`.
  - `schema_builder.py`: against the real `documents/config_v2.yaml` — 9 groups present, toggle items incl. `phase_4: optional`, 3 `ai_sections` with prompts + `requires`, identity base fields.
  - `context_builder.py`: toggle gating (disabled phase section drops blocks), `phase_4` optional, `gate_by_flag` children's data, `override_input` precedence, missing AI content raises with block ids.
  - `ai_bridge.py`: mocked `subprocess.run` — valid JSON, fenced JSON, invalid after retry → `AIError`; timeout → `AIError`.
  - `smartart.py`: patch a rendered package; assert only mapped diagram nodes changed and other entries are byte-identical.
- **API tests** (Django test client, Postgres test DB):
  - Seed `TemplateMaster` rows: one valid (real `documents/` files via relative paths), one with a bogus config path.
  - `GET /templates/` excludes the bogus row; 404 schema for inactive/unknown; 409 schema for bogus files; 200 schema payload assertions.
  - `POST preview/` with a small valid input set → 200, content-type docx, non-empty bytes, opens as zip with `word/document.xml`.
  - `POST preview/` without `ai_content` → 400 `missing_ai_content`.
  - `POST /ai/generate-section/` with mocked bridge → 200 content; malformed request → 400; bridge failure → 502.
- **Manual smoke** (end of implementation): register the DPDPA row, run a real preview with representative inputs, open the .docx in Word — verify headings, tables, phase loops, milestones table, SmartArt diagrams, and the AI-section placement against `Mission_for_Vision-DPDPA_IA_Proposal_V1.docx`.

### Deployment considerations

- Server prerequisites: opencode installed + authenticated + background service reachable; `documents/` present under `DOCUMENTS_ROOT`; `.env` entries for the new settings if defaults differ; `uv sync` after `uv add`; `manage.py migrate`.

---

## 5. Change Template

| File | Change Type | Proposed Change | Reason |
| :--- | :--- | :--- | :--- |
| `src/document_generator/template_master/models.py` | Modify | Replace stub with `TemplateMaster` model (§3.1) | Registry table with the user's columns |
| `src/document_generator/template_master/migrations/0001_initial.py` | Create | Generated migration for `TemplateMaster` | Persist the registry |
| `src/document_generator/template_master/serializers.py` | Create | `TemplateMasterSerializer`, `AISectionRequestSerializer`, `PreviewRequestSerializer` | Request/response validation |
| `src/document_generator/template_master/exceptions.py` | Create | `FilesMissing` (409), `AIGenerationFailed` (502), `RenderFailed` (500) | Error contract (clients precedent) |
| `src/document_generator/template_master/views.py` | Modify | Replace stub with 4 APIViews (§3.4–3.6) | The user's three endpoints + AI endpoint |
| `src/document_generator/template_master/urls.py` | Create | Routes: `templates/`, `templates/<id>/schema/`, `templates/<id>/preview/`, `ai/generate-section/` | RESTful naming (decision #6) |
| `src/document_generator/template_master/admin.py` | Modify | Register `TemplateMaster` | Admin manageability |
| `src/document_generator/template_master/tests.py` | Modify | Replace stub with unit + API test suite (§4 Testing) | Coverage per testing strategy |
| `src/document_generator/backend/settings.py` | Modify | Add `DOCUMENTS_ROOT`, `OPENCODE_BIN`, `OPENCODE_MODEL`, `OPENCODE_TIMEOUT` | Path base + opencode tunables |
| `src/document_generator/backend/urls.py` | Modify | Include `template_master.urls` before the frontend include | Route mounting; keep frontend LAST |
| `src/document_generator/engine/__init__.py` | Create | Empty package init | Config-declared engine home |
| `src/document_generator/engine/errors.py` | Create | `EngineError` hierarchy | Typed engine errors |
| `src/document_generator/engine/manifest.py` | Create | Config load + structural validation + path safety | Config-declared contract |
| `src/document_generator/engine/schema_builder.py` | Create | Form-schema + `ai_sections` JSON builder | Endpoint 2 payload |
| `src/document_generator/engine/computed.py` | Create | `ordinal_date`, `financial_year`, `indian_format`, `milestone_amounts`, `list_phrase` | Config `computed:` declarations |
| `src/document_generator/engine/context_builder.py` | Create | Render-context assembly, gating, overrides, AI-content enforcement | Endpoint 3 core |
| `src/document_generator/engine/renderer.py` | Create | docxtpl render → SmartArt patch → bytes | Endpoint 3 core |
| `src/document_generator/engine/smartart.py` | Create | Diagram XML node patching (v1, decision #4) | Org chart / methodology / reporting cadence |
| `src/document_generator/engine/ai_bridge.py` | Create | The only opencode caller: prompt render check, `opencode run --format json`, parse/validate/retry | Decision #1 + separate-file requirement |
| `pyproject.toml` (+ `uv.lock` via `uv add`) | Modify | Add `pyyaml`, `docxtpl` | Config parsing + docx rendering |

**Explicitly out of scope**: frontend UI for this module; `lint` rule execution in v1 (config stays authoritative; deferred follow-up); auth; opencode HTTP-API integration (bridge swap point only); storing generated previews.

---

## 6. To-Do Matrix

| File / Change | Proposed Action | Executed | Tested | Deployed |
| :--- | :--- | :---: | :---: | :---: |
| `src/document_generator/template_master/models.py` | `TemplateMaster` model | [x] | [x] | [ ] |
| `src/document_generator/template_master/migrations/0001_initial.py` | makemigrations + migrate | [x] | [x] | [x] |
| `src/document_generator/template_master/serializers.py` | request/response serializers | [x] | [x] | [ ] |
| `src/document_generator/template_master/exceptions.py` | error classes | [x] | [x] | [ ] |
| `src/document_generator/template_master/views.py` | 4 APIViews | [x] | [x] | [ ] |
| `src/document_generator/template_master/urls.py` | routes | [x] | [x] | [ ] |
| `src/document_generator/template_master/admin.py` | register model | [x] | [ ] | [ ] |
| `src/document_generator/backend/settings.py` | DOCUMENTS_ROOT + OPENCODE_* | [x] | [x] | [ ] |
| `src/document_generator/backend/urls.py` | include before frontend | [x] | [x] | [ ] |
| `src/document_generator/engine/*` (9 files) | engine package per §3.2 | [x] | [x] | [ ] |
| `engine/ai_bridge.py` spike | pin `--format json` envelope (A1) | [x] | [x] | [ ] |
| `pyproject.toml` + `uv.lock` | `uv add pyyaml docxtpl` | [x] | [x] | [ ] |
| `src/document_generator/template_master/tests.py` | unit + API suite; run to green (except pre-existing known failure) | [x] | [x] | [ ] |
| Manual smoke | real DPDPA preview render + Word inspection vs golden | [x] | [x] | [ ] |

Evidence (2026-10-28): E2E session `tests/session-20261028-153500/` — all 4 endpoints
verified end-to-end incl. 10 REAL opencode generations (4 industries) and live-HTTP smoke;
golden structural coverage passed. 4 defects reported (D1/D3 opencode invocation on Windows,
D2 tool-debris risk in `text`, D4 docxtpl 0.20.2 drops bare `&` — breaks golden parity);
see `FINAL_REPORT.md`. Requires `OPENCODE_BIN` pointing at the real `opencode.exe` on this server.

---

## 7. Sources

Repository:

- `src/document_generator/backend/settings.py`, `backend/urls.py` — wiring, DRF no-auth config, BASE_DIR.
- `src/document_generator/clients/{models,serializers,views,urls,exceptions}.py` — conventions.
- `src/document_generator/template_master/*` — empty skeleton state.
- `src/document_generator/frontend/views.py` — page-route patterns (include ordering).
- `documents/config_v2.yaml` — inputs/computed/smartart/library/sections contract, AI blocks + prompts (restructured 2026-10-26).
- `documents/master_dpdpa_ia_v2.docx` — docxtpl binding inventory (decomposed in the prior session).
- `pyproject.toml` — current dependencies.
- `docs/plan-config-restructure-industries-ai-toggles-version.md` — config contract source.

External (fetched during research):

- https://opencode.ai/v2/docs/cli — headless `opencode run`, background service, `--standalone`/`--server`.
- https://opencode.ai/v2/docs/api — V2 HTTP API surface (session/generate routes; not used in v1).
- Local CLI probes: `opencode --version` (v2.0.28), `opencode run --help` (flags incl. `--format json`, `--model`), `opencode service status`, `opencode api get /api/model/default` (default model `opencode-go/kimi-k3`).
- Context7 `/elapouya/python-docx-template` — `{%p %}`/`{%tr %}` special tags, `DocxTemplate.render()` options.

---

## 8. Summary

Build the `template_master` backend as a thin DRF layer over a new `document_generator.engine` package that implements the contract already declared inside `config_v2.yaml`: manifest validation, form-schema building (with AI-section descriptors carrying prompts), computed functions, render-context assembly with toggle gating and AI-ONLY enforcement, docxtpl rendering with custom SmartArt OOXML patching, and an isolated opencode bridge (`opencode run --format json`) for generalized AI section generation. The registry table stores repo-root-relative paths resolved under a configurable `DOCUMENTS_ROOT`. Preview returns the rendered `.docx` directly; AI generation is synchronous per section with a visible-failure contract (validated JSON, one retry, then 502). Key risks: the `--format json` envelope (spike first — A1) and SmartArt XML surgery (guarded by unit tests against the real master). Dependencies `pyyaml` + `docxtpl` must be added; opencode must stay installed/authenticated on the server. Frontend integration (form rendering from the schema, per-section AI calls, preview download) is the designated follow-up.

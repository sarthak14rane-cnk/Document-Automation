# template_master backend — plan digest (docs/plan-template-master-backend.md)

Status: PLANNED 2026-10-26, awaiting executor. App skeleton unchanged.

## User decisions (confirmed 2026-10-26)
- opencode invocation: headless `opencode run --format json` subprocess (NOT TUI automation).
- AI prompt ownership: frontend-supplied prompt (generalized endpoint); schema endpoint returns raw prompts per AI block.
- Preview returns the generated .docx as a file response (no storage).
- SmartArt XML patching included in v1.
- AI generation synchronous per section (~10-60s, no job queue).
- RESTful URLs.

## Endpoints
- GET /templates/ — active templates whose config + master files both exist on the server (missing-file rows skipped + logged).
- GET /templates/{id}/schema/ — inputs JSON from config: template identity + groups (fields 1:1 from inputs:) + fixed identity base fields (service/version fixed; client_id/created_by) + ai_sections [{section_id, block_id, label, output_schema, editable, prompt(raw), requires(via jinja2.meta)}].
- POST /templates/{id}/preview/ — body {inputs, ai_content} -> .docx FileResponse. Missing AI content -> 400 missing_ai_content (block ids listed). Files missing -> 409 config_file_missing/template_file_missing. Invalid config -> 400 invalid_config.
- POST /ai/generate-section/ — body {prompt, output_schema(text|bullets|categories), industries, client_context}; backend Jinja-renders the prompt (strict undefined -> 400 unresolved_prompt_vars); 200 {output_schema, content}; 502 ai_generation_failed on opencode failure/timeout/invalid JSON after 1 retry (visible-failure contract).

## Model
TemplateMaster: template_id BigAuto PK, template_name unique, config_path + template_path (repo-root-relative, resolved under DOCUMENTS_ROOT; absolute/../rejected), is_active, created_at, updated_at. Migration 0001.

## Engine package (src/document_generator/engine/, plain non-Django package)
- errors.py: EngineError -> ConfigError / RenderError / AIError / MissingAIContentError.
- manifest.py: yaml.safe_load + structural validation (top keys, sections shape, AI blocks have prompt+output_schema and NO fallback, enabled_when shape) + anti-dead-key (every library key referenced by >=1 block via path/config_default) + path safety.
- schema_builder.py: form schema + ai_sections.
- computed.py: ordinal_date, financial_year, indian_format, milestone_amounts, list_phrase ("A, B and C"). Match formats to golden doc (A4).
- context_builder.py: validate/coerce inputs; namespaces client, cnk, commercials, timeline, retention, narrative, ai (industries + industries_phrase), computed (executed), phases (bridge incl. phase_4 treat_optional_as: enabled), sections (heading/blocks payloads); enabled_when both forms; filter_by_toggle; gate_by_flag; overrides_from; override_input precedence.
- renderer.py: DocxTemplate(template_path).render(context, autoescape=False) -> smartart patch -> BytesIO.
- smartart.py: zip/XML surgery on word/diagrams/*.xml per config node maps (nodes/source/format/sparse/when/skip_if_empty); other package entries byte-identical.
- ai_bridge.py: THE ONLY opencode caller. subprocess argv list (no shell), cwd=DOCUMENTS_ROOT (A2 note), timeout kill, output cap; parse --format json envelope (A1 SPIKE FIRST), strip fences, validate per output_schema, 1 full retry then AIError.

## Settings + wiring
- settings.py additions: DOCUMENTS_ROOT (default BASE_DIR.parent.parent), OPENCODE_BIN (default 'opencode'), OPENCODE_MODEL (default '' = opencode default opencode-go/kimi-k3), OPENCODE_TIMEOUT (default 180).
- backend/urls.py: include template_master.urls BEFORE the frontend include (frontend stays LAST).
- Deps: uv add pyyaml docxtpl (jinja2 transitive).
- admin.py: register TemplateMaster.

## Assumptions to verify during implementation
- A1: 'opencode run --format json' output envelope shape — run a trivial-prompt spike first.
- A2: opencode run inherits project context of cwd; default cwd = repo root, switch to neutral dir if instructions pollute.
- A4: computed formats (ordinal date, Indian FY, Rs. format) matched against golden.
- Lint execution (config lint block) deferred out of v1.
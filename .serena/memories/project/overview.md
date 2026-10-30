# Project overview — Document Automation

Django 6.1.2 + DRF app generating DPDP (Digital Personal Data Protection Act 2023) Impact
Assessment proposal .docx documents from a YAML config + Word master template, with AI-generated
sections via the opencode CLI.

## Stack
- Backend: Django 6.1.2 + DRF 3.18, PostgreSQL DB **cnk** (user postgres) on 127.0.0.1:2478.
- Doc engine: src/document_generator/engine/ (manifest, schema_builder, computed,
  context_builder, renderer, smartart, ai_bridge). docxtpl + pyyaml.
- AI: opencode CLI headless (`opencode run --format json`), called only by engine/ai_bridge.py.
- Frontend: clients CRUD pages (Bootstrap 5.3.8 vendored); template_master UI not built.

## Apps
- clients/ — client CRUD (list/add/edit, soft-delete). See mem:clients-app/*.
- template_master/ — TemplateMaster registry + 4 REST endpoints over the engine.
  See mem:template-master/api-reference.
- engine/ — non-Django package (the document engine).

## template_master status (2026-10-30)
Built + E2E verified. Registered template_id=40 "DPDPA Impact Assessment Proposal".
Config + master docx live at src/document_generator/media/DPDP_IA/ (moved from documents/,
service-scoped subfolder). See mem:template-master/registry.
E2E defects D1-D4 fixed + regression-tested (75/75 unit, 138/138 E2E, 10/10 live-HTTP smoke).
See mem:template-master/e2e-verification.

## Key conventions
- TemplateMaster paths are repo-root-relative, resolved under settings.DOCUMENTS_ROOT
  (= repo root) at access time; absolute/../rejected.
- AI blocks are AI-ONLY (no fallback); generation failure must fail visibly (error + retry),
  never render empty.
- Render namespaces: client, cnk, commercials, timeline, retention, narrative, ai, computed,
  library, phases, sections.
- Work is uncommitted/pushed unless asked (engine/, media/, tests/, docs/plan-*.md untracked).
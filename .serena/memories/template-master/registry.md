# TemplateMaster registry + artifact locations (2026-10-30)

## Registered row (DB cnk, table template_master_templatemaster)
- template_id=40, template_name="DPDPA Impact Assessment Proposal", is_active=True.
- config_path  = src/document_generator/media/DPDP_IA/config_v2.yaml
- template_path= src/document_generator/media/DPDP_IA/master_dpdpa_ia_v2.docx
Registered via get_or_create. List serializer omits is_active (fields: template_id,
template_name, config_path, template_path, created_at).

## Artifact relocation (2026-10-30)
User moved config+docx documents/ -> src/document_generator/media/DPDP_IA/ (service-scoped
subfolder) and updated both DB path columns. Verified: resolve_under_documents_root resolves
both (paths are repo-root-relative; DOCUMENTS_ROOT = repo root; absolute/../ rejected),
load_config parses (service DPDPA_IA v2), docx zip 34 parts, and full preview render returns
200 (1,042,903 bytes) with golden & -verbatim headings intact.

## Path contract
Stored paths are repo-root-relative and resolved at access time under settings.DOCUMENTS_ROOT
(= BASE_DIR.parent.parent = repo root). The media/ restructure is valid because it stays under
the repo root. documents/Mission_for_Vision-DPDPA_IA_Proposal_V1.docx (unrelated, unregistered)
still lives in documents/.

## Caution
E2E harnesses tests/session-20261028-171000/{e2e_rerun,complete_technova}.py still reference old
documents/config_v2.yaml + documents/master_dpdpa_ia_v2.docx fixture paths — update before re-run.
# config_v2.yaml contract (post-restructure, 2026-10-26)

Executed + validated per docs/plan-config-restructure-industries-ai-toggles-version.md.
File: src/document_generator/media/DPDP_IA/config_v2.yaml (MOVED from documents/config_v2.yaml 2026-10-30, service-scoped media/ subfolder). 1,175 lines, LF, UTF-8 no BOM, untracked in git. Sibling master docx: src/document_generator/media/DPDP_IA/master_dpdpa_ia_v2.docx.

## Top-level keys (order matters)
service, display_name, version, inputs, computed, smartart, lint, library, sections
- version: 2 — single key; resolves master_dpdpa_ia_v2.docx (same media/DPDP_IA/ dir). No config_version/template_version.
- No top-level toggles: or industries: blocks (both removed 2026-10-26).

## inputs (9 groups)
client (name, short_name, address_lines, contact.salutation select, contact.name, website, entities, profile = "Client Profile (AI context, optional)" — injected into the client_profile prompt via {% if client.profile %}, stakeholder_roles, flags), reference (reference_number / proposal_date / validity_days — the ONLY validation:base fields), scope (scope.phases phase_toggles with 5 inline items incl. phase_4 default 'optional'; scope.addons addon_toggles 3 items; scope.bullet_overrides json), commercials, timeline, retention, ai_context (ai.industries required list -> {{ ai.industries_phrase }}), narrative (outcome_closing default_from library.outcomes.closing_default; timeline_context plain default ''; conclusion_context), cnk.

## computed
proposal_date_ordinal, financial_year, total_fee_indian, milestones, entities_phrase, ai_industries_phrase — all list_phrase/indian_format etc.; the only remaining 'fallback:' strings in the file are the 2 computed list_phrase args.

## sections (33)
- 3 AI blocks (AI-ONLY, no fallback key): entity_coverage/client_profile (text, editable), data_categories/categories (categories, editable, gate_by_flag client.flags), data_processing_characteristics/processing_bullets (bullets, editable:false, grounding:false).
- Visible-failure contract: AI generation failure with no user-edited/stored content must fail visibly (error + retry), never render empty.
- Static blocks carry golden ngo_healthcare wording in default: values (config alone reproduces Mission for Vision).
- Phases bind {{ phases.<key>.title }}; phase_4 enabled_when treat_optional_as: enabled.

## Engine contract (declared in the config header)
- anti-dead-key: every library top key (obligations, cover_letter, addons, outcomes, assumptions, phases, standard_terms, annexures) referenced by >=1 block via path/config_default.
- render namespaces: client, cnk, commercials, timeline, retention, narrative, ai (ai.industries + ai.industries_phrase), computed, library, phases, sections (per-section heading/blocks payloads).
- override_input (narrative) beats block default when non-empty; filter_by_toggle; gate_by_flag drops requires_flag items; overrides_from scope.bullet_overrides.<phase>.
- master docx binds: {%p for blk in sections.X.blocks %}, {{ sections.data_categories.heading }}, {{ phases.phase_X.title }}, {%tr for m in milestones %}, inline {% if %} (docxtpl syntax).
- lint block (denylist + 7 rules) declared — execution deferred out of engine v1.
# Config Restructure: AI-Only Industries, Inline Toggles, Unified Version

## 1. Objective

The user is defining the configuration contract for config-driven document generation in the
Document-Automation repo. The intended end state of this task:

- From **one config file** (`documents/config_v2.yaml`) a reader can identify:
  1. **which sections** the generated document contains,
  2. **how each section's content is produced** (static content vs AI-generated with its prompt),
  3. **which inputs** must be collected from the user.
- The **master template** (`documents/master_dpdpa_ia_v2.docx`) continues to carry only
  structure/alignment/references (layout, styles, tables, SmartArt, TOC field, page geometry).

Four explicit restructuring requirements were given:

1. **Industries become AI context only.** "Industries" content exists exclusively as
   user-entered input values that are injected into AI prompts. Every section marked
   `ai` must be *AI-only* — no fallback may be declared for AI blocks.
2. **Toggles move into `inputs:`** — toggles are just a kind of input; no top-level
   `toggles:` block.
3. **The top-level `industries:` content-variant library is removed completely.**
4. **`config_version` and `template_version` are combined into a single `version` key.**

Two design decisions were confirmed by the user during planning:

- **D1:** the `client.profile` textarea (previously only an AI fallback) is **kept and
  relabelled as optional AI context**, injected into the Client-Profile AI prompt when
  non-empty (no fallback semantics).
- **D2:** the golden (industry-variant) wording that currently has no other copy is
  **promoted into the static blocks' `default:` values**, so the restructured config alone
  still reproduces `Mission_for_Vision-DPDPA_IA_Proposal_V1.docx` faithfully.

This is a **configuration-contract change only**. No application code, DB schema, API or
runtime files change (none currently consume this config — verified). The plan also records
the verification result for the master template: **no modifications required** (§4.x).

---

## 2. Context

### Artifacts in scope (all under `documents/`, all untracked in git — `git status` shows `?? documents/`)

| Artifact | Role |
| :--- | :--- |
| `documents/config_v2.yaml` | 1,336-line structured config (the ONLY file modified in this task) |
| `documents/master_dpdpa_ia_v2.docx` | Jinja-in-DOCX master layout — **verified: unchanged** |
| `documents/Mission_for_Vision-DPDPA_IA_Proposal_V1.docx` | Golden/source instance — unchanged |

### Verified repository facts

- **No engine exists in this repo**: `engine/manifest.py`, `engine/schema_builder.py`,
  `engine/computed.py`, `content/<service>/config.yaml`, `template_store/` and
  `docs/plan-config-driven-document-generation.md` do **not** exist (glob-verified).
  The config's header comments describe conventions from a prior materialisation;
  until the engine is built, validation of those conventions is structural/manual only.
- Existing docs plans (`docs/plan-clients-frontend-ui.md`, `docs/plan-clients-app-crud.md`)
  belong to unrelated tasks and are **not** touched.
- Config structure today (line anchors of the current file, pre-edit):
  - header conventions comment: lines 1–58
  - identity scalars (`config_version`/`template_version`): lines 61–64
  - top-level `toggles:` block: lines 66–87
  - `inputs:` block: lines 88–208 (toggle consumers at 145–146; `industry` select at 130–140;
    `client.profile` at 120)
  - `computed:`: 214–222; `smartart:`: 224–241; `lint:`: 243–257
  - `industries:` content-variant block: 259–402 (to be deleted)
  - `library:`: 404–751; `sections:` manifest: 753–1336 (33 sections, 3 AI blocks)
- Master template binding inventory (from decomposition): `{{ sections.*.by_id.* }}` typed
  bindings, `{%p for blk in sections.X.blocks %}` loops, variant headings bound as
  `{{ sections.data_categories.heading }}` / `{{ sections.impact_enable.heading }}` /
  `{{ sections.annexure_*.heading }}`, phase titles bound as `{{ phases.<key>.title }}`,
  addon box table loop, milestones `{%tr for m in milestones %}` row loop, inline
  `{% if %}` conditionals. **None of these depend on** `industries:`, `fallback:`,
  `industry_key`, the top-level `toggles:` block, or the version keys — so removing them
  from config does not touch the master (the resolver keeps emitting the same
  `sections.*` / `phases.*` context shapes from the restructured config).

### Consumers / dependencies

- Nothing in the repo consumes this config yet (no engine). Future engine work must honour
  the restructured contract (encoded in the rewritten header comment).
- `computed.ai_industries_phrase` and the `ai_context` input group (`ai.industries`)
  **remain** — they are the user-input side of "industries" and feed every AI prompt.

### Constraints discovered

- Golden verbatim details preserved so far (trailing spaces in headings, `\t` in subject
  line, curly quotes) must **not** be lost by the edit — edits must be surgical.
- The file is a working-tree artifact (untracked); no commit/push/deploy is part of this task.

---

## 3. What / Why / How to Build

All changes are inside `documents/config_v2.yaml`.

### 3.1 Combine the version keys (Requirement 4)

**What** — replace (current lines 63–64):

```yaml
config_version: 2
template_version: v2            # resolves template_store/master_dpdpa_ia_v2.docx
```

**with:**

```yaml
version: 2                      # single config + template version; resolves the
                                # master layout: documents/master_dpdpa_ia_v2.docx
```

**Why** — one version governs config schema and template pairing (`master_<service>_v<version>.docx`);
removes the possibility of divergent config/template revisions.

**Decision D-date:** value is the numeric `2` (matches both the current config revision and
the `v2` in the master filename). Assumption to verify during future engine work: version
is interpolated into the filename pattern; if a string like `v2` is preferred later it is a
one-line change in the same key.

### 3.2 Move toggles into `inputs:` (Requirement 2)

**What**
- Delete the whole top-level block (current lines 66–87), including its banner comment.
- In `inputs:` → group `scope`, replace the two reference-style fields

  ```yaml
  - { key: scope.phases, label: Phases, type: phase_toggles, required: false, from: toggles.phases }
  - { key: scope.addons, label: Add-ons, type: addon_toggles, required: false, from: toggles.addons }
  ```

  with inline definitions:

  ```yaml
  - key: scope.phases
    label: Phases
    type: phase_toggles
    required: false
    items:
      - { key: phase_1,  default: true }
      - { key: phase_2a, default: true }
      - { key: phase_2b, default: true }
      - { key: phase_3,  default: true }
      - { key: phase_4,  default: optional }   # 'optional' = rendered with disclaimer ON
  - key: scope.addons
    label: Add-ons
    type: addon_toggles
    required: false
    items:
      - { key: dpo_service,  default: true }
      - { key: consent_mgmt, default: true }
      - { key: ropa,         default: true }
  ```

**Why** — toggles are a type of input; declaring them inline makes `inputs:` the single home
of everything the user provides. `scope_key` is dropped because the field key already *is*
the scope path (`scope.phases`).

**How** — keep `type: phase_toggles` / `addon_toggles` and `enabled_when`,
`filter_by_toggle` semantics unchanged: they still reference the scope paths
(`scope.phases`, `scope.addons`), which remain input paths. Labels for individual toggle
items continue to be derived by the future form-schema builder from
`library.phases.<key>.label` / `library.addons.addons[key].title` — nothing is duplicated.

### 3.3 Remove the `industries:` block (Requirement 3)

**What** — delete current lines 259–402: the `INDUSTRIES` banner comment and the whole
`industries:` mapping (`ngo_healthcare` variants).

**Why** — with AI blocks AI-only and inputs as the single source of per-client context, a
per-industry *content-variant* library is dead weight. Its role collapses to either
(AI-generated content) or (static block defaults, §3.5).

### 3.4 AI blocks become AI-only; industries context stays (Requirement 1)

**What**
1. Remove the `fallback:` line from all three AI blocks:
   - `sections.entity_coverage.blocks[id=client_profile]` —
     delete `fallback: { source: input, path: client.profile }`
   - `sections.data_categories.blocks[id=categories]` —
     delete `fallback: { source: industry, path: data_categories }`
   - `sections.data_processing_characteristics.blocks[id=processing_bullets]` —
     delete `fallback: { source: industry, path: data_processing_bullets }`
2. Update the Client-Profile prompt to accept the user context input (decision D1): insert,
   directly after the `Client organisation:` line:

   ```yaml
         {% if client.profile %}Additional user-provided context about the organisation:
         {{ client.profile }}

         {% endif %}Entities/subsidiaries covered: {{ computed.entities_phrase }}
   ```

   (rest of the prompt unchanged)
3. Relabel the corresponding input (current line 120):

   ```yaml
   - { key: client.profile, label: Client Profile (AI context, optional), type: textarea, required: false, default: '', hint: 'When non-empty, it is injected into the Client Profile AI prompt as user-supplied context.', meta: { rows: 8 } }
   ```

4. Remove the `industry` select input entirely from group `reference` (current lines 130–140,
   including the `NOTE:` comment about the upstream template-master step): it exists to
   select a static content variant that no longer exists, and its `options_from: industries`
   would resolve to nothing.

**Why** — an `ai` block must never render library/industry text instead of generated content;
user inputs (industries, profile, client details, website) are *context inputs* only.

**AI failure contract (new, encode in header conventions — §3.6):** with no fallback,
if AI generation fails and no user-edited/stored content exists, generation must **fail
visibly** (error state surfaced to the user with retry) — it must never silently render an
empty or placeholder block.

### 3.5 Promote golden text into static block defaults (decision D2) and drop `industry_key`

For every static block that consumed `industries.<industry>.<key>` via `industry_key:`,
remove the `industry_key:` line and set/replace the block's `default:` with the golden
(ngo_healthcare) wording transcribed from the removed block. Exact values:

| Section | Block id | Action |
| :--- | :--- | :--- |
| `data_categories` | `heading` | remove `industry_key: data_categories_heading`; keep default `What is Personal Data for {{ client.name }}` (already golden-equivalent) |
| `data_categories` | `intro` | remove `industry_key: data_categories_intro`; replace default with golden: `'Based on our understanding of {{ client.name }}''s activities and programs, we believe that the organization processes personal data across multiple operational, programme, healthcare, donor and support functions. The nature of personal data may include the following:'` |
| `data_processing_characteristics` | `heading` | remove `industry_key: data_processing_characteristics_heading` (default text identical to golden — keep) |
| `data_processing_characteristics` | `intro` | remove `industry_key: data_processing_characteristics_intro` (default text identical to golden — keep) |
| `impact_enable` | `heading` | remove `industry_key: impact_enable_heading` (default text identical to golden — keep) |
| `impact_enable` | `bullets` | remove `industry_key: impact_bullets`; promote golden 7-bullet list: *"Identify and address DPDPA compliance gaps" / "Strengthen personal data privacy and security" / "Enhance stakeholder trust and accountability" / "Improve regulatory readiness" / "Strengthen beneficiary and patient data protection" / "Enhance third-party and data-sharing governance" / "Embed privacy-by-design practices across operations"* |
| `objective` | `bullets` | remove `industry_key: objective_bullets`; promote golden 9-bullet list (from removed `industries.ngo_healthcare.objective_bullets`, verbatim) |
| `conclusion_assessment` | `paragraphs` | remove `industry_key: conclusion_assessment_paragraphs`; promote golden 4-paragraph list (verbatim) |
| `timelines` | `paragraphs` | remove `industry_key: timelines_paragraphs`; promote golden 2 paragraphs: *"The Phase 1 to 3 will be executed over a period of {{ timeline.duration_weeks }} weeks. Covering planning, assessment, remediation support, and ongoing compliance assurance activities."* / *"Phase 4 comprises of On-Going Compliance Support which is a quarterly activity.  The time to be spent for each quarter will be decided on a mutually agreed scope at that juncture."* (note: the double space after "activity." is verbatim-golden) |
| `timelines` | `timeline_context` | remove `industry_key: timeline_context_default`; set default to golden: `'For {{ client.name }}, these obligations apply across key operational touchpoints, communities and internal HR, payroll, and vendor management systems.'`; keep `override_input: narrative.timeline_context` |

**Related input fix:** `inputs` → group `narrative` → field `narrative.timeline_context`
(current lines 191–196): remove `default_from: industries.<industry>.timeline_context_default`
and leave `default: ''` (mirrors the other narrative override fields; when left empty the
block default above renders — behaviour identical to today's industry-selected output).

### 3.6 Rewrite the header conventions comment

The header (lines 1–58) is the written contract; it must describe the restructured config.
Surgical changes, keeping the file's comment style:

1. **Title line** — suffix `(RESTRUCTURED)` and note: industries variance removed (AI-only),
   toggles embedded in inputs, single `version` key.
2. **HISTORY paragraph** — replace the stale promotion note (it references
   `docs/plan-config-driven-document-generation.md` and `template_store/master_dpdpa_ia_v1.docx`,
   neither of which exists in this repo) with: restructured per
   `docs/plan-config-restructure-industries-ai-toggles-version.md`; materialisation baseline
   unchanged (`documents/Mission_for_Vision-DPDPA_IA_Proposal_V1.docx` +
   `documents/master_dpdpa_ia_v2.docx`).
3. **NOTE paragraph** — keep the verbatim-transcription and anti-dead-key sentences; remove
   the `industries:` registry-compatibility clause.
4. **CONVENTIONS bullets**:
   - DELETE the bullet *“industry-variant static text: block declares industry_key …”*.
   - UPDATE the `ai blocks` bullet: fields are `prompt` (Jinja, MUST reference
     `{{ ai.industries_phrase }}`), `output_schema`, `grounding`, `editable`, `label` —
     **no `fallback` may be declared**; state the AI-failure contract from §3.4
     (fail visibly; never silent emptiness).
   - UPDATE the *AI resolution order* bullet: `user-edited ai.<block_id>` >
     `stored Proposal.ai_content_json` > `freshly generated` — final, **no fallback**.
   - ADD bullet: *toggles live only inside `inputs:` (`phase_toggles`/`addon_toggles`
     fields carry inline `items[]` with defaults; no top-level `toggles:` block; the field
     key is the toggle scope path used by `enabled_when` and `filter_by_toggle`)*.
   - UPDATE the *Render context namespaces* bullet: remove
     `industry (selected industries entry)`; keep `ai (ai.industries + ai.industries_phrase)`.
5. **Inputs banner comment (lines 88–97)** — update the base-identity sentence:
   `service/version/proposal_date/reference_number/validity_days/client_id/created_by`
   (removing `template_version` and `industry`); keep the sentence about AI-block fields
   being auto-appended by the form-schema builder. Everything else stays.

### 3.7 What must NOT change

- `sections:` count (33), order, headings (verbatim trailing spaces), groups, `enabled_when`
  semantics, `gate_by_flag: client.flags` on the categories AI block (kept; future engine
  gates only items that explicitly carry `requires_flag`).
- `library:` block entirely (all keys remain referenced — anti-dead-key intact).
- `computed:` (incl. `ai_industries_phrase`), `smartart:`, `lint:` blocks.
- `ai.industries` input (group `ai_context`) — the surviving "industries" face: user-entered,
  AI-context-only, injected as `{{ ai.industries_phrase }}`.
- All three DOCX artifacts other than within `config_v2.yaml` itself.

---

## 4. Technical Specification

### Architecture changes

Conceptual, declared in the config contract (no code in repo yet):

- **Content variance model** shrinks from three sources (static/config, AI, industry-variant)
  to two (static/config, AI). "Industries" is redefined as *user input context* (`ai.industries`)
  feeding AI prompts, not a content library.
- **Single-version contract**: one `version` key governs both config revision and master
  template pairing.

### Data flow

```text
inputs (incl. inline toggle items, ai.industries, client.profile-as-context)
  → computed: (derived values)
  → resolver (future engine):
        context namespaces: client, cnk, commercials, timeline, retention,
        narrative, ai, computed, library, phases, sections
        (NO `industry` namespace)
  → AI blocks: prompts ← context; AI-only output (no fallback);
        failure ⇒ visible generation error
  → template_store/master_dpdpa_ia_v2.docx bindings unchanged
  → rendered .docx
```

### Master template changes

**Not applicable — verified unchanged.** Binding inventory of
`documents/master_dpdpa_ia_v2.docx` (headings bound as `{{ sections.<id>.heading }}`,
`{{ phases.<key>.title }}`, all `sections.*.by_id.*` typed blocks, `{%p %}` loops,
`{%tr for m in milestones %}`, inline `{% if %}`, SmartArt drawings, TOC field) contains no
reference to `industries:`, `fallback:`, `industry_key`, the top-level `toggles:` block, or
the version keys. The resolver keeps emitting identical `sections.*` / `phases.*` shapes, so
the master's bindings resolve unchanged against the restructured config. Heading default
texts promoted per §3.5 match the golden headings already bound in the master.

### API changes

Not applicable.

### Database/schema changes

Not applicable.

### Backend changes

Not applicable (no application code touches this config).

### Frontend changes

Not applicable.

### Configuration changes

Everything in §3 operates on `documents/config_v2.yaml` only: header rewrite, identity
scalars, top-level `toggles:` removal, inputs restructuring (toggle inline items,
`industry` select removal, `client.profile` relabel), `industries:` deletion, AI-block
fallback removal + prompt context injection, static-default promotions, narrative
`default_from` fix.

### Security considerations

- No new inputs, endpoints or secrets. Removed `industry` select shrinks accepted input surface.
- AI-only contract removes a failure mode where library text could mask a prompt-generation
  regression (silent degradation); replace with explicit error surfacing (§3.4).
- Prompt injection surface note (informational): `client.profile`, `client.website`,
  `ai.industries` are user-supplied free text injected into AI prompts; future engine should
  keep treating AI output as untrusted data (render via text runs, never as layout) — this
  matches the existing resolver design where content binds inside text bodies only.

### Error handling

- New contract: AI block generation failure ⇒ visible error state + retry in the future
  UI; never an empty/placeholder render. Encoded as a header conventions bullet (§3.6).
- All other error handling unchanged (`gate_by_flag`, `enabled_when`,
  `filter_by_toggle`, lint rules).

### Validation

Executor-side validation (structural — the manifest validator does not exist in this repo):

1. **YAML parse + assertions** (read-only, no env modification):

   `uv run --with pyyaml python -c "<assert-script>"` from repo root, asserting:
   - file parses; top-level keys are exactly: `service`, `display_name`, `version`,
     `inputs`, `computed`, `smartart`, `lint`, `library`, `sections`
     (no `config_version`, `template_version`, `toggles`, `industries`);
   - `version == 2`; `len(sections) == 33`;
   - exactly 3 blocks with `source: ai`; **none** has a `fallback` key;
   - **no** block has `industry_key`; **no** field has `options_from: industries`;
     **no** field has `default_from: industries…`;
   - `inputs` scope group: `scope.phases` has 5 `items`, `scope.addons` has 3 `items`,
     no `from:` key;
   - exactly 3 occurrences of `validation: base` (reference_number, proposal_date,
     validity_days);
   - no reference group field named `industry`;
   - `client.profile` label contains “AI context”;
   - every `library.*` top-level key still referenced by ≥1 `config_ref` block path
     (anti-dead-key).

2. **Grep audits** on the file (must all be clean):
   `industry_key` → 0; `fallback:` → 0; `source: industry` → 0; `^toggles:` → 0;
   `from: toggles` → 0; `^industries:` → 0; `options_from:` → 0; `config_version` → 0;
   `template_version` → 0.
   Expected remaining `industr*` matches: `ai.industries`, `ai_context` group,
   `computed.ai_industries_phrase`, `ai_industries_phrase` prompt references, and the
   English word "Industry / sectors" inside AI prompts.

3. **Diff review**: `git diff documents/config_v2.yaml` read-through — confirm the 33
   section ids/order unchanged, golden verbatim artifacts preserved (subject-line `\t`,
   heading trailing spaces), and no incidental reformatting of untouched YAML.

### Performance considerations

Not applicable (declarative file; future engine parse cost reduced by ~150 lines removed).

### Compatibility considerations

- Section/block context shapes emitted to the template are unchanged ⇒ master template
  modification avoided entirely (important: keeps the committed master artifact stable).
- Removed top-level keys (truthy `toggles:`, `industries:`, duplicate version keys) must
  disappear rather than remain for compatibility — the engine does not exist yet, so there
  is no consumer to break; the future engine implements the restructured contract only.
- `gate_by_flag` semantics note for future engine: on AI `categories` output, gate only
  items explicitly carrying `requires_flag` (industry-style items no longer exist).

### Testing strategy

- T1–T2 above (structural validation) are the automated portion, run as **read-only
  commands** by the executor.
- T3: diff read-through (behavioural invariants: 33 sections, 3 AI blocks, verbatim
  golden-text promotions, master-visible heading defaults match golden headings).
- T4 (deferred): real manifest/lint enforcement belongs to the future engine build and must
  be covered by that task's plan — cannot be run here (blocker, see §2).

### Deployment considerations

- Nothing is deployed; `documents/` is currently untracked in git, so all changes remain
  working-tree changes until the user asks to commit. No commit/push in this task.

---

## 5. Change Template

| File | Change Type | Proposed Change | Reason |
| :--- | :--- | :--- | :--- |
| `documents/config_v2.yaml` | Modify | Rewrite header comment block: title suffix, restructured HISTORY (drop stale engine/plan references), NOTE without industries clause, conventions: delete industry-variant bullet, AI-only ai-block bullet + visible-failure contract, 3-step AI resolution order (no fallback), new toggles-in-inputs bullet, namespaces without `industry` | Header is the contract; must match the restructured config |
| `documents/config_v2.yaml` | Modify | Replace `config_version: 2` + `template_version: v2` with single `version: 2` (comment: resolves `documents/master_dpdpa_ia_v2.docx`) | Requirement 4 — one version governs config + template |
| `documents/config_v2.yaml` | Modify | Delete top-level `toggles:` block; expand `inputs` → scope fields `scope.phases` / `scope.addons` with inline `items[]` (defaults preserved incl. `phase_4: optional`), drop `scope_key`, remove `from: toggles.*` | Requirement 2 — toggles are inputs |
| `documents/config_v2.yaml` | Modify | Delete the whole `industries:` mapping (banner comment + `ngo_healthcare` variants, current lines 259–402) | Requirement 3 — remove content-variant library |
| `documents/config_v2.yaml` | Modify | Inputs: remove `industry` select field (+ its `options_from`/NOTE comment) from group `reference`; relabel `client.profile` to “Client Profile (AI context, optional)” with new hint; fix `narrative.timeline_context` (drop `default_from: industries…`, keep `default: ''`); update inputs banner base-identity list (`version`, no `industry`/`template_version`) | Forced consequences of §3.4/§3.6; prevents dangling references |
| `documents/config_v2.yaml` | Modify | AI blocks: delete `fallback:` from `client_profile`, `categories`, `processing_bullets`; add conditional user-context injection (`{% if client.profile %}…`) into the client_profile prompt | Requirement 1 — AI-only, no fallbacks; D1 |
| `documents/config_v2.yaml` | Modify | Static blocks: remove `industry_key:` (10 occurrences) and promote golden defaults per §3.5 table (data_categories intro; impact bullets ×7; objective bullets ×9; conclusion_assessment paragraphs ×4; timelines paragraphs ×2; timelines.timeline_context text; heading blocks keep identical defaults) | D2 — config alone reproduces the golden document |

Explicitly **out of scope** (verified, not modified):
`documents/master_dpdpa_ia_v2.docx`, `documents/Mission_for_Vision-DPDPA_IA_Proposal_V1.docx`,
all files under `src/`, `docs/plan-clients-*.md`, `tests/`, settings, dependencies.

---

## 6. To-Do Matrix

| File / Change | Proposed Action | Executed | Tested | Deployed |
| :--- | :--- | :---: | :---: | :---: |
| `documents/config_v2.yaml` | Rewrite header comment block (title/HISTORY/NOTE/conventions/namespaces) | [x] | [x] | [ ] |
| `documents/config_v2.yaml` | Merge `config_version` + `template_version` → `version: 2` | [x] | [x] | [ ] |
| `documents/config_v2.yaml` | Delete top-level `toggles:` block; inline items into `inputs` scope fields | [x] | [x] | [ ] |
| `documents/config_v2.yaml` | Delete `industries:` block (lines ~259–402) | [x] | [x] | [ ] |
| `documents/config_v2.yaml` | Remove `industry` select input; relabel `client.profile`; fix `narrative.timeline_context`; update inputs banner | [x] | [x] | [ ] |
| `documents/config_v2.yaml` | Remove `fallback:` from 3 AI blocks; add user-context injection to client_profile prompt | [x] | [x] | [ ] |
| `documents/config_v2.yaml` | Drop 10 `industry_key:` lines; promote golden static defaults (§3.5 table) | [x] | [x] | [ ] |
| `documents/config_v2.yaml` | Structural validation T1 (uv+pyyaml assertions) and T2 grep audits; diff review T3 | [x] | [x] | [ ] |

> Execution note (2026-10-26): T1/T2 ran via `uv run --with pyyaml` — 25/25 checks PASS
> (top-level keys, `version: 2`, 33 sections, 3 AI blocks with no fallback and prompts intact,
> no residual `industry_key`/`options_from`/`from:`/`default_from: industries` refs, inline
> toggle items incl. `phase_4: optional`, exactly 3 `validation: base` fields, client.profile
> relabeled, anti-dead-key library refs complete, all grep audits 0; the only remaining
> `fallback:` strings are the 2 computed list_phrase fn args, which the plan keeps).
> T2 `industr*` sweep: clean after allowing the plan-doc filename and the English phrase
> "industry practices" in golden library content. T3: `git diff --no-index` vs pre-edit
> snapshot (temp copy) — 15 hunks, +83/−244, every hunk maps to a planned edit; promoted
> golden defaults verified byte-identical to the deleted industries lines. File is now
> 1,175 lines (was 1,336).

---

## 7. Sources

Repository artifacts (read/analyzed directly — no external web/MCP research was required):

- `documents/config_v2.yaml` — read in full (1,336 lines; structure, line anchors, all
  `industry_key`/`fallback` occurrences, toggles/version blocks, sections manifest).
- `documents/master_dpdpa_ia_v2.docx` — decomposed (stdlib XML walk): heading/style/text
  outline, Jinja `{%p %}`/`{%tr %}`/`{{ }}` binding inventory, tables, TOC field, diagrams.
- `documents/Mission_for_Vision-DPDPA_IA_Proposal_V1.docx` — decomposed: golden paragraph
  outline, page geometry, SmartArt parts (`data1–3.xml`), TOC field, footer.
- Repository structure checks: glob over `documents/`, `src/**`, `docs/`, root (confirmed
  absence of `engine/`, `content/`, `template_store/`, referenced plan file; confirmed only
  two `*config*`/`*master*` artifacts in repo).
- `git status --porcelain documents/` — documents/ untracked (working-tree-only artifact).
- Outline dumps from the decomposition investigation:
  `C:\Users\LT-IS-07\AppData\Local\Temp\opencode\outline_master_dpdpa_ia_v2.txt`,
  `C:\Users\LT-IS-07\AppData\Local\Temp\opencode\outline_Mission_for_Vision-DPDPA_IA_Proposal_V1.txt`
  (scratch artifacts, not project files).
- User confirmations (this session): D1 (client.profile kept as AI context) and D2 (golden
  static text promoted into defaults), plus the four restructuring requirements.
- Unrelated existing plan docs observed but untouched: `docs/plan-clients-frontend-ui.md`,
  `docs/plan-clients-app-crud.md`.

---

## 8. Summary

The plan restructures `documents/config_v2.yaml` (its version keys, inputs, and
AI/content-variance model) so that the single config reads as the authoritative map of
*sections → content generation method (static vs AI-with-prompt) → user inputs*, while the
master template remains purely the structural/alignment artifact:

1. **AI-only AI blocks** — all three `source: ai` blocks lose their `fallback:`; the
   industries concept survives only as user input (`ai.industries` → `{{ ai.industries_phrase }}`
   prompt context; plus `client.profile` as optional prompt context, per D1). AI failure
   becomes a visible error, never silent substitution.
2. **Toggles fold into `inputs:`** — `scope.phases`/`scope.addons` become self-contained
   `phase_toggles`/`addon_toggles` fields with inline `items[]` (defaults preserved,
   including `phase_4: optional`).
3. **`industries:` deleted entirely** — its golden wording that lacks any other copy is
   promoted into the affected static blocks' `default:` values (D2), so the config still
   reproduces the Mission for Vision proposal faithfully.
4. **Single `version: 2`** replaces `config_version`/`template_version`; the master template
   pairing (`master_dpdpa_ia_v2.docx`) is preserved.

**Scope:** one file (`documents/config_v2.yaml`, ~150 lines net removed). Master template,
golden DOCX, source code, settings, DB, and existing plans are untouched. Structural
validation (YAML assertions + grep audits + diff review) is executable immediately;
formal manifest/lint enforcement is deferred to the future engine build, which becomes the
sole substantive dependency for further verification.

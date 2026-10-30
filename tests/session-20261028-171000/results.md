# E2E Rerun Results (post-fix, combined)

OPENCODE_BIN env absent; settings.OPENCODE_BIN='opencode'

Run 1 (e2e_rerun.log): acme + bharat + error contracts; technova blocked by
provider.quota (free-tier, non-defect). Completion run: technova live +
error contracts + D4 acceptance + golden markers + DB hygiene.

Total checks: 113; FAIL: 2

- [PASS] acme_ngo: GET /templates/ -> 200
- [PASS] acme_ngo: list contains row w/ full shape
- [PASS] acme_ngo: GET schema -> 200
- [PASS] acme_ngo: schema has 3 ai_sections
- [PASS] acme_ngo: AI client_profile (text) -> 200
- [PASS] acme_ngo: AI client_profile no tool-debris
- [PASS] acme_ngo: AI profile industry-fit keyword
- [PASS] acme_ngo: AI categories (categories) -> 200
- [PASS] acme_ngo: AI categories categories shape
- [PASS] acme_ngo: AI categories no tool-debris
- [PASS] acme_ngo: AI processing_bullets (bullets) -> 200
- [PASS] acme_ngo: AI processing_bullets bullets shape
- [PASS] acme_ngo: POST preview -> 200 docx
- [PASS] acme_ngo: filename slugified reference
- [PASS] acme_ngo: package has document+diagrams
- [PASS] acme_ngo: doc contains client name
- [PASS] acme_ngo: heading binds name
- [PASS] acme_ngo: fee golden
- [PASS] acme_ngo: milestone Rs.   607500
- [PASS] acme_ngo: milestone Rs.   810000
- [PASS] acme_ngo: ordinal date golden
- [PASS] acme_ngo: FY golden
- [PASS] acme_ngo: profile text in doc
- [PASS] acme_ngo: first category title in doc
- [PASS] acme_ngo: first processing bullet in doc
- [PASS] acme_ngo: doc no tool-debris
- [PASS] acme_ngo: data2 client-name node
- [PASS] acme_ngo: data2 role Medical Director
- [PASS] acme_ngo: data2 role Program Lead
- [PASS] acme_ngo: data2 role HR Head
- [PASS] acme_ngo: data2 role IT Head
- [PASS] acme_ngo: data2 role Finance Head
- [PASS] acme_ngo: data2 partner patched
- [PASS] acme_ngo: data2 manager patched
- [PASS] acme_ngo: data3 weekly
- [PASS] acme_ngo: phase_4 on
- [PASS] acme_ngo: phase_4 disclaimer
- [PASS] acme_ngo: registry row rolled back
- [PASS] bharat_manufacturing: GET /templates/ -> 200
- [PASS] bharat_manufacturing: list contains row w/ full shape
- [PASS] bharat_manufacturing: GET schema -> 200
- [PASS] bharat_manufacturing: schema has 3 ai_sections
- [PASS] bharat_manufacturing: AI client_profile (text) -> 200
- [PASS] bharat_manufacturing: AI client_profile no tool-debris
- [PASS] bharat_manufacturing: AI profile industry-fit keyword
- [PASS] bharat_manufacturing: AI categories (categories) -> 200
- [PASS] bharat_manufacturing: AI categories categories shape
- [PASS] bharat_manufacturing: AI categories no tool-debris
- [PASS] bharat_manufacturing: AI processing_bullets (bullets) -> 200
- [PASS] bharat_manufacturing: AI processing_bullets bullets shape
- [PASS] bharat_manufacturing: POST preview -> 200 docx
- [PASS] bharat_manufacturing: filename slugified reference
- [PASS] bharat_manufacturing: package has document+diagrams
- [PASS] bharat_manufacturing: doc contains client name
- [PASS] bharat_manufacturing: heading binds name
- [PASS] bharat_manufacturing: fee golden
- [PASS] bharat_manufacturing: milestone Rs.   450000
- [PASS] bharat_manufacturing: milestone Rs.   600000
- [PASS] bharat_manufacturing: ordinal date golden
- [PASS] bharat_manufacturing: FY golden
- [PASS] bharat_manufacturing: profile text in doc
- [PASS] bharat_manufacturing: first category title in doc
- [PASS] bharat_manufacturing: first processing bullet in doc
- [PASS] bharat_manufacturing: doc no tool-debris
- [PASS] bharat_manufacturing: data2 client-name node
- [PASS] bharat_manufacturing: data2 role Plant Head
- [PASS] bharat_manufacturing: data2 role Quality Head
- [PASS] bharat_manufacturing: data2 role Legal Head
- [PASS] bharat_manufacturing: data2 partner kept (disabled)
- [PASS] bharat_manufacturing: data3 weekly
- [PASS] bharat_manufacturing: phase_4 off ù body blanked
- [PASS] bharat_manufacturing: phase_4 off ù only stale TOC mentions Sustain
- [PASS] bharat_manufacturing: phase_4 off ù disclaimer absent
- [PASS] bharat_manufacturing: registry row rolled back
- [PASS] technova_fintech: GET /templates/ -> 200
- [PASS] technova_fintech: list contains row w/ full shape
- [PASS] technova_fintech: GET schema -> 200
- [PASS] technova_fintech: schema has 3 ai_sections
- [PASS] technova_fintech: AI client_profile (text) -> 200
- [PASS] technova_fintech: AI client_profile no tool-debris
- [PASS] technova_fintech: AI profile industry-fit keyword
- [PASS] technova_fintech: AI categories (categories) -> 200
- [PASS] technova_fintech: AI categories categories shape
- [PASS] technova_fintech: AI categories no tool-debris
- [FAIL] technova_fintech: AI processing_bullets (bullets) -> 200  -- status=502 body=b'{"detail":"AI generation failed: assistant output is not valid JSON","code":"ai_generation_failed"}'
- [FAIL] technova_fintech: POST preview -> 200 docx  -- status=400 ct=application/json
- [PASS] err: schema unknown -> 404
- [PASS] err: schema inactive -> 404
- [PASS] err: list excludes inactive
- [PASS] err: list excludes missing-file row
- [PASS] err: schema missing config -> 409 code
- [PASS] err: preview missing config -> 409
- [PASS] err: schema missing template -> 409 code
- [PASS] err: schema invalid config -> 400 invalid_config
- [PASS] err: preview unknown key -> 400
- [PASS] err: preview w/o ai_content -> 400 missing_ai_content
- [PASS] err: preview required empty -> 400
- [PASS] err: preview malformed categories -> 400
- [PASS] err: AI empty body -> 400
- [PASS] err: AI bad schema -> 400
- [PASS] err: AI unresolved vars -> 400 code
- [PASS] err: AI bridge failure -> 502 code
- [PASS] d4: subject line & verbatim
- [PASS] d4: phase 2a title & verbatim
- [PASS] d4: phase 2b title & verbatim
- [PASS] d4: phase 3 title & verbatim
- [PASS] d4: risk-list title & verbatim
- [PASS] d4: golden section headings & verbatim
- [PASS] d4: bharat_manufacturing AI &-title verbatim (former FAIL)
- [PASS] d4: technova_fintech AI &-title verbatim (former FAIL)
- [PASS] markers sanity present in golden file
- [PASS] all markers present in fresh acme render
- [PASS] DB clean: no E2E rows at end (as found)

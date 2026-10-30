# HTTP Smoke Results

Total: 10; FAIL: 0

- [PASS] http: GET /templates/ -> 200 + row present
- [PASS] http: GET schema -> 200 + 3 ai_sections
- [PASS] http: POST /ai/generate-section/ -> 200 (real opencode, default env)
- [PASS] http: AI content non-empty text, no debris
- [PASS] http: AI organic-food industry fit
- [PASS] http: POST preview -> 200 docx
- [PASS] http: preview filename attachment+slug
- [PASS] http: D4 & verbatim over HTTP (phase 2a title)
- [PASS] http: D4 & verbatim over HTTP (subject line)
- [PASS] http: golden & verbatim over HTTP (standard terms)

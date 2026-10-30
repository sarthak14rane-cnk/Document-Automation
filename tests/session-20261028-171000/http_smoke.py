"""Live-HTTP smoke against a running runserver (127.0.0.1:8765) — real sockets,
NO OPENCODE_BIN env (D1/D3 proof over HTTP). Args: <template_id>.
Artifacts -> session dir; results -> http_smoke.md."""
import html
import io
import json
import re
import socket
import sys
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

SESSION = Path(__file__).resolve().parent
REPO = SESSION.parent.parent
sys.path.insert(0, str(REPO / "src" / "document_generator"))
BASE = "http://127.0.0.1:8765"
TID = int(sys.argv[1])
socket.setdefaulttimeout(180)

RESULTS = []


def check(name, cond, detail=""):
    RESULTS.append((name, "PASS" if cond else "FAIL", detail))
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}"
          + (f"  -- {detail}" if detail and not cond else ""), flush=True)


def get(path):
    with urllib.request.urlopen(BASE + path) as r:
        return r.status, dict(r.headers), r.read()


def post(path, payload):
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()


# 1. list ------------------------------------------------------------------
st, _, body = get("/templates/")
rows = json.loads(body)
(SESSION / "http_list.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
check("http: GET /templates/ -> 200 + row present",
      st == 200 and any(r["template_id"] == TID for r in rows), f"status={st}")

# 2. schema ----------------------------------------------------------------
st, _, body = get(f"/templates/{TID}/schema/")
schema = json.loads(body)
(SESSION / "http_schema.json").write_text(json.dumps(schema, indent=2), encoding="utf-8")
ai_sections = schema.get("ai_sections", [])
check("http: GET schema -> 200 + 3 ai_sections",
      st == 200 and len(ai_sections) == 3, f"status={st} n={len(ai_sections)}")
prompt = ai_sections[0]["prompt"]
assert "\n" in prompt

# 3. REAL AI over HTTP (no OPENCODE_BIN in this process tree) ---------------
body = {
    "prompt": prompt,
    "output_schema": "text",
    "industries": ["Organic Food Retail", "Agri Supply Chain"],
    "client_context": {
        "name": "GreenLeaf Organic Foods Pvt Ltd",
        "short_name": "GreenLeaf",
        "website": "https://greenleaf.example",
        "entities": ["GreenLeaf Farms", "GreenLeaf Retail LLP"],
        "profile": "",
    },
}
t0 = time.time()
st, _, raw = post("/ai/generate-section/", body)
elapsed = time.time() - t0
payload = json.loads(raw)
content = payload.get("content") if st == 200 else None
(SESSION / "http_ai_greenleaf.json").write_text(
    json.dumps({"status": st, "content": content, "elapsed_s": elapsed}, indent=2),
    encoding="utf-8",
)
check("http: POST /ai/generate-section/ -> 200 (real opencode, default env)",
      st == 200, f"status={st} body={raw[:250]!r}")
if content:
    check("http: AI content non-empty text, no debris",
          isinstance(content, str) and content.strip() and "<tool_use" not in content,
          str(content)[:200])
    blob = content.lower()
    check("http: AI organic-food industry fit",
          any(k in blob for k in ("organic", "farm", "food", "supply", "retail")),
          content[:200])
    print(f"    AI over HTTP: {elapsed:.1f}s -> {content[:150]!r}", flush=True)

# 4. preview over HTTP (real render; inputs + run-1 AI content) ------------
import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings")
import django

django.setup()
from template_master.tests import full_inputs  # noqa: E402

inputs = full_inputs()
ai_content = json.loads(
    (SESSION / "ai_content_acme_ngo.json").read_text(encoding="utf-8")
)
st, headers, raw = post(f"/templates/{TID}/preview/", {"inputs": inputs, "ai_content": ai_content})
cd = headers.get("Content-Disposition", "")
check("http: POST preview -> 200 docx",
      st == 200 and "wordprocessingml.document" in headers.get("Content-Type", ""),
      f"status={st} ct={headers.get('Content-Type')}")
check("http: preview filename attachment+slug",
      "attachment" in cd and "cnkpropc5026-27.docx" in cd, cd)
if st == 200:
    (SESSION / "preview_http.docx").write_bytes(raw)
    print(f"    preview over HTTP: {len(raw)} bytes", flush=True)
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        doc_xml = z.read("word/document.xml")
    text = html.unescape(re.sub(r"<[^>]+>", "", doc_xml.decode("utf-8", "replace")))
    (SESSION / "extracted_http.txt").write_text(text, encoding="utf-8")
    check("http: D4 & verbatim over HTTP (phase 2a title)",
          "Governance, Policy & Compliance Framework Design" in text)
    check("http: D4 & verbatim over HTTP (subject line)",
          "Impact Analysis & Compliance for Acme Eye Care Foundation" in text)
    check("http: golden & verbatim over HTTP (standard terms)",
          "STANDARD TERMS & CONDITIONS" in text)

fails = [r for r in RESULTS if r[1] == "FAIL"]
print(f"\n=== HTTP SMOKE: {len(RESULTS)} checks, {len(fails)} FAIL ===", flush=True)
lines = ["# HTTP Smoke Results", "", f"Total: {len(RESULTS)}; FAIL: {len(fails)}", ""]
for n, s, d in RESULTS:
    lines.append(f"- [{s}] {n}" + (f"  -- {d}" if d and s == "FAIL" else ""))
(SESSION / "http_smoke.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
sys.exit(1 if fails else 0)

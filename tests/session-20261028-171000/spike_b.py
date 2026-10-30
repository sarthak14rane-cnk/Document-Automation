"""Spike B (fix-plan §4): real multi-line client_profile prompt through
generate_section with NO OPENCODE_BIN override -> must succeed with
opencode/mimo-v2.6-flash-free via npm-shim resolution (D1+D3 acceptance)."""
import json
import os
import sys
import time
from pathlib import Path

SESSION = Path(__file__).resolve().parent
REPO = SESSION.parent.parent
sys.path.insert(0, str(REPO / "src" / "document_generator"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings")
os.environ.pop("OPENCODE_BIN", None)  # prove DEFAULT settings only

import django

django.setup()

from django.conf import settings
from loguru import logger

assert "OPENCODE_BIN" not in os.environ, "env override present!"
print(f"settings.OPENCODE_BIN (default): {settings.OPENCODE_BIN!r}")
print(f"settings.OPENCODE_MODEL (default): {settings.OPENCODE_MODEL!r}")

from engine.ai_bridge import generate_section
from engine.computed import list_phrase
from engine.manifest import load_config, resolve_under_documents_root
from engine.schema_builder import build_form_schema
from template_master.views import AISectionView

config = load_config("documents/config_v2.yaml")
schema = build_form_schema(config)
ai_sections = schema["ai_sections"]
sec = next(s for s in ai_sections if s["block_id"] == "client_profile")
raw_prompt = sec["prompt"]
assert "\n" in raw_prompt, "prompt is not multi-line!"
print(f"raw prompt lines: {len(raw_prompt.splitlines())}  schema: {sec['output_schema']}")

client_context = {
    "name": "GreenLeaf Organic Foods Pvt Ltd",
    "short_name": "GreenLeaf",
    "website": "https://greenleaf.example",
    "entities": ["GreenLeaf Farms", "GreenLeaf Retail LLP"],
    "profile": "",
}
industries = ["Organic Food Retail", "Agri Supply Chain"]
prompt_context = {
    "client": client_context,
    "ai": {
        "industries": list(industries),
        "industries_phrase": list_phrase(industries, "the organisation"),
    },
    "computed": {
        "entities_phrase": list_phrase(
            client_context.get("entities"), "its operating entities"
        ),
    },
}
rendered = AISectionView._render_prompt(raw_prompt, prompt_context)
assert "\n" in rendered
print(f"rendered prompt chars: {len(rendered)}")

records = []
sink = logger.add(records.append, level="INFO")
t0 = time.time()
try:
    content = generate_section(rendered, "text")
finally:
    logger.remove(sink)
elapsed = time.time() - t0

joined = "\n".join(str(r) for r in records)
bin_lines = [ln for ln in joined.splitlines() if "AI_BRIDGE_BIN" in ln]
ok_lines = [ln for ln in joined.splitlines() if "AI_BRIDGE_OK" in ln]
fail_lines = [ln for ln in joined.splitlines() if "AI_BRIDGE_FAILED" in ln]
mismatch = [ln for ln in joined.splitlines() if "AI_BRIDGE_MODEL_MISMATCH" in ln]

print(f"\n--- bridge log evidence ({elapsed:.1f}s) ---")
for ln in bin_lines + ok_lines + fail_lines + mismatch:
    print(" ", ln.strip())

results = []
def check(name, cond, detail=""):
    results.append((name, cond, detail))
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f"  -- {detail}" if not cond else ""))

check("no OPENCODE_BIN env override", "OPENCODE_BIN" not in os.environ)
check("resolution logged (AI_BRIDGE_BIN)", bool(bin_lines), "missing")
check(
    "resolved to real opencode.exe (npm-shim parse)",
    any("opencode.exe" in ln for ln in bin_lines),
    bin_lines[0] if bin_lines else "no bin log",
)
check("AI_BRIDGE_OK logged", bool(ok_lines), "missing")
check(
    "requested model mimo-v2.6-flash-free",
    any("model=opencode/mimo-v2.6-flash-free" in ln for ln in ok_lines),
    ok_lines[0] if ok_lines else "no OK log",
)
check("non-empty text result", isinstance(content, str) and bool(content.strip()),
      repr(content)[:120])
check("no tool debris in result", "<tool_use" not in content, content[:200])
check("no mismatch warning needed", not mismatch, str(mismatch))

(SESSION / "spike_b_result.txt").write_text(
    json.dumps({"elapsed_s": elapsed, "content": content}, indent=2), encoding="utf-8"
)
print(f"\ncontent preview: {content[:300]!r}")
fails = [n for n, c, d in results if not c]
print(f"\n=== SPIKE B: {len(results)} checks, {len(fails)} FAIL ===")
sys.exit(1 if fails else 0)

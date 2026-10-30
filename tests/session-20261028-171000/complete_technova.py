"""Complete the post-fix E2E battery after free-tier quota recovery.

Run 1 (e2e_rerun.log): acme 33/33 + bharat 28/28 PASS, error contracts 16/16,
d4 partial 7 PASS, then technova's categories/bullets hit provider.quota
(free-tier limit — NOT a defect; resolution/invocation had already succeeded
for 7/7 prior calls). This script:
  1. seeds run-1 PASS/FAIL lines for acme + bharat ONLY (others re-run fresh);
  2. re-runs technova live (3 real AI calls + preview + content checks);
  3. re-runs error contracts + D4 acceptance + golden markers + DB hygiene;
  4. writes the combined results.md (exit 1 if any FAIL remains)."""
import os
import re
import sys
from pathlib import Path

SESSION = Path(__file__).resolve().parent
sys.path.insert(0, str(SESSION))  # e2e_rerun lives beside this file

import e2e_rerun as E  # django setup happens here; main() is guarded

# --- 1. seed run-1 results (acme + bharat only) ----------------------------
raw = (SESSION / "e2e_rerun.log").read_bytes()
enc = "utf-16" if raw[:2] in (b"\xff\xfe", b"\xfe\xff") else "utf-8"
log_text = raw.decode(enc, errors="replace")
seeded = 0
for m in re.finditer(r"^  \[(PASS|FAIL)\] (.+?)(?:  -- (.*))?$", log_text, re.M):
    name, status, detail = m.group(2), m.group(1), (m.group(3) or "").strip()
    if not (name.startswith("acme_ngo:") or name.startswith("bharat_manufacturing:")):
        continue  # everything else is re-run fresh below (incl. run-1 technova FAILs)
    E.RESULTS.append((name, status, detail))
    seeded += 1
print(f"[complete] seeded {seeded} run-1 checks (acme + bharat)", flush=True)

# --- 2. technova live ------------------------------------------------------
E.TemplateMaster.objects.filter(template_name__startswith="E2E").delete()
E.run_client_flow(next(fx for fx in E.CLIENTS if fx["key"] == "technova_fintech"))

# --- 3. fresh sections -----------------------------------------------------
E.run_error_contracts()
E.run_d4_acceptance()
E.run_golden_markers()
E.run_db_hygiene()

# --- 4. combined results ---------------------------------------------------
fails = [r for r in E.RESULTS if r[1] == "FAIL"]
print(f"\n=== COMBINED SUMMARY: {len(E.RESULTS)} checks, {len(fails)} FAIL ===", flush=True)
lines = [
    "# E2E Rerun Results (post-fix, combined)",
    "",
    E.ENV_NOTE,
    "",
    "Run 1 (e2e_rerun.log): acme + bharat + error contracts; technova blocked by",
    "provider.quota (free-tier, non-defect). Completion run: technova live +",
    "error contracts + D4 acceptance + golden markers + DB hygiene.",
    "",
    f"Total checks: {len(E.RESULTS)}; FAIL: {len(fails)}",
    "",
]
for name, status, detail in E.RESULTS:
    lines.append(
        "- [" + status + "] " + name + (f"  -- {detail}" if detail and status == "FAIL" else "")
    )
(SESSION / "results.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
print(f"results.md written ({len(E.RESULTS)} checks)", flush=True)
sys.exit(1 if fails else 0)

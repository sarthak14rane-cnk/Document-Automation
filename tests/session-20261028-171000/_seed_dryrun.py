"""Dry-run: validate seeding parse of run-1 log (no AI, no results.md)."""
import re
import sys
from pathlib import Path

SESSION = Path(__file__).resolve().parent
raw = (SESSION / "e2e_rerun.log").read_bytes()
enc = "utf-16" if raw[:2] in (b"\xff\xfe", b"\xfe\xff") else "utf-8"
text = raw.decode(enc, errors="replace")
seed = [
    (m.group(1), m.group(2), (m.group(3) or "").strip())
    for m in re.finditer(r"^  \[(PASS|FAIL)\] (.+?)(?:  -- (.*))?$", text, re.M)
]
acme_bharat = [s for s in seed if s[1].startswith(("acme_ngo:", "bharat_manufacturing:"))]
others = [s for s in seed if not s[1].startswith(("acme_ngo:", "bharat_manufacturing:"))]
print("encoding:", enc, "| total check lines:", len(seed))
print("will seed (acme+bharat):", len(acme_bharat),
      "PASS:", sum(1 for s in acme_bharat if s[0] == "PASS"),
      "FAIL:", sum(1 for s in acme_bharat if s[0] == "FAIL"))
print("will skip (re-run fresh):", len(others))
for s in others:
    print("   skip:", s[0], s[1][:70])
sample = text[:200]
print("head repr:", repr(sample[:120]))
sys.exit(0 if acme_bharat else 1)

"""A1 liveness spike: real (unmocked) call through engine.ai_bridge."""
import os
import sys
import time

sys.path.insert(0, r"C:\Users\LT-IS-07\PycharmProjects\Document-Automation\src\document_generator")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings")

import django

django.setup()

from engine.ai_bridge import generate_section
from engine.errors import AIError

start = time.time()
try:
    content = generate_section(
        "Reply with the single word: PONG",
        "text",
    )
    print(f"SPIKE_OK elapsed={time.time()-start:.1f}s content={content!r}")
except AIError as exc:
    print(f"SPIKE_AIERROR elapsed={time.time()-start:.1f}s error={exc}")
    sys.exit(2)
except Exception as exc:  # noqa: BLE001 -- spike must report anything unexpected
    print(f"SPIKE_UNEXPECTED elapsed={time.time()-start:.1f}s error={type(exc).__name__}: {exc}")
    sys.exit(3)

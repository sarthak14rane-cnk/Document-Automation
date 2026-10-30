"""opencode bridge — the ONLY module that shells out to opencode (§3.6).

User requirements honoured here:
- separate dedicated module (no other engine/app module calls opencode);
- headless ``opencode run`` CLI subprocess (decision #1), never TUI automation.

A1 spike (verified live against opencode v2.0.28, ``--format json``):
    {"type":"step_start","timestamp":...,"sessionID":...,"part":{...}}
    {"type":"text","timestamp":...,"sessionID":...,"part":{"type":"text",
     "text":"PONG",...}}
    {"type":"error", ...,"error":{"type":"provider.auth","message":...}}
  -> NDJSON event stream; assistant text lives in ``part.text`` of ``text``
  events; failures surface as ``error`` events (and non-zero exit codes).

A2 (cwd): the subprocess runs with ``cwd`` = DOCUMENTS_ROOT by default, so
``opencode run`` inherits this repository's project context. If repository
instructions visibly pollute generation, point ``cwd`` at a neutral scratch
directory via the ``cwd`` argument.

D1/D3 fix (verified live 2026-10-28, opencode v2.0.28): npm installs only
``opencode.cmd``/``opencode.ps1`` shims on Windows, so the bare default name
used to fail with WinError 2 (D1), and going through ``opencode.cmd`` made
cmd.exe re-parse the command line — splitting multi-line prompts at newlines
and (prompt-first argv) dropping ``--format``/``--model`` → silent fallback
to the subscription-gated default model → 502 for every real prompt (D3).
``resolve_opencode_bin`` maps the name onto a real executable and argv now
puts flags BEFORE the positional prompt (Spike A: accepted by v2.0.28, keeps
the flags applied even in degraded .cmd mode). Spike C: neither successful
stdout NDJSON nor stderr exposes the served model, so the
AI_BRIDGE_MODEL_MISMATCH warning is a best-effort no-op today (the defensive
scan stays for future envelopes). D2: ``_strip_tool_debris`` removes
``<tool_use>`` transcripts before validation for every schema (logged).

Default model: ``mimo-v2.6-flash-free`` on the free ``opencode`` provider
(user decision 2026-10-26; the ``opencode-go`` default currently fails with
provider.auth 403 without an active Go subscription). ``model_id`` may also
arrive per-request from the AI endpoint JSON (bare ids are prefixed with the
default provider).

Output contract: parse assistant text, strip code fences, json.loads, then
validate against ``output_schema`` (text -> non-empty str; bullets -> list of
non-empty str; categories -> list of {id,title,summary,bullets[str]}). One
full retry on parse/validation failure; timeout or exhausted retries raise
:class:`AIError` — visible failure, never empty content.
"""

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from django.conf import settings
from loguru import logger

from .errors import AIError

DEFAULT_PROVIDER = "opencode"
_FENCE_RE = re.compile(r"^\s*```[A-Za-z0-9_-]*\s*|\s*```\s*$")
_MAX_CAPTURED = 200_000  # defensive cap per captured stream


def normalize_model(model):
    """Accept 'model-id' or 'provider/model-id'; default from settings."""
    if not model:
        return None
    model = str(model).strip()
    if not model:
        return None
    if "/" in model:
        return model
    return f"{DEFAULT_PROVIDER}/{model}"


_SHIM_QUOTED_EXE_RE = re.compile(r'"([^"]+\.exe)"', re.IGNORECASE)
_SHIM_BARE_EXE_RE = re.compile(r"(\S+\.exe)", re.IGNORECASE)


def _shim_target_exe(shim_path):
    """Best-effort: the ``...\\*.exe`` an npm-style .cmd/.bat shim forwards to.

    npm shims are formulaic — e.g. ``"%dp0%\\node_modules\\@opencode\\cli\\
    bin\\opencode.exe" %*`` — so extracting the first ``.exe`` target makes the
    shim's directory (``%dp0%``) resolve to the real binary. Foreign/unreadable
    shim layouts return None so the caller falls back to the shim itself
    (degraded but visible)."""
    if shim_path.suffix.lower() not in (".cmd", ".bat"):
        return None
    try:
        text = shim_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    match = _SHIM_QUOTED_EXE_RE.search(text) or _SHIM_BARE_EXE_RE.search(text)
    if not match:
        return None
    target = match.group(1)
    target = target.replace("%dp0%", str(shim_path.parent) + os.sep)
    target = target.replace("%~dp0%", str(shim_path.parent) + os.sep)
    candidate = Path(target)
    if not candidate.is_absolute():
        candidate = shim_path.parent / candidate
    candidate = Path(os.path.normpath(str(candidate)))  # "%dp0%\\node_modules" doubles
    return candidate if candidate.is_file() else None


def resolve_opencode_bin(raw):
    """Resolve ``OPENCODE_BIN`` to an executable CreateProcess can run (D1).

    Order (fix plan §3.1):
      1. explicit override containing a path separator, or an existing file
         → used as-is (``OPENCODE_BIN`` may point straight at opencode.exe);
      2. bare name → prefer ``<name>.exe`` found anywhere on PATH (real
         executables win over npm shims);
      3. ``shutil.which`` (PATHEXT-aware; may return an npm ``.cmd``/``.bat``
         shim);
      4. shim → its target ``...\\*.exe`` (avoids cmd.exe re-parsing, which
         split multi-line prompts and dropped the flags → silent model
         fallback, D3);
      5. nothing resolves → :class:`AIError` naming OPENCODE_BIN (visible
         failure, consistent with this module's contract).
    """
    raw = (raw or "").strip()
    if not raw:
        raise AIError("OPENCODE_BIN is empty; set it to the full path of opencode.exe")
    if (
        os.path.isfile(raw)
        or os.path.sep in raw
        or (os.path.altsep and os.path.altsep in raw)
    ):
        return raw
    for directory in os.environ.get("PATH", "").split(os.pathsep):
        if not directory:
            continue
        candidate = os.path.join(directory, raw if raw.lower().endswith(".exe") else f"{raw}.exe")
        if os.path.isfile(candidate):
            return candidate
    resolved = shutil.which(raw)
    if resolved:
        target = _shim_target_exe(Path(resolved))
        if target:
            logger.info("AI_BRIDGE_BIN_RESOLVED shim={} exe={}", resolved, target)
            return str(target)
        return resolved
    raise AIError(
        f"opencode binary {raw!r} not found on PATH; "
        "set OPENCODE_BIN to the full path of opencode.exe"
    )


def _strip_fences(text):
    """Remove markdown code fences around a payload."""
    text = text.strip()
    if text.startswith("```"):
        text = _FENCE_RE.sub("", text, count=0)
    return text.strip()


_TOOL_BLOCK_RE = re.compile(r"<tool_use\b.*?</tool_use>", re.DOTALL | re.IGNORECASE)
_TOOL_FRAGMENT_RES = tuple(
    re.compile(rf"<{name}\b.*?</{name}>", re.DOTALL | re.IGNORECASE)
    for name in ("tool_name", "tool_input", "tool_use_error")
)


def _strip_tool_debris(text):
    """Remove opencode ``<tool_use>`` transcripts from assistant text (D2).

    Strips whole tool blocks plus stray fragments, collapses 3+ blank lines
    and strips the result. Debris-only text becomes empty here, so the normal
    empty-output retry → visible AIError contract still applies. Logs
    AI_BRIDGE_DEBRIS_STRIPPED whenever tool markup was actually removed.
    """
    if not text:
        return ""
    cleaned = _TOOL_BLOCK_RE.sub("", text)
    for pattern in _TOOL_FRAGMENT_RES:
        cleaned = pattern.sub("", cleaned)
    if cleaned != text:
        logger.warning("AI_BRIDGE_DEBRIS_STRIPPED bytes={}", len(text) - len(cleaned))
    return re.sub(r"\n{3,}", "\n\n", cleaned).strip()


def _scan_model(obj):
    """Best-effort: first non-empty ``modelID``/``model`` string in an event (D3)."""
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key in ("modelID", "model") and isinstance(value, str) and value.strip():
                return value.strip()
            found = _scan_model(value)
            if found:
                return found
    elif isinstance(obj, list):
        for item in obj:
            found = _scan_model(item)
            if found:
                return found
    return None


def _extract_assistant_text(stdout):
    """Parse the NDJSON event stream defensively; returns (text, errors, model).

    ``model`` is the first ``modelID``/``model`` value found anywhere in the
    events — best-effort served-model detection (Spike C 2026-10-28: current
    opencode envelopes expose none, so it stays ``None`` today).
    """
    texts, errors, parsed_any = [], [], False
    served_model = None
    for line in (stdout or "").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        parsed_any = True
        if not isinstance(event, dict):
            continue
        if served_model is None:
            served_model = _scan_model(event)
        if event.get("type") == "error":
            error = event.get("error") or {}
            message = error.get("message") or json.dumps(event)[:500]
            errors.append(str(message))
            continue
        part = event.get("part") if isinstance(event.get("part"), dict) else event
        if part.get("type") == "text" and isinstance(part.get("text"), str):
            texts.append(part["text"])
        elif isinstance(event.get("text"), str):
            texts.append(event["text"])
    if not parsed_any and (stdout or "").strip():
        # Non-JSON fallback: treat the whole stream as plain assistant text.
        return stdout.strip()[:_MAX_CAPTURED], [], None
    return "\n".join(texts)[:_MAX_CAPTURED], errors, served_model


def _validate(text, output_schema):
    """Returns (parsed_content, None) on success or (None, reason) on failure."""
    text = _strip_tool_debris((text or "").strip())  # D2: tool transcripts out first
    if not text:
        return None, "empty assistant text"
    if output_schema == "text":
        content = _strip_fences(text)
        if not content:
            return None, "empty text content"
        return content, None

    payload = _strip_fences(text)
    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError:
        return None, "assistant output is not valid JSON"
    if output_schema == "bullets":
        if not isinstance(parsed, list) or not parsed:
            return None, "expected a non-empty JSON array of strings"
        if not all(isinstance(item, str) and item.strip() for item in parsed):
            return None, "every bullet must be a non-empty string"
        return [item for item in parsed], None
    if output_schema == "categories":
        if not isinstance(parsed, list) or not parsed:
            return None, "expected a non-empty JSON array of category objects"
        for index, item in enumerate(parsed):
            if not isinstance(item, dict):
                return None, f"category {index} is not an object"
            for key in ("id", "title", "summary"):
                value = item.get(key)
                if not isinstance(value, str) or not value.strip():
                    return None, f"category {index}: {key!r} missing/empty"
            bullets = item.get("bullets")
            if (
                not isinstance(bullets, list)
                or not bullets
                or not all(isinstance(b, str) and b.strip() for b in bullets)
            ):
                return None, f"category {index}: bullets must be non-empty strings"
        return parsed, None
    return None, f"unsupported output_schema {output_schema!r}"


def _run_once(argv, timeout, cwd):
    try:
        proc = subprocess.run(
            argv,
            shell=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            cwd=str(cwd),
        )
    except subprocess.TimeoutExpired as exc:
        # subprocess.run already killed the child process on timeout.
        raise AIError(f"opencode run timed out after {timeout}s") from exc
    except OSError as exc:
        raise AIError(f"opencode binary could not be executed: {exc}") from exc
    stdout = (proc.stdout or "")[:_MAX_CAPTURED]
    stderr = (proc.stderr or "")[:4000]
    return proc.returncode, stdout, stderr


def generate_section(prompt, output_schema, model=None, timeout=None, cwd=None):
    """Generate one section via headless ``opencode run`` (synchronous).

    Retries once on parse/validation or non-zero-exit failures; timeouts and
    exhausted retries raise AIError (visible failure contract).
    """
    if timeout is None:
        timeout = getattr(settings, "OPENCODE_TIMEOUT", 180)
    if cwd is None:
        cwd = getattr(settings, "DOCUMENTS_ROOT", ".")

    resolved_bin = resolve_opencode_bin(getattr(settings, "OPENCODE_BIN", "opencode"))
    logger.info("AI_BRIDGE_BIN path={}", resolved_bin)
    resolved_model = normalize_model(model or getattr(settings, "OPENCODE_MODEL", None))
    # Flags BEFORE the positional prompt (Spike A, opencode v2.0.28): even if
    # a .cmd shim lets cmd.exe split a multi-line prompt, --format/--model
    # still apply (D3 degraded mode fails visibly, never silently on another
    # model).
    argv = [resolved_bin, "run", "--format", "json"]
    if resolved_model:
        argv += ["--model", resolved_model]
    argv.append(str(prompt))

    last_reason = "unknown failure"
    for attempt in (1, 2):  # one full retry per plan §3.6
        returncode, stdout, stderr = _run_once(argv, timeout, cwd)
        if returncode != 0:
            last_reason = (
                f"opencode exited with code {returncode}"
                + (f"; stderr: {stderr.strip()[:500]}" if stderr.strip() else "")
            )
            continue
        text, errors, served_model = _extract_assistant_text(stdout)
        if errors and not text:
            last_reason = "; ".join(errors)[:500]
            continue
        parsed, reason = _validate(text, output_schema)
        if parsed is not None:
            if attempt == 1:
                logger.info("AI_BRIDGE_OK model={} schema={}", resolved_model, output_schema)
            if served_model and resolved_model and served_model != resolved_model:
                # Best-effort observable for silent model fallbacks (D3).
                logger.warning(
                    "AI_BRIDGE_MODEL_MISMATCH requested={} served={}",
                    resolved_model,
                    served_model,
                )
            return parsed
        last_reason = reason

    logger.error(
        "AI_BRIDGE_FAILED model={} schema={} reason={}", resolved_model, output_schema, last_reason
    )
    raise AIError(f"AI generation failed: {last_reason}")

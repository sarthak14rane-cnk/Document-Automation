"""Render-context assembly (§3.2) — inputs + AI content -> docxtpl context.

``build_context(config, inputs, ai_content)`` returns the single context dict
handed to the master template. Layout mirrors the namespaces declared in the
config header: client / cnk / commercials / timeline / retention / narrative /
ai / computed (executed) / library / phases (bridge) / sections (payloads),
plus top-level computed merges (total_fee_indian, milestones, ...) and the
identity base values (reference_number, proposal_date, validity_days,
client_id, created_by, service, version).

The template's actual binding inventory (documents/master_dpdpa_ia_v2.docx)
consumes:
- ``{{ sections.<id>.by_id.<block>.text|paragraphs|bullets|entries|categories }}``
- ``{%p for blk in sections.<id>.blocks %}`` with blk.paragraphs / blk.bullets /
  blk.text  -> every block payload carries ALL payload keys (blank defaults)
- ``{{ sections.<id>.heading }}`` for the 5 resolver-rendered headings
- ``{{ phases.phase_X.title|objective|objective_lead|bullets|... }}`` bridge
  bindings (phase sections bind directly, not via sections loops)
- top-level ``milestones`` rows (label/percent/amount_indian) for the fee
  sentence and the {%tr %} milestone table, plus total_fee_indian.

Block text is pre-rendered server-side (two-pass): library strings carry
inline Jinja ({{ client.name }}, {{ total_fee_indian }}, {% if %} ...) which
docxtpl must never see.

Disabled sections/blocks (toggle gating) are BLANKED — empty strings/lists —
per the config contract ("no {%p if %} needed"). Phase bridge entries blank
their entire namespace entry because the phase bindings are static template
text outside any sections loop.

AI blocks are AI-ONLY: missing/empty content raises MissingAIContentError
listing every affected block id (visible-failure contract).

Raises InputValidationError (field-keyed messages) for unknown / missing /
mistyped inputs, and MissingAIContentError for empty AI blocks.
"""

import datetime
import json
import re
from decimal import Decimal, InvalidOperation

from jinja2 import Environment, StrictUndefined

from . import computed as computed_mod
from .errors import InputValidationError, MissingAIContentError

_JINJA_ENV = Environment(undefined=StrictUndefined, keep_trailing_newline=False)

# Dotted-reference detection for computed args: 'commercials.total_fee' is a
# scope reference; 'Rs. ' / 'its operating entities' are literal strings
# (spaces and non-identifier characters mark literals).
_REFERENCE_RE = re.compile(r"^[A-Za-z_][\w]*(?:\.[A-Za-z_][\w]*)*$")

# Uniform block payload keys (the master's generic block loops iterate
# blk.paragraphs / blk.bullets / blk.text for every block in a section).
_BLOCK_PAYLOAD_KEYS = ("text", "paragraphs", "bullets", "entries", "categories")

_PHASE_STRING_KEYS = (
    "label", "title", "objective", "objective_lead", "deliverables_title",
    "guidance_lead", "disclaimer",
)
_PHASE_LIST_KEYS = ("bullets", "deliverables", "guidance_bullets")


class _Bunch(dict):
    """Dict with attribute access so Jinja resolves dotted paths naturally."""

    def __getattr__(self, item):
        try:
            return self[item]
        except KeyError:
            raise AttributeError(item)


def _resolve_path(scope, dotted):
    """Resolve 'a.b.c' against nested dicts; returns None when any step is absent."""
    current = scope
    for part in str(dotted).split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None
    return current


def _render(template_text, scope):
    """Two-pass server-side render of a Jinja-bearing string (StrictUndefined)."""
    return _JINJA_ENV.from_string(str(template_text)).render(scope)


def _flatten_field_specs(config):
    specs = {}
    for group in config.get("inputs") or []:
        for field in group.get("fields") or []:
            specs[field["key"]] = field
    return specs


# ---------------------------------------------------------------------------
# Input coercion
# ---------------------------------------------------------------------------

def _coerce_text(value):
    return "" if value is None else str(value)


def _coerce_number(value):
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise ValueError("expected a number")
    if isinstance(value, (int, float, Decimal)):
        return value
    text = str(value).strip().replace(",", "")
    try:
        number = Decimal(text)
    except InvalidOperation:
        raise ValueError(f"expected a number, got {value!r}")
    return int(number) if number == number.to_integral_value() else float(number)


def _coerce_boolean(value):
    if isinstance(value, bool):
        return value
    if value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in ("true", "yes", "1"):
            return True
        if lowered in ("false", "no", "0", ""):
            return False
    raise ValueError(f"expected a boolean, got {value!r}")


def _coerce_date(value):
    if value in (None, ""):
        return None
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    if isinstance(value, str):
        text = value.strip().split("T")[0]
        for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"):
            try:
                return datetime.datetime.strptime(text, fmt).date()
            except ValueError:
                continue
    raise ValueError(f"expected a date (YYYY-MM-DD), got {value!r}")


def _coerce_string_list(value):
    if value is None:
        return []
    if isinstance(value, str):
        value = [line for line in (chunk.strip() for chunk in value.splitlines()) if line]
    if not isinstance(value, list):
        raise ValueError("expected a list of strings")
    return [str(item) for item in value]


def _coerce_json_dict(value):
    if value in (None, ""):
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            raise ValueError("expected a JSON object")
        if not isinstance(parsed, dict):
            raise ValueError("expected a JSON object")
        return parsed
    raise ValueError("expected a JSON object")


def _coerce_toggle_dict(value, items):
    """phase_toggles / addon_toggles -> {key: True|False|'optional'}."""
    if value in (None, ""):
        value = {}
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            raise ValueError("expected a toggle object")
    if not isinstance(value, dict):
        raise ValueError("expected a toggle object")
    allowed = {item.get("key"): item.get("default") for item in items or []}
    coerced = {}
    for key, default in allowed.items():
        raw = value.get(key, default)
        if raw == "optional":
            coerced[key] = "optional"
        elif isinstance(raw, bool):
            coerced[key] = raw
        elif raw in (0, 1):
            coerced[key] = bool(raw)
        elif isinstance(raw, str) and raw.strip().lower() in ("true", "false"):
            coerced[key] = raw.strip().lower() == "true"
        else:
            coerced[key] = bool(raw)
    for key in value:
        if key not in allowed:
            raise ValueError(f"unknown toggle key {key!r}")
    return coerced


def _coerce_milestones(value):
    if value in (None, ""):
        return []
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            raise ValueError("expected a list of milestones")
    if not isinstance(value, list):
        raise ValueError("expected a list of milestones")
    rows = []
    for item in value:
        if not isinstance(item, dict):
            raise ValueError("each milestone must be an object with label/percent")
        rows.append({"label": str(item.get("label", "")), "percent": item.get("percent")})
    return rows


_COERCERS = {
    "text": _coerce_text,
    "textarea": _coerce_text,
    "select": _coerce_text,
    "number": _coerce_number,
    "date": _coerce_date,
    "boolean": _coerce_boolean,
    "list": _coerce_string_list,
    "json": _coerce_json_dict,
    "phase_toggles": lambda v, f: _coerce_toggle_dict(v, f.get("items")),
    "addon_toggles": lambda v, f: _coerce_toggle_dict(v, f.get("items")),
    "milestones": _coerce_milestones,
}


def _collect_inputs(config, inputs):
    """Validate + coerce user inputs against the flattened schema."""
    if inputs is None:
        inputs = {}
    if not isinstance(inputs, dict):
        raise InputValidationError({"inputs": "Expected a JSON object of schema keys."})

    specs = _flatten_field_specs(config)
    messages = {}

    # Fixed identity base values (content-agnostic; config-supplied).
    coerced = {
        "service": config.get("service"),
        "version": config.get("version"),
        "client_id": _coerce_number(inputs.get("client_id")) if inputs.get("client_id") not in (None, "") else None,
        "created_by": _coerce_text(inputs.get("created_by") or ""),
    }
    for key in ("client_id", "created_by"):
        inputs.pop(key, None)

    for key in inputs:
        if key not in specs:
            messages[key] = "Unknown input key (not declared in this template's schema)."

    for key, spec in specs.items():
        provided = inputs.get(key)
        if provided is None and "default" in spec:
            provided = spec.get("default")
        field_type = spec.get("type", "text")
        try:
            if field_type in ("phase_toggles", "addon_toggles"):
                value = _COERCERS[field_type](provided, spec)
            else:
                value = _COERCERS.get(field_type, _coerce_text)(provided)
        except ValueError as exc:
            messages[key] = str(exc)
            continue
        if spec.get("required") and value in (None, "", [], {}):
            messages[key] = "This field is required."
            continue
        coerced[key] = value

    if messages:
        raise InputValidationError(messages)
    return coerced


# ---------------------------------------------------------------------------
# Namespaces
# ---------------------------------------------------------------------------

def _build_namespaces(coerced):
    client = _Bunch(
        name=coerced.get("client.name", ""),
        short_name=coerced.get("client.short_name", ""),
        address_lines=list(coerced.get("client.address_lines") or []),
        contact=_Bunch(
            salutation=coerced.get("client.contact.salutation", ""),
            name=coerced.get("client.contact.name", ""),
        ),
        website=coerced.get("client.website", ""),
        entities=list(coerced.get("client.entities") or []),
        profile=coerced.get("client.profile", ""),
        stakeholder_roles=list(coerced.get("client.stakeholder_roles") or []),
        flags=dict(coerced.get("client.flags") or {}),
    )
    cnk = _Bunch(
        partner=_Bunch(
            name=coerced.get("cnk.partner.name", ""),
            designation=coerced.get("cnk.partner.designation", ""),
            email=coerced.get("cnk.partner.email", ""),
            phone=coerced.get("cnk.partner.phone", ""),
        ),
        joint_partner=_Bunch(
            enabled=bool(coerced.get("cnk.joint_partner.enabled") or False),
            name=coerced.get("cnk.joint_partner.name", ""),
            short=coerced.get("cnk.joint_partner.short", ""),
        ),
    )
    commercials = _Bunch(
        total_fee=coerced.get("commercials.total_fee"),
        currency=coerced.get("commercials.currency", "INR"),
        gst_exclusive=bool(coerced.get("commercials.gst_exclusive", True)),
        ope_exclusive=bool(coerced.get("commercials.ope_exclusive", True)),
        milestones=list(coerced.get("commercials.milestones") or []),
    )
    timeline = _Bunch(
        duration_weeks=coerced.get("timeline.duration_weeks", ""),
        reporting=_Bunch(
            weekly_day=coerced.get("timeline.reporting.weekly_day", ""),
            monthly=coerced.get("timeline.reporting.monthly", ""),
        ),
    )
    retention = _Bunch(
        working_papers_years=coerced.get("retention.working_papers_years"),
        reports_years=coerced.get("retention.reports_years"),
    )
    narrative = _Bunch(
        outcome_closing=coerced.get("narrative.outcome_closing", ""),
        timeline_context=coerced.get("narrative.timeline_context", ""),
        conclusion_context=coerced.get("narrative.conclusion_context", ""),
    )
    return client, cnk, commercials, timeline, retention, narrative


def _execute_computed(config, scope, ai):
    """Execute config ``computed:`` declarations against the flat scope."""
    executed = {}
    for name, decl in (config.get("computed") or {}).items():
        fn = computed_mod.FUNCTIONS[decl["fn"]]
        args = {}
        for arg_name, arg_spec in (decl.get("args") or {}).items():
            resolved = _resolve_path(scope, arg_spec) if isinstance(arg_spec, str) else None
            if resolved is not None:
                args[arg_name] = resolved
            elif (
                isinstance(arg_spec, str)
                and _REFERENCE_RE.match(arg_spec)
                and ("." in arg_spec or arg_spec in scope)
            ):
                # Intended reference that resolved to nothing (e.g. an empty
                # milestone list) — pass None through to the function.
                args[arg_name] = None
            else:
                # Literal argument (e.g. prefix 'Rs. ', fallback phrases).
                args[arg_name] = arg_spec
        executed[name] = fn(**args)

    # Contract: ai_industries_phrase is aliased into ai.industries_phrase and
    # ai.industries comes from the inputs.
    ai = dict(ai or {})
    if "ai_industries_phrase" in executed:
        ai["industries_phrase"] = executed["ai_industries_phrase"]
    elif "industries_phrase" not in ai:
        ai["industries_phrase"] = computed_mod.list_phrase(
            ai.get("industries"), "the organisation"
        )
    return executed, ai


# ---------------------------------------------------------------------------
# Toggle / gating helpers
# ---------------------------------------------------------------------------

def _toggle_enabled(toggle_dict, key, treat_optional_as=None):
    value = (toggle_dict or {}).get(key)
    if value == "optional":
        return treat_optional_as == "enabled"
    return bool(value)


def _eval_enabled_when(enabled_when, scope):
    if not enabled_when:
        return True
    if "toggle" in enabled_when:
        toggle_dict = _resolve_path(scope, enabled_when["toggle"]) or {}
        return _toggle_enabled(
            toggle_dict, enabled_when.get("key"), enabled_when.get("treat_optional_as")
        )
    if "input" in enabled_when:
        return _resolve_path(scope, enabled_when["input"]) == enabled_when.get("equals")
    if "key" in enabled_when:  # field-level {key, value} form
        return _resolve_path(scope, enabled_when["key"]) == enabled_when.get("value")
    return True


def _override_value(block, scope, spec):
    """override_input precedence: user value wins over block default (non-empty)."""
    user_value = _resolve_path(scope, block.get("override_input") or "")
    if user_value:
        return str(user_value)
    if block.get("config_default"):
        return _resolve_path(scope, block["config_default"]) or ""
    return block.get("default") or ""


# ---------------------------------------------------------------------------
# Phase bridge context
# ---------------------------------------------------------------------------

def _phase_enabled(section, scope):
    ew = section.get("enabled_when") or {}
    if not ew:
        return True
    return _eval_enabled_when(ew, scope)


def _phase_data(phase_key, config, scope):
    data = (config.get("library") or {}).get("phases", {}).get(phase_key)
    if data is None:
        return None
    rendered = {}
    for key, value in data.items():
        if isinstance(value, list):
            rendered[key] = [_render(item, scope) for item in value]
        elif isinstance(value, str):
            rendered[key] = _render(value, scope)
        else:
            rendered[key] = value
    return rendered


def _blank_phase():
    blank = {key: "" for key in _PHASE_STRING_KEYS}
    blank.update({key: [] for key in _PHASE_LIST_KEYS})
    return blank


def _build_phases(config, scope):
    """Bridge context consumed by the template's static phase bindings."""
    sections_by_phase = {
        section["id"]: section
        for section in config.get("sections") or []
        if isinstance(section, dict)
    }
    phases = {}
    for phase_key in ((config.get("library") or {}).get("phases") or {}):
        section = sections_by_phase.get(phase_key, {})
        if not _phase_enabled(section, scope):
            phases[phase_key] = _blank_phase()
            continue
        data = _phase_data(phase_key, config, scope)
        if data is None:
            phases[phase_key] = _blank_phase()
            continue
        entry = dict(_blank_phase())
        entry.update(data)
        # overrides_from: scope.bullet_overrides.<phase> -> remove/add bullets.
        overrides_from = None
        for block in section.get("blocks") or []:
            if block.get("id") == "phase_data" and block.get("overrides_from"):
                overrides_from = block["overrides_from"]
                break
        if overrides_from:
            overrides = _resolve_path(scope, overrides_from) or {}
            removals = {str(item) for item in overrides.get("remove", [])}
            bullets = [b for b in entry.get("bullets", []) if b not in removals]
            bullets.extend(str(item) for item in overrides.get("add", []))
            entry["bullets"] = bullets
        phases[phase_key] = entry
    return phases


# ---------------------------------------------------------------------------
# Section / block payloads
# ---------------------------------------------------------------------------

def _blank_payload(block_id, block_type):
    payload = {"id": block_id, "type": block_type}
    payload.update({key: ([] if key != "text" else "") for key in _BLOCK_PAYLOAD_KEYS})
    return payload


def _resolve_static_value(block, scope):
    if "text" in block:
        return block["text"]
    if "default" in block:
        return block["default"]
    if block.get("config_default"):
        return _resolve_path(scope, block["config_default"]) or ""
    return ""


def _render_item_entry(item, item_keys, scope):
    """Render one items/boxes/clauses entry with loop-safe uniform keys."""
    entry = {
        "title": "", "intro": "", "body": "",
        "paragraphs": [], "bullets": [], "extra_paragraphs": [],
    }
    for key in item_keys or ("title", "body"):
        value = item.get(key)
        if value is None:
            continue
        if isinstance(value, list):
            entry[key] = [_render(element, scope) for element in value]
        else:
            entry[key] = _render(value, scope)
    # Loop-safety: the template iterates box.paragraphs / box.bullets and
    # it.bullets / it.extra_paragraphs even when a source item omits them.
    if item.get("paragraphs") is not None and "paragraphs" not in (item_keys or []):
        entry["paragraphs"] = [_render(p, scope) for p in item["paragraphs"]]
    if item.get("bullets") is not None and "bullets" not in (item_keys or []):
        entry["bullets"] = [_render(b, scope) for b in item["bullets"]]
    return entry


def _validate_ai_content(block, content):
    schema = block.get("output_schema")
    if schema == "text":
        if not isinstance(content, str) or not content.strip():
            raise ValueError("AI content must be a non-empty string")
        return content
    if schema == "bullets":
        if not isinstance(content, list) or not content:
            raise ValueError("AI content must be a non-empty array of strings")
        for item in content:
            if not isinstance(item, str) or not item.strip():
                raise ValueError("every bullet must be a non-empty string")
        return [str(item) for item in content]
    if schema == "categories":
        if not isinstance(content, list) or not content:
            raise ValueError("AI content must be a non-empty array of category objects")
        categories = []
        for index, item in enumerate(content):
            if not isinstance(item, dict):
                raise ValueError(f"category {index} must be an object")
            for key in ("id", "title", "summary"):
                if not isinstance(item.get(key), str) or not item[key].strip():
                    raise ValueError(f"category {index}: {key!r} must be a non-empty string")
            bullets = item.get("bullets")
            if not isinstance(bullets, list) or not bullets or not all(
                isinstance(b, str) and b.strip() for b in bullets
            ):
                raise ValueError(
                    f"category {index}: bullets must be a non-empty array of strings"
                )
            category = {
                "id": item["id"],
                "title": item["title"],
                "summary": item["summary"],
                "bullets": [str(b) for b in bullets],
            }
            # gate_by_flag contract: items may carry requires_flag, which the
            # gate consumes after validation (must survive normalization).
            requires_flag = item.get("requires_flag")
            if isinstance(requires_flag, str) and requires_flag.strip():
                category["requires_flag"] = requires_flag.strip()
            categories.append(category)
        return categories
    raise ValueError(f"unsupported AI output_schema {schema!r}")


def _gate_by_flag(items, gate_path, scope):
    """Drop items carrying requires_flag when that flag is absent/false."""
    flags = _resolve_path(scope, gate_path) or {}
    gated = []
    for item in items:
        requires_flag = item.get("requires_flag") if isinstance(item, dict) else None
        if requires_flag and not flags.get(requires_flag):
            continue
        gated.append(item)
    return gated


def _build_block_payload(block, scope, ai_content, errors_ai_missing):
    block_id = block["id"]
    block_type = block.get("type")
    payload = _blank_payload(block_id, block_type)
    source = block.get("source")

    if source == "ai":
        content = (ai_content or {}).get(block_id)
        if content in (None, "", [], {}):
            errors_ai_missing.add(block_id)
            return payload
        try:
            content = _validate_ai_content(block, content)
        except ValueError as exc:
            raise InputValidationError({f"ai_content.{block_id}": str(exc)})
        if block.get("gate_by_flag") and block_type == "categories":
            content = _gate_by_flag(content, block["gate_by_flag"], scope)
        if block_type == "paragraphs":
            payload["text"] = content  # golden binds .text for AI paragraphs
        elif block_type == "bullets":
            payload["bullets"] = content
        elif block_type == "categories":
            payload["categories"] = content
        else:
            payload["text"] = content if isinstance(content, str) else ""
        return payload

    if source == "input_loop":
        entries = list(_resolve_path(scope, block.get("input") or "") or [])
        payload["entries"] = [_render(item, scope) for item in entries]
        return payload

    if source == "computed_ref":
        # Milestone table stays in the template layout (top-level loop);
        # the payload documents columns and carries the computed rows.
        rows = _resolve_path(scope, block.get("computed") or "") or []
        payload["entries"] = rows
        payload["columns"] = block.get("columns") or []
        return payload

    if source == "config_ref":
        data = _resolve_path(scope, block.get("path") or "")
        if data is None:
            raise InputValidationError(
                {block_id: f"Config path {block.get('path')!r} resolved to nothing."}
            )
        if block_type in ("text",):
            payload["text"] = _render(data, scope)
        elif block_type == "paragraphs":
            payload["paragraphs"] = [
                _render(item, scope) for item in (data if isinstance(data, list) else [data])
            ]
        elif block_type == "bullets":
            payload["bullets"] = [
                _render(item, scope) for item in (data if isinstance(data, list) else [data])
            ]
        elif block_type in ("items", "boxes", "clause"):
            entries = [
                _render_item_entry(item, block.get("item_keys"), scope)
                for item in (data if isinstance(data, list) else [])
            ]
            if block.get("filter_by_toggle"):
                toggle = _resolve_path(scope, block["filter_by_toggle"]) or {}
                entries = [
                    entry
                    for entry, raw in zip(entries, data)
                    if toggle.get(raw.get("key") or raw.get("id"))
                ]
            payload["entries"] = entries
        elif block_type == "phase":
            # Rendered via the phases bridge namespace, not the block payload.
            pass
        return payload

    # source: static
    if block_type == "text":
        value = _resolve_static_value(block, scope)
        if block.get("override_input"):
            value = _override_value(block, scope, None)
        payload["text"] = _render(value, scope)
    elif block_type == "paragraphs":
        values = block.get("paragraphs")
        if values is None:
            values = block.get("default") or []
        payload["paragraphs"] = [_render(item, scope) for item in values]
    elif block_type == "bullets":
        values = block.get("default") or block.get("bullets") or []
        payload["bullets"] = [_render(item, scope) for item in values]
    elif block_type == "table":
        payload["columns"] = block.get("columns") or []
        payload["rows"] = block.get("rows") or []
    return payload


def _build_sections(config, scope, ai_content, errors_ai_missing):
    sections = {}
    for section in config.get("sections") or []:
        section_id = section["id"]
        if not _phase_enabled(section, scope):
            sections[section_id] = {"heading": "", "blocks": [], "by_id": {}}
            continue
        heading = section.get("heading")
        heading_text = (
            _render(heading["text"], scope) if isinstance(heading, dict) else ""
        )
        by_id = {}
        blocks = []
        for block in section.get("blocks") or []:
            payload = _build_block_payload(block, scope, ai_content, errors_ai_missing)
            by_id[block["id"]] = payload
            blocks.append(payload)
        sections[section_id] = {"heading": heading_text, "blocks": blocks, "by_id": by_id}
    return sections


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def build_context(config, inputs, ai_content):
    """Assemble the full docxtpl render context (plan §3.2)."""
    coerced = _collect_inputs(config, inputs)

    client, cnk, commercials, timeline, retention, narrative = _build_namespaces(coerced)

    scope = {
        # input namespaces
        "client": client, "cnk": cnk, "commercials": commercials,
        "timeline": timeline, "retention": retention, "narrative": narrative,
        "ai": {"industries": list(coerced.get("ai.industries") or [])},
        "scope": {
            "phases": coerced.get("scope.phases") or {},
            "addons": coerced.get("scope.addons") or {},
            "bullet_overrides": coerced.get("scope.bullet_overrides") or {},
        },
        # identity base
        "reference_number": coerced.get("reference_number", ""),
        "proposal_date": coerced.get("proposal_date"),
        "validity_days": coerced.get("validity_days"),
        "client_id": coerced.get("client_id"),
        "created_by": coerced.get("created_by", ""),
        "service": coerced.get("service"),
        "version": coerced.get("version"),
        # populated below
        "computed": {}, "library": config.get("library") or {},
        "phases": {}, "sections": {},
    }

    computed_values, ai = _execute_computed(config, scope, scope["ai"])
    scope["ai"] = ai
    scope["computed"] = computed_values
    # Top-level merges: the template binds {{ total_fee_indian }} and
    # {% for m in milestones %} directly (master binding inventory).
    for name, value in computed_values.items():
        scope.setdefault(name, value)

    scope["phases"] = _build_phases(config, scope)

    errors_ai_missing = set()
    scope["sections"] = _build_sections(config, scope, ai_content, errors_ai_missing)

    if errors_ai_missing:
        # Visible-failure contract: never render an empty/placeholder AI block.
        raise MissingAIContentError(sorted(errors_ai_missing))

    return scope

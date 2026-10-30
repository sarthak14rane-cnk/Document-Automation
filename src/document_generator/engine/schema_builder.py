"""Form-schema builder (§3.2/§3.4) — the payload served by GET schema/.

``build_form_schema(config)`` returns:
    {
      'service', 'display_name', 'version',
      'groups': [config ``inputs:`` groups mirrored 1:1 with normalized fields],
      'base_fields': [fixed identity base fields: service/version (fixed) +
                      client_id/created_by (user-supplied), validation 'base'],
      'ai_sections': [every block with source: ai — raw prompt + output_schema
                      + requires (variables referenced by the prompt)]
    }

The view wraps this with the template registry row (template_id/template_name).
``requires`` combines jinja2.meta.find_undeclared_variables (root names) with
regex-extracted dotted paths (client.name, computed.entities_phrase, ...) so
the frontend knows exactly which inputs to collect before generating.
"""

import re

from jinja2 import Environment
from jinja2.meta import find_undeclared_variables

from .errors import ConfigError

_FIELD_KEYS = (
    "key", "label", "type", "required", "default", "hint", "options",
    "enabled_when", "items", "meta", "validation", "default_from",
)

_PROMPT_JINJA_ENV = Environment()

# Dotted paths like client.name / computed.entities_phrase / ai.industries_phrase
_DOTTED_PATH_RE = re.compile(r"\b((?:client|ai|computed|cnk|commercials|timeline|retention|narrative|scope|library)\.[A-Za-z_][\w.]*)")


def _normalize_field(field):
    normalized = {key: field.get(key) for key in _FIELD_KEYS}
    # `validation: base` markers stay visible; other keys default to None.
    return normalized


def _prompt_requires(prompt):
    """Variable references in the prompt: jinja root names + dotted paths."""
    try:
        roots = find_undeclared_variables(_PROMPT_JINJA_ENV.parse(prompt))
    except Exception:  # pragma: no cover - prompts are manifest-validated
        roots = set()
    dotted = {match.group(1) for match in _DOTTED_PATH_RE.finditer(prompt or "")}
    return sorted(set(roots) | dotted)


def _base_fields(config):
    """Fixed content-agnostic identity base (config header contract)."""
    return [
        {"key": "service", "label": "Service", "type": "text", "required": True,
         "default": config.get("service"), "validation": "base", "fixed": True,
         "value": config.get("service")},
        {"key": "version", "label": "Config Version", "type": "number", "required": True,
         "default": config.get("version"), "validation": "base", "fixed": True,
         "value": config.get("version")},
        {"key": "client_id", "label": "Client ID", "type": "number", "required": False,
         "default": None, "validation": "base", "fixed": False,
         "hint": "Optional link to an existing clients module record."},
        {"key": "created_by", "label": "Created By", "type": "text", "required": False,
         "default": "", "validation": "base", "fixed": False,
         "hint": "User identifier recorded with the generated document."},
    ]


def build_form_schema(config):
    """Build the schema-endpoint JSON body (without the template row wrapper)."""
    if not isinstance(config, dict):
        raise ConfigError("build_form_schema expects a loaded config mapping.")

    groups = []
    for group in config.get("inputs") or []:
        groups.append(
            {
                "group": group.get("group"),
                "title": group.get("title"),
                "fields": [_normalize_field(field) for field in group.get("fields") or []],
            }
        )

    ai_sections = []
    for section in config.get("sections") or []:
        for block in section.get("blocks") or []:
            if block.get("source") != "ai":
                continue
            ai_sections.append(
                {
                    "section_id": section.get("id"),
                    "block_id": block.get("id"),
                    "label": block.get("label"),
                    "type": block.get("type"),
                    "output_schema": block.get("output_schema"),
                    "editable": bool(block.get("editable", False)),
                    "grounding": bool(block.get("grounding", False)),
                    "prompt": block.get("prompt"),
                    "requires": _prompt_requires(block.get("prompt") or ""),
                }
            )

    return {
        "service": config.get("service"),
        "display_name": config.get("display_name"),
        "version": config.get("version"),
        "groups": groups,
        "base_fields": _base_fields(config),
        "ai_sections": ai_sections,
    }

"""Config manifest — loading, path safety and structural validation (§3.2/§3.8).

``load_config(config_path)`` reads a repo-root-relative YAML path, enforces
path safety (resolve_under_documents_root) and validates the config against
the contract declared in the config header:

- required top keys: version / inputs / computed / sections / library
- every section has id / group / blocks (+ valid heading / enabled_when shape)
- every block has id / source / type; AI blocks carry prompt + output_schema
  and MUST NOT declare a fallback (AI-only contract, no library fallbacks)
- every top-level ``library`` key is referenced by at least one block via
  ``path`` or ``config_default`` (anti-dead-key rule)
- ``computed:`` entries reference known functions in engine.computed
- ``smartart:`` entries are part -> list of node mappings with the documented
  shape (nodes / source / optional when / format / skip_if_empty / sparse)

All failures raise :class:`engine.errors.ConfigError` with precise messages.
"""

import os
from pathlib import Path, PurePosixPath

import yaml

from . import computed as computed_mod
from .errors import ConfigError

REQUIRED_TOP_KEYS = ("version", "inputs", "computed", "sections", "library")

SECTION_SOURCES = {"static", "config_ref", "computed_ref", "input_loop", "ai"}
SECTION_TYPES = {
    "paragraphs", "bullets", "items", "categories", "boxes", "table",
    "clause", "text", "toc", "phase", "smartart_asset", "list",
}
AI_OUTPUT_SCHEMAS = {"text", "bullets", "categories"}


def resolve_under_documents_root(rel_path, documents_root=None):
    """Resolve a repo-root-relative path under DOCUMENTS_ROOT (A5).

    Rejects absolute paths, any ``..`` escape, and paths resolving outside
    the documents root. Returns an absolute :class:`pathlib.Path`.
    """
    if documents_root is None:
        from django.conf import settings  # imported lazily; engine stays importable

        documents_root = settings.DOCUMENTS_ROOT
    root = Path(documents_root).resolve()

    candidate = Path(str(rel_path))
    if candidate.is_absolute():
        raise ConfigError(f"Path must be relative to the documents root: {rel_path!r}")
    if ".." in PurePosixPath(str(rel_path).replace("\\", "/")).parts:
        raise ConfigError(f"Path must not escape the documents root: {rel_path!r}")

    resolved = (root / candidate).resolve()
    if resolved != root and not str(resolved).startswith(str(root) + os.sep):
        raise ConfigError(f"Path resolves outside the documents root: {rel_path!r}")
    return resolved


def _validate_inputs(config, errors):
    groups = config.get("inputs")
    if not isinstance(groups, list) or not groups:
        errors.append("inputs: must be a non-empty list of groups.")
        return
    seen_keys = set()
    for gi, group in enumerate(groups):
        if not isinstance(group, dict) or not group.get("group") or not group.get("title"):
            errors.append(f"inputs[{gi}]: each group needs 'group' and 'title'.")
            continue
        fields = group.get("fields")
        if not isinstance(fields, list):
            errors.append(f"inputs[{gi}] ({group['group']}): 'fields' must be a list.")
            continue
        for fi, field in enumerate(fields):
            if not isinstance(field, dict) or not field.get("key"):
                errors.append(f"inputs[{gi}].fields[{fi}]: field needs a 'key'.")
                continue
            key = field["key"]
            if key in seen_keys:
                errors.append(f"inputs[{gi}].fields[{fi}]: duplicate input key {key!r}.")
            seen_keys.add(key)
            if field.get("enabled_when") is not None and not isinstance(
                field["enabled_when"], dict
            ):
                errors.append(f"inputs[{gi}].fields[{fi}] ({key}): enabled_when must be a dict.")


def _validate_sections(config, errors):
    sections = config.get("sections")
    if not isinstance(sections, list) or not sections:
        errors.append("sections: must be a non-empty list.")
        return
    seen_ids = set()
    for si, section in enumerate(sections):
        label = f"sections[{si}]"
        if not isinstance(section, dict):
            errors.append(f"{label}: must be a mapping.")
            continue
        sid = section.get("id")
        if not sid or not isinstance(sid, str):
            errors.append(f"{label}: missing string 'id'.")
            continue
        if sid in seen_ids:
            errors.append(f"{label}: duplicate section id {sid!r}.")
        seen_ids.add(sid)
        if not section.get("group"):
            errors.append(f"{label} ({sid}): missing 'group'.")
        heading = section.get("heading", {})
        if heading not in (False, None) and not (
            isinstance(heading, dict) and "text" in heading
        ):
            errors.append(
                f"{label} ({sid}): heading must be a dict with 'text' or false."
            )
        if section.get("enabled_when") is not None and not _enabled_when_shape(
            section["enabled_when"]
        ):
            errors.append(
                f"{label} ({sid}): enabled_when must be "
                "{toggle, key[, treat_optional_as]} or {input, equals} or {key, value}."
            )
        blocks = section.get("blocks")
        if not isinstance(blocks, list) or not blocks:
            errors.append(f"{label} ({sid}): 'blocks' must be a non-empty list.")
            continue
        for bi, block in enumerate(blocks):
            _validate_block(f"{label} ({sid}).blocks[{bi}]", block, errors)


def _enabled_when_shape(ew):
    if not isinstance(ew, dict):
        return False
    if "toggle" in ew:
        return isinstance(ew.get("key"), str) and ew["key"] != ""
    if "input" in ew:
        return "equals" in ew
    if "key" in ew:  # field-level form: {key, value}
        return "value" in ew
    return False


def _validate_block(label, block, errors):
    if not isinstance(block, dict):
        errors.append(f"{label}: must be a mapping.")
        return
    bid = block.get("id")
    if not bid or not isinstance(bid, str):
        errors.append(f"{label}: missing string 'id'.")
        return
    label = f"{label} ({bid})"
    source = block.get("source")
    if source not in SECTION_SOURCES:
        errors.append(f"{label}: source must be one of {sorted(SECTION_SOURCES)}.")
        return
    if block.get("type") not in SECTION_TYPES:
        errors.append(f"{label}: type must be one of {sorted(SECTION_TYPES)}.")
    if source == "config_ref" and not block.get("path"):
        errors.append(f"{label}: config_ref block needs 'path'.")
    if source == "computed_ref" and not block.get("computed"):
        errors.append(f"{label}: computed_ref block needs 'computed'.")
    if source == "input_loop" and not block.get("input"):
        errors.append(f"{label}: input_loop block needs 'input'.")
    if source == "ai":
        prompt = block.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip():
            errors.append(f"{label}: AI block needs a non-empty 'prompt'.")
        if block.get("output_schema") not in AI_OUTPUT_SCHEMAS:
            errors.append(
                f"{label}: output_schema must be one of {sorted(AI_OUTPUT_SCHEMAS)}."
            )
        if "fallback" in block:
            # AI-only contract: library fallbacks were removed; a declared
            # fallback would silently mask generation failures.
            errors.append(
                f"{label}: AI blocks must not declare 'fallback' (AI-only contract)."
            )


def _validate_computed(config, errors):
    entries = config.get("computed")
    if not isinstance(entries, dict) or not entries:
        errors.append("computed: must be a non-empty mapping of name -> declaration.")
        return
    for name, decl in entries.items():
        if not isinstance(decl, dict) or not decl.get("fn"):
            errors.append(f"computed.{name}: needs a 'fn' declaration.")
            continue
        if decl["fn"] not in computed_mod.FUNCTIONS:
            errors.append(
                f"computed.{name}: unknown function {decl['fn']!r} "
                f"(known: {sorted(computed_mod.FUNCTIONS)})."
            )
        if not isinstance(decl.get("args"), dict):
            errors.append(f"computed.{name}: 'args' must be a mapping.")


def _validate_smartart(config, errors):
    entries = config.get("smartart")
    if entries is None:
        return
    if not isinstance(entries, dict):
        errors.append("smartart: must be a mapping of part -> node mappings.")
        return
    for part, mappings in entries.items():
        if not isinstance(part, str) or not part.startswith("word/diagrams/"):
            errors.append(f"smartart.{part}: part must be a word/diagrams/*.xml path.")
        if not isinstance(mappings, list):
            errors.append(f"smartart.{part}: value must be a list of node mappings.")
            continue
        for mi, mapping in enumerate(mappings):
            label = f"smartart.{part}[{mi}]"
            if not isinstance(mapping, dict):
                errors.append(f"{label}: must be a mapping.")
                continue
            nodes = mapping.get("nodes")
            if not isinstance(nodes, list) or not nodes:
                errors.append(f"{label}: needs a non-empty 'nodes' index list.")
            source = mapping.get("source") or {}
            if not isinstance(source, dict) or not source.get("input"):
                errors.append(f"{label}: source must carry an 'input'.")
            if mapping.get("when") is not None and not isinstance(mapping["when"], dict):
                errors.append(f"{label}: 'when' must be a dict.")


def _validate_library_references(config, errors):
    """Anti-dead-key rule: every top-level library key must be referenced."""
    library = config.get("library") or {}
    if not isinstance(library, dict):
        return  # already reported by the top-key check
    referenced = set()

    def _note(path):
        if isinstance(path, str) and path.startswith("library."):
            parts = path.split(".")
            if len(parts) >= 2:
                referenced.add(parts[1])

    for section in config.get("sections") or []:
        if not isinstance(section, dict):
            continue
        for block in section.get("blocks") or []:
            if not isinstance(block, dict):
                continue
            _note(block.get("path"))
            _note(block.get("config_default"))
            for extra in block.get("extra_config_refs", []) or []:
                _note(extra)

    dead = sorted(set(library) - referenced)
    if dead:
        errors.append(
            "library: dead key(s) never referenced by any block "
            f"(path/config_default): {', '.join(dead)}."
        )


def load_config(config_path, documents_root=None):
    """Load + validate a config file; returns the parsed mapping."""
    path = resolve_under_documents_root(config_path, documents_root)
    if not path.is_file():
        raise ConfigError(f"Config file not found: {config_path!r} (resolved {path})")
    try:
        config = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigError(f"Config YAML parse error in {config_path!r}: {exc}") from exc
    if not isinstance(config, dict):
        raise ConfigError(f"Config root must be a mapping: {config_path!r}")

    errors = []
    for key in REQUIRED_TOP_KEYS:
        if key not in config:
            errors.append(f"Missing required top-level key: {key!r}.")
    if config.get("inputs") is not None:
        _validate_inputs(config, errors)
    if config.get("sections") is not None:
        _validate_sections(config, errors)
    if config.get("computed") is not None:
        _validate_computed(config, errors)
    if config.get("smartart") is not None:
        _validate_smartart(config, errors)
    if config.get("library") is not None and config.get("sections") is not None:
        _validate_library_references(config, errors)

    if errors:
        raise ConfigError(
            f"Config validation failed for {config_path!r}:\n- " + "\n- ".join(errors)
        )
    return config

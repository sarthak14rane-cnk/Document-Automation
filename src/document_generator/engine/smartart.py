"""SmartArt diagram patching (§3.2/§3.5, decision #4 — included in v1).

docxtpl has no SmartArt support, so the rendered package is reopened as a zip
and the diagram parts declared in config ``smartart:`` are patched by direct
OOXML surgery. Every other package entry is copied byte-identical; the zip is
rewritten preserving entry order (deflate).

Node addressing — verified against both shipped diagrams (master + golden):

- Data nodes are ``<dgm:pt>`` elements without an explicit ``type`` attribute
  that carry a ``<dgm:t>`` text body (doc/pres/parTrans/sibTrans points are
  ignored).
- A mapping's ``nodes`` index is the position of the target **paragraph**
  (``<a:p>``) in the global list of paragraphs across the diagram's data
  nodes, in document order. This reproduces every data2.xml mapping
  (4=client name, 5-9=stakeholder roles, 10='{short} PARTNER', 3='{short}
  MANAGER') and data3.xml's weekly node (0).

Known artifact (documented choice): data3.xml's ``nodes: [4]`` (monthly
label) predates the current master, whose reporting diagram only exposes 3
paragraphs — the mapping is skipped with a loguru warning instead of failing
the render, preserving the template's own text for that node (golden parity).
All other structural mismatches (missing part, malformed XML) raise
RenderError.

Value rules per mapping:

- ``when: {input, equals}``  -> patch only when the resolved input equals.
- ``source.input``           -> dotted path into the render context; dicts
  (e.g. cnk.joint_partner) feed ``{key}`` placeholders in ``format``.
- ``format``                 -> 'Weekly {value_upper} ', '{short} PARTNER'.
  With a format, only the paragraph's FIRST text run is replaced and the
  remaining runs are preserved (keeps the golden ': Progress Report' suffix).
- Without ``format``, the paragraph's first run receives the value and the
  remaining runs are blanked (full-node text replacement).
- ``skip_if_empty: true``    -> leave the node untouched when the value is
  empty (org-chart/reporting slots keep template text).
- ``sparse: true``           -> value is a list; fill the mapped nodes in
  order up to the list length, leave the rest untouched.
"""

import io
import zipfile

from loguru import logger
from lxml import etree

from .errors import RenderError

_A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
_DGM_NS = "http://schemas.openxmlformats.org/drawingml/2006/diagram"

_MAX_OUTPUT_BYTES = 20_000_000  # defensive cap per diagram part


def _data_paragraphs(root):
    """Global list of (paragraph_element,) across the diagram's data nodes."""
    paragraphs = []
    for pt in root.iter(f"{{{_DGM_NS}}}pt"):
        if pt.get("type"):  # doc/pres/parTrans/sibTrans -> presentation space
            continue
        text_body = pt.find(f"{{{_DGM_NS}}}t")
        if text_body is None:
            continue
        paragraphs.extend(text_body.iter(f"{{{_A_NS}}}p"))
    return paragraphs


def _interpolate(format_text, value):
    """Apply {value}/{value_upper} (scalar) or {key} (dict) placeholders."""
    if isinstance(value, dict):
        text = str(format_text)
        for key, field in value.items():
            text = text.replace("{" + str(key) + "}", str(field or ""))
        return text
    scalar = "" if value is None else str(value)
    return str(format_text).replace("{value_upper}", scalar.upper()).replace(
        "{value}", scalar
    )


def _mapping_value(mapping, context):
    """Resolve the mapping's source value; returns (value, skip_reason)."""
    source = mapping.get("source") or {}
    value = _resolve_path(context, source.get("input") or "")
    when = mapping.get("when")
    if when:
        expected = _resolve_path(context, when.get("input") or "")
        if expected != when.get("equals"):
            return None, f"when-guard not satisfied ({when.get('input')!r})"
    # Config declares skip_if_empty inside source; accept top level too.
    skip_if_empty = bool(mapping.get("skip_if_empty") or source.get("skip_if_empty"))
    if skip_if_empty and value in (None, "", [], {}):
        return None, "skip_if_empty (empty value)"
    if value is None:
        return None, f"input {source.get('input')!r} resolved to nothing"
    return value, None


def _resolve_path(scope, dotted):
    current = scope
    for part in str(dotted).split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None
    return current


def _set_paragraph_text(paragraph, value, keep_other_runs):
    runs = paragraph.findall(f"{{{_A_NS}}}r")
    if not runs:
        raise RenderError("SmartArt paragraph has no text runs to patch.")
    first_t = runs[0].find(f"{{{_A_NS}}}t")
    if first_t is None:
        first_t = etree.SubElement(runs[0], f"{{{_A_NS}}}t")
    first_t.text = value
    for run in runs[1:]:
        run_t = run.find(f"{{{_A_NS}}}t")
        if run_t is not None:
            if keep_other_runs:
                continue  # preserve suffixes like ': Progress Report'
            run_t.text = ""


def _apply_mapping(mapping, paragraphs, context, part_name):
    value, skip_reason = _mapping_value(mapping, context)
    if value is None:
        logger.warning(
            "SMARTART_MAPPING_SKIPPED part={} nodes={} reason={}",
            part_name, mapping.get("nodes"), skip_reason,
        )
        return
    nodes = list(mapping.get("nodes") or [])
    source = mapping.get("source") or {}
    # Config declares sparse/skip_if_empty inside source; accept top level too.
    sparse = bool(mapping.get("sparse") or source.get("sparse"))
    if sparse and isinstance(value, list):
        pairs = list(zip(nodes, value))
    else:
        formatted = (
            _interpolate(source.get("format"), value)
            if source.get("format") is not None
            else ("" if value is None else (value if isinstance(value, str) else str(value)))
        )
        if not isinstance(value, (str, int, float)) and source.get("format") is None:
            logger.warning(
                "SMARTART_MAPPING_SKIPPED part={} nodes={} reason=non-scalar value without format",
                part_name, nodes,
            )
            return
        pairs = [(node, formatted) for node in nodes]

    for node_index, text in pairs:
        if not isinstance(node_index, int) or node_index < 0:
            raise RenderError(
                f"SmartArt node index must be a non-negative int: {node_index!r} "
                f"({part_name})"
            )
        if node_index >= len(paragraphs):
            # Documented artifact handling (see module docstring): a mapping
            # pointing past the current diagram keeps the template text.
            logger.warning(
                "SMARTART_NODE_OUT_OF_RANGE part={} node={} max={}",
                part_name, node_index, len(paragraphs) - 1,
            )
            continue
        keep_other_runs = source.get("format") is not None
        _set_paragraph_text(paragraphs[node_index], text, keep_other_runs)


def patch_smartart(docx_bytes, config, context):
    """Return ``docx_bytes`` with config-declared diagram nodes patched."""
    smartart = (config or {}).get("smartart") or {}
    if not smartart:
        return docx_bytes

    with zipfile.ZipFile(io.BytesIO(docx_bytes)) as archive:
        entries = archive.namelist()
        data = {name: archive.read(name) for name in entries}
        infos = {info.filename: info for info in archive.infolist()}

    for part_name, mappings in smartart.items():
        if part_name not in data:
            raise RenderError(f"SmartArt part missing from the rendered package: {part_name}")
        raw = data[part_name]
        if len(raw) > _MAX_OUTPUT_BYTES:
            raise RenderError(f"SmartArt part unexpectedly large: {part_name}")
        try:
            root = etree.fromstring(raw)
        except etree.XMLSyntaxError as exc:
            raise RenderError(f"SmartArt part XML parse error ({part_name}): {exc}") from exc

        paragraphs = _data_paragraphs(root)
        for mapping in mappings or []:
            _apply_mapping(mapping, paragraphs, context, part_name)

        data[part_name] = etree.tostring(
            root, xml_declaration=True, encoding="UTF-8", standalone=True
        )

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in entries:
            info = infos[name]
            archive.writestr(
                zipfile.ZipInfo(name, date_time=info.date_time), data[name]
            )
    return buffer.getvalue()

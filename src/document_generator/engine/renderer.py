"""Document renderer (§3.2) — docxtpl render -> SmartArt patch -> bytes.

``render_document(config, template_path, context)``:
    1. ``DocxTemplate(template_path)``  (Jinja master, {%p %}/{%tr %} tags)
    2. ``render(_xml_escape_context(context), autoescape=False)``
    3. save to BytesIO
    4. ``smartart.patch_smartart`` on the saved package bytes (RAW context)
    5. return the patched bytes

D4 (fix plan): docxtpl 0.20.2's ``fix_tables`` re-parses the rendered XML
with ``recover=True``, silently dropping bare ``&`` (and mangling other
invalid fragments) from ANY string context value — AI content, inputs and
static config text alike. Every string leaf is therefore XML-escaped
(``&``/``<``/``>``) in a COPY handed to the docxtpl render; values are plain
text, never markup (a value that already contains an entity such as
``&amp;`` renders as that literal text). SmartArt keeps the RAW context —
lxml escapes its text on serialization already — and dict keys / non-string
leaves are untouched.

No temp files are created (in-memory BytesIO throughout). Engine failures
raise :class:`RenderError`; unexpected library errors are wrapped so the view
can map them to 500 render_failed.
"""

import io
from xml.sax.saxutils import escape as _xml_escape

from docxtpl import DocxTemplate

from .errors import RenderError
from . import smartart


def _xml_escape_context(value):
    """Deep-copy ``value`` with ``&``/``<``/``>`` escaped in every string leaf.

    Only the copy handed to docxtpl is escaped (D4). Booleans, numbers,
    dates and other non-string leaves pass through unchanged; dict keys are
    never escaped. The result is plain dicts/lists — Jinja resolves dotted
    names on dicts via item lookup, so attribute access keeps working.
    """
    if isinstance(value, dict):
        return {key: _xml_escape_context(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_xml_escape_context(item) for item in value]
    if isinstance(value, str):
        return _xml_escape(value)
    return value


def render_document(config, template_path, context):
    try:
        template = DocxTemplate(str(template_path))
        template.render(_xml_escape_context(context), autoescape=False)
        buffer = io.BytesIO()
        template.save(buffer)
        rendered = buffer.getvalue()
    except RenderError:
        raise
    except Exception as exc:  # docxtpl/jinja/lxml/zip failures -> visible 500
        raise RenderError(f"Document rendering failed: {exc}") from exc

    try:
        return smartart.patch_smartart(rendered, config, context)
    except RenderError:
        raise
    except Exception as exc:
        raise RenderError(f"SmartArt patching failed: {exc}") from exc

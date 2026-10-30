"""template_master API views (§3.4–3.6) — thin DRF layer over the engine.

Routes (template_master/urls.py):
    GET  /templates/                        -> TemplateActiveListView
    GET  /templates/{id}/schema/            -> TemplateSchemaView
    POST /templates/{id}/preview/           -> TemplatePreviewView
    POST /ai/generate-section/              -> AISectionView

All views are unauthenticated this iteration (AllowAny; no-auth decision in
backend.settings REST_FRAMEWORK) and loguru-log every served/failed action.
"""

import io
import re
from datetime import datetime

from django.http import FileResponse
from django.utils.text import slugify
from loguru import logger
from rest_framework import status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from engine.ai_bridge import AIError, generate_section
from engine.computed import list_phrase
from engine.context_builder import InputValidationError, MissingAIContentError, build_context
from engine.errors import ConfigError, RenderError
from engine.manifest import load_config, resolve_under_documents_root
from engine.renderer import render_document
from engine.schema_builder import build_form_schema
from jinja2 import Environment, StrictUndefined
from jinja2.exceptions import UndefinedError
from jinja2.meta import find_undeclared_variables

from .exceptions import AIGenerationFailed, FilesMissing, RenderFailed
from .models import TemplateMaster
from .serializers import AISectionRequestSerializer, PreviewRequestSerializer, TemplateMasterSerializer

DOCX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

# Prompt rendering is strict: any unresolved variable is a visible 400.
_PROMPT_ENV = Environment(undefined=StrictUndefined, keep_trailing_newline=True)


def _get_active_template(template_id):
    """404 when the row is missing or inactive (plan message, verbatim)."""
    try:
        return TemplateMaster.objects.get(pk=template_id, is_active=True)
    except TemplateMaster.DoesNotExist:
        raise NotFound("Template not found or inactive.")


def _resolve_artifacts(row):
    """Resolve + verify both artifacts; 409 with the specific missing code."""
    resolved = []
    for rel_path, code in (
        (row.config_path, "config_file_missing"),
        (row.template_path, "template_file_missing"),
    ):
        try:
            path = resolve_under_documents_root(rel_path)
        except ConfigError as exc:
            raise FilesMissing(str(exc), code=code)
        if not path.is_file():
            raise FilesMissing(
                f"File not found on the server: {rel_path}", code=code
            )
        resolved.append(path)
    return resolved[0], resolved[1]


def _load_config_or_400(config_path):
    try:
        return load_config(config_path)
    except ConfigError as exc:
        raise ValidationError({"detail": str(exc), "code": "invalid_config"})


class TemplateActiveListView(APIView):
    """GET /templates/ — active templates whose two files both exist."""

    permission_classes = [AllowAny]

    def get(self, request):
        available = []
        for row in TemplateMaster.objects.filter(is_active=True):
            try:
                config_path, template_path = _resolve_artifacts(row)
            except FilesMissing as exc:
                logger.warning(
                    "TEMPLATE_SKIPPED_FILE_MISSING template_id={} name={} code={}",
                    row.template_id, row.template_name, exc.detail.get("code"),
                )
                continue
            available.append(row)
        serializer = TemplateMasterSerializer(available, many=True)
        logger.info("TEMPLATE_LIST_SERVED count={}", len(available))
        return Response(serializer.data, status=status.HTTP_200_OK)


class TemplateSchemaView(APIView):
    """GET /templates/{id}/schema/ — inputs JSON structure from the config."""

    permission_classes = [AllowAny]

    def get(self, request, template_id):
        row = _get_active_template(template_id)
        # Existence check only (409 codes); load_config resolves the
        # repo-relative registry path itself (it rejects absolute paths).
        _resolve_artifacts(row)
        config = _load_config_or_400(row.config_path)
        schema = build_form_schema(config)
        logger.info(
            "TEMPLATE_SCHEMA_SERVED template_id={} name={}", row.template_id, row.template_name
        )
        return Response(
            {
                "template": {
                    "template_id": row.template_id,
                    "template_name": row.template_name,
                    "service": schema["service"],
                    "display_name": schema["display_name"],
                    "version": schema["version"],
                },
                "groups": schema["groups"],
                "base_fields": schema["base_fields"],
                "ai_sections": schema["ai_sections"],
            },
            status=status.HTTP_200_OK,
        )


def _safe_filename_fragment(value, fallback):
    fragment = slugify(str(value or ""))[:80]
    return fragment or fallback


class TemplatePreviewView(APIView):
    """POST /templates/{id}/preview/ — render + stream the .docx back."""

    permission_classes = [AllowAny]

    def post(self, request, template_id):
        row = _get_active_template(template_id)
        _resolve_artifacts(row)  # 409 existence check for both artifacts
        config = _load_config_or_400(row.config_path)
        template_path = resolve_under_documents_root(row.template_path)

        serializer = PreviewRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        inputs = serializer.validated_data.get("inputs") or {}
        ai_content = serializer.validated_data.get("ai_content") or {}

        try:
            context = build_context(config, inputs, ai_content)
        except MissingAIContentError as exc:
            return Response(
                {
                    "detail": str(exc),
                    "code": "missing_ai_content",
                    "blocks": exc.block_ids,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        except InputValidationError as exc:
            raise ValidationError(exc.messages)

        try:
            docx_bytes = render_document(config, template_path, context)
        except RenderError as exc:
            logger.exception(
                "TEMPLATE_PREVIEW_FAILED template_id={} name={}",
                row.template_id, row.template_name,
            )
            raise RenderFailed(str(exc))

        reference = _safe_filename_fragment(inputs.get("reference_number"), "")
        stamp = datetime.now().strftime("%Y%m%d%H%M%S")
        filename = f"{_safe_filename_fragment(row.template_name, 'template')}"
        filename += f"_{reference}" if reference else f"_{stamp}"
        filename += ".docx"

        logger.info(
            "TEMPLATE_PREVIEW_RENDERED template_id={} name={} bytes={}",
            row.template_id, row.template_name, len(docx_bytes),
        )
        response = FileResponse(
            io.BytesIO(docx_bytes), content_type=DOCX_CONTENT_TYPE, as_attachment=True,
            filename=filename,
        )
        return response


class AISectionView(APIView):
    """POST /ai/generate-section/ — generalized AI section generation.

    The frontend sends the raw Jinja prompt (as delivered by the schema
    endpoint) + output_schema + industries + client_context; the backend
    renders the prompt server-side (strict undefined -> 400) and shells the
    rendered prompt to opencode via the dedicated bridge module. Optional
    ``model_id`` selects the model per request (default:
    settings.OPENCODE_MODEL -> opencode/mimo-v2.6-flash-free).
    """

    permission_classes = [AllowAny]

    def post(self, request):
        serializer = AISectionRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        prompt = serializer.validated_data["prompt"]
        output_schema = serializer.validated_data["output_schema"]
        industries = serializer.validated_data.get("industries") or []
        client_context = serializer.validated_data.get("client_context") or {}
        model_id = serializer.validated_data.get("model_id") or None

        client_context = dict(client_context)
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

        try:
            rendered_prompt = self._render_prompt(prompt, prompt_context)
        except ValidationError:
            logger.warning("AI_SECTION_FAILED reason=unresolved_prompt_vars")
            raise

        try:
            content = generate_section(rendered_prompt, output_schema, model=model_id)
        except AIError as exc:
            logger.error("AI_SECTION_FAILED schema={} reason={}", output_schema, exc)
            raise AIGenerationFailed(str(exc))

        logger.info(
            "AI_SECTION_GENERATED schema={} model={}", output_schema, model_id or "default"
        )
        return Response(
            {"output_schema": output_schema, "content": content},
            status=status.HTTP_200_OK,
        )

    @staticmethod
    def _render_prompt(prompt, prompt_context):
        """Server-side Jinja render with strict undefined handling (§3.6)."""
        try:
            parsed = _PROMPT_ENV.parse(prompt)
            undeclared = find_undeclared_variables(parsed)
        except UndefinedError:
            undeclared = set()
        missing = sorted(
            name for name in undeclared
            if name not in prompt_context and name.split(".")[0] not in prompt_context
        )
        if missing:
            raise ValidationError(
                {
                    "detail": "Prompt references unresolved variables.",
                    "code": "unresolved_prompt_vars",
                    "variables": missing,
                }
            )
        try:
            return _PROMPT_ENV.from_string(prompt).render(prompt_context)
        except UndefinedError as exc:
            raise ValidationError(
                {
                    "detail": f"Prompt references unresolved variables: {exc.message}",
                    "code": "unresolved_prompt_vars",
                }
            )

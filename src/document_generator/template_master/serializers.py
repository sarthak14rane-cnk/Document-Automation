from rest_framework import serializers

from .models import TemplateMaster


class TemplateMasterSerializer(serializers.ModelSerializer):
    """List output for GET /templates/ (read-only projection)."""

    class Meta:
        model = TemplateMaster
        fields = (
            "template_id",
            "template_name",
            "config_path",
            "template_path",
            "created_at",
        )
        read_only_fields = fields



class AISectionRequestSerializer(serializers.Serializer):
    """POST /ai/generate-section/ body (generalized, frontend-supplied prompt).

    ``model_id`` is optional: bare model ids are prefixed with the default
    provider by the bridge; omission falls back to settings.OPENCODE_MODEL
    (default: opencode/mimo-v2.6-flash-free — user decision 2026-10-26).
    """

    OUTPUT_SCHEMA_CHOICES = ("text", "bullets", "categories")

    prompt = serializers.CharField(required=True, allow_blank=False, allow_null=False)
    output_schema = serializers.ChoiceField(choices=OUTPUT_SCHEMA_CHOICES, required=True)
    industries = serializers.ListField(
        child=serializers.CharField(allow_blank=True),
        allow_empty=True,
        required=False,
        default=list,
    )
    client_context = serializers.DictField(required=False, default=dict, allow_null=True)
    model_id = serializers.CharField(required=False, allow_blank=True, default="")

    def validate_prompt(self, value):
        if not value.strip():
            raise serializers.ValidationError("prompt must not be blank.")
        return value

    def validate_model_id(self, value):
        return value.strip()


class PreviewRequestSerializer(serializers.Serializer):
    """POST /templates/{id}/preview/ body. Deep input validation is
    schema-driven and lives in the engine (context_builder), not DRF fields."""

    inputs = serializers.DictField(required=True)
    ai_content = serializers.DictField(required=False, default=dict, allow_null=True)

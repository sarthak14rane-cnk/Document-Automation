from rest_framework import serializers

from clients.exceptions import Conflict
from clients.models import Client


def _validate_string_list(value, field_name):
    """Coerce None -> [], reject non-list / non-string members."""
    if value is None:
        return []
    if not isinstance(value, list):
        raise serializers.ValidationError(
            {field_name: f"{field_name} must be a list of strings."}
        )
    for item in value:
        if not isinstance(item, str):
            raise serializers.ValidationError(
                {field_name: f"All items in {field_name} must be strings."}
            )
    return value


def _strip(value):
    return value.strip() if value else value


class ClientSerializer(serializers.ModelSerializer):
    """Create serializer — business fields optional where the model allows blank."""

    # D1 fix: optional on create, but must default to "" — the DB column is NOT NULL
    # (blank=True is validation-only), so an omitted key would otherwise insert NULL
    # and crash with IntegrityError (HTTP 500).
    client_short_name = serializers.CharField(required=False, allow_blank=True, default="")

    class Meta:
        model = Client
        fields = (
            "client_id",
            "client_name",
            "client_short_name",
            "client_industries",
            "client_spoc_name",
            "client_spoc_email",
            "list_of_entities",
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("client_id", "is_active", "created_at", "updated_at")
        # D2 fix: accept explicit null for the list fields; the shared validator
        # (_validate_string_list) then coerces None -> [] per plan §3.4.
        extra_kwargs = {
            "client_industries": {"allow_null": True},
            "list_of_entities": {"allow_null": True},
        }

    def validate_client_industries(self, value):
        return _validate_string_list(value, "client_industries")

    def validate_list_of_entities(self, value):
        return _validate_string_list(value, "list_of_entities")

    def validate(self, data):
        client_name = _strip(data.get("client_name"))
        candidate = client_name or getattr(self.instance, "client_name", None)
        if not candidate:
            raise serializers.ValidationError(
                {"client_name": "This field is required and must not be blank."}
            )

        qs = Client.objects.filter(client_name__iexact=candidate)
        if self.instance is not None:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise Conflict(
                {"client_name": "A client with this name (case-insensitive) already exists."}
            )

        data["client_name"] = candidate
        data["client_short_name"] = _strip(data.get("client_short_name"))
        data["client_spoc_name"] = _strip(data.get("client_spoc_name"))
        data["client_spoc_email"] = _strip(data.get("client_spoc_email"))
        return data


class UpdateClientSerializer(serializers.ModelSerializer):
    """Full-update (PUT) serializer — every business key must be present."""

    class Meta:
        model = Client
        fields = (
            "client_id",
            "client_name",
            "client_short_name",
            "client_industries",
            "client_spoc_name",
            "client_spoc_email",
            "list_of_entities",
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("client_id", "is_active", "created_at", "updated_at")
        # D2 fix: null values coerce to [] via the shared validator (key presence
        # is still enforced in validate() below).
        extra_kwargs = {
            "client_industries": {"allow_null": True},
            "list_of_entities": {"allow_null": True},
        }

    def validate_client_industries(self, value):
        return _validate_string_list(value, "client_industries")

    def validate_list_of_entities(self, value):
        return _validate_string_list(value, "list_of_entities")

    def validate(self, data):
        # All keys are required on PUT.
        required_keys = [
            "client_name",
            "client_short_name",
            "client_industries",
            "client_spoc_name",
            "client_spoc_email",
            "list_of_entities",
        ]
        for key in required_keys:
            if key not in data:
                raise serializers.ValidationError(
                    {key: "This field is required on full update."}
                )

        candidate = _strip(data.get("client_name"))
        if not candidate:
            raise serializers.ValidationError(
                {"client_name": "This field is required and must not be blank."}
            )

        qs = Client.objects.filter(client_name__iexact=candidate).exclude(pk=self.instance.pk)
        if qs.exists():
            raise Conflict(
                {"client_name": "A client with this name (case-insensitive) already exists."}
            )

        data["client_name"] = candidate
        data["client_short_name"] = _strip(data.get("client_short_name"))
        data["client_spoc_name"] = _strip(data.get("client_spoc_name"))
        data["client_spoc_email"] = _strip(data.get("client_spoc_email"))
        return data

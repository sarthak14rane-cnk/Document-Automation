from rest_framework import status, viewsets
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from loguru import logger

from clients.models import Client
from clients.serializers import ClientSerializer, UpdateClientSerializer


class ClientViewSet(viewsets.ModelViewSet):
    """
    CRUD over Client. Active-only enforcement on every action:
    GET /clients/            -> active clients, newest first
    POST /clients/           -> create (case-insensitive dup check -> 409)
    GET /clients/{client_id} -> details (inactive or unknown -> 404)
    PUT /clients/{client_id} -> full update, all keys required (inactive -> 404)
    DELETE /clients/{client_id} -> soft delete (is_active=False) -> 204

    PATCH is intentionally disabled.
    """

    serializer_class = ClientSerializer
    permission_classes = [AllowAny]
    http_method_names = ["get", "post", "put", "delete"]
    lookup_field = "client_id"
    lookup_value_regex = r"[0-9]+"

    def get_queryset(self):
        # Active-only precheck for list / retrieve / update / destroy.
        return Client.objects.filter(is_active=True)

    def get_serializer_class(self):
        if self.action == "update":
            return UpdateClientSerializer
        return ClientSerializer

    def perform_create(self, serializer):
        client = serializer.save()
        logger.info("CLIENT_CREATED client_id={} name={}", client.client_id, client.client_name)

    def perform_update(self, serializer):
        client = serializer.save()
        logger.info("CLIENT_UPDATED client_id={}", client.client_id)

    def destroy(self, request, *args, **kwargs):
        client = self.get_object()  # 404 if missing OR inactive
        client.is_active = False
        client.save()  # auto_now refreshes updated_at
        logger.info("CLIENT_DEACTIVATED client_id={}", client.client_id)
        return Response(status=status.HTTP_204_NO_CONTENT)

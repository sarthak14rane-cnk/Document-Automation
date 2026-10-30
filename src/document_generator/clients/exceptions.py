from rest_framework.exceptions import APIException


class Conflict(APIException):
    """HTTP 409 Conflict — raised when a client name already exists (case-insensitive)."""

    status_code = 409
    default_detail = "Client with the given name already exists."
    default_code = "client_name_conflict"

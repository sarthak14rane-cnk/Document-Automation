from rest_framework.exceptions import APIException


class FilesMissing(APIException):
    """HTTP 409 — a registered artifact (config or master file) is absent.

    Raised with a specific code so the API can distinguish
    ``config_file_missing`` from ``template_file_missing`` (plan §3.4).
    """

    status_code = 409
    default_detail = "Required template files are missing on the server."
    default_code = "files_missing"

    def __init__(self, detail=None, code=None):
        message = detail or self.default_detail
        self.detail = {"detail": message, "code": code or self.default_code}


class AIGenerationFailed(APIException):
    """HTTP 502 — opencode generation failed/timeout/invalid output
    (retryable by design; plan §3.6)."""

    status_code = 502
    default_detail = "AI generation failed. Please retry."
    default_code = "ai_generation_failed"

    def __init__(self, detail=None, code=None):
        message = detail or self.default_detail
        self.detail = {"detail": message, "code": code or self.default_code}


class RenderFailed(APIException):
    """HTTP 500 — engine render/SmartArt failure (details logged, plan §3.5)."""

    status_code = 500
    default_detail = "Document rendering failed."
    default_code = "render_failed"

    def __init__(self, detail=None, code=None):
        message = detail or self.default_detail
        self.detail = {"detail": message, "code": code or self.default_code}

"""Request/response logging middleware backed by Loguru.

Logs method, path, status code, request duration, and the request body
(truncated at 2000 characters) into the rotated log file configured in
backend.logging_setup. Reading request.body here is safe: Django caches it,
so DRF's parsers downstream reuse the same value.
"""

import time

from loguru import logger


class LoguruRequestLoggerMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        started = time.perf_counter()
        response = self.get_response(request)
        duration_ms = (time.perf_counter() - started) * 1000

        body = getattr(request, "body", b"") or b""
        body_text = body.decode("utf-8", errors="replace")[:2000]

        logger.info(
            "REQ {} {} -> {} ({:.1f} ms) body={}",
            request.method,
            request.get_full_path(),
            response.status_code,
            duration_ms,
            body_text,
        )
        return response

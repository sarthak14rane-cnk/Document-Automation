"""Typed engine exception hierarchy (plan §3.2 / §4 Error handling).

Views map these to HTTP statuses:
    ConfigError            -> 400 invalid_config        (manifest)
    InputValidationError   -> 400 field-keyed           (context_builder)
    MissingAIContentError  -> 400 missing_ai_content    (visible-failure contract)
    RenderError            -> 500 render_failed         (renderer/smartart)
    AIError                -> 502 ai_generation_failed  (ai_bridge)
"""


class EngineError(Exception):
    """Base class for all engine errors."""


class ConfigError(EngineError):
    """Config file could not be loaded or violates the manifest contract."""


class InputValidationError(EngineError):
    """User inputs failed schema-driven validation/coercion.

    ``messages`` is a dict keyed by input path (DRF-ValidationError style) so
    the view can surface it directly as a 400 body.
    """

    def __init__(self, messages):
        self.messages = messages
        super().__init__(str(messages))


class MissingAIContentError(EngineError):
    """AI-only blocks rendered without user/AI content (visible failure).

    ``block_ids`` lists every AI block id lacking content so the caller can
    retry generation per section. Never silently render an empty AI block.
    """

    def __init__(self, block_ids):
        self.block_ids = list(block_ids)
        detail = "Missing AI content for block(s): " + ", ".join(self.block_ids)
        super().__init__(detail)


class RenderError(EngineError):
    """Document rendering or SmartArt patching failed."""


class AIError(EngineError):
    """opencode AI generation failed (subprocess error, timeout, bad output)."""

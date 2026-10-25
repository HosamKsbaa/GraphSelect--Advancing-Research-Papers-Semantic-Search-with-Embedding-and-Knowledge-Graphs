"""Bounded Gemini model client with structured validation and error sanitization.

Ported from archive commit 865cd08 (`code/backend/ai/core/model_client.py`),
decoupled from `ai.core.activity` and global `config.Settings`.
"""

from __future__ import annotations

import hashlib
import time
from collections.abc import Awaitable, Callable, Sequence
from typing import TypeVar

from google.genai.types import FinishReason
from langchain_core.exceptions import (
    ModelAuthenticationError,
    ModelNotFoundError,
    ModelPermissionDeniedError,
    ModelRateLimitError,
)
from langchain_core.messages import BaseMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError
from pydantic_core import from_json

TextCallback = Callable[[str], Awaitable[None]]
ResultModel = TypeVar("ResultModel", bound=BaseModel)
MODEL_TIMEOUT_SECONDS = 60
CONTEXT_TOKEN_HEADROOM = 1000


class ModelClientSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    gemini_api_key: SecretStr | None = None
    default_model: str = "gemini-2.5-flash"
    context_token_limit: int = 128000


class ModelValidationDiagnostic(BaseModel):
    error_type: str
    location: list[str | int] = Field(default_factory=list)


class ModelUsage(BaseModel):
    model_name: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    duration_seconds: float = 0.0
    prompt_hash: str
    cost: float | None = None
    success: bool = False
    finish_reason: str | None = None
    validation_errors: list[ModelValidationDiagnostic] = Field(default_factory=list)


ModelUsageCallback = Callable[[ModelUsage], Awaitable[None]]


class ModelError(RuntimeError):
    """Sanitized model failure; provider responses and credentials stay private."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def partial_visible_text(content: str, field: str) -> str:
    try:
        parsed = from_json(content, allow_partial="trailing-strings")
    except ValueError:
        return ""
    if not isinstance(parsed, dict):
        return ""
    value = parsed.get(field)
    return value if isinstance(value, str) else ""


def provider_status_code(error: BaseException) -> int | None:
    """Inspect typed status codes across chained exceptions without reading raw text."""
    visited: set[int] = set()
    current: BaseException | None = error
    while current is not None and id(current) not in visited:
        visited.add(id(current))
        code = getattr(current, "code", None)
        if isinstance(code, int):
            return code
        current = current.__cause__ or current.__context__
    return None


def sanitized_model_error(error: Exception) -> ModelError:
    code = provider_status_code(error)
    if code in (401, 403) or isinstance(
        error, (ModelAuthenticationError, ModelPermissionDeniedError)
    ):
        return ModelError("model_authentication", "Gemini rejected the configured credentials.")
    if code == 429 or isinstance(error, ModelRateLimitError):
        return ModelError(
            "model_rate_limited",
            "Gemini rejected the request because of rate or usage limits.",
        )
    if code == 404 or isinstance(error, ModelNotFoundError):
        return ModelError(
            "model_not_found", "The configured Gemini model or endpoint was not found."
        )
    return ModelError(
        "model_unavailable", "Gemini could not complete this request; retry explicitly."
    )


def model_validation_diagnostics(
    error: ValidationError, schema: type[BaseModel]
) -> list[ModelValidationDiagnostic]:
    document = schema.model_json_schema()
    definitions = [document, *document.get("$defs", {}).values()]
    known_fields = {
        name for definition in definitions for name in definition.get("properties", {})
    }
    diagnostics: list[ModelValidationDiagnostic] = []
    for failure in error.errors(include_input=False, include_context=False, include_url=False):
        location = [
            part if isinstance(part, int) or part in known_fields else "[unknown_field]"
            for part in failure["loc"]
        ]
        diagnostics.append(
            ModelValidationDiagnostic(error_type=failure["type"], location=location)
        )
    return diagnostics


def safe_finish_reason(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    return value if value in {reason.value for reason in FinishReason} else "UNKNOWN"


def validate_model_result(
    content: str, schema: type[ResultModel], usage: ModelUsage
) -> ResultModel:
    if usage.finish_reason == "MAX_TOKENS":
        raise ModelError(
            "model_output_limit",
            "The AI answer was cut short by its output limit. Retry the task; no final result was saved.",
        )
    try:
        return schema.model_validate_json(content)
    except ValidationError as error:
        usage.validation_errors = model_validation_diagnostics(error, schema)
        failures = error.errors(include_input=False, include_url=False)
        is_incomplete = any(
            failure["type"] == "json_invalid"
            and str(failure.get("ctx", {}).get("error", "")).startswith("EOF while parsing")
            for failure in failures
        )
        if is_incomplete:
            raise ModelError(
                "model_response_incomplete",
                "The AI answer ended before it was complete. Retry the task; no final result was saved.",
            ) from None
        raise ModelError(
            "invalid_model_response",
            "The AI answer did not match the required format. Retry the task; no final result was saved.",
        ) from None


class GeminiModelClient:
    """Bounded LangChain Gemini client."""

    def __init__(self, settings: ModelClientSettings) -> None:
        self.settings = settings
        self.model_name = settings.default_model
        self.context_token_limit = settings.context_token_limit
        self._chat_model: ChatGoogleGenerativeAI | None = None
        if (
            settings.gemini_api_key
            and settings.gemini_api_key.get_secret_value().strip()
        ):
            self._chat_model = ChatGoogleGenerativeAI(
                model=self.model_name,
                google_api_key=settings.gemini_api_key.get_secret_value().strip(),
                temperature=0.0,
                timeout=MODEL_TIMEOUT_SECONDS,
                max_retries=1,
            )

    @property
    def configured(self) -> bool:
        return self._chat_model is not None

    @property
    def chat_model(self) -> ChatGoogleGenerativeAI:
        if self._chat_model is None:
            raise ModelError(
                "model_not_configured",
                "Configure GEMINI_API_KEY before calling the Gemini model.",
            )
        return self._chat_model

    async def generate_structured(
        self,
        messages: Sequence[BaseMessage],
        schema: type[ResultModel],
    ) -> tuple[ResultModel, ModelUsage]:
        if not self.configured:
            raise ModelError(
                "model_not_configured",
                "Configure GEMINI_API_KEY before calling the Gemini model.",
            )
        prompt_text = "\n".join(str(m.content) for m in messages)
        prompt_hash = hashlib.sha256(prompt_text.encode("utf-8")).hexdigest()
        usage = ModelUsage(model_name=self.model_name, prompt_hash=prompt_hash)
        started = time.monotonic()
        try:
            response = await self.chat_model.ainvoke(
                list(messages),
                response_mime_type="application/json",
                response_schema=schema.model_json_schema(),
            )
        except Exception as exc:
            usage.duration_seconds = max(0.0, time.monotonic() - started)
            raise sanitized_model_error(exc) from None

        usage.duration_seconds = max(0.0, time.monotonic() - started)
        meta = getattr(response, "response_metadata", {}) or {}
        usage.finish_reason = safe_finish_reason(meta.get("finish_reason"))
        usage_meta = getattr(response, "usage_metadata", None) or {}
        if isinstance(usage_meta, dict):
            usage.input_tokens = usage_meta.get("input_tokens")
            usage.output_tokens = usage_meta.get("output_tokens")

        content = response.content if isinstance(response.content, str) else str(response.content)
        validated = validate_model_result(content, schema, usage)
        usage.success = True
        return validated, usage

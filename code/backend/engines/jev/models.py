"""Typed models and errors for the Jev epistemic decision engine.

Ported from archive commit 865cd08 (`code/backend/ai/core/jev_client.py`),
decoupled from global `config.Settings` and `ai.core.activity`.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    SecretStr,
    StrictInt,
    TypeAdapter,
    field_validator,
)

JEV_ENDPOINT = "https://api.typesafe.ai/v1/systemone"
DEFAULT_PROBABILITY_TOLERANCE: float = 0.005
IEEE_754_EPSILON: float = 1e-12
MAX_DIAGNOSTIC_SNIPPET_LENGTH: int = 1024

Probability = Annotated[float, Field(strict=True, ge=0, le=1, allow_inf_nan=False)]
JSON_VALUE: TypeAdapter[JsonValue] = TypeAdapter(JsonValue)

JevFailureCategory = Literal[
    "probability_drift_exceeded",
    "schema_validation_error",
    "rubric_criteria_mismatch",
    "choice_argmax_mismatch",
    "http_error",
    "timeout",
]


class JevClientSettings(BaseModel):
    """Explicit settings passed into `JevDecisionClient`."""

    model_config = ConfigDict(extra="forbid")

    jev_enabled: bool = False
    typesafe_api_key: SecretStr | None = None
    jev_model: str = Field(default="jev-1.13.0", min_length=1)
    jev_timeout_seconds: float = Field(default=30.0, gt=0.0)
    jev_max_questions: int = Field(default=18, ge=1)
    jev_max_input_chars: int = Field(default=32000, ge=1)
    jev_max_calls_per_function: int = Field(default=4, ge=0)


class JevDiagnosticReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    query_id: str | None = None
    batch_index: int | None = None
    failure_category: JevFailureCategory
    status_code: int | None = None
    validation_details: str = Field(default="", max_length=MAX_DIAGNOSTIC_SNIPPET_LENGTH)
    raw_payload_snippet: str = Field(default="", max_length=MAX_DIAGNOSTIC_SNIPPET_LENGTH)
    input_hash: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    timestamp: str
    attempt_number: int = Field(default=1, ge=1, le=2)


class JevChoiceQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, revalidate_instances="always")

    type: Literal["choice"] = "choice"
    instructions: str = Field(min_length=1)
    criteria: dict[str, str] = Field(min_length=2, max_length=255)

    @field_validator("instructions")
    @classmethod
    def require_instructions(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("A decision needs explicit instructions.")
        return value

    @field_validator("criteria")
    @classmethod
    def require_described_choices(cls, value: dict[str, str]) -> dict[str, str]:
        if any(not choice.strip() or not description.strip() for choice, description in value.items()):
            raise ValueError("Every allowed choice needs an identifier and description.")
        return value


class JevChoiceAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    type: Literal["choice"]
    choice: str = Field(min_length=1)
    probabilities: dict[str, float] = Field(min_length=2)
    confidence: Probability


class JevTokenUsage(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    input_tokens: StrictInt = Field(ge=0)
    output_tokens: StrictInt = Field(ge=0)


class JevDecisionResult(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    model: str = Field(min_length=1)
    answers: dict[str, JevChoiceAnswer]
    usage: JevTokenUsage
    duration_seconds: float = Field(ge=0, allow_inf_nan=False)
    input_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


class JevResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    model: str = Field(min_length=1)
    answers: dict[str, JevChoiceAnswer]
    usage: JevTokenUsage


class JevError(RuntimeError):
    """A safe failure without credentials, research input, or provider error text."""

    def __init__(
        self,
        code: str,
        message: str,
        diagnostic: JevDiagnosticReceipt | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.diagnostic = diagnostic


class JevValidationError(JevError):
    """Internal validation error classifying failure category for diagnostic construction."""

    def __init__(self, failure_category: JevFailureCategory, message: str) -> None:
        super().__init__("invalid_jev_response", message)
        self.failure_category = failure_category

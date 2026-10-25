"""Bounded, lifespan-owned Jev client for explicit research choices.

Ported from archive commit 865cd08 (`code/backend/ai/core/jev_client.py`),
with `ai.core.activity` and global `config.Settings` dependencies removed.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import re
import time
from datetime import datetime, timezone

import httpx
from pydantic import JsonValue, ValidationError

from .models import (
    DEFAULT_PROBABILITY_TOLERANCE,
    IEEE_754_EPSILON,
    JEV_ENDPOINT,
    JSON_VALUE,
    MAX_DIAGNOSTIC_SNIPPET_LENGTH,
    JevChoiceQuestion,
    JevClientSettings,
    JevDecisionResult,
    JevDiagnosticReceipt,
    JevError,
    JevFailureCategory,
    JevResponse,
    JevValidationError,
)


def normalize_probability_distribution(
    dist: dict[str, float],
    tolerance: float = DEFAULT_PROBABILITY_TOLERANCE,
) -> dict[str, float]:
    """Rescale a probability distribution that sums to 1.0 within numerical tolerance.

    Enforces:
    1. Distribution has at least 2 choices.
    2. All probabilities are finite numbers.
    3. Minor negative floats in [-1e-5, 0.0] are clamped to 0.0.
    4. Probabilities < -1e-5 or > 1.0 + tolerance + 1e-12 are rejected.
    5. abs(sum - 1.0) <= tolerance + 1e-12.
    6. Proportional rescaling: p'_i = p_i / sum(p).
    7. Exact keys and argmax preserved. Never invent choices.
    """
    if not isinstance(dist, dict) or len(dist) < 2:
        raise ValueError("A decision answer requires at least two probability values.")
    for key, val in dist.items():
        if math.isnan(val) or math.isinf(val):
            raise ValueError(f"Probability for choice '{key}' is not a finite number: {val}")
        if val < -1e-5:
            raise ValueError(f"Negative probability for choice '{key}' ({val}) is outside allowed bounds.")
        if val > 1.0 + tolerance + IEEE_754_EPSILON:
            raise ValueError(f"Probability for choice '{key}' ({val}) exceeds 1 + tolerance.")
    clamped = {key: 0.0 if -1e-5 <= val < 0.0 else float(val) for key, val in dist.items()}
    total = sum(clamped.values())
    drift = abs(total - 1.0)
    if drift > tolerance + IEEE_754_EPSILON:
        raise ValueError(f"Probability drift exceeded: sum={total:.6f}, drift={drift:.6f} > {tolerance}")
    if total <= 0.0:
        raise ValueError("Probability distribution sum must be positive.")
    if math.isclose(total, 1.0, rel_tol=0, abs_tol=1e-14):
        return dict(clamped)
    return {key: val / total for key, val in clamped.items()}


def validate_answers(
    response: JevResponse,
    questions: dict[str, JevChoiceQuestion],
    model: str,
    tolerance: float = DEFAULT_PROBABILITY_TOLERANCE,
) -> None:
    if response.model != model or set(response.answers) != set(questions):
        raise JevValidationError(
            "rubric_criteria_mismatch",
            "Jev returned an unexpected model or decision identifiers.",
        )
    for identifier, question in questions.items():
        answer = response.answers[identifier]
        if set(answer.probabilities) != set(question.criteria) or answer.choice not in question.criteria:
            raise JevValidationError(
                "rubric_criteria_mismatch",
                "Jev returned an option outside the supplied decision rubric.",
            )
        try:
            normalized = normalize_probability_distribution(answer.probabilities, tolerance=tolerance)
        except ValueError as exc:
            msg = str(exc)
            category: JevFailureCategory = (
                "probability_drift_exceeded"
                if ("drift exceeded" in msg or "tolerance" in msg)
                else "schema_validation_error"
            )
            raise JevValidationError(
                category,
                f"Jev returned an invalid probability distribution: {msg}",
            ) from exc
        answer.probabilities = normalized
        if answer.probabilities[answer.choice] < max(answer.probabilities.values()) - 0.000001:
            raise JevValidationError(
                "choice_argmax_mismatch",
                "Jev's selected option does not match its probability distribution.",
            )


def sanitize_diagnostic_text(
    text: str,
    secret_key: str | None = None,
    max_length: int = MAX_DIAGNOSTIC_SNIPPET_LENGTH,
) -> str:
    if not text:
        return ""
    sanitized = text
    if secret_key and secret_key.strip():
        sanitized = sanitized.replace(secret_key.strip(), "[redacted]")
    sanitized = re.sub(r"Bearer\s+[A-Za-z0-9_\-\.\:\=\+\/]{8,}", "Bearer [redacted]", sanitized)
    if len(sanitized) > max_length:
        sanitized = sanitized[:max_length]
    return sanitized


def check_http_status(status: int) -> None:
    if status == 200:
        return
    if status in (401, 403):
        raise JevError("jev_authentication", "Jev rejected the configured credentials.")
    if status in (429, 529):
        raise JevError("jev_rate_limited", "Jev could not accept this request; retry explicitly later.")
    if status == 422:
        raise JevError("jev_request_rejected", "Jev rejected the decision request format.")
    raise JevError("jev_unavailable", "Jev could not complete this decision; retry explicitly.")


def redact_credential(value: JsonValue, key: str) -> JsonValue:
    """Protect the configured secret even if research input accidentally contains it."""
    if isinstance(value, str):
        return value.replace(key, "[redacted]")
    if isinstance(value, list):
        return [redact_credential(item, key) for item in value]
    if isinstance(value, dict):
        return {name.replace(key, "[redacted]"): redact_credential(item, key) for name, item in value.items()}
    return value


class JevDecisionClient:
    """The caller owns the injected HTTP client and closes it at shutdown."""

    def __init__(
        self,
        settings: JevClientSettings,
        http_client: httpx.AsyncClient,
        *,
        tolerance: float = DEFAULT_PROBABILITY_TOLERANCE,
    ) -> None:
        self.settings = settings
        self.http_client = http_client
        self.tolerance = tolerance

    @property
    def configured(self) -> bool:
        return bool(
            self.settings.jev_enabled
            and self.settings.typesafe_api_key
            and self.settings.typesafe_api_key.get_secret_value().strip()
        )

    async def decide(
        self,
        state: JsonValue,
        questions: dict[str, JevChoiceQuestion],
        *,
        function: str = "e_graphselect",
    ) -> JevDecisionResult:
        del function  # Reserved for caller telemetry labels
        if not self.configured:
            raise JevError(
                "jev_not_configured",
                "Enable Jev and configure TYPESAFE_API_KEY to use these decisions.",
            )
        _, encoded, validated_questions = self.prepare_request(state, questions)
        return await self.request_decision(encoded, validated_questions)

    def prepare_request(
        self,
        state: JsonValue,
        questions: dict[str, JevChoiceQuestion],
    ) -> tuple[dict[str, JsonValue], bytes, dict[str, JevChoiceQuestion]]:
        if not isinstance(state, (str, dict, list)):
            raise JevError("invalid_jev_request", "Jev needs a text, object, or array decision context.")
        if (
            not questions
            or len(questions) > self.settings.jev_max_questions
            or any(not key.strip() for key in questions)
        ):
            raise JevError(
                "jev_question_limit",
                "The decision request has no questions or exceeds its question limit.",
            )
        try:
            validated_state = JSON_VALUE.validate_python(state)
            validated_questions = {
                key: JevChoiceQuestion.model_validate(question) for key, question in questions.items()
            }
            payload: dict[str, JsonValue] = {
                "state": validated_state,
                "model": self.settings.jev_model,
                "questions": {
                    key: question.model_dump(mode="json") for key, question in validated_questions.items()
                },
            }
            encoded_text = json.dumps(
                payload,
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            )
        except (ValidationError, ValueError, TypeError):
            raise JevError(
                "invalid_jev_request",
                "The decision context or rubric does not match its required JSON format.",
            ) from None
        if len(encoded_text) > self.settings.jev_max_input_chars:
            raise JevError(
                "jev_input_limit",
                "The Jev decision input exceeds its size limit. Supply less context; nothing was truncated.",
            )
        return payload, encoded_text.encode(), validated_questions

    async def request_decision(
        self,
        encoded: bytes,
        questions: dict[str, JevChoiceQuestion],
    ) -> JevDecisionResult:
        assert self.settings.typesafe_api_key is not None
        key = self.settings.typesafe_api_key.get_secret_value().strip()
        if any(ord(character) < 33 or ord(character) > 126 for character in key):
            raise JevError(
                "jev_authentication",
                "The configured Jev credential is not a valid HTTP credential.",
            )
        started = time.monotonic()
        response = await self.send_request(encoded, key)
        return self.validate_response(response, questions, encoded, started, tolerance=self.tolerance)

    async def send_request(self, encoded: bytes, key: str) -> httpx.Response:
        input_hash = hashlib.sha256(encoded).hexdigest()
        try:
            async with asyncio.timeout(self.settings.jev_timeout_seconds):
                return await self.http_client.post(
                    JEV_ENDPOINT,
                    content=encoded,
                    headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                    timeout=self.settings.jev_timeout_seconds,
                    follow_redirects=False,
                )
        except (TimeoutError, httpx.TimeoutException):
            diag = JevDiagnosticReceipt(
                failure_category="timeout",
                status_code=None,
                validation_details="Jev exceeded its response time limit; retry explicitly.",
                raw_payload_snippet="",
                input_hash=input_hash,
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
            raise JevError(
                "jev_timeout",
                "Jev exceeded its response time limit; retry explicitly.",
                diagnostic=diag,
            ) from None
        except httpx.TransportError as exc:
            diag = JevDiagnosticReceipt(
                failure_category="http_error",
                status_code=None,
                validation_details=sanitize_diagnostic_text(str(exc), key),
                raw_payload_snippet="",
                input_hash=input_hash,
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
            raise JevError(
                "jev_unavailable",
                "Jev could not complete this decision; retry explicitly.",
                diagnostic=diag,
            ) from None

    def validate_response(
        self,
        response: httpx.Response,
        questions: dict[str, JevChoiceQuestion],
        encoded: bytes,
        started: float,
        *,
        query_id: str | None = None,
        batch_index: int | None = None,
        attempt_number: int = 1,
        tolerance: float | None = None,
    ) -> JevDecisionResult:
        tol = self.tolerance if tolerance is None else tolerance
        input_hash = hashlib.sha256(encoded).hexdigest()
        key = (
            self.settings.typesafe_api_key.get_secret_value().strip()
            if (self.settings.typesafe_api_key and self.settings.typesafe_api_key.get_secret_value())
            else ""
        )
        raw_text = response.content.decode("utf-8", errors="replace")

        if response.status_code != 200:
            diag = JevDiagnosticReceipt(
                query_id=query_id,
                batch_index=batch_index,
                failure_category="http_error",
                status_code=response.status_code,
                validation_details=sanitize_diagnostic_text(f"HTTP status {response.status_code}", key),
                raw_payload_snippet=sanitize_diagnostic_text(raw_text, key),
                input_hash=input_hash,
                timestamp=datetime.now(timezone.utc).isoformat(),
                attempt_number=attempt_number,
            )
            try:
                check_http_status(response.status_code)
            except JevError as err:
                err.diagnostic = diag
                raise

        try:
            parsed = JevResponse.model_validate_json(response.content)
        except (ValidationError, ValueError) as val_err:
            diag = JevDiagnosticReceipt(
                query_id=query_id,
                batch_index=batch_index,
                failure_category="schema_validation_error",
                status_code=response.status_code,
                validation_details=sanitize_diagnostic_text(str(val_err), key),
                raw_payload_snippet=sanitize_diagnostic_text(raw_text, key),
                input_hash=input_hash,
                timestamp=datetime.now(timezone.utc).isoformat(),
                attempt_number=attempt_number,
            )
            raise JevError(
                "invalid_jev_response",
                "Jev returned a response that does not match its required format.",
                diagnostic=diag,
            ) from None

        try:
            validate_answers(parsed, questions, self.settings.jev_model, tolerance=tol)
        except JevValidationError as val_err:
            diag = JevDiagnosticReceipt(
                query_id=query_id,
                batch_index=batch_index,
                failure_category=val_err.failure_category,
                status_code=response.status_code,
                validation_details=sanitize_diagnostic_text(str(val_err), key),
                raw_payload_snippet=sanitize_diagnostic_text(raw_text, key),
                input_hash=input_hash,
                timestamp=datetime.now(timezone.utc).isoformat(),
                attempt_number=attempt_number,
            )
            val_err.diagnostic = diag
            raise
        except JevError as err:
            diag = JevDiagnosticReceipt(
                query_id=query_id,
                batch_index=batch_index,
                failure_category="schema_validation_error",
                status_code=response.status_code,
                validation_details=sanitize_diagnostic_text(str(err), key),
                raw_payload_snippet=sanitize_diagnostic_text(raw_text, key),
                input_hash=input_hash,
                timestamp=datetime.now(timezone.utc).isoformat(),
                attempt_number=attempt_number,
            )
            err.diagnostic = diag
            raise

        return JevDecisionResult(
            model=parsed.model,
            answers=parsed.answers,
            usage=parsed.usage,
            duration_seconds=max(0.0, time.monotonic() - started),
            input_hash=input_hash,
        )

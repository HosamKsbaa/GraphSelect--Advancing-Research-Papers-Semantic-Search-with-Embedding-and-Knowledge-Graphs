"""Deterministic Error Taxonomy for Autonomous Research Enhancements.

Complies with Constitution v2.2.1:
- C7: Strict static typing.
- C9: Granular functions under 25 lines with single responsibility.
- A17, A37: Zero citation hallucination and structured error reporting.
"""
from __future__ import annotations

from typing import Any


class EnhancementToolError(Exception):
    """Base exception for autonomous research enhancement tools."""

    def __init__(
        self,
        message: str,
        error_code: str = "ENHANCEMENT_TOOL_ERROR",
        http_status_code: int = 500,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.http_status_code = http_status_code

    def to_dict(self) -> dict[str, Any]:
        """Serialize error payload for structured API or tool reporting."""
        return {
            "error_code": self.error_code,
            "message": self.message,
            "http_status_code": self.http_status_code,
        }


class MultiHopUnauthorizedError(EnhancementToolError):
    """Raised when an agent attempts multi-hop discovery without valid FR-015 authorization."""

    def __init__(self, message: str) -> None:
        super().__init__(
            message=message,
            error_code="MULTIHOP_UNAUTHORIZED",
            http_status_code=403,
        )


class UnresolvableIdentifierError(EnhancementToolError):
    """Raised when an identifier cannot be resolved against OpenAlex."""

    def __init__(self, identifier: str) -> None:
        self.identifier = identifier
        super().__init__(
            message=f"Identifier '{identifier}' could not be resolved in OpenAlex",
            error_code="UNRESOLVABLE_IDENTIFIER",
            http_status_code=404,
        )


class TitleConfirmationRequiredError(EnhancementToolError):
    """Raised when free-text title is submitted without confirmation chip click."""

    def __init__(self, title: str) -> None:
        self.title = title
        super().__init__(
            message=f"Free-text title '{title}' requires user confirmation chip click",
            error_code="CONFIRMATION_REQUIRED",
            http_status_code=400,
        )


class DuplicatePaperError(EnhancementToolError):
    """Raised when paper is already fully ingested in library."""

    def __init__(self, doi: str) -> None:
        self.doi = doi
        super().__init__(
            message=f"Paper '{doi}' is already indexed in the campaign library",
            error_code="DUPLICATE_PAPER",
            http_status_code=409,
        )


class CoverageEvaluationError(EnhancementToolError):
    """Raised when research question semantic coverage calculation fails."""

    def __init__(self, rq_id: str, reason: str) -> None:
        self.rq_id = rq_id
        self.reason = reason
        super().__init__(
            message=f"Coverage calculation for RQ '{rq_id}' failed: {reason}",
            error_code="COVERAGE_EVALUATION_FAILED",
            http_status_code=500,
        )


class MatrixGenerationError(EnhancementToolError):
    """Raised when section synthesis matrix generation fails."""

    def __init__(self, section_id: str, reason: str) -> None:
        self.section_id = section_id
        self.reason = reason
        super().__init__(
            message=f"Matrix generation for section '{section_id}' failed: {reason}",
            error_code="MATRIX_GENERATION_FAILED",
            http_status_code=500,
        )


class CitationHallucinationError(EnhancementToolError):
    """Raised when section synthesis matrix cites ungrounded evidence or unindexed DOIs."""

    def __init__(self, doi: str, section_id: str) -> None:
        self.doi = doi
        self.section_id = section_id
        super().__init__(
            message=f"Ungrounded DOI '{doi}' detected in section '{section_id}' synthesis matrix",
            error_code="CITATION_HALLUCINATION",
            http_status_code=422,
        )


ERROR_STATUS_CODE_MAP: dict[type[EnhancementToolError], int] = {
    EnhancementToolError: 500,
    MultiHopUnauthorizedError: 403,
    UnresolvableIdentifierError: 404,
    TitleConfirmationRequiredError: 400,
    DuplicatePaperError: 409,
    CoverageEvaluationError: 500,
    MatrixGenerationError: 500,
    CitationHallucinationError: 422,
}


def get_http_status_code(exc: EnhancementToolError) -> int:
    """Retrieve corresponding HTTP status code for an enhancement tool error."""
    return getattr(exc, "http_status_code", ERROR_STATUS_CODE_MAP.get(type(exc), 500))

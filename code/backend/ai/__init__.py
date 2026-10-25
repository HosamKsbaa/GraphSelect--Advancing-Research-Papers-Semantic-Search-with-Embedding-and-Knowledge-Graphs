"""Public interface for the ALRS single research agent (`ai`)."""

from .agent import AgentRunStatus, ResearchAgent, ResearchAgentState
from .model_client import (
    GeminiModelClient,
    ModelClientSettings,
    ModelError,
    ModelUsage,
    ModelValidationDiagnostic,
    validate_model_result,
)
from .tools import (
    AgentToolRuntime,
    DiscoverLiteratureOutput,
    GetCollectionOutput,
    SearchPapersOutput,
    WriteReviewOutput,
)
from .verification import VerificationReport, verify_review_citations

__all__ = [
    "AgentRunStatus",
    "AgentToolRuntime",
    "DiscoverLiteratureOutput",
    "GeminiModelClient",
    "GetCollectionOutput",
    "ModelClientSettings",
    "ModelError",
    "ModelUsage",
    "ModelValidationDiagnostic",
    "ResearchAgent",
    "ResearchAgentState",
    "SearchPapersOutput",
    "VerificationReport",
    "WriteReviewOutput",
    "validate_model_result",
    "verify_review_citations",
]

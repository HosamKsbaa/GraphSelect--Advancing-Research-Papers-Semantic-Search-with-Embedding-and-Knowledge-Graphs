"""Public interface for the ALRS single research agent (`ai`)."""

from .agent import ResearchAgent, ResearchAgentState
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

__all__ = [
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
    "WriteReviewOutput",
    "validate_model_result",
]

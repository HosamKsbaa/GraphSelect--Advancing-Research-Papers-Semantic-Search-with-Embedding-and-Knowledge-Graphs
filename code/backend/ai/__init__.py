"""Public interface for the ALRS single research agent (`ai`)."""

from .agent import AgentRunStatus, ResearchAgent, ResearchAgentState
from .mcp_server import (
    McpRpcRequest,
    McpServerAdapter,
    McpToolDefinition,
    build_fastmcp_server,
    create_mcp_router,
)
from .model_client import (
    GeminiModelClient,
    ModelClientSettings,
    ModelError,
    ModelUsage,
    ModelValidationDiagnostic,
    validate_model_result,
)
from .skills import LoadedSkill, SkillMetadata, list_available_skills, load_skill
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
    "LoadedSkill",
    "McpRpcRequest",
    "McpServerAdapter",
    "McpToolDefinition",
    "ModelClientSettings",
    "ModelError",
    "ModelUsage",
    "ModelValidationDiagnostic",
    "ResearchAgent",
    "ResearchAgentState",
    "SearchPapersOutput",
    "SkillMetadata",
    "VerificationReport",
    "WriteReviewOutput",
    "build_fastmcp_server",
    "create_mcp_router",
    "list_available_skills",
    "load_skill",
    "validate_model_result",
    "verify_review_citations",
]

"""Pydantic request and response models for Agent Swarm Inspector and Configuration."""
from __future__ import annotations

from typing import Any, Literal, Optional
from pydantic import BaseModel, Field, field_validator


class ToolParameterProperty(BaseModel):
    """Schema definition for a single tool argument property."""
    type: str = Field(description="JSON schema data type (e.g., 'string', 'integer', 'number', 'boolean', 'array', 'object')")
    description: Optional[str] = Field(None, description="Human-readable description of the argument")
    enum: Optional[list[str]] = Field(None, description="Allowed enumeration values if applicable")
    items: Optional[dict[str, Any]] = Field(None, description="Schema definition for array items")
    default: Optional[Any] = Field(None, description="Default value if not provided")


class ToolParameterSchema(BaseModel):
    """JSON Schema for a tool's parameters."""
    type: str = Field(default="object", description="Root schema type, typically 'object'")
    properties: dict[str, Any] = Field(default_factory=dict, description="Dictionary of argument names to property schemas")
    required: list[str] = Field(default_factory=list, description="List of required parameter names")


class AgentToolDefinition(BaseModel):
    """Registered tool metadata and argument schema."""
    name: str = Field(description="Tool function or class name")
    description: str = Field(default="", description="Tool documentation / docstring summary")
    parameters: ToolParameterSchema = Field(default_factory=ToolParameterSchema, description="JSON argument schema")


class AgentConfig(BaseModel):
    """Active and default configuration parameters for an agent."""
    model: str = Field(description="Currently active model identifier (e.g. 'gemini-2.5-flash', 'gemini-3.7-flash')")
    default_model: str = Field(description="System canonical default model identifier")
    temperature: float = Field(description="Sampling temperature (0.00 to 2.00)")
    default_temperature: float = Field(description="System default temperature")
    top_p: float = Field(description="Sampling nucleus threshold (0.00 to 1.00)")
    default_top_p: float = Field(description="System default top_p")
    max_output_tokens: int = Field(description="Maximum response token limit")
    default_max_output_tokens: int = Field(description="System default maximum response token limit")
    custom_prompt_prefix: Optional[str] = Field(None, description="User-customized prompt prefix / system instruction override")
    system_prompt: str = Field(description="Base / canonical system instruction text")
    is_default: bool = Field(default=True, description="True if active configuration matches canonical system defaults")


class AgentMetadata(BaseModel):
    """Complete metadata and live state for a single agent in the swarm."""
    name: str = Field(description="Canonical agent identifier (e.g. 'ProjectAgent', 'ALRSAgent')")
    display_name: str = Field(description="Human-friendly agent title")
    description: str = Field(description="Detailed agent purpose and role description")
    role: str = Field(description="Architectural specialization role")
    tier: str = Field(description="Hierarchy tier classification ('tier1' or 'tier2')")
    sub_agents: list[str] = Field(default_factory=list, description="List of sub-agent names directly subordinate to this agent")
    tools: list[AgentToolDefinition] = Field(default_factory=list, description="Registered tools with docstrings and argument schemas")
    config: AgentConfig = Field(description="Active and default configuration parameters")


class AgentRegistryResponse(BaseModel):
    """Response payload for GET /api/agents/registry."""
    agents: list[AgentMetadata] = Field(description="All discovered agents in the live hierarchy")
    total: int = Field(description="Total number of agents discovered")
    system_default_tier1_model: str = Field(description="Default model for Tier 1 Orchestrator and Reasoning agents")
    system_default_tier2_model: str = Field(description="Default model for Tier 2 Worker agents")


class AgentConfigUpdate(BaseModel):
    """Per-agent configuration parameters update payload."""
    model: Optional[str] = Field(None, description="New model identifier")
    temperature: Optional[float] = Field(None, ge=0.0, le=2.0, description="Temperature between 0.0 and 2.0")
    top_p: Optional[float] = Field(None, ge=0.0, le=1.0, description="Top-P nucleus sampling parameter between 0.0 and 1.0")
    max_output_tokens: Optional[int] = Field(None, ge=128, le=65536, description="Max output tokens between 128 and 65,536")
    custom_prompt_prefix: Optional[str] = Field(None, description="Optional custom prompt prefix override")

    @field_validator("model", "custom_prompt_prefix", mode="before")
    @classmethod
    def strip_strings(cls, v: Any) -> Any:
        if isinstance(v, str):
            return v.strip()
        return v


class AgentSettingsUpdateRequest(BaseModel):
    """Request payload for PUT /api/agents/settings."""
    settings: dict[str, AgentConfigUpdate] = Field(
        ...,
        description="Map of agent name to updated configuration parameters"
    )


class AgentSettingsUpdateResponse(BaseModel):
    """Response payload after updating agent settings."""
    success: bool = Field(description="True if settings were saved and hot-reloaded successfully")
    message: str = Field(description="Summary message")
    updated_agents: list[str] = Field(default_factory=list, description="List of agent names whose configurations were modified")


class AgentResetRequest(BaseModel):
    """Request payload for POST /api/agents/settings/reset."""
    agent_name: Optional[str] = Field(None, description="Optional specific agent name to reset; if omitted, resets all agents")


class AgentResetResponse(BaseModel):
    """Response payload after resetting agent settings."""
    success: bool = Field(description="True if reset completed successfully")
    message: str = Field(description="Summary message")
    reset_agents: list[str] = Field(default_factory=list, description="List of agent names that were restored to factory defaults")


class ToolCallTrace(BaseModel):
    """Structured tool execution trace."""
    name: str = Field(description="Tool function name")
    arguments: dict[str, Any] = Field(default_factory=dict, description="Arguments passed to tool")
    result: str = Field(default="", description="Summary / stringified result of tool execution")


class LiveAgentTrace(BaseModel):
    """Structured execution trace event for LLM calls and tool executions."""
    id: str = Field(description="Unique trace event identifier")
    timestamp: str = Field(description="ISO 8601 formatted timestamp")
    project_id: Optional[str] = Field(None, description="Associated project ID if applicable")
    agent_name: str = Field(description="Name of agent that emitted the trace")
    action_summary: str = Field(description="Short human-readable summary of the action or event")
    llm_prompt: Optional[str] = Field(None, description="Prompt payload / system instructions sent to LLM")
    llm_response: Optional[str] = Field(None, description="Raw text or structured JSON completion from LLM")
    tool_calls: list[ToolCallTrace] = Field(default_factory=list, description="List of tool invocations performed in this event")
    token_count: int = Field(default=0, description="Tokens consumed during this operation")
    latency_ms: Optional[float] = Field(None, description="Execution latency in milliseconds")
    status: str = Field(default="success", description="'success' or 'error'")
    decision_outcome: Optional[str] = Field(None, description="Next-step decision or outcome")


class AgentTraceListResponse(BaseModel):
    """Response payload for GET /api/agents/traces."""
    traces: list[LiveAgentTrace] = Field(default_factory=list, description="List of recent execution traces")
    total: int = Field(description="Total count of matching trace events")

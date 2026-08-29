"""Pydantic request and response models for Agent Swarm Inspector, Tier Management & Configuration."""
from __future__ import annotations

import re
from typing import Any, Literal, Optional
from pydantic import BaseModel, Field, field_validator, model_validator

# Regex pattern for hex colors (#RGB, #RRGGBB, #RRGGBBAA)
HEX_COLOR_REGEX = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")
# Slug pattern for Tier IDs
TIER_ID_REGEX = re.compile(r"^[a-z0-9_-]{1,64}$")


# ============================================================================
# Tool Schema Models
# ============================================================================

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


# ============================================================================
# Model Tier Schemas (Milestone 1)
# ============================================================================

class ModelTier(BaseModel):
    """Represents a configured model tier in the dynamic registry."""
    id: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="Unique tier identifier slug (e.g., 'tier1', 'tier2', 'tier3', 'tier_fast_eval')"
    )
    name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Human-readable tier title (e.g., 'Tier 1: Orchestration & Reasoning')"
    )
    description: Optional[str] = Field(
        default="",
        description="Architectural purpose and role description for this tier"
    )
    model: str = Field(
        ...,
        min_length=1,
        description="Default LLM model identifier for agents in this tier (e.g., 'gemini-2.5-flash', 'gemini-2.5-pro')"
    )
    temperature: float = Field(
        default=0.7,
        ge=0.0,
        le=2.0,
        description="Default sampling temperature (0.00 to 2.00)"
    )
    top_p: float = Field(
        default=0.95,
        ge=0.0,
        le=1.0,
        description="Default nucleus sampling parameter (0.00 to 1.00)"
    )
    max_output_tokens: int = Field(
        default=8192,
        ge=128,
        le=65536,
        description="Default maximum response token limit (128 to 65,536)"
    )
    color: str = Field(
        default="#3b82f6",
        description="Hex color code for UI badges and cards (e.g., '#3b82f6', '#10b981', '#8b5cf6')"
    )
    is_system: bool = Field(
        default=False,
        description="True if this is a built-in immutable system tier that cannot be deleted"
    )

    @field_validator("id", mode="before")
    @classmethod
    def normalize_id(cls, v: Any) -> Any:
        if isinstance(v, str):
            v_clean = v.strip().lower()
            if not TIER_ID_REGEX.match(v_clean):
                raise ValueError(
                    f"Tier ID '{v}' must be 1-64 alphanumeric characters, underscores, or hyphens (lowercase)."
                )
            return v_clean
        return v

    @field_validator("name", "model", "description", "color", mode="before")
    @classmethod
    def sanitize_strings(cls, v: Any) -> Any:
        if isinstance(v, str):
            return v.strip()
        return v

    @field_validator("color")
    @classmethod
    def validate_color_hex(cls, v: str) -> str:
        if not HEX_COLOR_REGEX.match(v):
            raise ValueError(f"Color '{v}' must be a valid hex color format (e.g. '#3b82f6', '#10b981').")
        return v


class TierCreateRequest(BaseModel):
    """Request payload for creating a new custom tier (POST /api/agents/tiers)."""
    id: Optional[str] = Field(
        None,
        min_length=1,
        max_length=64,
        description="Optional custom tier ID slug; auto-generated if omitted"
    )
    name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Human-readable tier title"
    )
    description: Optional[str] = Field(
        default="",
        description="Optional tier description"
    )
    model: str = Field(
        ...,
        min_length=1,
        description="Default LLM model identifier (e.g. 'gemini-2.5-flash')"
    )
    temperature: float = Field(
        default=0.7,
        ge=0.0,
        le=2.0,
        description="Default sampling temperature"
    )
    top_p: float = Field(
        default=0.95,
        ge=0.0,
        le=1.0,
        description="Default nucleus sampling parameter"
    )
    max_output_tokens: int = Field(
        default=8192,
        ge=128,
        le=65536,
        description="Default max output tokens limit"
    )
    color: str = Field(
        default="#3b82f6",
        description="Hex color code (e.g. '#3b82f6')"
    )

    @field_validator("id", mode="before")
    @classmethod
    def normalize_id(cls, v: Any) -> Any:
        if isinstance(v, str):
            v_clean = v.strip().lower()
            if v_clean in {"tier1", "tier2", "tier3"}:
                raise ValueError(f"Cannot create custom tier with reserved system ID '{v_clean}'.")
            if not TIER_ID_REGEX.match(v_clean):
                raise ValueError(f"Tier ID '{v}' must match pattern {TIER_ID_REGEX.pattern}")
            return v_clean
        return v

    @field_validator("name", "model", "description", "color", mode="before")
    @classmethod
    def sanitize_strings(cls, v: Any) -> Any:
        if isinstance(v, str):
            return v.strip()
        return v

    @field_validator("color")
    @classmethod
    def validate_color_hex(cls, v: str) -> str:
        if not HEX_COLOR_REGEX.match(v):
            raise ValueError(f"Color '{v}' must be a valid hex color format (e.g. '#3b82f6').")
        return v


class TierUpdateRequest(BaseModel):
    """Request payload for updating an existing tier (PUT /api/agents/tiers/{tier_id})."""
    name: Optional[str] = Field(None, min_length=1, max_length=100, description="Updated tier title")
    description: Optional[str] = Field(None, description="Updated tier description")
    model: Optional[str] = Field(None, min_length=1, description="Updated default model identifier")
    temperature: Optional[float] = Field(None, ge=0.0, le=2.0, description="Updated default temperature")
    top_p: Optional[float] = Field(None, ge=0.0, le=1.0, description="Updated default top_p")
    max_output_tokens: Optional[int] = Field(None, ge=128, le=65536, description="Updated max output tokens")
    color: Optional[str] = Field(None, description="Updated hex color badge")

    @field_validator("name", "model", "description", "color", mode="before")
    @classmethod
    def sanitize_strings(cls, v: Any) -> Any:
        if isinstance(v, str):
            return v.strip()
        return v

    @field_validator("color")
    @classmethod
    def validate_color_hex(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not HEX_COLOR_REGEX.match(v):
            raise ValueError(f"Color '{v}' must be a valid hex color format (e.g. '#3b82f6').")
        return v


class TierListResponse(BaseModel):
    """Response payload for GET /api/agents/tiers."""
    tiers: list[ModelTier] = Field(description="All registered system and custom model tiers")
    total: int = Field(description="Total count of registered tiers")


class TierDeleteResponse(BaseModel):
    """Response payload after deleting a custom tier (DELETE /api/agents/tiers/{tier_id})."""
    status: str = Field(default="deleted", description="Operation status ('deleted')")
    tier_id: str = Field(description="ID of the deleted tier")
    reassigned_agents_count: int = Field(
        default=0,
        description="Number of agents previously in this tier safely reassigned to default tier"
    )
    reassigned_to_tier_id: str = Field(
        default="tier1",
        description="Target tier ID that orphaned agents were reassigned to"
    )
    message: Optional[str] = Field(default=None, description="Confirmation message")


# ============================================================================
# Agent Configuration Models (Enhanced with Inheritance & Effective Values)
# ============================================================================

class AgentConfig(BaseModel):
    """Active, inherited, and effective configuration parameters for a swarm agent."""
    
    # Mode & Tier assignment
    config_mode: str = Field(
        default="inherit",
        description="Configuration mode: 'inherit' (cascades from assigned tier) or 'custom' (uses per-agent parameter overrides)"
    )
    assigned_tier_id: str = Field(
        default="tier1",
        description="Assigned ModelTier ID (e.g. 'tier1', 'tier2', 'tier3', or custom tier slug)"
    )
    
    # Active / configured parameters
    model: str = Field(description="Active or configured model identifier (e.g. 'gemini-2.5-flash')")
    default_model: str = Field(description="System canonical default model identifier")
    temperature: float = Field(description="Sampling temperature (0.00 to 2.00)")
    default_temperature: float = Field(description="System canonical default temperature")
    top_p: float = Field(description="Sampling nucleus threshold (0.00 to 1.00)")
    default_top_p: float = Field(description="System canonical default top_p")
    max_output_tokens: int = Field(description="Maximum response token limit")
    default_max_output_tokens: int = Field(description="System canonical default maximum response token limit")
    custom_prompt_prefix: Optional[str] = Field(None, description="User-customized prompt prefix / system instruction override")
    system_prompt: str = Field(description="Base / canonical system instruction text")
    is_default: bool = Field(default=True, description="True if active configuration matches canonical system defaults")

    # Resolved Effective Runtime Values (Computed from Tier vs Custom Override)
    effective_model: str = Field(
        description="Resolved runtime model (from inherited tier or custom override)"
    )
    effective_temperature: float = Field(
        description="Resolved runtime temperature (from inherited tier or custom override)"
    )
    effective_top_p: float = Field(
        description="Resolved runtime top_p (from inherited tier or custom override)"
    )
    effective_max_output_tokens: int = Field(
        description="Resolved runtime max output tokens (from inherited tier or custom override)"
    )


class AgentMetadata(BaseModel):
    """Complete metadata and live state for a single agent in the swarm."""
    name: str = Field(description="Canonical agent identifier (e.g. 'ProjectAgent', 'ALRSAgent')")
    display_name: str = Field(description="Human-friendly agent title")
    description: str = Field(description="Detailed agent purpose and role description")
    role: str = Field(description="Architectural specialization role")
    tier: str = Field(description="Hierarchy tier classification ('tier1', 'tier2', 'tier3', or assigned tier ID)")
    assigned_tier_id: Optional[str] = Field(default=None, description="Assigned tier ID slug")
    config_mode: Optional[str] = Field(default="inherit", description="Configuration mode ('inherit' or 'custom')")
    sub_agents: list[str] = Field(default_factory=list, description="List of sub-agent names directly subordinate to this agent")
    tools: list[AgentToolDefinition] = Field(default_factory=list, description="Registered tools with docstrings and argument schemas")
    config: AgentConfig = Field(description="Active, inherited, and effective configuration parameters")


class AgentRegistryResponse(BaseModel):
    """Response payload for GET /api/agents/registry."""
    agents: list[AgentMetadata] = Field(description="All discovered agents in the live hierarchy")
    total: int = Field(description="Total number of agents discovered")
    tiers: list[ModelTier] = Field(default_factory=list, description="All available system and custom model tiers")
    system_default_tier1_model: str = Field(description="Default model for Tier 1 Orchestrator and Reasoning agents")
    system_default_tier2_model: str = Field(description="Default model for Tier 2 Worker agents")


# ============================================================================
# Update & Mutation Request/Response Models
# ============================================================================

class AgentConfigUpdate(BaseModel):
    """Per-agent configuration parameters update payload."""
    config_mode: Optional[str] = Field(
        None,
        description="Switch between 'inherit' (inherits tier defaults) and 'custom' (uses individual overrides)"
    )
    assigned_tier_id: Optional[str] = Field(
        None,
        description="Assign agent to a new ModelTier ID (e.g. 'tier1', 'tier2', 'tier3', or custom tier ID)"
    )
    tier_id: Optional[str] = Field(
        None,
        description="Alias for assigned_tier_id for backward compatibility and concise payload construction"
    )
    model: Optional[str] = Field(None, description="New custom model identifier")
    temperature: Optional[float] = Field(None, ge=0.0, le=2.0, description="Temperature between 0.0 and 2.0")
    top_p: Optional[float] = Field(None, ge=0.0, le=1.0, description="Top-P nucleus sampling parameter between 0.0 and 1.0")
    max_output_tokens: Optional[int] = Field(None, ge=128, le=65536, description="Max output tokens between 128 and 65,536")
    custom_prompt_prefix: Optional[str] = Field(None, description="Optional custom prompt prefix override")

    @model_validator(mode="before")
    @classmethod
    def unify_tier_id(cls, values: Any) -> Any:
        if isinstance(values, dict):
            tier_id = values.get("tier_id")
            assigned = values.get("assigned_tier_id")
            if tier_id and not assigned:
                values["assigned_tier_id"] = tier_id
        return values

    @field_validator("model", "custom_prompt_prefix", "assigned_tier_id", "tier_id", mode="before")
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


# Models for GET/PUT /api/agents/config
class AgentConfigItem(BaseModel):
    """Configuration state for an individual agent in the swarm."""
    agent_id: str = Field(description="Canonical agent identifier (e.g. 'ProjectAgent', 'ALRSAgent')")
    name: Optional[str] = Field(None, description="Canonical agent name")
    display_name: str = Field(description="Human-friendly agent title")
    role: str = Field(description="Specialized agent architectural role")
    tier_id: str = Field(description="Assigned tier identifier (e.g. 'tier1', 'tier2', 'tier3', or custom tier slug)")
    assigned_tier_id: str = Field(description="Assigned tier identifier")
    config_mode: str = Field(
        default="inherit",
        description="'inherit' to inherit model and sampling parameters from tier; 'custom' to use explicit overrides",
    )
    model: str = Field(description="Currently active or configured model identifier")
    temperature: float = Field(description="Currently active or configured sampling temperature")
    top_p: float = Field(description="Currently active or configured nucleus sampling top_p")
    max_output_tokens: int = Field(description="Currently active or configured maximum response token limit")
    custom_prompt_prefix: Optional[str] = Field(None, description="Optional custom prompt prefix override")
    system_prompt: str = Field(description="Base / canonical system instruction text")
    effective_model: str = Field(description="Resolved effective model identifier")
    effective_temperature: float = Field(description="Resolved effective temperature")
    effective_top_p: float = Field(description="Resolved effective top_p")
    effective_max_output_tokens: int = Field(description="Resolved effective max tokens")
    is_default: bool = Field(default=True, description="True if active configuration matches canonical system defaults")


class AgentConfigListResponse(BaseModel):
    """Response payload for GET /api/agents/config."""
    agents: list[AgentConfigItem] = Field(description="Configuration state for all agents in the swarm")
    total: int = Field(description="Total number of agents")


class AgentConfigOverrideItem(BaseModel):
    """Individual agent override specification in batch update."""
    agent_id: str = Field(description="Canonical agent identifier")
    tier_id: Optional[str] = Field(None, description="Tier to assign the agent to")
    assigned_tier_id: Optional[str] = Field(None, description="Alias for tier_id")
    config_mode: Optional[Literal["inherit", "custom"]] = Field(
        None,
        description="'inherit' or 'custom'"
    )
    model: Optional[str] = Field(None, description="Explicit model override (when mode is custom)")
    temperature: Optional[float] = Field(None, ge=0.0, le=2.0, description="Explicit temperature override")
    top_p: Optional[float] = Field(None, ge=0.0, le=1.0, description="Explicit top_p override")
    max_output_tokens: Optional[int] = Field(None, ge=128, le=65536, description="Explicit max tokens override")
    custom_prompt_prefix: Optional[str] = Field(None, description="Custom prompt prefix override")

    @model_validator(mode="before")
    @classmethod
    def unify_tier_id(cls, values: Any) -> Any:
        if isinstance(values, dict):
            tier_id = values.get("tier_id")
            assigned = values.get("assigned_tier_id")
            if tier_id and not assigned:
                values["assigned_tier_id"] = tier_id
        return values


class AgentConfigBatchUpdateRequest(BaseModel):
    """Request payload for PUT /api/agents/config."""
    overrides: list[AgentConfigOverrideItem] = Field(
        ...,
        description="List of agent configuration overrides to apply",
    )


class AgentConfigBatchUpdateResponse(BaseModel):
    """Response payload for PUT /api/agents/config."""
    success: bool = Field(default=True, description="True if updates were applied and hot-reloaded successfully")
    message: str = Field(description="Summary message")
    updated_agents: list[str] = Field(default_factory=list, description="List of updated agent IDs")
    agents: list[AgentConfigItem] = Field(default_factory=list, description="Updated configurations for all agents")


# ============================================================================
# Execution Tracing Models
# ============================================================================

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

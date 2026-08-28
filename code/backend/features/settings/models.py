"""Pydantic request/response models for the settings feature."""
from __future__ import annotations

from typing import Any, Literal, Optional
from pydantic import BaseModel, Field, field_validator


class SettingsResponse(BaseModel):
    """Current settings with dual-mode metadata (API keys are masked)."""

    gemini_api_key_set: bool = Field(description="Whether a real Gemini API key is configured")
    gemini_api_key_preview: str = Field(description="Masked preview of the key (last 4 chars)")
    openalex_api_key_set: bool = Field(description="Whether a real OpenAlex API key is configured")
    openalex_api_key_preview: str = Field(description="Masked preview of the key (last 4 chars)")
    openalex_email: str = Field(description="Email for OpenAlex polite pool")
    embedding_model: str = Field(description="Current embedding model name")
    embedding_dimensions: int = Field(description="Current embedding dimensions")

    # Dual-mode auth extensions
    use_vertex_ai: bool = Field(default=False, description="Whether Vertex AI mode is active")
    mode: Literal["studio", "vertex"] = Field(default="studio", description="Active auth mode ('studio' or 'vertex')")
    vertex_project: Optional[str] = Field(default=None, description="GCP project for Vertex AI")
    vertex_location: Optional[str] = Field(default="us-central1", description="GCP location for Vertex AI")
    has_credentials: bool = Field(default=False, description="Whether active mode has valid credentials configured")

    # Tiered Model Architecture extensions
    adk_tier1_model: str = Field(default="gemini-2.5-flash", description="Model for Tier 1 Orchestration & Reasoning agents")
    adk_tier2_model: str = Field(default="gemini-3.5-flash-lite", description="Model for Tier 2 Specialized Worker agents")
    available_models: list[str] = Field(
        default_factory=lambda: [
            "gemini-2.5-flash",
            "gemini-2.5-pro",
            "gemini-3.5-flash",
            "gemini-3.5-flash-lite",
            "gemini-3.1-flash-lite",
        ],
        description="List of selectable models for agent tiers",
    )


class ModelInfo(BaseModel):
    """Metadata for an available Gemini model fetched from the Google API."""

    name: str = Field(description="Unique model name e.g. 'gemini-2.5-flash'")
    display_name: Optional[str] = Field(None, description="Human-readable display name")
    description: Optional[str] = Field(None, description="Short summary of model capabilities")
    supported_actions: list[str] = Field(default_factory=list, description="Supported operations e.g. generateContent")


class AvailableModelsResponse(BaseModel):
    """Response containing live models fetched directly from Google API."""

    models: list[str] = Field(description="List of model names for select dropdowns")
    model_details: list[ModelInfo] = Field(default_factory=list, description="Full model metadata if available")
    source: Literal["google_api", "fallback"] = Field(description="Whether models were fetched live from Google API or fallback")
    total: int = Field(description="Total models returned")


class SettingsUpdateRequest(BaseModel):
    """Request body for updating settings."""

    gemini_api_key: Optional[str] = Field(None, description="New Gemini API key (leave empty to keep current)")
    openalex_api_key: Optional[str] = Field(None, description="New OpenAlex API key (leave empty to keep current)")
    openalex_email: Optional[str] = Field(None, description="Email for OpenAlex polite pool")
    use_vertex_ai: Optional[bool] = Field(None, description="Whether to use Vertex AI")
    vertex_project: Optional[str] = Field(None, description="Google Cloud project ID for Vertex AI")
    vertex_location: Optional[str] = Field(None, description="Vertex AI location region")
    mode: Optional[Literal["studio", "vertex"]] = Field(None, description="Auth mode ('studio' or 'vertex')")
    adk_tier1_model: Optional[str] = Field(None, description="Model for Tier 1 Orchestration agents")
    adk_tier2_model: Optional[str] = Field(None, description="Model for Tier 2 Worker agents")

    @field_validator(
        "gemini_api_key", "vertex_project", "vertex_location",
        "openalex_api_key", "openalex_email", mode="before", check_fields=False
    )
    @classmethod
    def sanitize_input_lines(cls, v: Any) -> Any:
        if isinstance(v, str):
            lines = [line.strip() for line in v.splitlines() if line.strip()]
            return lines[0] if lines else ""
        return v


class SettingsUpdateResponse(BaseModel):
    """Response after updating settings."""

    success: bool
    message: str
    restart_required: bool = Field(
        default=False,
        description="Whether a server restart is needed for changes to take effect",
    )


class AuthStatusResponse(BaseModel):
    """Active authentication status and credentials state for frontend UI/modal."""

    mode: Literal["studio", "vertex"] = Field(
        description="Active provider mode: 'studio' for Google AI Studio, 'vertex' for Google Cloud Vertex AI"
    )
    has_credentials: bool = Field(
        description="True if the active provider mode has valid, non-placeholder credentials configured"
    )
    gemini_api_key_preview: Optional[str] = Field(
        default=None,
        description="Masked preview of Gemini API key, or null if unset"
    )
    gemini_api_key_set: bool = Field(
        default=False,
        description="True if Gemini API key is configured"
    )
    vertex_project: Optional[str] = Field(
        default=None,
        description="Configured Google Cloud Project ID for Vertex AI, or null if unset"
    )
    vertex_location: str = Field(
        default="us-central1",
        description="Configured Google Cloud Location/Region for Vertex AI"
    )
    use_vertex_ai: bool = Field(
        default=False,
        description="Boolean flag matching mode: True if vertex, False if studio"
    )
    openalex_api_key_preview: Optional[str] = Field(
        default=None,
        description="Masked preview of OpenAlex API key, or null if unset"
    )
    openalex_api_key_set: bool = Field(
        default=False,
        description="True if an OpenAlex API key is configured"
    )
    openalex_email: Optional[str] = Field(
        default="",
        description="Email address for OpenAlex polite pool"
    )


# Alias for spec.md contract consistency
SettingsAuthResponse = AuthStatusResponse


class TestConnectionRequest(BaseModel):
    """Request payload for connection testing."""

    mode: Optional[Literal["studio", "vertex"]] = Field(
        default=None,
        description="Provider mode to test: 'studio' or 'vertex' (defaults to active mode if omitted)",
    )
    gemini_api_key: Optional[str] = Field(
        default=None,
        description="Candidate Gemini API key to test (optional; uses configured key if omitted)",
    )
    vertex_project: Optional[str] = Field(
        default=None,
        description="Candidate GCP Project ID for Vertex AI (optional; uses configured project if omitted)",
    )
    vertex_location: Optional[str] = Field(
        default="us-central1",
        description="Candidate GCP location/region for Vertex AI",
    )

    @field_validator("gemini_api_key", "vertex_project", "vertex_location", mode="before", check_fields=False)
    @classmethod
    def sanitize_input_lines(cls, v: Any) -> Any:
        if isinstance(v, str):
            lines = [line.strip() for line in v.splitlines() if line.strip()]
            return lines[0] if lines else ""
        return v


class TestConnectionResponse(BaseModel):
    """Response payload for connection testing."""

    success: bool = Field(
        ...,
        description="True if probe ping succeeded, False if failed"
    )
    message: str = Field(
        ...,
        description="Summary status message"
    )
    model: Optional[str] = Field(
        default=None,
        description="Model name that answered the probe ping (e.g. 'gemini-3.5-flash')"
    )
    latency_ms: Optional[float] = Field(
        default=None,
        description="Round-trip probe latency in milliseconds"
    )
    mode: Optional[Literal["studio", "vertex"]] = Field(
        default=None,
        description="Provider mode tested"
    )
    error: Optional[str] = Field(
        default=None,
        description="Human-readable error details if success is False"
    )
    details: Optional[str] = Field(
        default=None,
        description="Actionable troubleshooting guidance"
    )


class AuthUpdateRequest(BaseModel):
    """Request payload for updating auth settings."""

    mode: Optional[Literal["studio", "vertex"]] = Field(
        default=None,
        description="Target provider mode: 'studio' or 'vertex'"
    )
    use_vertex_ai: Optional[bool] = Field(
        default=None,
        description="Explicit boolean flag for Vertex AI mode"
    )
    gemini_api_key: Optional[str] = Field(
        default=None,
        description="New Gemini API key (leave null to keep current)"
    )
    vertex_project: Optional[str] = Field(
        default=None,
        description="New GCP Project ID (leave null to keep current)"
    )
    vertex_location: Optional[str] = Field(
        default="us-central1",
        description="New GCP Location (leave null to keep current)"
    )
    openalex_api_key: Optional[str] = Field(
        default=None,
        description="New OpenAlex API key (leave null to keep current)"
    )
    openalex_email: Optional[str] = Field(
        default=None,
        description="New OpenAlex contact email"
    )

    @field_validator(
        "gemini_api_key", "vertex_project", "vertex_location",
        "openalex_api_key", "openalex_email", mode="before", check_fields=False
    )
    @classmethod
    def sanitize_input_lines(cls, v: Any) -> Any:
        if isinstance(v, str):
            lines = [line.strip() for line in v.splitlines() if line.strip()]
            return lines[0] if lines else ""
        return v


# Alias for spec.md contract consistency
SettingsAuthUpdateRequest = AuthUpdateRequest


class SettingsAuthUpdateResponse(BaseModel):
    """Response payload after updating auth settings."""

    success: bool = Field(..., description="True if settings were saved and hot-swapped successfully")
    message: str = Field(..., description="Summary message of changes applied")
    mode: Literal["studio", "vertex"] = Field(..., description="Active provider mode after update")
    has_credentials: bool = Field(..., description="True if active mode has valid credentials")
    gemini_api_key_preview: Optional[str] = Field(default=None, description="Masked preview of Gemini API key")
    vertex_project: Optional[str] = Field(default=None, description="Active GCP Project ID")
    vertex_location: str = Field(default="us-central1", description="Active GCP Location")
    use_vertex_ai: bool = Field(..., description="Active use_vertex_ai boolean flag")
    restart_required: bool = Field(
        default=False,
        description="Always False due to dynamic in-memory hot-swapping"
    )


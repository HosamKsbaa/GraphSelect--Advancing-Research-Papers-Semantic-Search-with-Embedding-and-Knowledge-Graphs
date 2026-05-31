"""Pydantic request/response models for the settings feature."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class SettingsResponse(BaseModel):
    """Current settings (API keys are masked)."""

    gemini_api_key_set: bool = Field(description="Whether a real Gemini API key is configured")
    gemini_api_key_preview: str = Field(description="Masked preview of the key (last 4 chars)")
    openalex_api_key_set: bool = Field(description="Whether a real OpenAlex API key is configured")
    openalex_api_key_preview: str = Field(description="Masked preview of the key (last 4 chars)")
    openalex_email: str = Field(description="Email for OpenAlex polite pool")
    embedding_model: str = Field(description="Current embedding model name")
    embedding_dimensions: int = Field(description="Current embedding dimensions")


class SettingsUpdateRequest(BaseModel):
    """Request body for updating settings."""

    gemini_api_key: Optional[str] = Field(None, description="New Gemini API key (leave empty to keep current)")
    openalex_api_key: Optional[str] = Field(None, description="New OpenAlex API key (leave empty to keep current)")
    openalex_email: Optional[str] = Field(None, description="Email for OpenAlex polite pool")


class SettingsUpdateResponse(BaseModel):
    """Response after updating settings."""

    success: bool
    message: str
    restart_required: bool = Field(
        default=True,
        description="Whether a server restart is needed for changes to take effect",
    )

"""Project management Pydantic models for ALRS v2.

Defines the request/response shapes for the project lifecycle:
create, read, update, and archive operations.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ProjectCreate(BaseModel):
    """Schema for creating a new research project."""

    name: str = Field(..., min_length=1, max_length=200, description="Project name")
    description: str | None = Field(default=None, max_length=2000, description="Project description")
    topic: str | None = Field(default=None, max_length=500, description="Research topic")
    target_level: Literal["master", "phd"] = Field(
        default="master",
        description="Academic level of the literature review",
    )
    similarity_threshold: float = Field(
        default=0.6,
        ge=0.0,
        le=1.0,
        description="Minimum relevance score for paper inclusion",
    )
    token_budget: int = Field(
        default=500000,
        ge=1000,
        description="Token budget for the full pipeline run",
    )


class ProjectUpdate(BaseModel):
    """Schema for updating an existing project. All fields are optional."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    topic: str | None = Field(default=None, max_length=500)
    target_level: Literal["master", "phd"] | None = None
    similarity_threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    token_budget: int | None = Field(default=None, ge=1000)


class ProjectResponse(BaseModel):
    """Full project representation returned by the API."""

    id: str = Field(..., description="UUID project identifier")
    name: str
    description: str | None = None
    topic: str | None = None
    target_level: str = "master"
    similarity_threshold: float = 0.6
    token_budget: int = 500000
    status: str = "active"
    created_at: datetime | None = None
    updated_at: datetime | None = None

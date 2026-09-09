"""Pydantic v2 domain models for continuous literature ingestion.

Complies with Constitution v2.2.1:
- C7: Strict static typing without bare signatures or Any bloat.
- C9: Granular sub-routines under 25 lines with single responsibility.
- C11: Intention-revealing domain types and predicate booleans.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


class IngestionSource(str, Enum):
    """Origin source of literature ingestion into epistemic graph."""

    SEED = "seed"
    SNOWBALL = "snowball"
    USER_CONTEXT = "user_context"
    GAP_REMEDIATION = "gap_remediation"
    MULTI_HOP_BRIDGE = "multi_hop_bridge"


class IdentifierType(str, Enum):
    """Class of academic publication identifier detected in chat stream."""

    DOI = "doi"
    ARXIV = "arxiv"
    URL = "url"
    TITLE = "title"


class TitleConfirmationChip(BaseModel):
    """Interactive confirmation chip rendered in chat UI for fuzzy paper titles."""

    chip_id: str = Field(..., description="Unique UUID for this confirmation interaction")
    extracted_title: str = Field(..., min_length=3, description="Cleaned title extracted from message")
    resolved_openalex_id: str = Field(..., description="Resolved canonical OpenAlex ID")
    resolved_doi: str | None = Field(default=None, description="Resolved canonical DOI if available")
    resolved_title: str = Field(..., description="Official title returned by OpenAlex")
    similarity_score: float = Field(..., ge=0.0, le=1.0, description="String similarity score (>= 0.90)")
    status: str = Field(default="pending", description="'pending' | 'confirmed' | 'dismissed'")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class UserIngestedPaper(BaseModel):
    """Paper extracted dynamically from conversational review context."""

    raw_identifier: str = Field(..., description="Raw text identifier, arXiv string, or URL mentioned by researcher")
    doi: str = Field(..., min_length=5, description="Normalized canonical lowercase DOI (e.g. 10.1145/...)")
    openalex_id: str | None = Field(default=None, description="OpenAlex Work identifier (e.g. W12345)")
    title: str = Field(..., min_length=1, description="Official paper title")
    authors: list[str] = Field(default_factory=list, description="List of author display names")
    year: int | None = Field(default=None, ge=1900, le=2100, description="Publication year")
    abstract: str | None = Field(default=None, description="Reconstructed plain text abstract")
    embedding: list[float] | None = Field(default=None, description="768-dimensional normalized embedding")
    ingestion_source: IngestionSource = Field(default=IngestionSource.USER_CONTEXT)
    referenced_dois: list[str] = Field(default_factory=list, description="Outbound reference DOIs")
    resolution_status: str = Field(default="resolved", description="'resolved' | 'pending' | 'failed'")
    is_stub: bool = Field(default=False, description="True if only stub metadata is known")
    is_bridge: bool = Field(default=False, description="True if discovered as a multi-hop bridge")
    can_expand_deeply: bool = Field(default=False, description="True if FR-016 relevance gate is passed")
    is_retracted: bool = Field(default=False, description="True if paper has an official retraction notice")
    mentioned_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp of user mention in chat",
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("doi")
    @classmethod
    def normalize_doi(cls, v: str) -> str:
        """Normalize input string to canonical lowercase DOI prefix '10.'."""
        clean = v.lower().strip()
        prefixes = (
            "https://doi.org/",
            "http://doi.org/",
            "https://dx.doi.org/",
            "http://dx.doi.org/",
            "doi.org/",
            "dx.doi.org/",
        )
        for prefix in prefixes:
            if clean.startswith(prefix):
                clean = clean[len(prefix) :]
        if not clean.startswith("10."):
            raise ValueError(f"Invalid canonical DOI format: {v}")
        return clean


class IngestUserPaperInput(BaseModel):
    """Input contract for ingesting a user-referenced paper into campaign library."""

    identifier: str = Field(default="", description="Normalized DOI, arXiv ID, or URL extracted from chat")
    raw_input: str | None = Field(default=None, description="Raw input alias for identifier")
    project_id: str = Field(..., description="Active research project / campaign UUID")
    is_title_confirmed: bool = Field(default=False, description="True if free-text title was confirmed by researcher")
    run_id: str = Field(..., description="Active workflow execution / run UUID per Constitution C5, A15, A49")
    stage_index: int = Field(default=2, description="Workflow stage index where ingestion occurred")

    @model_validator(mode="before")
    @classmethod
    def synchronize_identifier_fields(cls, data: Any) -> Any:
        """Support both identifier and raw_input aliases across tool callers."""
        if isinstance(data, dict):
            if not data.get("identifier") and data.get("raw_input"):
                data["identifier"] = data["raw_input"]
            elif not data.get("raw_input") and data.get("identifier"):
                data["raw_input"] = data["identifier"]
        return data


class IngestUserPaperOutput(BaseModel):
    """Output contract returned after paper ingestion and bidirectional wiring."""

    status: str = Field(default="success", description="'success' | 'failed' | 'pending_confirmation'")
    doi: str | None = Field(default=None, description="Normalized canonical lowercase DOI")
    openalex_id: str | None = Field(default=None, description="Canonical OpenAlex identifier")
    title: str = Field(default="", description="Official publication title")
    citation_links_created: int = Field(default=0, description="Total bidirectional :CITES edges created")
    can_expand_deeply: bool = Field(default=False, description="True if FR-016 relevance gate is satisfied")
    max_rq_relevance: float = Field(default=0.0, ge=0.0, le=1.0, description="Max cosine similarity against active RQs")
    message: str = Field(default="", description="Human-readable execution summary")
    confirmation_chip: TitleConfirmationChip | None = Field(
        default=None, description="Optional chip if title requires confirmation"
    )


class ConfirmTitleIngestionInput(BaseModel):
    """Input contract when user clicks an interactive confirmation chip."""

    chip_id: str = Field(..., description="UUID of the confirmation chip")
    project_id: str = Field(..., description="Active research project UUID")
    confirmed: bool = Field(..., description="True if researcher confirmed ingestion, False if dismissed")
    resolved_openalex_id: str = Field(..., description="Resolved OpenAlex identifier from chip")
    resolved_doi: str | None = Field(default=None, description="Resolved canonical DOI if available")
    resolved_title: str = Field(..., description="Paper title to be ingested")
    run_id: str = Field(..., description="Active workflow execution / run UUID per Constitution C5, A15, A49")
    stage_index: int = Field(default=2, description="Workflow stage index where ingestion occurred")


class ConfirmTitleIngestionOutput(BaseModel):
    """Output contract after handling title confirmation action."""

    status: str = Field(..., description="'confirmed' | 'dismissed'")
    doi: str | None = Field(default=None, description="Ingested paper DOI if confirmed")
    openalex_id: str = Field(..., description="OpenAlex ID")
    title: str = Field(..., description="Paper title")
    citation_links_created: int = Field(default=0, description="Number of CITES edges wired")
    can_expand_deeply: bool = Field(default=False, description="Relevance gate status")

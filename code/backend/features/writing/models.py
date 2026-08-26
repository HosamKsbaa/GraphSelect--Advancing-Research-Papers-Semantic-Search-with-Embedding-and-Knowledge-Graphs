"""Pydantic request and response models for the writing feature."""
from __future__ import annotations

from typing import Any, Optional
from pydantic import BaseModel, ConfigDict, Field


class AbstractsRequest(BaseModel):
    """Body for the abstracts retrieval endpoint."""

    dois: list[str] = Field(..., min_length=1, description="DOI strings to look up")


class DraftRequest(BaseModel):
    """Body for the section drafting endpoint."""

    section_title: str = Field(..., description="Heading for this section")
    section_description: str = Field(default="", description="2-3 sentence scope description")
    paper_dois: list[str] = Field(default_factory=list, description="DOIs assigned to this section")
    target_level: str = Field(default="master", description="Academic level: 'master' or 'phd'")
    outline_context: Optional[str] = Field(default=None, description="Optional outline context")


class ReviewRequest(BaseModel):
    """Body for the section review endpoint."""

    section_title: str = Field(..., description="Title of the section being reviewed")
    draft_text: str = Field(..., description="Full Markdown text of the draft")
    paper_dois: list[str] = Field(default_factory=list, description="DOIs that should be cited")
    target_level: str = Field(default="master", description="Academic level: 'master' or 'phd'")


class CitationVerificationRequest(BaseModel):
    """Body for the citation verification endpoint."""

    draft_text: str = Field(..., description="Full text of the drafted section containing inline citations")
    assigned_dois: Optional[list[str]] = Field(default=None, description="Optional list of DOIs assigned to this section")


class CitationVerificationResponse(BaseModel):
    """Response containing citation grounding and verification metrics."""

    model_config = ConfigDict(from_attributes=True)

    cited_dois: list[str] = Field(default_factory=list, description="All extracted DOIs in draft")
    verified_dois: list[str] = Field(default_factory=list, description="DOIs verified in graph/library")
    hallucinated_dois: list[str] = Field(default_factory=list, description="Cited DOIs not found in graph")
    missing_assigned_dois: list[str] = Field(default_factory=list, description="Assigned DOIs missing from draft")
    hallucination_rate: float = Field(default=0.0, description="Fraction of citations that are hallucinated")
    coverage_rate: float = Field(default=1.0, description="Fraction of assigned DOIs that were cited")
    is_grounded: bool = Field(default=True, description="True if no hallucinated citations exist")
    passed: bool = Field(default=True, description="True if grounded and all assigned citations present")


__all__ = [
    "AbstractsRequest",
    "DraftRequest",
    "ReviewRequest",
    "CitationVerificationRequest",
    "CitationVerificationResponse",
]

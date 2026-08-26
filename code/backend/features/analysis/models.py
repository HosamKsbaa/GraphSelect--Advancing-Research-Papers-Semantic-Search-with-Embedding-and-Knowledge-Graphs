"""Pydantic request and response models for the analysis feature."""
from __future__ import annotations

from typing import Any, Optional
from pydantic import BaseModel, ConfigDict, Field

from agents.research.models import (
    ComparisonDimension,
    PaperFinding,
    StructuredComparisonMatrix,
)


class GapQueriesBody(BaseModel):
    """Body for the suggest-gap-queries endpoint."""

    gap_question: str = Field(..., min_length=5, description="The research question text that lacks coverage.")
    max_queries: int = Field(default=5, ge=1, le=10, description="Number of queries to generate.")


class SynthesisRequest(BaseModel):
    """Request body for synthesizing literature evidence across project papers."""

    dois: Optional[list[str]] = Field(
        default=None,
        description="Optional list of paper DOIs to synthesize. If omitted, all project papers are analyzed.",
    )
    research_questions: Optional[list[str]] = Field(
        default=None,
        description="Optional custom research questions for synthesis. If omitted, project questions are fetched from database.",
    )


class SynthesisResponse(BaseModel):
    """Response payload containing extracted findings, comparison matrix, markdown table, and synthesis narrative."""

    model_config = ConfigDict(from_attributes=True)

    project_id: str = Field(..., description="Associated project identifier")
    paper_count: int = Field(..., description="Number of papers synthesized")
    findings: list[PaperFinding] = Field(default_factory=list, description="Structured findings per paper")
    comparison_matrix: StructuredComparisonMatrix = Field(..., description="Synthesized multi-dimensional comparison matrix")
    markdown_table: str = Field(..., description="Rendered Markdown comparison table")
    synthesis_narrative: str = Field(..., description="High-level narrative synthesis of literature findings")


__all__ = [
    "GapQueriesBody",
    "SynthesisRequest",
    "SynthesisResponse",
    "PaperFinding",
    "ComparisonDimension",
    "StructuredComparisonMatrix",
]

"""Pydantic v2 domain models for Section-Granular Synthesis Matrices.

Complies with Constitution v2.2.1:
- C7: Strict static typing without bare signatures.
- C9: Granular sub-routines under 25 lines.
- C11: Intention-revealing domain types and predicate booleans.
- A37: Zero citation hallucination with validated LaTeX citekeys.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Final, Pattern

from pydantic import BaseModel, Field, field_validator

CITEKEY_PATTERN: Final[Pattern[str]] = re.compile(r"^\\cite\{doi_[a-zA-Z0-9_\-\.\/]+\}$")


class AnalyticalDimension(BaseModel):
    """Specific sub-dimension evaluated for an outline section."""

    dimension_id: str = Field(..., description="Slug identifier (e.g. 'mitigation_mechanism')")
    name: str = Field(..., description="Display column name (e.g. 'Mitigation Mechanism')")
    description: str = Field(..., description="Narrative evaluation focus for this column")
    evaluation_type: str = Field(default="qualitative", description="'qualitative' | 'metric' | 'benchmark'")


class CellEvidenceExtract(BaseModel):
    """Granular evidence extract populating a specific matrix cell."""

    evidence_text: str = Field(..., min_length=1, description="Synthesized finding or direct claim excerpt")
    quantitative_metric: str | None = Field(default=None, description="Extracted numerical metric or percentage")
    citekey: str = Field(..., description="Verified LaTeX citekey (e.g. \\cite{doi_10_1145_...})")
    is_grounded: bool = Field(default=True, description="True if DOI is verified in Neo4j SSOT")

    @field_validator("citekey")
    @classmethod
    def validate_latex_citekey(cls, v: str) -> str:
        """Enforce canonical LaTeX citekey format \\cite{doi_...}."""
        if not CITEKEY_PATTERN.match(v):
            raise ValueError(f"Invalid LaTeX citekey format: '{v}'. Expected format '\\cite{{doi_<identifier>}}'")
        return v


class SectionSynthesisMatrix(BaseModel):
    """Granular evidence table for an outline section (FR-012)."""

    matrix_id: str = Field(..., description="UUID of this synthesis matrix")
    section_id: str = Field(..., description="ID matching the target OutlineSection")
    section_title: str = Field(..., description="Title of the outline section")
    narrative_theme: str = Field(..., description="Analytical theme of this section")
    dimensions: list[AnalyticalDimension] = Field(..., min_length=3, max_length=5)
    assigned_dois: list[str] = Field(..., min_length=1)
    verified_dois: list[str] = Field(
        default_factory=list,
        description="Verified DOI references grounded in Neo4j SSOT",
    )
    cell_data: dict[str, dict[str, CellEvidenceExtract]] = Field(
        ..., description="Nested map: doi -> dimension_id -> CellEvidenceExtract"
    )
    markdown_path: str = Field(..., description="Local filepath in stage_04_artifacts/matrices/{section_id}.md")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class GenerateSectionSynthesisMatrixInput(BaseModel):
    """Input contract for generating a section synthesis matrix."""

    project_id: str = Field(..., description="Active research project UUID")
    section_id: str = Field(..., description="Outline section slug (e.g. 'sec_02_methodology')")
    section_title: str = Field(..., description="Title of the outline section")
    narrative_theme: str = Field(..., description="Analytical focus of the section")
    assigned_dois: list[str] = Field(..., min_length=1, description="DOIs assigned to this section")
    run_id: str = Field(..., description="Active workflow execution / run UUID per Constitution C5, A15, A49")
    stage_index: int = Field(default=4, description="Workflow stage index (Stage 4 Drafting)")


class GenerateSectionSynthesisMatrixOutput(BaseModel):
    """Output contract returned after matrix generation and dual persistence."""

    status: str = Field(default="success", description="'success' | 'failed'")
    matrix_id: str = Field(..., description="UUID of the created matrix")
    section_id: str = Field(..., description="Target section slug")
    dimensions: list[AnalyticalDimension] = Field(..., min_length=3, max_length=5)
    paper_count: int = Field(..., ge=1, description="Number of papers included in matrix")
    verified_dois: list[str] = Field(default_factory=list, description="List of verified DOIs grounded in Neo4j")
    markdown_path: str = Field(..., description="Local filepath in stage_04_artifacts/matrices/{section_id}.md")

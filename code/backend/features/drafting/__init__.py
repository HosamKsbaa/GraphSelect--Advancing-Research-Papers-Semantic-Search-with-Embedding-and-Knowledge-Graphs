"""Drafting and Section Synthesis Matrix feature module.

Exports Pydantic v2 domain models and contracts for evidence synthesis matrices.
"""
from __future__ import annotations

from features.drafting.matrix_models import (
    AnalyticalDimension,
    CellEvidenceExtract,
    GenerateSectionSynthesisMatrixInput,
    GenerateSectionSynthesisMatrixOutput,
    SectionSynthesisMatrix,
)

__all__ = [
    "AnalyticalDimension",
    "CellEvidenceExtract",
    "GenerateSectionSynthesisMatrixInput",
    "GenerateSectionSynthesisMatrixOutput",
    "SectionSynthesisMatrix",
]

"""Drafting and Section Synthesis Matrix feature module.

Exports Pydantic v2 domain models, dimension deriver, persistence engine,
and synthesis matrix services for evidence synthesis matrices.
"""
from __future__ import annotations

from features.drafting.dimension_deriver import (
    derive_section_dimensions,
    validate_dimensions,
)
from features.drafting.matrix_models import (
    AnalyticalDimension,
    CellEvidenceExtract,
    GenerateSectionSynthesisMatrixInput,
    GenerateSectionSynthesisMatrixOutput,
    SectionSynthesisMatrix,
)
from features.drafting.matrix_persistence import (
    persist_matrix_to_neo4j,
    serialize_matrix_to_markdown,
)
from features.drafting.matrix_service import (
    MatrixService,
    extract_cell_evidence,
    format_doi_citekey,
    get_section_matrix_for_drafting,
    load_section_matrix_context,
)

__all__ = [
    "AnalyticalDimension",
    "CellEvidenceExtract",
    "GenerateSectionSynthesisMatrixInput",
    "GenerateSectionSynthesisMatrixOutput",
    "MatrixService",
    "SectionSynthesisMatrix",
    "derive_section_dimensions",
    "extract_cell_evidence",
    "format_doi_citekey",
    "get_section_matrix_for_drafting",
    "load_section_matrix_context",
    "persist_matrix_to_neo4j",
    "serialize_matrix_to_markdown",
    "validate_dimensions",
]

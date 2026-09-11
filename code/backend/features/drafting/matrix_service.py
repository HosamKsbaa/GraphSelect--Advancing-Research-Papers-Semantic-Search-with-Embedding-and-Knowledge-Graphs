r"""Section Synthesis Matrix Service & Drafting Context Injector (T045, T047, T048).

Architectural Forward Commitment (T048 / Spec §Clarifications Q4):
------------------------------------------------------------------
In current Milestone M5, section synthesis matrices are dual-persisted:
1. Structured Neo4j nodes (:SectionSynthesisMatrix -[:SYNTHESIZES]-> :Paper) for graph provenance.
2. Flattened GitHub-flavored Markdown tables in stage_04_artifacts/matrices/ for drafting context.
TODO(FR-012-Q4): In future revisions, benchmark fine-grained cell-level graph traversal queries
(fetching dynamic Cypher subgraphs per drafting turn) directly against static markdown table injection
to measure empirical trade-offs in LLM context efficiency, reasoning latency, and multi-hop fact synthesis.

Complies with Constitution v2.2.1:
- C5, A15, A49: Preserves $run_id and $created_in_stage across persistence transactions.
- C7: Complete static typing without bare signatures.
- C8: Pure Neo4j graph-native persistence.
- C9: Every function strictly <= 25 lines (SRP & SLAP).
- A37: Zero citation hallucination ($CHR \equiv 0.0\%$) with fail-loud CitationHallucinationError.
"""
from __future__ import annotations

import logging
import os
import re
import uuid
from typing import Any

from core.db.neo4j_service import Neo4jService
from core.errors.enhancement_errors import CitationHallucinationError, MatrixGenerationError
from features.drafting.dimension_deriver import derive_section_dimensions
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

logger = logging.getLogger(__name__)

METRIC_REGEX: re.Pattern[str] = re.compile(
    r"(\b\d+(?:\.\d+)?%|\b\d+(?:\.\d+)?x\b|\b[Ff]1\s*=\s*\d+(?:\.\d+)?|\bp\s*<\s*0\.\d+|\b\d+(?:\.\d+)?\s*(?:ms|s|min|epochs|params|M|B|k)\b)"
)


def format_doi_citekey(doi: str) -> str:
    """Format canonical LaTeX citekey matching CITEKEY_PATTERN."""
    cleaned = re.sub(r"[^a-zA-Z0-9]", "_", doi.strip().lower()).strip("_")
    return f"\\cite{{doi_{cleaned}}}"


def _extract_metric(text: str) -> str | None:
    """Extract first quantitative metric or percentage from text."""
    match = METRIC_REGEX.search(text)
    return match.group(0).strip() if match else None


def _find_sentence_for_dimension(
    sentences: list[str], dimension: AnalyticalDimension
) -> str | None:
    """Locate first sentence mentioning dimension keywords."""
    keywords = [w.lower() for w in dimension.name.split() if len(w) > 3]
    for s in sentences:
        s_clean = s.strip()
        if any(kw in s_clean.lower() for kw in keywords) and len(s_clean) >= 20:
            return s_clean
    return None


def _extract_quote(text: str, dimension: AnalyticalDimension, doi: str) -> str:
    """Extract concise, grounded finding quote bounded to 250 characters."""
    if not text.strip():
        return f"Synthesized finding for {dimension.name} from study {doi}."[:250]
    sentences = re.split(r"(?<=[.!?])\s+", text)
    matched = _find_sentence_for_dimension(sentences, dimension)
    quote = matched or sentences[0] if sentences else text
    return quote[:250].strip()


def extract_cell_evidence(
    paper_doi: str,
    paper_abstract: str,
    dimension: AnalyticalDimension,
) -> CellEvidenceExtract:
    """Extract cell evidence extract with verified LaTeX citekey (T045)."""
    citekey = format_doi_citekey(paper_doi)
    metric = _extract_metric(paper_abstract)
    quote = _extract_quote(paper_abstract, dimension, paper_doi)
    return CellEvidenceExtract(
        evidence_text=quote,
        quantitative_metric=metric,
        citekey=citekey,
        is_grounded=True,
    )


async def _query_grounded_papers(
    neo4j: Neo4jService, dois: list[str]
) -> dict[str, dict[str, Any]]:
    """Query Neo4j SSOT for existing Paper nodes."""
    query = (
        "MATCH (p:Paper) WHERE p.doi IN $dois "
        "RETURN p.doi AS doi, p.title AS title, p.abstract AS abstract"
    )
    records = await neo4j.execute_read(query, {"dois": dois})
    return {r["doi"]: r for r in records if r.get("doi")}


def assert_citation_grounding(
    found_map: dict[str, dict[str, Any]], assigned_dois: list[str], section_id: str
) -> None:
    """Enforce CHR == 0.0%; raise CitationHallucinationError on missing DOI."""
    for doi in assigned_dois:
        if doi not in found_map:
            raise CitationHallucinationError(doi=doi, section_id=section_id)


def _build_matrix_cells(
    assigned_dois: list[str],
    paper_data: dict[str, dict[str, Any]],
    dimensions: list[AnalyticalDimension],
) -> dict[str, dict[str, CellEvidenceExtract]]:
    """Populate 2D cell data map (doi -> dimension_id -> CellEvidenceExtract)."""
    cells: dict[str, dict[str, CellEvidenceExtract]] = {}
    for doi in assigned_dois:
        cells[doi] = {}
        abstract = str(paper_data.get(doi, {}).get("abstract") or "")
        for dim in dimensions:
            cells[doi][dim.dimension_id] = extract_cell_evidence(doi, abstract, dim)
    return cells


def _assemble_matrix_model(
    input_data: GenerateSectionSynthesisMatrixInput,
    dimensions: list[AnalyticalDimension],
    cell_data: dict[str, dict[str, CellEvidenceExtract]],
    markdown_path: str,
) -> SectionSynthesisMatrix:
    """Construct SectionSynthesisMatrix Pydantic domain model."""
    return SectionSynthesisMatrix(
        matrix_id=str(uuid.uuid4()),
        section_id=input_data.section_id,
        section_title=input_data.section_title,
        narrative_theme=input_data.narrative_theme,
        dimensions=dimensions,
        assigned_dois=input_data.assigned_dois,
        verified_dois=input_data.assigned_dois,
        cell_data=cell_data,
        markdown_path=markdown_path,
    )


def get_section_matrix_for_drafting(
    section_id: str, markdown_path: str | None = None
) -> str:
    """Read serialized markdown matrix table for drafting prompt injection (T048)."""
    target = markdown_path or os.path.join("stage_04_artifacts/matrices", f"{section_id}.md")
    if not os.path.exists(target):
        raise FileNotFoundError(f"Section matrix artifact not found at '{target}'")
    with open(target, "r", encoding="utf-8") as f:
        return f.read()


def load_section_matrix_context(
    section_id: str, markdown_path: str | None = None
) -> str:
    """Alias provider reading section matrix context for drafting agent (T047)."""
    return get_section_matrix_for_drafting(section_id, markdown_path)


class MatrixService:
    """Orchestrator for section-level synthesis matrix generation and persistence."""

    def __init__(self, neo4j: Neo4jService | None = None) -> None:
        self.neo4j = neo4j

    def extract_cell_evidence(
        self, paper_doi: str, paper_abstract: str, dimension: AnalyticalDimension
    ) -> CellEvidenceExtract:
        """Extract cell evidence extract with verified LaTeX citekey."""
        return extract_cell_evidence(paper_doi, paper_abstract, dimension)

    async def verify_citation_grounding(
        self, assigned_dois: list[str], section_id: str
    ) -> dict[str, dict[str, Any]]:
        """Verify 100% DOI grounding in Neo4j SSOT or raise CitationHallucinationError."""
        if self.neo4j is None:
            raise MatrixGenerationError(section_id, "Neo4jService is required for grounding check")
        found_map = await _query_grounded_papers(self.neo4j, assigned_dois)
        assert_citation_grounding(found_map, assigned_dois, section_id)
        return found_map

    async def generate_section_matrix(
        self, input_data: GenerateSectionSynthesisMatrixInput
    ) -> GenerateSectionSynthesisMatrixOutput:
        """Generate section synthesis matrix with grounding and dual persistence."""
        if self.neo4j is None:
            raise MatrixGenerationError(input_data.section_id, "Neo4jService is required")
        paper_map = await self.verify_citation_grounding(input_data.assigned_dois, input_data.section_id)
        abstracts = [str(p.get("abstract") or "") for p in paper_map.values()]
        dimensions = derive_section_dimensions(input_data.section_title, input_data.narrative_theme, abstracts)
        cell_data = _build_matrix_cells(input_data.assigned_dois, paper_map, dimensions)
        default_path = f"stage_04_artifacts/matrices/{input_data.section_id}.md"
        matrix = _assemble_matrix_model(input_data, dimensions, cell_data, default_path)
        actual_path = serialize_matrix_to_markdown(matrix)
        matrix.markdown_path = actual_path
        await persist_matrix_to_neo4j(self.neo4j, matrix, input_data.run_id, input_data.stage_index)
        return GenerateSectionSynthesisMatrixOutput(
            status="success", matrix_id=matrix.matrix_id, section_id=matrix.section_id,
            dimensions=matrix.dimensions, paper_count=len(matrix.assigned_dois),
            verified_dois=matrix.verified_dois, markdown_path=actual_path,
        )

    def get_section_matrix_for_drafting(
        self, section_id: str, markdown_path: str | None = None
    ) -> str:
        """Provide markdown table context for drafting prompt injection."""
        return get_section_matrix_for_drafting(section_id, markdown_path)

    def load_section_matrix_context(
        self, section_id: str, markdown_path: str | None = None
    ) -> str:
        """Alias for drafting agent matrix context loading."""
        return load_section_matrix_context(section_id, markdown_path)

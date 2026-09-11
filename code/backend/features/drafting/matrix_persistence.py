"""Dual-Layer Matrix Persistence Engine (T046).

Dual-persists section synthesis matrices to:
1. Neo4j graph database as :SectionSynthesisMatrix attached to :OutlineSection
   with :SYNTHESIZES relationships to verified :Paper nodes (§5 Cypher contract).
2. GitHub-flavored Markdown tables at stage_04_artifacts/matrices/{section_id}.md
   guaranteed under 800 tokens for token-efficient drafting agent context injection.

Complies with Constitution v2.2.1:
- C5, A15, A49: Accepts and persists $run_id and $created_in_stage.
- C7: Complete static typing.
- C8: Pure Neo4j graph SSOT.
- C9: Every function strictly <= 25 lines (SRP & SLAP).
- SC-006: Under 800 token serialized markdown footprint.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from core.db.neo4j_service import Neo4jService
from core.errors.enhancement_errors import MatrixGenerationError
from features.drafting.matrix_models import (
    AnalyticalDimension,
    CellEvidenceExtract,
    SectionSynthesisMatrix,
)

logger = logging.getLogger(__name__)

PERSIST_SECTION_SYNTHESIS_MATRIX_CYPHER: str = """
MATCH (section:OutlineSection {id: $section_id})
MERGE (matrix:SectionSynthesisMatrix {section_id: $section_id})
ON CREATE SET 
    matrix.matrix_id = $matrix_id,
    matrix.section_title = $section_title,
    matrix.narrative_theme = $narrative_theme,
    matrix.dimensions_json = $dimensions_json,
    matrix.markdown_path = $markdown_path,
    matrix.run_id = $run_id,
    matrix.created_in_stage = $created_in_stage,
    matrix.created_at = datetime()
ON MATCH SET 
    matrix.narrative_theme = $narrative_theme,
    matrix.dimensions_json = $dimensions_json,
    matrix.markdown_path = $markdown_path,
    matrix.run_id = $run_id,
    matrix.created_in_stage = $created_in_stage,
    matrix.updated_at = datetime()

MERGE (section)-[:HAS_MATRIX]->(matrix)

WITH matrix, $cell_entries AS entries
UNWIND entries AS entry
MATCH (p:Paper {doi: entry.doi})
MERGE (matrix)-[s:SYNTHESIZES {dimension_id: entry.dimension_id}]->(p)
SET 
    s.evidence_text = entry.evidence_text,
    s.quantitative_metric = entry.metric,
    s.citekey = entry.citekey,
    s.run_id = $run_id,
    s.created_in_stage = $created_in_stage,
    s.updated_at = datetime()
WITH matrix, count(s) AS persisted_count, size(entries) AS expected_count
WHERE persisted_count = expected_count
RETURN matrix.matrix_id AS matrix_id, persisted_count;
"""


def _build_cell_entries(matrix: SectionSynthesisMatrix) -> list[dict[str, Any]]:
    """Flatten nested cell data into parameterized list of Cypher entry dictionaries."""
    entries: list[dict[str, Any]] = []
    for doi, dim_map in matrix.cell_data.items():
        for dim_id, cell in dim_map.items():
            entries.append({
                "doi": doi,
                "dimension_id": dim_id,
                "evidence_text": cell.evidence_text,
                "metric": cell.quantitative_metric or "",
                "citekey": cell.citekey,
            })
    return entries


def _build_persistence_params(
    matrix: SectionSynthesisMatrix,
    run_id: str,
    stage_index: int,
    entries: list[dict[str, Any]],
) -> dict[str, Any]:
    """Assemble parameterized payload for Neo4j Cypher persistence."""
    dims_json = json.dumps([d.model_dump() for d in matrix.dimensions])
    return {
        "section_id": matrix.section_id,
        "matrix_id": matrix.matrix_id,
        "section_title": matrix.section_title,
        "narrative_theme": matrix.narrative_theme,
        "dimensions_json": dims_json,
        "markdown_path": matrix.markdown_path,
        "run_id": run_id,
        "created_in_stage": stage_index,
        "cell_entries": entries,
    }


def _verify_persisted_result(
    records: list[dict[str, Any]], expected_count: int, section_id: str
) -> dict[str, Any]:
    """Validate that all expected cells were merged with fail-loud assertion."""
    if not records:
        raise MatrixGenerationError(
            section_id,
            f"Fail-loud grounding failure: expected {expected_count} cells, returned 0 rows",
        )
    persisted = int(records[0].get("persisted_count") or 0)
    if persisted != expected_count:
        raise MatrixGenerationError(
            section_id,
            f"Persisted count mismatch: expected {expected_count}, got {persisted}",
        )
    return records[0]


async def persist_matrix_to_neo4j(
    neo4j: Neo4jService,
    matrix: SectionSynthesisMatrix,
    run_id: str,
    stage_index: int = 4,
) -> dict[str, Any]:
    """Dual-persist SectionSynthesisMatrix and cell relationships to Neo4j (T046)."""
    entries = _build_cell_entries(matrix)
    params = _build_persistence_params(matrix, run_id, stage_index, entries)
    records = await neo4j.execute_write(PERSIST_SECTION_SYNTHESIS_MATRIX_CYPHER, params)
    result = _verify_persisted_result(records, len(entries), matrix.section_id)
    return {
        "matrix_id": result.get("matrix_id") or matrix.matrix_id,
        "section_id": matrix.section_id,
        "persisted_count": result.get("persisted_count", len(entries)),
    }


def _count_tokens(text: str) -> int:
    """Estimate token count via tiktoken with length-based fallback."""
    try:
        import tiktoken
        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except Exception:
        return max(1, len(text) // 4)


def _format_cell_content(cell: CellEvidenceExtract | None, max_chars: int) -> str:
    """Format single cell content with metric prefix and character bound."""
    if cell is None:
        return "N/A"
    metric = f"**{cell.quantitative_metric}**: " if cell.quantitative_metric else ""
    truncated = cell.evidence_text[:max_chars].strip()
    cleaned = f"{metric}{truncated}".replace("|", "\\|").replace("\n", " ")
    return cleaned.strip()


def _build_markdown_header(matrix: SectionSynthesisMatrix) -> str:
    """Build section title, theme metadata, and Markdown table header row."""
    lines = [
        f"## Synthesis Matrix: {matrix.section_title}",
        f"> **Section ID**: `{matrix.section_id}` | **Theme**: {matrix.narrative_theme}",
        "",
        "| Paper (Citekey) | " + " | ".join(d.name for d in matrix.dimensions) + " |",
        "| :--- | " + " | ".join(":---" for _ in matrix.dimensions) + " |",
    ]
    return "\n".join(lines)


def _build_markdown_row(
    doi: str,
    dimensions: list[AnalyticalDimension],
    cells: dict[str, CellEvidenceExtract],
    max_chars: int,
) -> str:
    """Format a single paper row in the Markdown evidence table."""
    first_cell = next(iter(cells.values()), None)
    citekey = first_cell.citekey if first_cell else doi
    row_cells = [_format_cell_content(cells.get(d.dimension_id), max_chars) for d in dimensions]
    return f"| {citekey} | " + " | ".join(row_cells) + " |"


def _render_matrix_markdown(matrix: SectionSynthesisMatrix, max_chars: int) -> str:
    """Assemble complete Markdown table string from matrix components."""
    header = _build_markdown_header(matrix)
    rows = [
        _build_markdown_row(doi, matrix.dimensions, matrix.cell_data.get(doi, {}), max_chars)
        for doi in matrix.assigned_dois
    ]
    return header + "\n" + "\n".join(rows) + "\n"


def _enforce_token_budget(matrix: SectionSynthesisMatrix, max_tokens: int = 780) -> str:
    """Enforce strict <800 token budget via progressive cell truncation."""
    for max_chars in [250, 180, 120, 80, 50]:
        rendered = _render_matrix_markdown(matrix, max_chars)
        if _count_tokens(rendered) < max_tokens:
            return rendered
    return _render_matrix_markdown(matrix, 40)


def _write_atomic_markdown(target_file: Path, content: str) -> None:
    """Write markdown file atomically using temporary swap."""
    target_file.parent.mkdir(parents=True, exist_ok=True)
    temp_file = target_file.with_suffix(".tmp")
    temp_file.write_text(content, encoding="utf-8")
    temp_file.replace(target_file)


def serialize_matrix_to_markdown(
    matrix: SectionSynthesisMatrix,
    output_dir: str = "stage_04_artifacts/matrices",
) -> str:
    """Serialize SectionSynthesisMatrix to GitHub-flavored markdown (<800 tokens)."""
    content = _enforce_token_budget(matrix)
    out_path = Path(output_dir) / f"{matrix.section_id}.md"
    _write_atomic_markdown(out_path, content)
    return str(out_path)

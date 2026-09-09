"""Atomic bidirectional Cypher graph wiring for ingested literature.

Complies with Constitution v2.2.1:
- C5: Auditability with run_id and created_in_stage tracking.
- C8: Pure Neo4j SSOT without relational ORMs.
- C9: Granular functions under 25 lines (SRP / SLAP).
"""
from __future__ import annotations

import logging
from typing import Any

from features.ingestion.models import UserIngestedPaper

logger = logging.getLogger(__name__)

BULK_INGEST_BIDIRECTIONAL_CYPHER = """
MERGE (new_paper:Paper {doi: $doi})
ON CREATE SET 
    new_paper.openalex_id = $openalex_id,
    new_paper.title = $title,
    new_paper.year = $year,
    new_paper.cited_by_count = $cited_by_count,
    new_paper.embedding = $embedding,
    new_paper.ingestion_source = $ingestion_source,
    new_paper.is_stub = false,
    new_paper.is_bridge = false,
    new_paper.can_expand_deeply = $can_expand_deeply,
    new_paper.is_retracted = $is_retracted,
    new_paper.run_id = $run_id,
    new_paper.created_in_stage = $created_in_stage,
    new_paper.created_at = datetime(),
    new_paper.updated_at = datetime()
ON MATCH SET 
    new_paper.title = coalesce(new_paper.title, $title),
    new_paper.openalex_id = coalesce(new_paper.openalex_id, $openalex_id),
    new_paper.year = coalesce(new_paper.year, $year),
    new_paper.embedding = coalesce(new_paper.embedding, $embedding),
    new_paper.is_retracted = coalesce($is_retracted, new_paper.is_retracted),
    new_paper.run_id = coalesce(new_paper.run_id, $run_id),
    new_paper.created_in_stage = coalesce(new_paper.created_in_stage, $created_in_stage),
    new_paper.is_stub = false,
    new_paper.can_expand_deeply = $can_expand_deeply,
    new_paper.updated_at = datetime()

FOREACH (_ IN CASE WHEN $project_id IS NOT NULL THEN [1] ELSE [] END |
    MERGE (proj:Project {project_id: $project_id})
    MERGE (proj)-[:CONTAINS]->(new_paper)
)

FOREACH (ref_doi IN $referenced_dois |
    MERGE (ref_paper:Paper {doi: ref_doi})
    ON CREATE SET 
        ref_paper.is_stub = true,
        ref_paper.is_bridge = false,
        ref_paper.can_expand_deeply = false,
        ref_paper.run_id = $run_id,
        ref_paper.created_in_stage = $created_in_stage,
        ref_paper.created_at = datetime()
    MERGE (new_paper)-[r:CITES]->(ref_paper)
    ON CREATE SET r.discovered_in_tier = 0, r.run_id = $run_id, r.created_in_stage = $created_in_stage, r.created_at = datetime()
)

FOREACH (citing_doi IN $citing_library_dois |
    MERGE (citing_paper:Paper {doi: citing_doi})
    MERGE (citing_paper)-[r:CITES]->(new_paper)
    ON CREATE SET r.discovered_in_tier = 0, r.run_id = $run_id, r.created_in_stage = $created_in_stage, r.created_at = datetime()
)
RETURN new_paper.doi AS doi
"""


def get_bulk_ingest_cypher_query() -> str:
    """Return parameterized Cypher query for atomic bidirectional ingestion."""
    return BULK_INGEST_BIDIRECTIONAL_CYPHER


def build_wiring_parameters(
    paper: UserIngestedPaper,
    project_id: str | None,
    run_id: str,
    stage_index: int = 2,
    citing_library_dois: list[str] | None = None,
) -> dict[str, Any]:
    """Construct parameterized dictionary for Cypher bulk ingestion."""
    return {
        "project_id": project_id,
        "doi": paper.doi,
        "openalex_id": paper.openalex_id or "",
        "title": paper.title,
        "year": paper.year,
        "cited_by_count": 0,
        "embedding": paper.embedding,
        "ingestion_source": str(paper.ingestion_source.value if hasattr(paper.ingestion_source, "value") else paper.ingestion_source),
        "can_expand_deeply": paper.can_expand_deeply,
        "is_retracted": paper.is_retracted,
        "run_id": run_id,
        "created_in_stage": stage_index,
        "referenced_dois": paper.referenced_dois or [],
        "citing_library_dois": citing_library_dois or [],
    }


async def find_citing_library_dois(
    neo4j_service: Any,
    target_doi: str,
    candidate_dois: list[str] | None = None,
    project_id: str | None = None,
) -> list[str]:
    """Identify existing library papers in project/graph that cite target DOI."""
    if not candidate_dois and not project_id:
        return []
    query = """
    MATCH (existing:Paper)
    WHERE (existing.doi IN $candidate_dois OR $candidate_dois IS NULL)
      AND ($project_id IS NULL OR (:Project {project_id: $project_id})-[:CONTAINS]->(existing))
      AND (existing)-[:CITES]->(:Paper {doi: $target_doi})
    RETURN DISTINCT existing.doi AS citing_doi
    """
    params = {"target_doi": target_doi, "candidate_dois": candidate_dois or None, "project_id": project_id}
    try:
        records = await neo4j_service.execute_read(query, params)
        return [str(r["citing_doi"]) for r in records if r.get("citing_doi")]
    except Exception as exc:
        logger.warning("Error finding citing library DOIs for %s: %s", target_doi, exc)
        return []


async def execute_bidirectional_wiring(
    neo4j_service: Any,
    params: dict[str, Any],
) -> dict[str, Any]:
    """Execute parameterized atomic Cypher transaction via Neo4j service."""
    query = get_bulk_ingest_cypher_query()
    try:
        records = await neo4j_service.execute_write(query, params)
        return {"status": "success", "doi": params.get("doi"), "records": records}
    except Exception as exc:
        logger.error("Failed executing bidirectional wiring for DOI %s: %s", params.get("doi"), exc)
        raise


async def wire_paper_bidirectional(
    neo4j_service: Any,
    paper: UserIngestedPaper,
    project_id: str | None,
    run_id: str,
    stage_index: int = 2,
    citing_library_dois: list[str] | None = None,
) -> int:
    """Wire newly ingested paper bidirectionally and return created edge count."""
    params = build_wiring_parameters(
        paper=paper,
        project_id=project_id,
        run_id=run_id,
        stage_index=stage_index,
        citing_library_dois=citing_library_dois,
    )
    await execute_bidirectional_wiring(neo4j_service, params)
    ref_count = len(paper.referenced_dois or [])
    citing_count = len(citing_library_dois or [])
    return ref_count + citing_count

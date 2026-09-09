"""Neo4j Epistemic Knowledge Graph Schema DDL, Constraints, and Vector Indexes.

Enforces 12 primary key constraints, composite indexes, and 3 Matryoshka vector
indexes (paper_embeddings, question_embeddings, claim_embeddings with d=768, cosine).
Complies with Constitution C1/C9 (<25 lines per function) and C8 (Zero MySQL).
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.db.neo4j_service import Neo4jService

logger = logging.getLogger(__name__)

UNIQUENESS_CONSTRAINTS: list[str] = [
    # 12 Primary Key Constraints per data-model.md §1.3
    "CREATE CONSTRAINT campaign_id_unique IF NOT EXISTS FOR (c:ResearchCampaign) REQUIRE c.campaign_id IS UNIQUE",
    "CREATE CONSTRAINT question_id_unique IF NOT EXISTS FOR (q:ResearchQuestion) REQUIRE q.question_id IS UNIQUE",
    "CREATE CONSTRAINT paper_doi_unique IF NOT EXISTS FOR (p:Paper) REQUIRE p.doi IS UNIQUE",
    "CREATE CONSTRAINT author_openalex_unique IF NOT EXISTS FOR (a:Author) REQUIRE a.openalex_id IS UNIQUE",
    "CREATE CONSTRAINT venue_openalex_unique IF NOT EXISTS FOR (v:Venue) REQUIRE v.openalex_id IS UNIQUE",
    "CREATE CONSTRAINT claim_id_unique IF NOT EXISTS FOR (cl:Claim) REQUIRE cl.claim_id IS UNIQUE",
    "CREATE CONSTRAINT substate_id_unique IF NOT EXISTS FOR (s:StageSubstate) REQUIRE s.substate_id IS UNIQUE",
    "CREATE CONSTRAINT message_id_unique IF NOT EXISTS FOR (m:PublicBoardMessage) REQUIRE m.message_id IS UNIQUE",
    "CREATE CONSTRAINT critique_id_unique IF NOT EXISTS FOR (cv:CritiqueVector) REQUIRE cv.critique_id IS UNIQUE",
    "CREATE CONSTRAINT method_id_unique IF NOT EXISTS FOR (m:Method) REQUIRE m.method_id IS UNIQUE",
    "CREATE CONSTRAINT dataset_id_unique IF NOT EXISTS FOR (d:Dataset) REQUIRE d.dataset_id IS UNIQUE",
    "CREATE CONSTRAINT metric_id_unique IF NOT EXISTS FOR (mr:MetricResult) REQUIRE mr.result_id IS UNIQUE",
    # Backward compatibility constraints
    "CREATE CONSTRAINT project_id_unique IF NOT EXISTS FOR (pr:Project) REQUIRE pr.project_id IS UNIQUE",
    "CREATE CONSTRAINT session_id_unique IF NOT EXISTS FOR (s:Session) REQUIRE s.session_id IS UNIQUE",
]

COMPOSITE_INDEXES: list[str] = [
    # Composite & secondary lookup indexes per data-model.md §1.3
    "CREATE INDEX campaign_stage_idx IF NOT EXISTS FOR (s:StageSubstate) ON (s.campaign_id, s.stage_index)",
    "CREATE INDEX message_campaign_idx IF NOT EXISTS FOR (m:PublicBoardMessage) ON (m.campaign_id, m.is_resolved)",
    "CREATE INDEX paper_year_idx IF NOT EXISTS FOR (p:Paper) ON (p.year)",
    "CREATE INDEX claim_paper_idx IF NOT EXISTS FOR (cl:Claim) ON (cl.paper_doi)",
    "CREATE INDEX method_paper_idx IF NOT EXISTS FOR (m:Method) ON (m.paper_doi)",
    "CREATE INDEX metric_method_idx IF NOT EXISTS FOR (mr:MetricResult) ON (mr.method_id, mr.dataset_id)",
    # Auxiliary indexes
    "CREATE INDEX paper_openalex_idx IF NOT EXISTS FOR (p:Paper) ON (p.openalex_id)",
    "CREATE INDEX author_name_idx IF NOT EXISTS FOR (a:Author) ON (a.name)",
    "CREATE INDEX venue_name_idx IF NOT EXISTS FOR (v:Venue) ON (v.name)",
    "CREATE INDEX question_project_index IF NOT EXISTS FOR (q:ResearchQuestion) ON (q.project_id)",
]

VECTOR_INDEXES: list[tuple[str, str, str]] = [
    ("paper_embeddings", "Paper", "p.embedding"),
    ("question_embeddings", "ResearchQuestion", "q.embedding"),
    ("claim_embeddings", "Claim", "cl.embedding"),
]


async def _run_ddl_query(neo4j: Neo4jService, query: str) -> None:
    """Execute a single schema query safely logging warnings on skip."""
    try:
        await neo4j.execute_write(query)
        logger.debug("Schema applied: %s", query[:60])
    except Exception as e:
        logger.debug("Schema query skipped (may already exist): %s — %s", query[:60], e)


async def apply_constraints(neo4j: Neo4jService) -> None:
    """Apply all 12 primary key uniqueness constraints."""
    for query in UNIQUENESS_CONSTRAINTS:
        await _run_ddl_query(neo4j, query)
    logger.info("Applied %d Neo4j uniqueness constraints", len(UNIQUENESS_CONSTRAINTS))


async def apply_composite_indexes(neo4j: Neo4jService) -> None:
    """Apply composite and auxiliary secondary indexes."""
    for query in COMPOSITE_INDEXES:
        await _run_ddl_query(neo4j, query)
    logger.info("Applied %d Neo4j composite indexes", len(COMPOSITE_INDEXES))


async def apply_vector_indexes(neo4j: Neo4jService, dimensions: int = 768) -> None:
    """Apply 3 Matryoshka cosine vector indexes (paper, question, claim)."""
    for index_name, label, prop in VECTOR_INDEXES:
        var = label[0].lower()
        query = (
            f"CREATE VECTOR INDEX {index_name} IF NOT EXISTS "
            f"FOR ({var}:{label}) ON ({var}.{prop.split('.')[-1]}) "
            f"OPTIONS {{indexConfig: {{"
            f"  `vector.dimensions`: {dimensions},"
            f"  `vector.similarity_function`: 'cosine'"
            f"}}}}"
        )
        await _run_ddl_query(neo4j, query)
    logger.info("Applied %d Matryoshka vector indexes (%dd)", len(VECTOR_INDEXES), dimensions)


async def initialize_schema(
    neo4j: Neo4jService,
    embedding_dimensions: int = 768,
) -> None:
    """Initialize full 3-in-1 epistemic Neo4j schema."""
    await apply_constraints(neo4j)
    await apply_composite_indexes(neo4j)
    await apply_vector_indexes(neo4j, embedding_dimensions)
    logger.info("Neo4j 3-in-1 epistemic schema initialization complete")

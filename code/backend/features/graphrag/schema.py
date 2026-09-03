"""Neo4j DDL schema definitions, constraints, and indexes for the Epistemic Fact Graph (GraphRAG).

Ensures uniqueness on all 9 node ID fields, B-Tree lookup indexes, and Neo4j 5
vector indexes for 768-dimensional Gemini embeddings.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.db.neo4j_service import Neo4jService

logger = logging.getLogger(__name__)

# ============================================================================
# Uniqueness Constraints (All 9 Node Types + Domain Keys)
# ============================================================================

GRAPHRAG_CONSTRAINTS: list[str] = [
    # 1. Fact
    "CREATE CONSTRAINT fact_id_unique IF NOT EXISTS FOR (f:Fact) REQUIRE f.fact_id IS UNIQUE",
    # 2. Proof
    "CREATE CONSTRAINT proof_id_unique IF NOT EXISTS FOR (p:Proof) REQUIRE p.proof_id IS UNIQUE",
    # 3. Methodology
    "CREATE CONSTRAINT methodology_id_unique IF NOT EXISTS FOR (m:Methodology) REQUIRE m.methodology_id IS UNIQUE",
    # 4. Source
    "CREATE CONSTRAINT source_id_unique IF NOT EXISTS FOR (s:Source) REQUIRE s.source_id IS UNIQUE",
    # 5. Concept
    "CREATE CONSTRAINT concept_id_unique IF NOT EXISTS FOR (c:Concept) REQUIRE c.concept_id IS UNIQUE",
    "CREATE CONSTRAINT concept_name_unique IF NOT EXISTS FOR (c:Concept) REQUIRE c.name IS UNIQUE",
    # 6. Dataset
    "CREATE CONSTRAINT dataset_id_unique IF NOT EXISTS FOR (d:Dataset) REQUIRE d.dataset_id IS UNIQUE",
    # 7. Question
    "CREATE CONSTRAINT epistemic_question_id_unique IF NOT EXISTS FOR (q:Question) REQUIRE q.question_id IS UNIQUE",
    # 8. Limitation
    "CREATE CONSTRAINT limitation_id_unique IF NOT EXISTS FOR (l:Limitation) REQUIRE l.limitation_id IS UNIQUE",
    # 9. Community
    "CREATE CONSTRAINT community_id_unique IF NOT EXISTS FOR (cm:Community) REQUIRE cm.community_id IS UNIQUE",
]

# ============================================================================
# B-Tree Indexes for Performance Optimization
# ============================================================================

GRAPHRAG_INDEXES: list[str] = [
    "CREATE INDEX fact_status_idx IF NOT EXISTS FOR (f:Fact) ON (f.status)",
    "CREATE INDEX fact_project_idx IF NOT EXISTS FOR (f:Fact) ON (f.project_id)",
    "CREATE INDEX fact_statement_idx IF NOT EXISTS FOR (f:Fact) ON (f.statement)",
    "CREATE INDEX proof_polarity_idx IF NOT EXISTS FOR (p:Proof) ON (p.polarity)",
    "CREATE INDEX proof_agent_idx IF NOT EXISTS FOR (p:Proof) ON (p.agent_id)",
    "CREATE INDEX proof_source_idx IF NOT EXISTS FOR (p:Proof) ON (p.source_paper_id)",
    "CREATE INDEX methodology_name_idx IF NOT EXISTS FOR (m:Methodology) ON (m.name)",
    "CREATE INDEX source_doi_idx IF NOT EXISTS FOR (s:Source) ON (s.doi)",
    "CREATE INDEX source_openalex_idx IF NOT EXISTS FOR (s:Source) ON (s.openalex_id)",
    "CREATE INDEX dataset_name_idx IF NOT EXISTS FOR (d:Dataset) ON (d.name)",
    "CREATE INDEX limitation_category_idx IF NOT EXISTS FOR (l:Limitation) ON (l.category)",
    "CREATE INDEX limitation_severity_idx IF NOT EXISTS FOR (l:Limitation) ON (l.severity)",
    "CREATE INDEX community_level_idx IF NOT EXISTS FOR (cm:Community) ON (cm.level)",
]

# ============================================================================
# Vector Indexes for Gemini 768-dim Embeddings
# ============================================================================

FACT_VECTOR_INDEX_QUERY: str = (
    "CREATE VECTOR INDEX fact_embeddings IF NOT EXISTS "
    "FOR (f:Fact) ON (f.embedding) "
    "OPTIONS {indexConfig: {"
    "  `vector.dimensions`: $dimensions,"
    "  `vector.similarity_function`: 'cosine'"
    "}}"
)

QUESTION_VECTOR_INDEX_QUERY: str = (
    "CREATE VECTOR INDEX question_epistemic_embeddings IF NOT EXISTS "
    "FOR (q:Question) ON (q.embedding) "
    "OPTIONS {indexConfig: {"
    "  `vector.dimensions`: $dimensions,"
    "  `vector.similarity_function`: 'cosine'"
    "}}"
)


async def init_graphrag_schema(
    neo4j_service: Neo4jService,
    embedding_dimensions: int = 768,
) -> None:
    """Initialize Neo4j schema with constraints, indexes, and vector indexes idempotently.
    
    Args:
        neo4j_service: Neo4j database service connection.
        embedding_dimensions: Dimensions of vector embeddings (default 768 for Gemini).
    """
    # 1. Apply Uniqueness Constraints
    for query in GRAPHRAG_CONSTRAINTS:
        try:
            await neo4j_service.execute_write(query)
            logger.info("GraphRAG constraint applied: %s", query[:65])
        except Exception as e:
            logger.warning("GraphRAG constraint skipped (may already exist): %s — %s", query[:65], e)

    # 2. Apply B-Tree Indexes
    for query in GRAPHRAG_INDEXES:
        try:
            await neo4j_service.execute_write(query)
            logger.info("GraphRAG index applied: %s", query[:65])
        except Exception as e:
            logger.warning("GraphRAG index skipped (may already exist): %s — %s", query[:65], e)

    # 3. Apply Vector Indexes
    try:
        await neo4j_service.execute_write(
            FACT_VECTOR_INDEX_QUERY,
            {"dimensions": embedding_dimensions},
        )
        logger.info("GraphRAG vector index (fact_embeddings) applied with %d dims", embedding_dimensions)
    except Exception as e:
        logger.warning("GraphRAG vector index (fact_embeddings) skipped: %s", e)

    try:
        await neo4j_service.execute_write(
            QUESTION_VECTOR_INDEX_QUERY,
            {"dimensions": embedding_dimensions},
        )
        logger.info("GraphRAG vector index (question_epistemic_embeddings) applied with %d dims", embedding_dimensions)
    except Exception as e:
        logger.warning("GraphRAG vector index (question_epistemic_embeddings) skipped: %s", e)

    logger.info("GraphRAG schema initialization completed successfully.")

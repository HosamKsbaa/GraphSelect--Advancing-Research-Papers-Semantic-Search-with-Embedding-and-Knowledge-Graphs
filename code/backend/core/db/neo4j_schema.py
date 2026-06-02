from __future__ import annotations
import logging
from core.db.neo4j_service import Neo4jService

logger = logging.getLogger(__name__)

SCHEMA_QUERIES: list[str] = [
    # Unique constraints
    'CREATE CONSTRAINT paper_doi_unique IF NOT EXISTS FOR (p:Paper) REQUIRE p.doi IS UNIQUE',
    'CREATE CONSTRAINT author_openalex_unique IF NOT EXISTS FOR (a:Author) REQUIRE a.openalex_id IS UNIQUE',
    'CREATE CONSTRAINT venue_openalex_unique IF NOT EXISTS FOR (v:Venue) REQUIRE v.openalex_id IS UNIQUE',
    'CREATE CONSTRAINT session_id_unique IF NOT EXISTS FOR (s:Session) REQUIRE s.session_id IS UNIQUE',
    'CREATE CONSTRAINT question_session_text_unique IF NOT EXISTS FOR (q:Question) REQUIRE (q.session_id, q.text) IS UNIQUE',
    # Project / ResearchQuestion constraints (agentic workflow)
    'CREATE CONSTRAINT project_id_unique IF NOT EXISTS FOR (pr:Project) REQUIRE pr.project_id IS UNIQUE',
    'CREATE CONSTRAINT question_id_unique IF NOT EXISTS FOR (q:ResearchQuestion) REQUIRE q.question_id IS UNIQUE',
    # Indexes for fast lookups
    'CREATE INDEX paper_openalex_idx IF NOT EXISTS FOR (p:Paper) ON (p.openalex_id)',
    'CREATE INDEX author_name_idx IF NOT EXISTS FOR (a:Author) ON (a.name)',
    'CREATE INDEX venue_name_idx IF NOT EXISTS FOR (v:Venue) ON (v.name)',
    'CREATE INDEX keyword_term_idx IF NOT EXISTS FOR (k:Keyword) ON (k.term)',
    # Project-scoped indexes
    'CREATE INDEX question_project_index IF NOT EXISTS FOR (q:ResearchQuestion) ON (q.project_id)',
]

VECTOR_INDEX_QUERY: str = (
    'CREATE VECTOR INDEX paper_embeddings IF NOT EXISTS '
    'FOR (p:Paper) ON (p.embedding) '
    'OPTIONS {indexConfig: {'
    '  `vector.dimensions`: $dimensions,'
    '  `vector.similarity_function`: $similarity'
    '}}'
)

QUESTION_VECTOR_INDEX_QUERY: str = (
    'CREATE VECTOR INDEX question_embeddings IF NOT EXISTS '
    'FOR (q:ResearchQuestion) ON (q.embedding) '
    'OPTIONS {indexConfig: {'
    '  `vector.dimensions`: $dimensions,'
    '  `vector.similarity_function`: $similarity'
    '}}'
)


async def initialize_schema(
    neo4j: Neo4jService,
    embedding_dimensions: int = 768,
) -> None:
    """Initialize Neo4j schema with constraints, indexes, and vector indexes."""
    for query in SCHEMA_QUERIES:
        try:
            await neo4j.execute_write(query)
            logger.info('Schema applied: %s', query[:60])
        except Exception as e:
            logger.warning('Schema query skipped (may already exist): %s — %s', query[:60], e)

    # Paper embeddings vector index
    try:
        await neo4j.execute_write(
            VECTOR_INDEX_QUERY,
            {'dimensions': embedding_dimensions, 'similarity': 'cosine'},
        )
        logger.info('Vector index (paper_embeddings) created with %d dimensions', embedding_dimensions)
    except Exception as e:
        logger.warning('Vector index (paper_embeddings) skipped (may already exist): %s', e)

    # ResearchQuestion embeddings vector index
    try:
        await neo4j.execute_write(
            QUESTION_VECTOR_INDEX_QUERY,
            {'dimensions': embedding_dimensions, 'similarity': 'cosine'},
        )
        logger.info('Vector index (question_embeddings) created with %d dimensions', embedding_dimensions)
    except Exception as e:
        logger.warning('Vector index (question_embeddings) skipped (may already exist): %s', e)

    logger.info('Neo4j schema initialization complete')


from __future__ import annotations
import logging
from typing import Any  # Only for neo4j Record type boundary
from neo4j import AsyncGraphDatabase, AsyncDriver
from neo4j.exceptions import ServiceUnavailable, AuthError

from models.paper import PaperCreate

logger = logging.getLogger(__name__)


class Neo4jService:
    """Async Neo4j driver wrapper with connection pool management."""

    def __init__(self, uri: str, user: str, password: str) -> None:
        self._uri = uri
        self._user = user
        self._password = password
        self._driver: AsyncDriver | None = None

    async def connect(self) -> None:
        """Initialize the Neo4j driver and verify connectivity."""
        self._driver = AsyncGraphDatabase.driver(
            self._uri,
            auth=(self._user, self._password),
        )
        await self._driver.verify_connectivity()
        logger.info('Neo4j connection established: %s', self._uri)

    async def close(self) -> None:
        """Close the Neo4j driver and release resources."""
        if self._driver is not None:
            await self._driver.close()
            self._driver = None
            logger.info('Neo4j connection closed')

    @property
    def driver(self) -> AsyncDriver:
        if self._driver is None:
            raise RuntimeError('Neo4j driver not initialized. Call connect() first.')
        return self._driver

    async def execute_read(
        self,
        query: str,
        parameters: dict[str, object] | None = None,
        database: str = 'neo4j',
    ) -> list[dict[str, Any]]:  # Any: neo4j Record values are dynamically typed
        """Execute a read-only Cypher query and return results as dicts."""
        async with self.driver.session(database=database) as session:
            result = await session.run(query, parameters or {})
            records = await result.data()
            return records  # type: ignore[return-value]

    async def execute_write(
        self,
        query: str,
        parameters: dict[str, object] | None = None,
        database: str = 'neo4j',
    ) -> list[dict[str, Any]]:  # Any: neo4j Record values are dynamically typed
        """Execute a write Cypher query within a transaction."""
        async with self.driver.session(database=database) as session:
            result = await session.run(query, parameters or {})
            records = await result.data()
            return records  # type: ignore[return-value]

    async def execute_query(
        self,
        query: str,
        parameters: dict[str, object] | None = None,
        database: str = 'neo4j',
    ) -> list[dict[str, Any]]:  # Any: neo4j Record values are dynamically typed
        """Execute a Cypher query (auto-detects read/write)."""
        return await self.execute_write(query, parameters, database)

    async def health_check(self) -> bool:
        """Verify Neo4j connectivity. Returns True if healthy."""
        try:
            await self.driver.verify_connectivity()
            return True
        except (ServiceUnavailable, AuthError, RuntimeError):
            return False

    # ------------------------------------------------------------------
    # Paper CRUD (used by GraphSearchService BFS engine)
    # ------------------------------------------------------------------

    async def create_paper(self, paper: PaperCreate) -> dict[str, Any]:
        """MERGE a paper node by DOI. Returns the paper data.

        Uses MERGE to be idempotent — safe to call multiple times for
        the same DOI without creating duplicates.
        """
        query = """
        MERGE (p:Paper {doi: $doi})
        SET p.title           = $title,
            p.abstract        = $abstract,
            p.year            = $year,
            p.cited_by_count  = $cited_by_count,
            p.openalex_id     = $openalex_id,
            p.publication_date = $publication_date,
            p.source          = $source,
            p.updated_at      = datetime()
        ON CREATE SET p.created_at = datetime()
        RETURN p.doi           AS doi,
               p.title         AS title,
               p.abstract      AS abstract,
               p.year          AS year,
               p.cited_by_count AS cited_by_count,
               p.openalex_id   AS openalex_id,
               p.publication_date AS publication_date,
               p.source        AS source
        """
        params: dict[str, object] = {
            'doi': paper.doi,
            'title': paper.title,
            'abstract': paper.abstract,
            'year': paper.year,
            'cited_by_count': paper.cited_by_count,
            'openalex_id': paper.openalex_id,
            'publication_date': paper.publication_date,
            'source': paper.source,
        }
        records = await self.execute_write(query, params)
        return records[0]

    async def get_paper_by_doi(self, doi: str) -> dict[str, Any] | None:
        """Get a paper by DOI. NEVER includes the embedding field."""
        query = """
        MATCH (p:Paper {doi: $doi})
        RETURN p.doi           AS doi,
               p.title         AS title,
               p.abstract      AS abstract,
               p.year          AS year,
               p.cited_by_count AS cited_by_count,
               p.openalex_id   AS openalex_id,
               p.publication_date AS publication_date,
               p.source        AS source
        """
        records = await self.execute_read(query, {'doi': doi})
        if not records:
            return None
        return records[0]

    async def paper_exists(self, doi: str) -> bool:
        """Check if a paper exists in the graph."""
        query = """
        MATCH (p:Paper {doi: $doi})
        RETURN count(p) AS cnt
        """
        records = await self.execute_read(query, {'doi': doi})
        return bool(records and records[0].get('cnt', 0) > 0)

    async def create_citation(self, citing_doi: str, cited_doi: str) -> None:
        """Create a CITES relationship between two papers.

        Both paper nodes must already exist. Uses MERGE for idempotency.
        """
        query = """
        MATCH (a:Paper {doi: $citing_doi})
        MATCH (b:Paper {doi: $cited_doi})
        MERGE (a)-[:CITES]->(b)
        """
        await self.execute_write(query, {
            'citing_doi': citing_doi,
            'cited_doi': cited_doi,
        })

    async def store_paper_embedding(
        self,
        doi: str,
        embedding: list[float],
        model: str = 'gemini-embedding-001',
    ) -> None:
        """Store embedding vector on a Paper node.

        The embedding is written directly to Neo4j and NEVER returned
        in read queries (zero-RAM-copy policy).
        """
        query = """
        MATCH (p:Paper {doi: $doi})
        SET p.embedding       = $embedding,
            p.embedding_model = $model,
            p.embedded_at     = datetime()
        """
        await self.execute_write(query, {
            'doi': doi,
            'embedding': embedding,
            'model': model,
        })

    async def has_embedding(self, doi: str) -> bool:
        """Check if a paper has an embedding stored."""
        query = """
        MATCH (p:Paper {doi: $doi})
        RETURN p.embedding IS NOT NULL AS has_emb
        """
        records = await self.execute_read(query, {'doi': doi})
        if not records:
            return False
        return bool(records[0].get('has_emb', False))

    async def get_paper_abstract(self, doi: str) -> str | None:
        """Get just the abstract of a paper for embedding."""
        query = """
        MATCH (p:Paper {doi: $doi})
        RETURN p.abstract AS abstract
        """
        records = await self.execute_read(query, {'doi': doi})
        if not records:
            return None
        abstract: str | None = records[0].get('abstract')  # type: ignore[assignment]
        return abstract

    async def store_question_embedding(
        self,
        session_id: str,
        question_text: str,
        embedding: list[float],
    ) -> None:
        """Store a research question embedding.

        MERGE by session + text so re-embedding is idempotent.
        """
        query = """
        MERGE (q:Question {session_id: $session_id, text: $question_text})
        SET q.embedding       = $embedding,
            q.embedding_model = 'gemini-embedding-001',
            q.embedded_at     = datetime()
        """
        await self.execute_write(query, {
            'session_id': session_id,
            'question_text': question_text,
            'embedding': embedding,
        })

    async def get_session_dois(
        self,
        session_id: str,
        depth: int | None = None,
    ) -> list[str]:
        """Get all DOIs associated with a session at a given depth (or all depths)."""
        if depth is not None:
            query = """
            MATCH (s:Session {session_id: $session_id})-[c:CONTAINS {depth: $depth}]->(p:Paper)
            RETURN p.doi AS doi
            """
            records = await self.execute_read(query, {
                'session_id': session_id,
                'depth': depth,
            })
        else:
            query = """
            MATCH (s:Session {session_id: $session_id})-[:CONTAINS]->(p:Paper)
            RETURN p.doi AS doi
            """
            records = await self.execute_read(query, {
                'session_id': session_id,
            })
        return [str(r['doi']) for r in records if r.get('doi')]

    async def link_paper_to_session(
        self,
        doi: str,
        session_id: str,
        depth: int,
    ) -> None:
        """Link a paper to a session with the BFS depth level.

        Creates the Session node if it does not exist yet.
        """
        query = """
        MATCH (p:Paper {doi: $doi})
        MERGE (s:Session {session_id: $session_id})
        MERGE (s)-[:CONTAINS {depth: $depth}]->(p)
        """
        await self.execute_write(query, {
            'doi': doi,
            'session_id': session_id,
            'depth': depth,
        })

    async def get_unembedded_dois(self, session_id: str) -> list[str]:
        """Get DOIs of papers in a session that don't have embeddings yet."""
        query = """
        MATCH (s:Session {session_id: $session_id})-[:CONTAINS]->(p:Paper)
        WHERE p.embedding IS NULL
          AND p.abstract IS NOT NULL
        RETURN p.doi AS doi
        """
        records = await self.execute_read(query, {'session_id': session_id})
        return [str(r['doi']) for r in records if r.get('doi')]

    async def update_session_stats(self, session_id: str) -> dict[str, int]:
        """Count papers in a session and return stats."""
        query = """
        MATCH (s:Session {session_id: $session_id})-[:CONTAINS]->(p:Paper)
        RETURN count(p) AS total_papers,
               count(p.embedding) AS embedded_papers,
               count(p.abstract) AS papers_with_abstract
        """
        records = await self.execute_read(query, {'session_id': session_id})
        if not records:
            return {'total_papers': 0, 'embedded_papers': 0, 'papers_with_abstract': 0}
        row = records[0]
        return {
            'total_papers': int(row.get('total_papers', 0)),
            'embedded_papers': int(row.get('embedded_papers', 0)),
            'papers_with_abstract': int(row.get('papers_with_abstract', 0)),
        }

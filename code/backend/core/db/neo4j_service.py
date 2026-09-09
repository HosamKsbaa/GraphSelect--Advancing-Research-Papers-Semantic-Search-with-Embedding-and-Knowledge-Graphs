from __future__ import annotations
import asyncio
import logging
import random
from collections.abc import Mapping
from typing import Any  # Only for neo4j Record type boundary
from neo4j import AsyncGraphDatabase, AsyncDriver
from neo4j.exceptions import ServiceUnavailable, AuthError, TransientError

from features.retrieval.models import PaperCreate

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

    async def _execute_with_retry(
        self,
        query: str,
        parameters: Mapping[str, Any] | None,
        database: str,
        max_retries: int,
        base_delay: float,
        max_delay: float,
        op_name: str,
    ) -> list[dict[str, Any]]:
        """Execute a Cypher query with exponential backoff on transient errors."""
        for attempt in range(max_retries + 1):
            try:
                async with self.driver.session(database=database) as session:
                    result = await session.run(query, dict(parameters) if parameters is not None else {})
                    return await result.data()  # type: ignore[return-value]
            except (TransientError, ServiceUnavailable) as exc:
                if attempt == max_retries:
                    logger.error("Exhausted %d retries executing Cypher %s: %s", max_retries, op_name, exc)
                    raise exc
                delay = min(max_delay, base_delay * (2 ** attempt))
                jittered = random.uniform(0.5 * delay, delay)
                logger.warning("Transient error in Cypher %s (attempt %d/%d): %s", op_name, attempt + 1, max_retries, exc)
                await asyncio.sleep(jittered)
        return []

    async def execute_read(
        self,
        query: str,
        parameters: Mapping[str, Any] | None = None,
        database: str = 'neo4j',
        max_retries: int = 3,
        base_delay: float = 0.05,
        max_delay: float = 0.5,
    ) -> list[dict[str, Any]]:
        """Execute a read-only Cypher query with transient retry resilience."""
        return await self._execute_with_retry(
            query, parameters, database, max_retries, base_delay, max_delay, "read"
        )

    async def execute_write(
        self,
        query: str,
        parameters: Mapping[str, Any] | None = None,
        database: str = 'neo4j',
        max_retries: int = 5,
        base_delay: float = 0.05,
        max_delay: float = 1.0,
    ) -> list[dict[str, Any]]:
        """Execute a write Cypher query with automatic retry on transient errors/deadlocks."""
        return await self._execute_with_retry(
            query, parameters, database, max_retries, base_delay, max_delay, "write"
        )

    async def execute_query(
        self,
        query: str,
        parameters: Mapping[str, Any] | None = None,
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

    async def _link_paper_authors(self, doi: str, authors: Any) -> None:
        """Link authors to paper node."""
        auth_params = [
            {'name': a.name, 'openalex_id': getattr(a, 'openalex_id', None),
             'orcid': getattr(a, 'orcid', None), 'institution': getattr(a, 'institution', None)}
            for a in (authors or []) if hasattr(a, "name") and a.name
        ]
        if not auth_params:
            return
        query = (
            "MATCH (p:Paper {doi: $doi}) UNWIND $authors AS auth "
            "MERGE (a:Author {name: auth.name}) "
            "ON CREATE SET a.openalex_id = auth.openalex_id, a.orcid = auth.orcid, "
            "a.institution = auth.institution, a.created_at = datetime() "
            "MERGE (a)-[:AUTHORED]->(p)"
        )
        await self.execute_write(query, {'doi': doi, 'authors': auth_params})

    async def _link_paper_venue(self, doi: str, venue: Any) -> None:
        """Link publication venue to paper node."""
        if not (venue and getattr(venue, "name", None)):
            return
        query = (
            "MATCH (p:Paper {doi: $doi}) MERGE (v:Venue {name: $v.name}) "
            "ON CREATE SET v.openalex_id = $v.openalex_id, v.issn = $v.issn, "
            "v.venue_type = $v.venue_type, v.created_at = datetime() "
            "MERGE (p)-[:PUBLISHED_IN]->(v)"
        )
        v_params = {
            'name': venue.name, 'openalex_id': getattr(venue, 'openalex_id', None),
            'issn': getattr(venue, 'issn', None), 'venue_type': getattr(venue, 'venue_type', None)
        }
        await self.execute_write(query, {'doi': doi, 'v': v_params})

    async def create_paper(self, paper: PaperCreate) -> dict[str, Any]:
        """MERGE a paper node by DOI and link its authors/venue."""
        query = (
            "MERGE (p:Paper {doi: $doi}) ON CREATE SET p.created_at = datetime() "
            "SET p.title = $title, p.abstract = $abstract, p.year = $year, "
            "p.cited_by_count = $cited_by_count, p.openalex_id = $openalex_id, "
            "p.publication_date = $publication_date, p.source = $source, p.updated_at = datetime() "
            "RETURN p.doi AS doi, p.title AS title, p.abstract AS abstract, p.year AS year, "
            "p.cited_by_count AS cited_by_count, p.openalex_id AS openalex_id, "
            "p.publication_date AS publication_date, p.source AS source"
        )
        params: dict[str, object] = {
            'doi': paper.doi, 'title': paper.title, 'abstract': paper.abstract,
            'year': paper.year, 'cited_by_count': paper.cited_by_count,
            'openalex_id': paper.openalex_id, 'publication_date': paper.publication_date,
            'source': paper.source,
        }
        records = await self.execute_write(query, params)
        await self._link_paper_authors(paper.doi, getattr(paper, "authors", None))
        await self._link_paper_venue(paper.doi, getattr(paper, "venue", None))
        return records[0] if records else {'doi': paper.doi, 'title': paper.title}

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

    async def ensure_stub_and_cite(self, citing_doi: str, cited_doi: str) -> None:
        """Atomically create paper stubs (if missing) and a CITES relationship.
        
        Uses MERGE ... ON CREATE SET to prevent overwriting real paper data.
        """
        query = """
        MERGE (a:Paper {doi: $citing_doi})
        ON CREATE SET a.title = '[pending]', a.source = 'stub', a.created_at = datetime(), a.updated_at = datetime()
        MERGE (b:Paper {doi: $cited_doi})
        ON CREATE SET b.title = '[pending]', b.source = 'stub', b.created_at = datetime(), b.updated_at = datetime()
        MERGE (a)-[:CITES]->(b)
        """
        await self.execute_write(query, {
            'citing_doi': citing_doi,
            'cited_doi': cited_doi,
        })

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
        model: str = 'text-embedding-005',
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

    async def batch_store_paper_embeddings(
        self,
        items: list[dict[str, Any]],
        model: str = "gemini-embedding-2",
    ) -> None:
        """Batch store embedding vectors on Paper nodes using UNWIND.

        Args:
            items: List of dicts, each containing 'doi' (str) and 'embedding' (list[float]).
            model: Embedding model name.
        """
        if not items:
            return
        query = """
        UNWIND $items AS item
        MATCH (p:Paper {doi: item.doi})
        SET p.embedding       = item.embedding,
            p.embedding_model = $model,
            p.embedded_at     = datetime()
        """
        await self.execute_write(query, {
            "items": items,
            "model": model,
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
        model: str = 'text-embedding-005',
    ) -> None:
        """Store a research question embedding.

        MERGE by session + text so re-embedding is idempotent.
        """
        query = """
        MERGE (q:Question {session_id: $session_id, text: $question_text})
        SET q.embedding       = $embedding,
            q.embedding_model = $model,
            q.embedded_at     = datetime()
        """
        await self.execute_write(query, {
            'session_id': session_id,
            'question_text': question_text,
            'embedding': embedding,
            'model': model,
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
        MERGE (s)-[r:CONTAINS]->(p)
        ON CREATE SET r.depth = $depth
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

    async def compute_similarities(
        self, session_id: str, threshold: float, top_k: int = 1000,
    ) -> list[dict[str, Any]]:
        """Compute cosine similarity between session papers and research questions."""
        query = (
            "MATCH (q:Question {session_id: $session_id}) WHERE q.embedding IS NOT NULL "
            "CALL db.index.vector.queryNodes('paper_embeddings', $top_k, q.embedding) YIELD node AS p, score "
            "MATCH (s:Session {session_id: $session_id})-[:CONTAINS]->(p) WHERE score >= $threshold "
            "RETURN p.doi AS doi, q.text AS question, score AS score"
        )
        return await self.execute_read(
            query, {'session_id': session_id, 'threshold': threshold, 'top_k': top_k}
        )

    async def _run_gds_pagerank_stream(
        self, graph_name: str, session_id: str, iterations: int, damping: float
    ) -> dict[str, float]:
        """Project GDS subgraph, stream PageRank scores, and drop projection."""
        p_nodes = "MATCH (s:Session {session_id: $session_id})-[:CONTAINS]->(p:Paper) RETURN id(p) AS id, ['Paper'] AS labels"
        p_edges = (
            "MATCH (s:Session {session_id: $session_id})-[:CONTAINS]->(p1:Paper)-[:CITES]->(p2:Paper) "
            "WHERE (s)-[:CONTAINS]->(p2) RETURN id(p1) AS source, id(p2) AS target, 'CITES' AS type"
        )
        await self.execute_write(
            "CALL gds.graph.project.cypher($g, $n, $e, {parameters: {session_id: $sid}})",
            {"g": graph_name, "n": p_nodes, "e": p_edges, "sid": session_id}
        )
        pr_q = "CALL gds.pageRank.stream($g, {maxIterations: $it, dampingFactor: $d}) YIELD nodeId, score RETURN gds.util.asNode(nodeId).doi AS doi, score"
        records = await self.execute_read(pr_q, {"g": graph_name, "it": iterations, "d": damping})
        await self.execute_write("CALL gds.graph.drop($g, false)", {"g": graph_name})
        return {str(r["doi"]): float(r["score"]) for r in records if r.get("doi")}

    async def compute_pagerank(
        self, session_id: str, iterations: int = 20, damping: float = 0.85,
    ) -> dict[str, float]:
        """Compute PageRank for papers in citation subgraph with GDS or fallback."""
        import uuid
        graph_name = f"subgraph_{session_id.replace('-', '_')}_{uuid.uuid4().hex[:8]}"
        try:
            scores = await self._run_gds_pagerank_stream(graph_name, session_id, iterations, damping)
            return self._normalize_score_dict(scores)
        except Exception as e:
            logger.warning("GDS PageRank failed, falling back to NetworkX: %s", e)
            try:
                await self.execute_write("CALL gds.graph.drop($g, false)", {"g": graph_name})
            except Exception:
                pass
            return await self._compute_pagerank_fallback(session_id, iterations, damping)

    def _normalize_score_dict(self, scores: dict[str, float]) -> dict[str, float]:
        """Normalize score values to [0.0, 1.0] range."""
        if not scores:
            return {}
        min_s, max_s = min(scores.values()), max(scores.values())
        diff = max_s - min_s
        if diff > 0.0:
            return {k: (v - min_s) / diff for k, v in scores.items()}
        return {k: 1.0 for k in scores}

    async def _fetch_subgraph_nodes_and_edges(
        self, session_id: str
    ) -> tuple[list[str], list[dict[str, Any]]]:
        """Fetch session node DOIs and internal citation edges."""
        nq = "MATCH (s:Session {session_id: $sid})-[:CONTAINS]->(p:Paper) RETURN p.doi AS doi"
        eq = (
            "MATCH (s:Session {session_id: $sid})-[:CONTAINS]->(p1:Paper)-[:CITES]->(p2:Paper) "
            "WHERE (s)-[:CONTAINS]->(p2) RETURN p1.doi AS source, p2.doi AS target"
        )
        nodes = await self.execute_read(nq, {"sid": session_id})
        edges = await self.execute_read(eq, {"sid": session_id})
        dois = [str(r["doi"]) for r in nodes if r.get("doi")]
        return dois, edges

    async def _compute_pagerank_fallback(
        self, session_id: str, iterations: int = 20, damping: float = 0.85,
    ) -> dict[str, float]:
        """Pure-Python NetworkX fallback for PageRank computation."""
        try:
            import networkx as nx
        except ImportError:
            logger.error("networkx not installed, falling back to degree centrality.")
            return await self._compute_degree_centrality_fallback(session_id)
        dois, edges = await self._fetch_subgraph_nodes_and_edges(session_id)
        if not dois:
            return {}
        g = nx.DiGraph()
        g.add_nodes_from(dois)
        for r in edges:
            if r.get("source") and r.get("target"):
                g.add_edge(str(r["source"]), str(r["target"]))
        try:
            pr = nx.pagerank(g, alpha=damping, max_iter=iterations)
            return self._normalize_score_dict({k: float(v) for k, v in pr.items()})
        except Exception as pr_err:
            logger.warning("NetworkX pagerank error, using degree centrality: %s", pr_err)
            return await self._compute_degree_centrality_fallback(session_id)

    async def _compute_degree_centrality_fallback(self, session_id: str) -> dict[str, float]:
        """Citation-degree fallback if NetworkX fails."""
        query = (
            "MATCH (s:Session {session_id: $session_id})-[:CONTAINS]->(p:Paper) "
            "OPTIONAL MATCH (s)-[:CONTAINS]->(other:Paper)-[:CITES]->(p) "
            "RETURN p.doi AS doi, count(other) AS degree"
        )
        records = await self.execute_read(query, {"session_id": session_id})
        scores = {str(r["doi"]): float(r.get("degree", 0.0)) for r in records if r.get("doi")}
        return self._normalize_score_dict(scores)

    # ------------------------------------------------------------------
    # Project management (agentic workflow)
    # ------------------------------------------------------------------

    async def create_project_node(
        self, project_id: str, name: str, status: str = 'active',
    ) -> dict[str, Any]:
        """Create a Project node in the graph idempotently."""
        query = (
            "MERGE (pr:Project {project_id: $project_id}) "
            "ON CREATE SET pr.created_at = datetime() "
            "SET pr.name = $name, pr.status = $status, pr.updated_at = datetime() "
            "RETURN pr.project_id AS project_id, pr.name AS name, pr.status AS status"
        )
        records = await self.execute_write(query, {'project_id': project_id, 'name': name, 'status': status})
        return records[0]

    async def create_research_question(
        self, question_id: str, text: str, embedding: list[float], project_id: str,
    ) -> dict[str, Any]:
        """Create a ResearchQuestion node linked to a Project."""
        query = (
            "MERGE (pr:Project {project_id: $project_id}) "
            "MERGE (q:ResearchQuestion {question_id: $question_id}) "
            "ON CREATE SET q.created_at = datetime() "
            "SET q.text = $text, q.embedding = $embedding, q.project_id = $project_id, q.updated_at = datetime() "
            "MERGE (q)-[:BELONGS_TO]->(pr) "
            "RETURN q.question_id AS question_id, q.text AS text, q.project_id AS project_id"
        )
        params = {'question_id': question_id, 'text': text, 'embedding': embedding, 'project_id': project_id}
        records = await self.execute_write(query, params)
        return records[0] if records else {'question_id': question_id, 'text': text, 'project_id': project_id}

    async def add_paper_to_project(
        self,
        project_id: str,
        doi: str,
    ) -> None:
        """Create a HAS_PAPER relationship between a Project and a Paper.

        Both nodes must already exist. Uses MERGE for idempotency.

        Args:
            project_id: The project's UUID.
            doi: The paper's DOI.
        """
        query = """
        MERGE (pr:Project {project_id: $project_id})
        MERGE (p:Paper {doi: $doi})
        MERGE (pr)-[:HAS_PAPER]->(p)
        """
        await self.execute_write(query, {
            'project_id': project_id,
            'doi': doi,
        })

    async def get_project_papers(self, project_id: str, limit: int = 50) -> list[dict[str, Any]]:
        """Get all papers associated with a project (without embeddings)."""
        query = (
            "MATCH (pr:Project {project_id: $project_id})-[:HAS_PAPER]->(p:Paper) "
            "RETURN p.doi AS doi, p.title AS title, p.abstract AS abstract, p.year AS year, "
            "p.cited_by_count AS cited_by_count, p.openalex_id AS openalex_id, p.source AS source "
            "LIMIT $limit"
        )
        return await self.execute_read(query, {'project_id': project_id, 'limit': limit})

    async def get_research_questions(
        self,
        project_id: str,
    ) -> list[dict[str, Any]]:
        """Get all research questions for a project.

        Args:
            project_id: The project's UUID.

        Returns:
            List of question property dicts (without embeddings).
        """
        query = """
        MATCH (q:ResearchQuestion)
        WHERE q.project_id = $project_id OR (q)-[:BELONGS_TO]->(:Project {project_id: $project_id})
        RETURN DISTINCT q.question_id AS question_id,
                        q.text        AS text,
                        q.project_id  AS project_id
        """
        return await self.execute_read(query, {'project_id': project_id})

    async def archive_project(
        self,
        project_id: str,
    ) -> None:
        """Set a project's status to 'archived' in the graph.

        Args:
            project_id: The project's UUID.
        """
        query = """
        MATCH (pr:Project {project_id: $project_id})
        SET pr.status     = 'archived',
            pr.updated_at = datetime()
        """
        await self.execute_write(query, {'project_id': project_id})

    # ------------------------------------------------------------------
    # Analytics queries (extracted from agent tools)
    # ------------------------------------------------------------------

    async def get_top_authors(
        self,
        project_id: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Get top authors by paper count within a project.

        Args:
            project_id: The project's UUID.
            limit: Maximum number of authors to return.

        Returns:
            List of dicts with name, openalex_id, paper_count.
        """
        query = """
        MATCH (pr:Project {project_id: $project_id})-[:HAS_PAPER]->(p:Paper)
        MATCH (a:Author)-[:AUTHORED]->(p)
        RETURN a.name AS name, a.openalex_id AS openalex_id, count(p) AS paper_count
        ORDER BY paper_count DESC
        LIMIT $limit
        """
        return await self.execute_read(query, {
            'project_id': project_id,
            'limit': limit,
        })

    async def get_top_venues(
        self,
        project_id: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Get top venues by paper count within a project.

        Args:
            project_id: The project's UUID.
            limit: Maximum number of venues to return.

        Returns:
            List of dicts with name, openalex_id, paper_count.
        """
        query = """
        MATCH (pr:Project {project_id: $project_id})-[:HAS_PAPER]->(p:Paper)-[:PUBLISHED_IN]->(v:Venue)
        RETURN v.name AS name, v.openalex_id AS openalex_id, count(p) AS paper_count
        ORDER BY paper_count DESC
        LIMIT $limit
        """
        return await self.execute_read(query, {
            'project_id': project_id,
            'limit': limit,
        })

    async def get_citation_graph_nodes(
        self,
        project_id: str,
    ) -> list[dict[str, Any]]:
        """Get all papers in a project as citation graph nodes.

        Args:
            project_id: The project's UUID.

        Returns:
            List of dicts with doi, title, year, cited_by_count.
        """
        query = """
        MATCH (pr:Project {project_id: $project_id})-[:HAS_PAPER]->(p:Paper)
        RETURN p.doi AS doi, p.title AS title,
               p.year AS year, p.cited_by_count AS cited_by_count
        """
        return await self.execute_read(query, {'project_id': project_id})

    async def get_citation_graph_edges(
        self,
        project_id: str,
    ) -> list[dict[str, Any]]:
        """Get all citation edges between papers in a project.

        Args:
            project_id: The project's UUID.

        Returns:
            List of dicts with source and target DOIs.
        """
        query = """
        MATCH (pr:Project {project_id: $project_id})-[:HAS_PAPER]->(p1:Paper)-[:CITES]->(p2:Paper)<-[:HAS_PAPER]-(pr)
        RETURN p1.doi AS source, p2.doi AS target
        """
        return await self.execute_read(query, {'project_id': project_id})

    async def get_project_gap_stats(
        self, project_id: str, threshold: float = 0.6,
    ) -> list[dict[str, Any]]:
        """Get coverage gap statistics for research questions in a project."""
        query = (
            "MATCH (q:ResearchQuestion {project_id: $project_id}) WHERE q.embedding IS NOT NULL "
            "CALL db.index.vector.queryNodes('paper_embeddings', 50, q.embedding) YIELD node AS p, score "
            "MATCH (pr:Project {project_id: $project_id})-[:HAS_PAPER]->(p) WHERE score >= $threshold "
            "RETURN q.text AS question, count(p) AS covered_count"
        )
        return await self.execute_read(query, {'project_id': project_id, 'threshold': threshold})

    # ------------------------------------------------------------------
    # Milestone 1 Batch Graph & Centrality Helper Methods
    # ------------------------------------------------------------------

    async def batch_get_paper_degrees(self, dois: list[str]) -> dict[str, int]:
        """Get the in-graph degree (CITES in + out count) for a list of DOIs."""
        if not dois:
            return {}
        clean_dois = [d.replace("https://doi.org/", "").strip() for d in dois if d]
        query = """
        UNWIND $dois AS target_doi
        MATCH (p:Paper {doi: target_doi})
        OPTIONAL MATCH (p)-[r:CITES]-(other:Paper)
        RETURN target_doi AS doi, count(DISTINCT r) AS degree
        """
        records = await self.execute_read(query, {"dois": clean_dois})
        result = {d: 0 for d in clean_dois}
        for r in records:
            if r.get("doi"):
                result[str(r["doi"])] = int(r.get("degree", 0))
        return result

    async def get_in_graph_degrees(self, dois: list[str]) -> dict[str, int]:
        """Alias for batch_get_paper_degrees."""
        return await self.batch_get_paper_degrees(dois)

    async def batch_check_project_papers(self, project_id: str, dois: list[str]) -> set[str]:
        """Check which DOIs in the provided list are already saved to the project library."""
        if not project_id or not dois:
            return set()
        clean_dois = [d.replace("https://doi.org/", "").strip() for d in dois if d]
        query = """
        MATCH (pr:Project {project_id: $project_id})-[:HAS_PAPER]->(p:Paper)
        WHERE p.doi IN $dois
        RETURN p.doi AS doi
        """
        records = await self.execute_read(query, {"project_id": project_id, "dois": clean_dois})
        return {str(r["doi"]) for r in records if r.get("doi")}

    async def check_project_papers_membership(
        self,
        project_id: str,
        dois: list[str],
    ) -> dict[str, bool]:
        """Check membership of DOIs in project library returning dict mapping DOI to bool."""
        if not project_id or not dois:
            return {d: False for d in dois}
        in_lib = await self.batch_check_project_papers(project_id, dois)
        return {d: (d.replace("https://doi.org/", "").strip() in in_lib) for d in dois if d}

    async def get_project_research_questions_with_embeddings(
        self, project_id: str
    ) -> list[dict[str, Any]]:
        """Retrieve all research questions and their pre-computed embeddings for a project."""
        query = """
        MATCH (q:ResearchQuestion)
        WHERE q.project_id = $project_id OR (q)-[:BELONGS_TO]->(:Project {project_id: $project_id})
        RETURN DISTINCT q.question_id AS question_id,
                        q.text        AS text,
                        q.embedding   AS embedding
        """
        records = await self.execute_read(query, {"project_id": project_id})
        return records

    async def batch_get_paper_embeddings(self, dois: list[str]) -> dict[str, list[float]]:
        """Fetch stored embedding vectors for a list of DOIs from Neo4j."""
        if not dois:
            return {}
        clean_dois = [d.replace("https://doi.org/", "").strip() for d in dois if d]
        query = """
        MATCH (p:Paper)
        WHERE p.doi IN $dois AND p.embedding IS NOT NULL
        RETURN p.doi AS doi, p.embedding AS embedding
        """
        records = await self.execute_read(query, {"dois": clean_dois})
        return {str(r["doi"]): list(r["embedding"]) for r in records if r.get("doi") and r.get("embedding")}

    async def get_papers_by_dois(self, dois: list[str]) -> list[dict[str, Any]]:
        """Batch fetch paper metadata, authors, and venue by DOIs."""
        if not dois:
            return []
        clean_dois = [d.replace("https://doi.org/", "").strip() for d in dois if d]
        query = """
        MATCH (p:Paper)
        WHERE p.doi IN $dois
        OPTIONAL MATCH (p)<-[:AUTHORED]-(a:Author)
        OPTIONAL MATCH (p)-[:PUBLISHED_IN]->(v:Venue)
        RETURN p.doi           AS doi,
               p.title         AS title,
               p.abstract      AS abstract,
               p.year          AS year,
               p.cited_by_count AS cited_by_count,
               p.openalex_id   AS openalex_id,
               p.publication_date AS publication_date,
               p.source        AS source,
               p.created_at    AS created_at,
               p.embedding IS NOT NULL AS has_embedding,
               collect(DISTINCT {name: a.name, openalex_id: a.openalex_id}) AS authors,
               v.name          AS venue_name
        """
        records = await self.execute_read(query, {'dois': clean_dois})
        return records

    def _extract_batch_rows(
        self, papers: list[PaperCreate]
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
        """Extract paper, author, and venue rows from batch."""
        p_rows, a_rows, v_rows = [], [], []
        for p in papers:
            p_rows.append({
                'doi': p.doi, 'title': p.title, 'abstract': p.abstract, 'year': p.year,
                'cited_by_count': p.cited_by_count, 'openalex_id': p.openalex_id,
                'publication_date': p.publication_date, 'source': p.source,
            })
            for a in getattr(p, "authors", []):
                if hasattr(a, "name") and a.name:
                    a_rows.append({
                        'doi': p.doi, 'name': a.name, 'openalex_id': getattr(a, 'openalex_id', None),
                        'orcid': getattr(a, 'orcid', None), 'institution': getattr(a, 'institution', None),
                    })
            venue = getattr(p, "venue", None)
            if venue and hasattr(venue, "name") and venue.name:
                v_rows.append({
                    'doi': p.doi, 'name': venue.name, 'openalex_id': getattr(venue, 'openalex_id', None),
                    'issn': getattr(venue, 'issn', None), 'venue_type': getattr(venue, 'venue_type', None),
                })
        return p_rows, a_rows, v_rows

    async def _write_batch_authors(self, author_rows: list[dict[str, Any]]) -> None:
        """MERGE authors and link to papers in batch."""
        if not author_rows:
            return
        query = (
            "UNWIND $batch AS row MATCH (p:Paper {doi: row.doi}) MERGE (a:Author {name: row.name}) "
            "ON CREATE SET a.openalex_id = row.openalex_id, a.orcid = row.orcid, "
            "a.institution = row.institution, a.created_at = datetime() "
            "MERGE (a)-[:AUTHORED]->(p)"
        )
        await self.execute_write(query, {'batch': author_rows})

    async def _write_batch_venues(self, venue_rows: list[dict[str, Any]]) -> None:
        """MERGE venues and link to papers in batch."""
        if not venue_rows:
            return
        query = (
            "UNWIND $batch AS row MATCH (p:Paper {doi: row.doi}) MERGE (v:Venue {name: row.name}) "
            "ON CREATE SET v.openalex_id = row.openalex_id, v.issn = row.issn, "
            "v.venue_type = row.venue_type, v.created_at = datetime() "
            "MERGE (p)-[:PUBLISHED_IN]->(v)"
        )
        await self.execute_write(query, {'batch': venue_rows})

    async def create_papers_batch(self, papers: list[PaperCreate]) -> int:
        """MERGE multiple papers and their author/venue relationships in a single batch."""
        if not papers:
            return 0
        p_rows, a_rows, v_rows = self._extract_batch_rows(papers)
        batch_q = (
            "UNWIND $batch AS row MERGE (p:Paper {doi: row.doi}) ON CREATE SET p.created_at = datetime() "
            "SET p.title = row.title, p.abstract = row.abstract, p.year = row.year, "
            "p.cited_by_count = row.cited_by_count, p.openalex_id = row.openalex_id, "
            "p.publication_date = row.publication_date, p.source = row.source, p.updated_at = datetime()"
        )
        await self.execute_write(batch_q, {'batch': p_rows})
        await self._write_batch_authors(a_rows)
        await self._write_batch_venues(v_rows)
        return len(papers)

    # ------------------------------------------------------------------
    # Layer 1: Bibliographic Graph (:CITES, :AUTHORED, :PUBLISHED_IN)
    # ------------------------------------------------------------------

    async def link_paper_citation(
        self, citing_doi: str, cited_doi: str, is_seed: bool = False
    ) -> None:
        """Create directed :CITES edge between two papers."""
        c_from = normalize_doi(citing_doi)
        c_to = normalize_doi(cited_doi)
        query = """
        MERGE (a:Paper {doi: $from_doi})
        MERGE (b:Paper {doi: $to_doi})
        MERGE (a)-[r:CITES]->(b)
        SET r.is_seed_citation = $is_seed
        """
        await self.execute_write(query, {"from_doi": c_from, "to_doi": c_to, "is_seed": is_seed})

    async def link_paper_author(
        self, doi: str, author_name: str, openalex_id: str | None = None, position: int = 0
    ) -> None:
        """Create :AUTHORED edge connecting author to paper."""
        c_doi = normalize_doi(doi)
        query = """
        MERGE (p:Paper {doi: $doi})
        MERGE (a:Author {name: $name})
        ON CREATE SET a.openalex_id = $openalex_id, a.created_at = datetime()
        MERGE (a)-[r:AUTHORED]->(p)
        SET r.author_position = $position
        """
        await self.execute_write(
            query,
            {"doi": c_doi, "name": author_name, "openalex_id": openalex_id, "position": position},
        )

    async def link_paper_venue(
        self, doi: str, venue_name: str, openalex_id: str | None = None, issn: str | None = None
    ) -> None:
        """Create :PUBLISHED_IN edge connecting paper to venue."""
        c_doi = normalize_doi(doi)
        query = """
        MERGE (p:Paper {doi: $doi})
        MERGE (v:Venue {name: $name})
        ON CREATE SET v.openalex_id = $openalex_id, v.issn = $issn, v.created_at = datetime()
        MERGE (p)-[:PUBLISHED_IN]->(v)
        """
        await self.execute_write(
            query,
            {"doi": c_doi, "name": venue_name, "openalex_id": openalex_id, "issn": issn},
        )

    # ------------------------------------------------------------------
    # Layer 2: Claims / Polarity Graph (:ASSERTS, :SUPPORTS, :REFUTES, etc.)
    # ------------------------------------------------------------------

    async def create_claim(
        self, claim_id: str, paper_doi: str, statement: str, confidence: float = 1.0,
        embedding: list[float] | None = None, page_number: int | None = None,
        bounding_box: list[float] | None = None, crop_uri: str | None = None,
        run_id: str | None = None, created_in_stage: int = 3,
    ) -> dict[str, Any]:
        """Create :Claim node linked via :ASSERTS to :Paper."""
        c_doi = normalize_doi(paper_doi)
        query = (
            "MERGE (p:Paper {doi: $paper_doi}) MERGE (cl:Claim {claim_id: $claim_id}) "
            "ON CREATE SET cl.created_at = datetime() "
            "SET cl.paper_doi = $paper_doi, cl.statement = $statement, cl.confidence = $confidence, "
            "cl.embedding = $embedding, cl.page_number = $page_number, cl.bounding_box = $bounding_box, "
            "cl.crop_uri = $crop_uri, cl.run_id = $run_id, cl.created_in_stage = $created_in_stage "
            "MERGE (p)-[:ASSERTS]->(cl) RETURN cl.claim_id AS claim_id, cl.statement AS statement"
        )
        params = {
            "claim_id": claim_id, "paper_doi": c_doi, "statement": statement, "confidence": confidence,
            "embedding": embedding, "page_number": page_number, "bounding_box": bounding_box,
            "crop_uri": crop_uri, "run_id": run_id, "created_in_stage": created_in_stage,
        }
        recs = await self.execute_write(query, params)
        return recs[0] if recs else {"claim_id": claim_id, "statement": statement}

    async def link_claim_supports(
        self, claim_id: str, question_id: str, confidence: float = 1.0
    ) -> None:
        """Create :SUPPORTS edge between Claim and ResearchQuestion."""
        query = """
        MATCH (cl:Claim {claim_id: $claim_id})
        MATCH (q:ResearchQuestion {question_id: $question_id})
        MERGE (cl)-[r:SUPPORTS]->(q)
        SET r.confidence = $confidence
        """
        await self.execute_write(
            query,
            {"claim_id": claim_id, "question_id": question_id, "confidence": confidence},
        )

    async def link_claim_refutes(
        self, claim_id: str, question_id: str, confidence: float = 1.0
    ) -> None:
        """Create :REFUTES edge between Claim and ResearchQuestion."""
        query = """
        MATCH (cl:Claim {claim_id: $claim_id})
        MATCH (q:ResearchQuestion {question_id: $question_id})
        MERGE (cl)-[r:REFUTES]->(q)
        SET r.confidence = $confidence
        """
        await self.execute_write(
            query,
            {"claim_id": claim_id, "question_id": question_id, "confidence": confidence},
        )

    async def link_claim_contradiction(
        self, claim_a_id: str, claim_b_id: str, reason: str = ""
    ) -> None:
        """Create bipartite :CONTRADICTS relationship between two conflicting claims."""
        query = """
        MATCH (a:Claim {claim_id: $claim_a})
        MATCH (b:Claim {claim_id: $claim_b})
        MERGE (a)-[r:CONTRADICTS]->(b)
        SET r.reason = $reason, r.detected_at = datetime()
        """
        await self.execute_write(
            query, {"claim_a": claim_a_id, "claim_b": claim_b_id, "reason": reason}
        )

    async def link_claim_resolution(
        self, claim_a_id: str, claim_b_id: str, resolution_id: str
    ) -> None:
        """Create :RESOLVED_BY synthesis resolution edge."""
        query = """
        MATCH (a:Claim {claim_id: $claim_a})
        MATCH (res:Claim {claim_id: $resolution_id})
        MERGE (a)-[:RESOLVED_BY]->(res)
        """
        await self.execute_write(
            query, {"claim_a": claim_a_id, "resolution_id": resolution_id}
        )

    # ------------------------------------------------------------------
    # Layer 3: Benchmark & Methodology (:PROPOSES, :EVALUATED_ON, :ACHIEVED)
    # ------------------------------------------------------------------

    async def create_method(
        self, method_id: str, paper_doi: str, name: str,
        description: str = "", loss_function: str = "",
    ) -> dict[str, Any]:
        """Create :Method node linked to Paper via :PROPOSES."""
        c_doi = normalize_doi(paper_doi)
        query = (
            "MERGE (p:Paper {doi: $paper_doi}) MERGE (m:Method {method_id: $method_id}) "
            "ON CREATE SET m.created_at = datetime() "
            "SET m.paper_doi = $paper_doi, m.name = $name, m.description = $description, m.loss_function = $loss_function "
            "MERGE (p)-[:PROPOSES]->(m) RETURN m.method_id AS method_id, m.name AS name"
        )
        params = {"method_id": method_id, "paper_doi": c_doi, "name": name, "description": description, "loss_function": loss_function}
        recs = await self.execute_write(query, params)
        return recs[0] if recs else {"method_id": method_id, "name": name}

    async def create_dataset(
        self, dataset_id: str, name: str, task_type: str = "", domain: str = ""
    ) -> dict[str, Any]:
        """Create :Dataset benchmark node."""
        query = """
        MERGE (d:Dataset {dataset_id: $dataset_id})
        ON CREATE SET d.created_at = datetime()
        SET d.name = $name, d.task_type = $task_type, d.domain = $domain
        RETURN d.dataset_id AS dataset_id, d.name AS name
        """
        recs = await self.execute_write(
            query,
            {"dataset_id": dataset_id, "name": name, "task_type": task_type, "domain": domain},
        )
        return recs[0] if recs else {"dataset_id": dataset_id, "name": name}

    async def create_metric_result(
        self, result_id: str, method_id: str, dataset_id: str, metric_name: str,
        score: float, variance: float = 0.0, is_sota: bool = False,
    ) -> dict[str, Any]:
        """Create :MetricResult node linked via :ACHIEVED and :ON_DATASET."""
        query = (
            "MATCH (m:Method {method_id: $method_id}) MATCH (d:Dataset {dataset_id: $dataset_id}) "
            "MERGE (mr:MetricResult {result_id: $result_id}) ON CREATE SET mr.created_at = datetime() "
            "SET mr.method_id = $method_id, mr.dataset_id = $dataset_id, mr.metric_name = $metric_name, "
            "mr.score = $score, mr.variance = $variance, mr.is_sota = $is_sota "
            "MERGE (m)-[:ACHIEVED]->(mr) MERGE (mr)-[:ON_DATASET]->(d) "
            "RETURN mr.result_id AS result_id, mr.score AS score"
        )
        params = {
            "result_id": result_id, "method_id": method_id, "dataset_id": dataset_id,
            "metric_name": metric_name, "score": score, "variance": variance, "is_sota": is_sota,
        }
        recs = await self.execute_write(query, params)
        return recs[0] if recs else {"result_id": result_id, "score": score}

    # ------------------------------------------------------------------
    # Workflow State Pointers & Compensating Rollbacks
    # ------------------------------------------------------------------

    async def link_campaign_stage_state(
        self, campaign_id: str, substate_id: str, stage_index: int,
        stage_name: str, status: str, sha256: str = "",
    ) -> None:
        """Link :ResearchCampaign to :StageSubstate via :HAS_STAGE_STATE."""
        query = (
            "MERGE (c:ResearchCampaign {campaign_id: $campaign_id}) "
            "MERGE (s:StageSubstate {substate_id: $substate_id}) ON CREATE SET s.created_at = datetime() "
            "SET s.campaign_id = $campaign_id, s.stage_index = $stage_index, s.stage_name = $stage_name, "
            "s.status = $status, s.checkpoint_sha256 = $sha256, s.updated_at = datetime() "
            "MERGE (c)-[:HAS_STAGE_STATE]->(s)"
        )
        params = {
            "campaign_id": campaign_id, "substate_id": substate_id, "stage_index": stage_index,
            "stage_name": stage_name, "status": status, "sha256": sha256,
        }
        await self.execute_write(query, params)

    async def rollback_stage_transaction(self, run_id: str, stage: int) -> int:
        """Compensating rollback Cypher deleting entities created at or after stage."""
        query = """
        MATCH (n)
        WHERE n.run_id = $run_id AND n.created_in_stage >= $stage
        WITH n, count(n) AS cnt
        DETACH DELETE n
        RETURN cnt
        """
        recs = await self.execute_write(query, {"run_id": run_id, "stage": stage})
        return int(recs[0]["cnt"]) if recs and "cnt" in recs[0] else 0

    async def flag_open_research_frontier(
        self, rq_id: str, remediation_notes: str, run_id: str
    ) -> dict[str, Any]:
        """Flag research question as Open Research Frontier after gap exhaustion."""
        query = (
            "MATCH (rq:ResearchQuestion {question_id: $rq_id}) "
            "SET rq.is_open_frontier = true, "
            "    rq.remediation_notes = $remediation_notes, "
            "    rq.remediation_run_id = $run_id, "
            "    rq.updated_at = datetime() "
            "RETURN rq.question_id AS rq_id, rq.is_open_frontier AS is_open_frontier"
        )
        params = {"rq_id": rq_id, "remediation_notes": remediation_notes, "run_id": run_id}
        recs = await self.execute_write(query, params)
        if recs:
            return {"rq_id": recs[0].get("rq_id", rq_id), "is_open_frontier": bool(recs[0].get("is_open_frontier", True))}
        return {"rq_id": rq_id, "is_open_frontier": True}


def normalize_doi(doi: str) -> str:
    """Normalize DOI to canonical lowercase format stripped of URL prefixes."""
    clean = str(doi).strip()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if clean.lower().startswith(prefix):
            clean = clean[len(prefix):]
    return clean.strip().lower()

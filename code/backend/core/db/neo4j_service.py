from __future__ import annotations
import logging
from typing import Any  # Only for neo4j Record type boundary
from neo4j import AsyncGraphDatabase, AsyncDriver
from neo4j.exceptions import ServiceUnavailable, AuthError

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
        ON CREATE SET p.created_at = datetime()
        SET p.title           = $title,
            p.abstract        = $abstract,
            p.year            = $year,
            p.cited_by_count  = $cited_by_count,
            p.openalex_id     = $openalex_id,
            p.publication_date = $publication_date,
            p.source          = $source,
            p.updated_at      = datetime()
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

        if getattr(paper, "authors", None):
            author_query = """
            MATCH (p:Paper {doi: $doi})
            UNWIND $authors AS auth
            MERGE (a:Author {name: auth.name})
            ON CREATE SET a.openalex_id = auth.openalex_id,
                          a.orcid       = auth.orcid,
                          a.institution = auth.institution,
                          a.created_at  = datetime()
            MERGE (a)-[:AUTHORED]->(p)
            """
            auth_params = [
                {
                    'name': a.name,
                    'openalex_id': a.openalex_id,
                    'orcid': a.orcid,
                    'institution': a.institution,
                }
                for a in paper.authors
                if hasattr(a, "name") and a.name
            ]
            if auth_params:
                await self.execute_write(author_query, {'doi': paper.doi, 'authors': auth_params})

        if getattr(paper, "venue", None) and hasattr(paper.venue, "name") and paper.venue.name:
            venue_query = """
            MATCH (p:Paper {doi: $doi})
            MERGE (v:Venue {name: $venue.name})
            ON CREATE SET v.openalex_id = $venue.openalex_id,
                          v.issn        = $venue.issn,
                          v.venue_type  = $venue.venue_type,
                          v.created_at  = datetime()
            MERGE (p)-[:PUBLISHED_IN]->(v)
            """
            v_params = {
                'name': paper.venue.name,
                'openalex_id': paper.venue.openalex_id,
                'issn': paper.venue.issn,
                'venue_type': paper.venue.venue_type,
            }
            await self.execute_write(venue_query, {'doi': paper.doi, 'venue': v_params})

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
        self,
        session_id: str,
        threshold: float,
        top_k: int = 1000,
    ) -> list[dict[str, Any]]:
        """Compute cosine similarity between all paper embeddings in a session
        and all research question embeddings in that session using the ANN vector index.

        Returns a list of dicts with keys: doi, question, score.
        Does not load embedding vectors into Python memory.
        """
        query = """
        MATCH (q:Question {session_id: $session_id})
        WHERE q.embedding IS NOT NULL
        CALL db.index.vector.queryNodes('paper_embeddings', $top_k, q.embedding)
        YIELD node AS p, score
        MATCH (s:Session {session_id: $session_id})-[:CONTAINS]->(p)
        WHERE score >= $threshold
        RETURN p.doi AS doi, q.text AS question, score AS score
        """
        records = await self.execute_read(query, {
            'session_id': session_id,
            'threshold': threshold,
            'top_k': top_k,
        })
        return records

    async def compute_pagerank(
        self,
        session_id: str,
        iterations: int = 20,
        damping: float = 0.85,
    ) -> dict[str, float]:
        """Compute PageRank for papers in the session's citation subgraph.

        Uses Neo4j GDS if available, otherwise falls back to standard
        pure-Python NetworkX PageRank calculation.
        """
        import uuid
        graph_name = f"subgraph_{session_id.replace('-', '_')}_{uuid.uuid4().hex[:8]}"

        try:
            # 1. Project the citation subgraph for papers in this session
            project_nodes = """
            MATCH (s:Session {session_id: $session_id})-[:CONTAINS]->(p:Paper)
            RETURN id(p) AS id, ["Paper"] AS labels
            """
            project_edges = """
            MATCH (s:Session {session_id: $session_id})-[:CONTAINS]->(p1:Paper)-[:CITES]->(p2:Paper)
            WHERE (s)-[:CONTAINS]->(p2)
            RETURN id(p1) AS source, id(p2) AS target, "CITES" AS type
            """
            await self.execute_write(
                "CALL gds.graph.project.cypher($graph_name, $nodes, $edges, {parameters: {session_id: $session_id}})",
                {
                    "graph_name": graph_name,
                    "nodes": project_nodes,
                    "edges": project_edges,
                    "session_id": session_id,
                }
            )

            # 2. Run PageRank stream
            pagerank_query = """
            CALL gds.pageRank.stream($graph_name, {
                maxIterations: $iterations,
                dampingFactor: $damping
            })
            YIELD nodeId, score
            RETURN gds.util.asNode(nodeId).doi AS doi, score AS score
            """
            records = await self.execute_read(pagerank_query, {
                "graph_name": graph_name,
                "iterations": iterations,
                "damping": damping,
            })

            # 3. Clean up the projected graph
            await self.execute_write(
                "CALL gds.graph.drop($graph_name, false)",
                {"graph_name": graph_name}
            )

            # Map results
            scores = {str(r["doi"]): float(r["score"]) for r in records if r.get("doi")}

            # Normalization to [0.0, 1.0] range
            if scores:
                min_s = min(scores.values())
                max_s = max(scores.values())
                diff = max_s - min_s
                if diff > 0.0:
                    scores = {k: (v - min_s) / diff for k, v in scores.items()}
                else:
                    scores = {k: 1.0 for k in scores}
            return scores

        except Exception as e:
            logger.warning(
                "Neo4j GDS PageRank failed (plugin may not be installed). "
                "Falling back to pure-Python NetworkX PageRank. Error: %s",
                e
            )
            # Try to drop graph just in case
            try:
                await self.execute_write(
                    "CALL gds.graph.drop($graph_name, false)",
                    {"graph_name": graph_name}
                )
            except Exception:
                pass
            return await self._compute_pagerank_fallback(session_id, iterations, damping)

    async def _compute_pagerank_fallback(
        self,
        session_id: str,
        iterations: int = 20,
        damping: float = 0.85,
    ) -> dict[str, float]:
        """Pure-Python NetworkX fallback for PageRank computation."""
        try:
            import networkx as nx
        except ImportError:
            logger.error("networkx package not installed. Degree centrality will be used as fallback.")
            return await self._compute_degree_centrality_fallback(session_id)

        # 1. Fetch all nodes in the session
        nodes_query = """
        MATCH (s:Session {session_id: $session_id})-[:CONTAINS]->(p:Paper)
        RETURN p.doi AS doi
        """
        node_records = await self.execute_read(nodes_query, {"session_id": session_id})
        dois = [str(r["doi"]) for r in node_records if r.get("doi")]

        if not dois:
            return {}

        # 2. Fetch CITES relations within these DOIs
        edges_query = """
        MATCH (s:Session {session_id: $session_id})-[:CONTAINS]->(p1:Paper)-[:CITES]->(p2:Paper)
        WHERE (s)-[:CONTAINS]->(p2)
        RETURN p1.doi AS source, p2.doi AS target
        """
        edge_records = await self.execute_read(edges_query, {"session_id": session_id})

        # 3. Construct graph
        g = nx.DiGraph()
        g.add_nodes_from(dois)
        for r in edge_records:
            if r.get("source") and r.get("target"):
                g.add_edge(str(r["source"]), str(r["target"]))

        # 4. Calculate PageRank
        try:
            pr_scores = nx.pagerank(g, alpha=damping, max_iter=iterations)
        except Exception as pr_err:
            logger.warning("NetworkX pagerank error, using degree centrality fallback: %s", pr_err)
            return await self._compute_degree_centrality_fallback(session_id)

        # Scale scores to [0.0, 1.0] range
        scores = {k: float(v) for k, v in pr_scores.items()}
        if scores:
            min_s = min(scores.values())
            max_s = max(scores.values())
            diff = max_s - min_s
            if diff > 0.0:
                scores = {k: (v - min_s) / diff for k, v in scores.items()}
            else:
                scores = {k: 1.0 for k in scores}
        return scores

    async def _compute_degree_centrality_fallback(self, session_id: str) -> dict[str, float]:
        """Trivial citation-degree fallback if NetworkX is also not installed."""
        query = """
        MATCH (s:Session {session_id: $session_id})-[:CONTAINS]->(p:Paper)
        OPTIONAL MATCH (s)-[:CONTAINS]->(other:Paper)-[:CITES]->(p)
        RETURN p.doi AS doi, count(other) AS degree
        """
        records = await self.execute_read(query, {"session_id": session_id})
        scores = {str(r["doi"]): float(r.get("degree", 0.0)) for r in records if r.get("doi")}
        if scores:
            min_s = min(scores.values())
            max_s = max(scores.values())
            diff = max_s - min_s
            if diff > 0.0:
                scores = {k: (v - min_s) / diff for k, v in scores.items()}
            else:
                scores = {k: 1.0 for k in scores}
        return scores

    # ------------------------------------------------------------------
    # Project management (agentic workflow)
    # ------------------------------------------------------------------

    async def create_project_node(
        self,
        project_id: str,
        name: str,
        status: str = 'active',
    ) -> dict[str, Any]:
        """Create a Project node in the graph.

        Uses MERGE for idempotency — safe to call multiple times for
        the same project_id.

        Args:
            project_id: UUID string for the project.
            name: Human-readable project name.
            status: Project status (default 'active').

        Returns:
            Dict of the created/updated project properties.
        """
        query = """
        MERGE (pr:Project {project_id: $project_id})
        ON CREATE SET pr.created_at = datetime()
        SET pr.name       = $name,
            pr.status     = $status,
            pr.updated_at = datetime()
        RETURN pr.project_id AS project_id,
               pr.name       AS name,
               pr.status     AS status
        """
        records = await self.execute_write(query, {
            'project_id': project_id,
            'name': name,
            'status': status,
        })
        return records[0]

    async def create_research_question(
        self,
        question_id: str,
        text: str,
        embedding: list[float],
        project_id: str,
    ) -> dict[str, Any]:
        """Create a ResearchQuestion node with a BELONGS_TO relationship to a Project.

        Args:
            question_id: UUID string for the question.
            text: The research question text.
            embedding: Pre-computed embedding vector.
            project_id: The owning project's ID.

        Returns:
            Dict of the created question properties.
        """
        query = """
        MERGE (pr:Project {project_id: $project_id})
        MERGE (q:ResearchQuestion {question_id: $question_id})
        ON CREATE SET q.created_at = datetime()
        SET q.text       = $text,
            q.embedding  = $embedding,
            q.project_id = $project_id,
            q.updated_at = datetime()
        MERGE (q)-[:BELONGS_TO]->(pr)
        RETURN q.question_id AS question_id,
               q.text        AS text,
               q.project_id  AS project_id
        """
        records = await self.execute_write(query, {
            'question_id': question_id,
            'text': text,
            'embedding': embedding,
            'project_id': project_id,
        })
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
        MATCH (p:Paper {doi: $doi})
        MERGE (pr)-[:HAS_PAPER]->(p)
        """
        await self.execute_write(query, {
            'project_id': project_id,
            'doi': doi,
        })

    async def get_project_papers(
        self,
        project_id: str,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Get all papers associated with a project.

        Args:
            project_id: The project's UUID.
            limit: Maximum number of papers to return.

        Returns:
            List of paper property dicts (without embeddings).
        """
        query = """
        MATCH (pr:Project {project_id: $project_id})-[:HAS_PAPER]->(p:Paper)
        RETURN p.doi            AS doi,
               p.title          AS title,
               p.abstract       AS abstract,
               p.year           AS year,
               p.cited_by_count AS cited_by_count,
               p.openalex_id   AS openalex_id,
               p.source         AS source
        LIMIT $limit
        """
        return await self.execute_read(query, {
            'project_id': project_id,
            'limit': limit,
        })

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
        self,
        project_id: str,
        threshold: float = 0.6,
    ) -> list[dict[str, Any]]:
        """Get coverage gap statistics for research questions in a project.

        Computes how many papers are above the similarity threshold
        for each research question.

        Args:
            project_id: The project's UUID.
            threshold: Minimum similarity score for a paper to be 'covered'.

        Returns:
            List of dicts with question, covered_count.
        """
        query = """
        MATCH (q:ResearchQuestion {project_id: $project_id})
        WHERE q.embedding IS NOT NULL
        CALL db.index.vector.queryNodes('paper_embeddings', 50, q.embedding)
        YIELD node AS p, score
        MATCH (pr:Project {project_id: $project_id})-[:HAS_PAPER]->(p)
        WHERE score >= $threshold
        RETURN q.text AS question, count(p) AS covered_count
        """
        return await self.execute_read(query, {
            'project_id': project_id,
            'threshold': threshold,
        })

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

    async def create_papers_batch(self, papers: list[PaperCreate]) -> int:
        """MERGE multiple papers and their author/venue relationships in a single batch."""
        if not papers:
            return 0

        paper_rows: list[dict[str, Any]] = []
        author_rows: list[dict[str, Any]] = []
        venue_rows: list[dict[str, Any]] = []

        for p in papers:
            paper_rows.append({
                'doi': p.doi,
                'title': p.title,
                'abstract': p.abstract,
                'year': p.year,
                'cited_by_count': p.cited_by_count,
                'openalex_id': p.openalex_id,
                'publication_date': p.publication_date,
                'source': p.source,
            })
            for a in getattr(p, "authors", []):
                if hasattr(a, "name") and a.name:
                    author_rows.append({
                        'doi': p.doi,
                        'name': a.name,
                        'openalex_id': getattr(a, 'openalex_id', None),
                        'orcid': getattr(a, 'orcid', None),
                        'institution': getattr(a, 'institution', None),
                    })
            venue = getattr(p, "venue", None)
            if venue and hasattr(venue, "name") and venue.name:
                venue_rows.append({
                    'doi': p.doi,
                    'name': venue.name,
                    'openalex_id': getattr(venue, 'openalex_id', None),
                    'issn': getattr(venue, 'issn', None),
                    'venue_type': getattr(venue, 'venue_type', None),
                })

        batch_papers_query = """
        UNWIND $batch AS row
        MERGE (p:Paper {doi: row.doi})
        ON CREATE SET p.created_at = datetime()
        SET p.title           = row.title,
            p.abstract        = row.abstract,
            p.year            = row.year,
            p.cited_by_count  = row.cited_by_count,
            p.openalex_id     = row.openalex_id,
            p.publication_date = row.publication_date,
            p.source          = row.source,
            p.updated_at      = datetime()
        """
        await self.execute_write(batch_papers_query, {'batch': paper_rows})

        if author_rows:
            batch_authors_query = """
            UNWIND $batch AS row
            MATCH (p:Paper {doi: row.doi})
            MERGE (a:Author {name: row.name})
            ON CREATE SET a.openalex_id = row.openalex_id,
                          a.orcid       = row.orcid,
                          a.institution = row.institution,
                          a.created_at  = datetime()
            MERGE (a)-[:AUTHORED]->(p)
            """
            await self.execute_write(batch_authors_query, {'batch': author_rows})

        if venue_rows:
            batch_venues_query = """
            UNWIND $batch AS row
            MATCH (p:Paper {doi: row.doi})
            MERGE (v:Venue {name: row.name})
            ON CREATE SET v.openalex_id = row.openalex_id,
                          v.issn        = row.issn,
                          v.venue_type  = row.venue_type,
                          v.created_at  = datetime()
            MERGE (p)-[:PUBLISHED_IN]->(v)
            """
            await self.execute_write(batch_venues_query, {'batch': venue_rows})

        return len(papers)




"""Retrieval service facade for ALRS v2.

Unified entry point for all paper retrieval operations: local graph
lookups (Neo4j), remote fetching (OpenAlex), batch operations, and
citation / reference / author / venue queries.

Absorbs the responsibilities of the former ``services.paper_service.PaperService``
and delegates to ``core.db.neo4j_service.Neo4jService`` for graph storage
and ``core.clients.openalex_client.OpenAlexService`` for remote API calls.

Architecture (feature-based)::

    Router (HTTP) → RetrievalService (orchestrate) → Neo4jService (graph)
                                                    → OpenAlexService (API)

Design decision — zero-RAM embedding policy:
    Cypher queries deliberately omit ``p.embedding`` from RETURN clauses.
    Embeddings are stored and compared *inside* Neo4j only; they must never
    travel to the Python process.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from features.retrieval.models import AuthorRead, PaperCreate, PaperRead, PaperSummary, VenueRead

if TYPE_CHECKING:
    from core.clients.openalex_client import OpenAlexService
    from core.db.neo4j_service import Neo4jService
    from core.logging.log_service import LogService

logger = logging.getLogger(__name__)


class RetrievalService:
    """Facade for paper retrieval — local graph + remote API.

    Attributes:
        _neo4j: Injected Neo4j graph database service.
        _openalex: Injected OpenAlex API client.
        _log_service: Optional logging service for telemetry.
    """

    def __init__(
        self,
        neo4j: Neo4jService,
        openalex: OpenAlexService,
        log_service: LogService | None = None,
    ) -> None:
        self._neo4j = neo4j
        self._openalex = openalex
        self._log_service = log_service

    # ==================================================================
    # Local graph lookups
    # ==================================================================

    async def get_paper(self, doi: str) -> PaperRead | None:
        """Fetch a single paper and its relationships by DOI from Neo4j.

        Runs a Cypher query that JOINs Paper → Author, Venue, and
        Keyword nodes, then maps the raw record dict into a validated
        ``PaperRead`` Pydantic model.

        Args:
            doi: The DOI string (e.g. ``"10.1109/ACCESS.2023.1234567"``).

        Returns:
            A ``PaperRead`` instance if found, or ``None`` if no Paper
            node exists for the given DOI.
        """
        records = await self._neo4j.execute_read(
            """MATCH (p:Paper {doi: $doi})
               OPTIONAL MATCH (p)<-[:AUTHORED]-(a:Author)
               OPTIONAL MATCH (p)-[:PUBLISHED_IN]->(v:Venue)
               OPTIONAL MATCH (p)-[:HAS_KEYWORD]->(k:Keyword)
               RETURN p.doi AS doi, p.title AS title, p.abstract AS abstract,
                      p.year AS year, p.cited_by_count AS cited_by_count,
                      p.openalex_id AS openalex_id,
                      p.publication_date AS publication_date,
                      p.source AS source, p.created_at AS created_at,
                      collect(DISTINCT {name: a.name, openalex_id: a.openalex_id}) AS authors,
                      v.name AS venue_name,
                      collect(DISTINCT k.term) AS keywords""",
            {"doi": doi},
        )

        if not records:
            return None

        record = records[0]
        return self._map_record_to_paper(record)

    async def paper_exists(self, doi: str) -> bool:
        """Check if a paper node exists in the local graph.

        Args:
            doi: The paper DOI.

        Returns:
            ``True`` if a Paper node with this DOI exists.
        """
        return await self._neo4j.paper_exists(doi)

    async def store_paper(self, paper: PaperCreate) -> dict[str, Any]:
        """MERGE a paper node by DOI into the local graph.

        Uses MERGE for idempotency — safe to call multiple times for
        the same DOI without creating duplicates.

        Args:
            paper: Validated ``PaperCreate`` model.

        Returns:
            Dict of the created/updated paper properties.
        """
        return await self._neo4j.create_paper(paper)

    async def store_citation(self, citing_doi: str, cited_doi: str) -> None:
        """Create a CITES relationship between two existing papers.

        Both paper nodes must already exist.  Uses MERGE for idempotency.

        Args:
            citing_doi: DOI of the citing paper.
            cited_doi: DOI of the cited paper.
        """
        await self._neo4j.create_citation(citing_doi, cited_doi)

    # ==================================================================
    # Local citation / reference queries
    # ==================================================================

    async def get_local_citations(self, doi: str) -> list[str]:
        """Get DOIs of papers that cite the given paper from the local graph.

        Traverses ``(p)<-[:CITES]-(citing)`` relationships in Neo4j.

        Args:
            doi: The cited paper's DOI.

        Returns:
            List of citing paper DOIs.
        """
        records = await self._neo4j.execute_read(
            """MATCH (citing:Paper)-[:CITES]->(p:Paper {doi: $doi})
               RETURN citing.doi AS doi""",
            {"doi": doi},
        )
        return [str(r["doi"]) for r in records if r.get("doi")]

    async def get_local_references(self, doi: str) -> list[str]:
        """Get DOIs of papers referenced by the given paper from the local graph.

        Traverses ``(p)-[:CITES]->(cited)`` relationships in Neo4j.

        Args:
            doi: The referencing paper's DOI.

        Returns:
            List of referenced paper DOIs.
        """
        records = await self._neo4j.execute_read(
            """MATCH (p:Paper {doi: $doi})-[:CITES]->(cited:Paper)
               RETURN cited.doi AS doi""",
            {"doi": doi},
        )
        return [str(r["doi"]) for r in records if r.get("doi")]

    # ==================================================================
    # Remote fetching (OpenAlex)
    # ==================================================================

    async def fetch_paper_remote(
        self,
        doi: str,
        *,
        session_id: str | None = None,
    ) -> PaperCreate | None:
        """Fetch a paper by DOI from the OpenAlex API.

        Args:
            doi: The DOI (e.g. ``'10.1145/3292500.3330919'``).
            session_id: Session ID for log correlation.

        Returns:
            ``PaperCreate`` model or ``None`` if not found.
        """
        return await self._openalex.get_paper_by_doi(doi, session_id=session_id)

    async def fetch_papers_batch(
        self,
        dois: list[str],
        *,
        session_id: str | None = None,
    ) -> list[PaperCreate]:
        """Fetch multiple papers by DOIs from OpenAlex efficiently.

        Chunks requests in batches of 50 using OR filter syntax.

        Args:
            dois: List of DOIs to fetch.
            session_id: Session ID for log correlation.

        Returns:
            List of ``PaperCreate`` models for found papers.
        """
        return await self._openalex.batch_get_papers_by_dois(
            dois, session_id=session_id,
        )

    async def search_papers_by_title(
        self,
        title: str,
        *,
        max_results: int = 10,
        session_id: str | None = None,
    ) -> list[PaperSummary]:
        """Search for papers by title via OpenAlex.

        Args:
            title: Search query string.
            max_results: Maximum number of results (1–25).
            session_id: Session ID for log correlation.

        Returns:
            List of ``PaperSummary`` models.
        """
        return await self._openalex.search_by_title(
            title, max_results=max_results, session_id=session_id,
        )

    async def get_citations(
        self,
        doi: str,
        *,
        max_results: int = 200,
        session_id: str | None = None,
        openalex_id: str | None = None,
    ) -> list[str]:
        """Get DOIs of papers that cite the given paper via OpenAlex.

        Args:
            doi: The DOI of the paper.
            max_results: Maximum number of citing DOIs.
            session_id: Session ID for log correlation.
            openalex_id: OpenAlex ID for robust filtering.

        Returns:
            List of citing paper DOIs.
        """
        return await self._openalex.get_citations(
            doi,
            max_results=max_results,
            session_id=session_id,
            openalex_id=openalex_id,
        )

    async def get_references(
        self,
        doi: str,
        *,
        max_results: int = 200,
        session_id: str | None = None,
        openalex_id: str | None = None,
    ) -> list[str]:
        """Get DOIs of papers referenced by the given paper via OpenAlex.

        Args:
            doi: The DOI of the paper.
            max_results: Maximum number of referenced DOIs.
            session_id: Session ID for log correlation.
            openalex_id: OpenAlex ID for robust filtering.

        Returns:
            List of referenced paper DOIs.
        """
        return await self._openalex.get_references(
            doi,
            max_results=max_results,
            session_id=session_id,
            openalex_id=openalex_id,
        )

    # ==================================================================
    # Author queries
    # ==================================================================

    async def get_author(self, openalex_id: str) -> AuthorRead | None:
        """Fetch an author by OpenAlex ID from the local graph.

        Args:
            openalex_id: The author's OpenAlex identifier.

        Returns:
            ``AuthorRead`` model or ``None`` if not found.
        """
        records = await self._neo4j.execute_read(
            """MATCH (a:Author {openalex_id: $openalex_id})
               OPTIONAL MATCH (a)-[:AUTHORED]->(p:Paper)
               RETURN a.name AS name,
                      a.openalex_id AS openalex_id,
                      a.orcid AS orcid,
                      a.institution AS institution,
                      count(p) AS paper_count""",
            {"openalex_id": openalex_id},
        )
        if not records:
            return None
        r = records[0]
        return AuthorRead(
            name=str(r["name"]),
            openalex_id=r.get("openalex_id"),  # type: ignore[arg-type]
            orcid=r.get("orcid"),  # type: ignore[arg-type]
            institution=r.get("institution"),  # type: ignore[arg-type]
            paper_count=int(r.get("paper_count", 0)),
        )

    async def get_author_papers(self, openalex_id: str) -> list[PaperRead]:
        """Get all papers authored by a given author.

        Args:
            openalex_id: The author's OpenAlex identifier.

        Returns:
            List of ``PaperRead`` models.
        """
        records = await self._neo4j.execute_read(
            """MATCH (a:Author {openalex_id: $openalex_id})-[:AUTHORED]->(p:Paper)
               OPTIONAL MATCH (p)<-[:AUTHORED]-(a2:Author)
               OPTIONAL MATCH (p)-[:PUBLISHED_IN]->(v:Venue)
               OPTIONAL MATCH (p)-[:HAS_KEYWORD]->(k:Keyword)
               RETURN p.doi AS doi, p.title AS title, p.abstract AS abstract,
                      p.year AS year, p.cited_by_count AS cited_by_count,
                      p.openalex_id AS openalex_id,
                      p.publication_date AS publication_date,
                      p.source AS source, p.created_at AS created_at,
                      collect(DISTINCT {name: a2.name, openalex_id: a2.openalex_id}) AS authors,
                      v.name AS venue_name,
                      collect(DISTINCT k.term) AS keywords""",
            {"openalex_id": openalex_id},
        )
        return [self._map_record_to_paper(r) for r in records if r.get("doi")]

    async def search_authors(self, name: str) -> list[AuthorRead]:
        """Search for authors by name (case-insensitive CONTAINS).

        Args:
            name: Partial or full author name.

        Returns:
            List of matching ``AuthorRead`` models.
        """
        records = await self._neo4j.execute_read(
            """MATCH (a:Author)
               WHERE toLower(a.name) CONTAINS toLower($name)
               OPTIONAL MATCH (a)-[:AUTHORED]->(p:Paper)
               RETURN a.name AS name,
                      a.openalex_id AS openalex_id,
                      a.orcid AS orcid,
                      a.institution AS institution,
                      count(p) AS paper_count
               LIMIT 25""",
            {"name": name},
        )
        return [
            AuthorRead(
                name=str(r["name"]),
                openalex_id=r.get("openalex_id"),  # type: ignore[arg-type]
                orcid=r.get("orcid"),  # type: ignore[arg-type]
                institution=r.get("institution"),  # type: ignore[arg-type]
                paper_count=int(r.get("paper_count", 0)),
            )
            for r in records
            if r.get("name")
        ]

    # ==================================================================
    # Venue queries
    # ==================================================================

    async def get_venue(self, openalex_id: str) -> VenueRead | None:
        """Fetch a venue by OpenAlex ID from the local graph.

        Args:
            openalex_id: The venue's OpenAlex identifier.

        Returns:
            ``VenueRead`` model or ``None`` if not found.
        """
        records = await self._neo4j.execute_read(
            """MATCH (v:Venue {openalex_id: $openalex_id})
               OPTIONAL MATCH (p:Paper)-[:PUBLISHED_IN]->(v)
               RETURN v.name AS name,
                      v.openalex_id AS openalex_id,
                      v.issn AS issn,
                      v.venue_type AS venue_type,
                      count(p) AS paper_count""",
            {"openalex_id": openalex_id},
        )
        if not records:
            return None
        r = records[0]
        return VenueRead(
            name=str(r["name"]),
            openalex_id=r.get("openalex_id"),  # type: ignore[arg-type]
            issn=r.get("issn"),  # type: ignore[arg-type]
            venue_type=r.get("venue_type"),  # type: ignore[arg-type]
            paper_count=int(r.get("paper_count", 0)),
        )

    async def get_venue_papers(self, openalex_id: str) -> list[PaperRead]:
        """Get all papers published in a given venue.

        Args:
            openalex_id: The venue's OpenAlex identifier.

        Returns:
            List of ``PaperRead`` models.
        """
        records = await self._neo4j.execute_read(
            """MATCH (p:Paper)-[:PUBLISHED_IN]->(v:Venue {openalex_id: $openalex_id})
               OPTIONAL MATCH (p)<-[:AUTHORED]-(a:Author)
               OPTIONAL MATCH (p)-[:HAS_KEYWORD]->(k:Keyword)
               RETURN p.doi AS doi, p.title AS title, p.abstract AS abstract,
                      p.year AS year, p.cited_by_count AS cited_by_count,
                      p.openalex_id AS openalex_id,
                      p.publication_date AS publication_date,
                      p.source AS source, p.created_at AS created_at,
                      collect(DISTINCT {name: a.name, openalex_id: a.openalex_id}) AS authors,
                      v.name AS venue_name,
                      collect(DISTINCT k.term) AS keywords""",
            {"openalex_id": openalex_id},
        )
        return [self._map_record_to_paper(r) for r in records if r.get("doi")]

    async def search_venues(self, name: str) -> list[VenueRead]:
        """Search for venues by name (case-insensitive CONTAINS).

        Args:
            name: Partial or full venue name.

        Returns:
            List of matching ``VenueRead`` models.
        """
        records = await self._neo4j.execute_read(
            """MATCH (v:Venue)
               WHERE toLower(v.name) CONTAINS toLower($name)
               OPTIONAL MATCH (p:Paper)-[:PUBLISHED_IN]->(v)
               RETURN v.name AS name,
                      v.openalex_id AS openalex_id,
                      v.issn AS issn,
                      v.venue_type AS venue_type,
                      count(p) AS paper_count
               LIMIT 25""",
            {"name": name},
        )
        return [
            VenueRead(
                name=str(r["name"]),
                openalex_id=r.get("openalex_id"),  # type: ignore[arg-type]
                issn=r.get("issn"),  # type: ignore[arg-type]
                venue_type=r.get("venue_type"),  # type: ignore[arg-type]
                paper_count=int(r.get("paper_count", 0)),
            )
            for r in records
            if r.get("name")
        ]

    # ==================================================================
    # Internal mapping
    # ==================================================================

    @staticmethod
    def _map_record_to_paper(record: dict) -> PaperRead:
        """Convert a raw Neo4j record dict into a PaperRead model.

        Handles nullable fields, empty author lists, and optional
        venue/keyword relationships gracefully.

        Args:
            record: A dict returned by Neo4j ``execute_read`` with
                    keys matching the Cypher RETURN aliases.

        Returns:
            A fully populated ``PaperRead`` instance.
        """
        # --- Authors ---
        authors: list[AuthorRead] = []
        raw_authors = record.get("authors", [])
        if isinstance(raw_authors, list):
            for author_dict in raw_authors:
                if isinstance(author_dict, dict) and author_dict.get("name"):
                    authors.append(
                        AuthorRead(
                            name=str(author_dict["name"]),
                            openalex_id=(
                                str(author_dict["openalex_id"])
                                if author_dict.get("openalex_id")
                                else None
                            ),
                        )
                    )

        # --- Venue ---
        venue: VenueRead | None = None
        if record.get("venue_name"):
            venue = VenueRead(name=str(record["venue_name"]))

        # --- Keywords ---
        keywords_raw = record.get("keywords", [])
        keywords: list[str] = (
            [str(k) for k in keywords_raw if k]
            if isinstance(keywords_raw, list)
            else []
        )

        return PaperRead(
            doi=str(record["doi"]),
            title=str(record.get("title", "")),
            abstract=(
                str(record["abstract"]) if record.get("abstract") else None
            ),
            year=record.get("year"),  # type: ignore[arg-type]
            cited_by_count=int(record.get("cited_by_count", 0)),
            openalex_id=(
                str(record["openalex_id"])
                if record.get("openalex_id")
                else None
            ),
            publication_date=(
                str(record["publication_date"])
                if record.get("publication_date")
                else None
            ),
            source=str(record.get("source", "openalex")),
            authors=authors,
            venue=venue,
            keywords=keywords,
        )

"""Atomic paper retrieval service for ALRS v2 agentic workflow.

Orchestrates the full paper ingestion pipeline in a single call:
fetch metadata → store graph nodes → create relationships → embed → link.
Wraps the existing ``features.retrieval`` and ``features.embedding``
services to provide a higher-level API for the agent pipeline.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from core.paper_retrieval.models import FullPaper, PaperMetadata

if TYPE_CHECKING:
    from core.clients.openalex_client import OpenAlexService
    from core.db.neo4j_service import Neo4jService
    from core.logging.log_service import LogService
    from features.embedding.providers.base import EmbeddingProvider

logger = logging.getLogger(__name__)


class PaperRetrievalService:
    """Atomic retrieval service for the agentic research workflow.

    Fetches metadata, references, citations, authors, and venues in a
    single shot and stores them immediately in Neo4j. Optionally embeds
    the abstract and links the paper to a project.

    Dependencies are injected via constructor — no global state.
    """

    def __init__(
        self,
        neo4j: Neo4jService,
        openalex: OpenAlexService,
        embedding_provider: EmbeddingProvider | None = None,
        log_service: LogService | None = None,
        projects_dir: str = "projects",
    ) -> None:
        self._neo4j = neo4j
        self._openalex = openalex
        self._embedding_provider = embedding_provider
        self._log_service = log_service
        self._projects_dir = projects_dir

    async def retrieve_paper(
        self,
        doi: str,
        project_id: str | None = None,
    ) -> FullPaper:
        """Atomically retrieve, store, embed, and link a paper.

        Pipeline steps:
            1. Fetch metadata from OpenAlex
            2. Store paper node in Neo4j
            3. Create author nodes and AUTHORED_BY relationships
            4. Create venue node and PUBLISHED_IN relationship
            5. Create citation stubs and CITES relationships
            6. Embed abstract using embedding provider
            7. Store embedding on paper node
            8. If project_id provided, create HAS_PAPER relationship
            9. Save backup to projects/{project_id}/papers/
            10. Return FullPaper

        Args:
            doi: The paper DOI (e.g. '10.1145/3292500.3330919').
            project_id: Optional project UUID to link the paper to.

        Returns:
            FullPaper with metadata, embedding, and status.

        Raises:
            ValueError: If the paper is not found in OpenAlex.
        """
        # Check if paper already exists
        already_existed = await self._neo4j.paper_exists(doi)

        # 1. Fetch metadata from OpenAlex
        paper_data = await self._openalex.get_paper_by_doi(doi)
        if paper_data is None:
            raise ValueError(f"Paper not found in OpenAlex: {doi}")

        # 2. Store paper node in Neo4j
        await self._neo4j.create_paper(paper_data)

        # Extract author/venue info from OpenAlex response for relationship creation
        openalex_data = await self._openalex._request("GET", f"/works/doi:{doi}")

        # 3. Create author nodes and AUTHORED_BY relationships
        authors: list[str] = []
        authorships = openalex_data.get("authorships", [])
        if isinstance(authorships, list):
            for authorship in authorships:
                if not isinstance(authorship, dict):
                    continue
                author_info = authorship.get("author", {})
                if not isinstance(author_info, dict):
                    continue
                author_name = author_info.get("display_name")
                author_openalex_id = author_info.get("id")
                if author_name and author_openalex_id:
                    authors.append(str(author_name))
                    openalex_id_str = str(author_openalex_id).replace("https://openalex.org/", "")
                    institution = None
                    institutions = authorship.get("institutions", [])
                    if isinstance(institutions, list) and institutions:
                        inst = institutions[0]
                        if isinstance(inst, dict):
                            institution = inst.get("display_name")
                    await self._neo4j.execute_write(
                        """MERGE (a:Author {openalex_id: $openalex_id})
                           ON CREATE SET a.name = $name, a.institution = $institution
                           WITH a
                           MATCH (p:Paper {doi: $doi})
                           MERGE (a)-[:AUTHORED]->(p)""",
                        {
                            "openalex_id": openalex_id_str,
                            "name": str(author_name),
                            "institution": institution,
                            "doi": doi,
                        },
                    )

        # 4. Create venue node and PUBLISHED_IN relationship
        venue_name: str | None = None
        primary_location = openalex_data.get("primary_location", {})
        if isinstance(primary_location, dict):
            source = primary_location.get("source", {})
            if isinstance(source, dict) and source.get("display_name"):
                venue_name = str(source["display_name"])
                venue_openalex_id = str(source.get("id", "")).replace("https://openalex.org/", "")
                if venue_openalex_id:
                    await self._neo4j.execute_write(
                        """MERGE (v:Venue {openalex_id: $openalex_id})
                           ON CREATE SET v.name = $name
                           WITH v
                           MATCH (p:Paper {doi: $doi})
                           MERGE (p)-[:PUBLISHED_IN]->(v)""",
                        {
                            "openalex_id": venue_openalex_id,
                            "name": venue_name,
                            "doi": doi,
                        },
                    )

        # 5. Create citation stubs and CITES relationships
        referenced_dois: list[str] = []
        try:
            referenced_dois = await self._openalex.get_references(
                doi,
                max_results=20,
                openalex_id=paper_data.openalex_id,
            )
            for ref_doi in referenced_dois[:20]:
                await self._neo4j.ensure_stub_and_cite(doi, ref_doi)
        except Exception as e:
            logger.warning("Failed to fetch references for %s: %s", doi, e)

        # Fallback to direct DOI strings in referenced_works if get_references yielded nothing
        if not referenced_dois:
            referenced_works = openalex_data.get("referenced_works", [])
            if isinstance(referenced_works, list):
                for ref_url in referenced_works[:50]:
                    ref_str = str(ref_url).replace("https://openalex.org/", "")
                    if ref_str.startswith("10."):
                        referenced_dois.append(ref_str)
                        await self._neo4j.ensure_stub_and_cite(doi, ref_str)

        # Also get citing papers (limited)
        citing_dois: list[str] = []
        try:
            citing_dois = await self._openalex.get_citations(
                doi,
                max_results=20,
                openalex_id=paper_data.openalex_id,
            )
            for citing_doi in citing_dois[:20]:
                await self._neo4j.ensure_stub_and_cite(citing_doi, doi)
        except Exception as e:
            logger.warning("Failed to fetch citations for %s: %s", doi, e)

        # 6. Embed abstract using embedding provider
        embedding: list[float] | None = None
        if self._embedding_provider and paper_data.abstract:
            try:
                embedding = await self._embedding_provider.embed_document(
                    text=paper_data.abstract,
                    title=paper_data.title,
                )
                # 7. Store embedding on paper node
                await self._neo4j.store_paper_embedding(
                    doi=doi,
                    embedding=embedding,
                    model=self._embedding_provider.model_name,
                )
            except Exception as e:
                logger.warning("Failed to embed paper %s: %s", doi, e)

        # 8. If project_id provided, create HAS_PAPER relationship
        if project_id:
            try:
                await self._neo4j.add_paper_to_project(project_id, doi)
            except Exception as e:
                logger.warning("Failed to link paper %s to project %s: %s", doi, project_id, e)

        # Build metadata
        metadata = PaperMetadata(
            doi=doi,
            title=paper_data.title,
            abstract=paper_data.abstract,
            year=paper_data.year,
            authors=authors,
            venue=venue_name,
            references=referenced_dois,
            citations=citing_dois,
        )

        full_paper = FullPaper(
            metadata=metadata,
            embedding=embedding,
            already_existed=already_existed,
        )

        # 9. Save backup to projects/{project_id}/papers/
        if project_id:
            try:
                await self._save_paper_backup(project_id, full_paper)
            except Exception as e:
                logger.warning("Failed to save paper backup for %s: %s", doi, e)

        logger.info(
            "Paper retrieved: %s (existed=%s, embedded=%s, project=%s)",
            doi, already_existed, embedding is not None, project_id,
        )
        return full_paper

    async def bulk_retrieve(
        self,
        dois: list[str],
        project_id: str | None = None,
    ) -> list[FullPaper]:
        """Batch retrieval of multiple DOIs.

        Args:
            dois: List of DOIs to retrieve.
            project_id: Optional project UUID to link papers to.

        Returns:
            List of FullPaper results (failures are logged and skipped).
        """
        results: list[FullPaper] = []
        for doi in dois:
            try:
                paper = await self.retrieve_paper(doi, project_id=project_id)
                results.append(paper)
            except Exception as e:
                logger.warning("Failed to retrieve paper %s: %s", doi, e)
        return results

    async def _save_paper_backup(
        self,
        project_id: str,
        paper: FullPaper,
    ) -> None:
        """Save a paper's metadata as JSON backup in the project directory.

        Args:
            project_id: UUID of the project.
            paper: The FullPaper to save.
        """
        backup_dir = Path(self._projects_dir) / project_id / "papers"
        backup_dir.mkdir(parents=True, exist_ok=True)

        # Sanitize DOI for filename
        safe_doi = paper.metadata.doi.replace("/", "_").replace(":", "_")
        backup_path = backup_dir / f"{safe_doi}.json"

        # Exclude embedding from backup (too large)
        backup_data = paper.model_dump(exclude={"embedding"})
        backup_path.write_text(json.dumps(backup_data, indent=2, default=str))
        logger.debug("Paper backup saved: %s", backup_path)

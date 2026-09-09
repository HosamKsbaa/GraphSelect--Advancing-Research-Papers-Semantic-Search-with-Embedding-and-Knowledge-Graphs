"""Continuous Ingestion service coordinating resolution, embedding, and graph wiring.

Complies with Constitution v2.2.1:
- C5: Auditability with run_id and created_in_stage tracking.
- C8: Pure Neo4j SSOT.
- C9: Granular sub-routines under 25 lines (SRP / SLAP).
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from core.errors.enhancement_errors import TitleConfirmationRequiredError, UnresolvableIdentifierError
from features.ingestion.graph_wiring import wire_paper_bidirectional
from features.ingestion.identifier_extractor import (
    clean_punctuation,
    match_title_candidate,
    normalize_identifier_input,
)
from features.ingestion.models import (
    ConfirmTitleIngestionInput,
    ConfirmTitleIngestionOutput,
    IdentifierType,
    IngestUserPaperInput,
    IngestUserPaperOutput,
    IngestionSource,
    TitleConfirmationChip,
    UserIngestedPaper,
)
from features.ingestion.relevance_gate import evaluate_paper_for_project

logger = logging.getLogger(__name__)


class IngestionService:
    """Service orchestrating continuous literature ingestion and bidirectional graph wiring."""

    def __init__(
        self,
        neo4j_service: Any,
        openalex_service: Any,
        embedding_service: Any = None,
        log_service: Any = None,
    ) -> None:
        self.neo4j = neo4j_service
        self.openalex = openalex_service
        self.embedding_service = embedding_service
        self.log_service = log_service

    async def ingest_paper(self, input_data: IngestUserPaperInput) -> IngestUserPaperOutput:
        """Resolve, embed, gate, and persist paper from user chat mention."""
        id_type, normalized_id = normalize_identifier_input(input_data.identifier or input_data.raw_input or "")
        if id_type == IdentifierType.TITLE and not input_data.is_title_confirmed:
            return await self._handle_unconfirmed_title(normalized_id, input_data)

        raw_meta = await self._fetch_metadata(normalized_id, id_type)
        if raw_meta is None:
            raise UnresolvableIdentifierError(normalized_id)

        user_paper = await self._build_user_paper(raw_meta, normalized_id, input_data)
        can_expand, max_sim = await evaluate_paper_for_project(
            self.neo4j, input_data.project_id, user_paper.embedding
        )
        user_paper.can_expand_deeply = can_expand

        citing_dois = await self._resolve_inbound_citations(user_paper.doi, input_data.project_id)
        links_count = await wire_paper_bidirectional(
            self.neo4j, user_paper, input_data.project_id, input_data.run_id, input_data.stage_index, citing_dois
        )
        await self._notify_board_on_ingestion(user_paper, input_data.project_id)
        return self._build_ingest_output(user_paper, links_count, max_sim)

    async def _handle_unconfirmed_title(
        self, title_text: str, input_data: IngestUserPaperInput
    ) -> IngestUserPaperOutput:
        """Evaluate free-text title candidate and produce confirmation chip or fail."""
        chip = await match_title_candidate(title_text, self.openalex)
        if chip is None:
            raise TitleConfirmationRequiredError(title_text)
        return IngestUserPaperOutput(
            status="pending_confirmation",
            title=chip.resolved_title,
            doi=chip.resolved_doi,
            openalex_id=chip.resolved_openalex_id,
            can_expand_deeply=False,
            max_rq_relevance=0.0,
            message="Title match found; awaiting user confirmation.",
            confirmation_chip=chip,
        )

    async def _fetch_metadata(self, identifier: str, id_type: IdentifierType) -> dict[str, Any] | None:
        """Fetch publication metadata from OpenAlex based on identifier type."""
        if id_type == IdentifierType.DOI or identifier.startswith("10."):
            return await self._fetch_by_doi(identifier)
        if id_type == IdentifierType.ARXIV:
            return await self._fetch_by_arxiv(identifier)
        if id_type == IdentifierType.TITLE:
            return await self._fetch_by_title_search(identifier)
        return await self._fetch_by_doi(identifier)

    async def _fetch_by_doi(self, doi: str) -> dict[str, Any] | None:
        """Fetch paper metadata by DOI from OpenAlex."""
        clean_doi = clean_punctuation(doi).lower()
        if hasattr(self.openalex, "batch_get_rich_papers"):
            rich = await self.openalex.batch_get_rich_papers([clean_doi])
            if rich and isinstance(rich, list) and isinstance(rich[0], dict):
                return dict(rich[0])
        if hasattr(self.openalex, "get_paper_by_doi"):
            paper = await self.openalex.get_paper_by_doi(clean_doi)
            if paper:
                return self._paper_create_to_dict(paper)
        return None

    async def _fetch_by_arxiv(self, arxiv_id: str) -> dict[str, Any] | None:
        """Search OpenAlex for an arXiv identifier."""
        if hasattr(self.openalex, "search_by_title"):
            results = await self.openalex.search_by_title(f"arxiv:{arxiv_id}", max_results=1)
            if results and getattr(results[0], "doi", None):
                return await self._fetch_by_doi(results[0].doi)
        return None

    async def _fetch_by_title_search(self, title: str) -> dict[str, Any] | None:
        """Search OpenAlex by title string."""
        if hasattr(self.openalex, "search_by_title"):
            results = await self.openalex.search_by_title(title, max_results=1)
            if results and getattr(results[0], "doi", None):
                return await self._fetch_by_doi(results[0].doi)
        return None

    def _paper_create_to_dict(self, paper: Any) -> dict[str, Any]:
        """Convert a PaperCreate instance into a standard dictionary."""
        return {
            "doi": getattr(paper, "doi", ""),
            "title": getattr(paper, "title", ""),
            "year": getattr(paper, "year", None),
            "abstract": getattr(paper, "abstract", None),
            "openalex_id": getattr(paper, "openalex_id", None),
            "is_retracted": getattr(paper, "is_retracted", False),
            "referenced_works": getattr(paper, "referenced_works", None) or [],
            "authors": [getattr(a, "name", str(a)) for a in (getattr(paper, "authors", None) or [])],
        }

    async def _build_user_paper(
        self, raw_meta: dict[str, Any], raw_id: str, input_data: IngestUserPaperInput
    ) -> UserIngestedPaper:
        """Construct UserIngestedPaper model with generated embedding."""
        doi = raw_meta.get("doi") or raw_id
        title = raw_meta.get("title") or f"Paper {doi}"
        abstract = raw_meta.get("abstract") or ""
        embedding = await self._generate_embedding(abstract, title)
        ref_dois = self._extract_clean_references(raw_meta.get("referenced_works") or [])
        is_retracted = bool(raw_meta.get("is_retracted", False))
        return UserIngestedPaper(
            raw_identifier=raw_id,
            doi=doi,
            openalex_id=raw_meta.get("openalex_id"),
            title=title,
            authors=raw_meta.get("authors") or [],
            year=raw_meta.get("year"),
            abstract=abstract,
            embedding=embedding,
            ingestion_source=IngestionSource.USER_CONTEXT,
            referenced_dois=ref_dois,
            is_retracted=is_retracted,
        )

    async def _generate_embedding(self, abstract: str, title: str) -> list[float] | None:
        """Generate normalized 768d document embedding vector."""
        if not self.embedding_service:
            return None
        text_payload = f"search_document: {title}. {abstract}".strip()
        try:
            if hasattr(self.embedding_service, "embed_document"):
                emb = await self.embedding_service.embed_document(text=text_payload, title=title)
                return [float(x) for x in emb] if isinstance(emb, list) else None
            if hasattr(self.embedding_service, "embed_paper"):
                emb = await self.embedding_service.embed_paper(text_payload)
                return [float(x) for x in emb] if isinstance(emb, list) else None
        except Exception as exc:
            logger.warning("Embedding generation failed: %s", exc)
        return None

    def _extract_clean_references(self, raw_refs: list[Any] | None) -> list[str]:
        """Normalize reference identifiers to clean DOIs or short IDs."""
        if not raw_refs:
            return []
        clean_refs: list[str] = []
        for ref in raw_refs:
            if not ref:
                continue
            r_str = str(ref).replace("https://doi.org/", "").replace("https://openalex.org/", "").strip()
            if r_str and r_str not in clean_refs:
                clean_refs.append(r_str)
        return clean_refs

    async def _resolve_inbound_citations(self, doi: str, project_id: str | None) -> list[str]:
        """Fetch papers citing the target paper and intersect with library."""
        if not hasattr(self.openalex, "get_citations"):
            return []
        try:
            citing_dois = await self.openalex.get_citations(doi, max_results=50)
            return [d.replace("https://doi.org/", "").strip() for d in citing_dois if d]
        except Exception as exc:
            logger.warning("Failed fetching citing papers for %s: %s", doi, exc)
            return []

    async def _notify_board_on_ingestion(self, paper: UserIngestedPaper, project_id: str) -> None:
        """Post ingestion milestone and optional retraction alert to message board."""
        query = """
        MERGE (proj:Project {project_id: $project_id})
        CREATE (m:BoardMessage {
            id: randomUUID(),
            project_id: $project_id,
            tag: $tag,
            content: $content,
            doi: $doi,
            created_at: datetime()
        })
        MERGE (proj)-[:HAS_MESSAGE]->(m)
        """
        tag = "warning" if paper.is_retracted else "insight"
        content = f"Paper '{paper.title}' ({paper.doi}) ingested."
        if paper.is_retracted:
            content += " ⚠️ RETRACTION NOTICE: Paper is flagged as retracted."
        try:
            await self.neo4j.execute_write(query, {"project_id": project_id, "tag": tag, "content": content, "doi": paper.doi})
        except Exception as exc:
            logger.warning("Board notification failed for %s: %s", paper.doi, exc)

    def _build_ingest_output(
        self, paper: UserIngestedPaper, links_count: int, max_sim: float
    ) -> IngestUserPaperOutput:
        """Construct IngestUserPaperOutput response model."""
        return IngestUserPaperOutput(
            status="success",
            doi=paper.doi,
            openalex_id=paper.openalex_id,
            title=paper.title,
            citation_links_created=links_count,
            can_expand_deeply=paper.can_expand_deeply,
            max_rq_relevance=round(max_sim, 4),
            message=f"Paper {paper.doi} successfully ingested with {links_count} citation links.",
        )

    def _build_dismissed_output(
        self, input_data: ConfirmTitleIngestionInput
    ) -> ConfirmTitleIngestionOutput:
        """Construct response when confirmation chip is dismissed."""
        return ConfirmTitleIngestionOutput(
            status="dismissed",
            doi=input_data.resolved_doi,
            openalex_id=input_data.resolved_openalex_id,
            title=input_data.resolved_title,
            citation_links_created=0,
            can_expand_deeply=False,
        )

    async def _execute_confirmed_ingestion(
        self, input_data: ConfirmTitleIngestionInput
    ) -> ConfirmTitleIngestionOutput:
        """Execute paper ingestion for confirmed title chip."""
        target_id = input_data.resolved_doi or input_data.resolved_openalex_id
        ingest_in = IngestUserPaperInput(
            identifier=target_id,
            project_id=input_data.project_id,
            run_id=input_data.run_id,
            is_title_confirmed=True,
            stage_index=input_data.stage_index,
        )
        res = await self.ingest_paper(ingest_in)
        return ConfirmTitleIngestionOutput(
            status="confirmed",
            doi=res.doi,
            openalex_id=res.openalex_id or input_data.resolved_openalex_id,
            title=res.title or input_data.resolved_title,
            citation_links_created=res.citation_links_created,
            can_expand_deeply=res.can_expand_deeply,
        )

    async def confirm_title_chip(
        self, input_data: ConfirmTitleIngestionInput
    ) -> ConfirmTitleIngestionOutput:
        """Handle title confirmation chip action (confirm or dismiss)."""
        if not input_data.confirmed:
            return self._build_dismissed_output(input_data)
        return await self._execute_confirmed_ingestion(input_data)

    def dispatch_background_ingestion(
        self, input_data: IngestUserPaperInput
    ) -> asyncio.Task[IngestUserPaperOutput]:
        """Dispatch non-blocking paper ingestion task in event loop."""
        return asyncio.create_task(self.ingest_paper(input_data))

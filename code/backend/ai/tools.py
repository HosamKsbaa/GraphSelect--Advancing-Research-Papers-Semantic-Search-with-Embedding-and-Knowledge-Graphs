"""Plain typed Python tools for the ALRS Research Agent (M1).

Wraps `engines.openalex`, `engines.alrs`, `engines.collections`, and
`engines.citations` public interfaces.
"""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from langchain_core.tools import BaseTool, StructuredTool
from pydantic import BaseModel, ConfigDict, Field

from engines.alrs import AlrsDiscoverRequest, AlrsDiscoverResult, AlrsEngine
from engines.budget import SpendingLedger
from engines.citations import (
    AnalysisFinding,
    PaperSourceReference,
    available_sources,
    format_apa,
    format_bibtex,
    validate_sources,
)
from engines.collections import (
    InMemoryCollectionStore,
    PaperCollection,
    build_paper_collection,
    collection_statistics,
)
from engines.openalex import OpenAlexWork, to_paper_create


class OpenAlexSearchProvider(Protocol):
    async def search_works(
        self, query: str, *, per_page: int | None = None
    ) -> list[OpenAlexWork]: ...


class PaperCandidateSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    doi: str
    title: str
    year: int | None = None
    citation_count: int = 0
    has_abstract: bool = False


class SearchPapersOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str
    candidates: list[PaperCandidateSummary]


class RankedPaperSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    doi: str | None = None
    title: str
    year: int | None = None
    depth: int
    similarity_score: float | None = None
    pagerank_score: float
    hybrid_score: float | None = None
    can_expand: bool = False


class DiscoverLiteratureOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    collection_id: str
    collection_hash: str
    seed_doi: str
    total_papers: int
    ranked_papers: list[RankedPaperSummary]
    reasons: list[str] = Field(default_factory=list)


class CollectionPaperContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entry_id: str
    doi: str | None = None
    title: str
    year: int | None = None
    abstract: str | None = None
    available_sources: list[PaperSourceReference]


class GetCollectionOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    collection_id: str
    collection_hash: str
    title: str
    research_questions: list[str]
    total_papers: int
    available_abstracts: int
    missing_abstracts: int
    papers: list[CollectionPaperContext]


class WriteReviewOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    collection_id: str
    markdown_review: str
    cited_dois: list[str]
    apa_references: list[str]
    bibtex_entries: list[str]
    verified_findings_count: int


class AgentToolRuntime:
    """Holds injected engine dependencies for the research agent tools."""

    def __init__(
        self,
        openalex: OpenAlexSearchProvider,
        alrs_engine: AlrsEngine,
        collection_store: InMemoryCollectionStore | None = None,
        spending_ledger: SpendingLedger | None = None,
    ) -> None:
        self.openalex = openalex
        self.alrs_engine = alrs_engine
        self.collection_store = collection_store or InMemoryCollectionStore()
        self.spending_ledger = spending_ledger
        self._discover_results: dict[UUID, AlrsDiscoverResult] = {}

    async def search_papers(self, query: str, limit: int = 5) -> SearchPapersOutput:
        """Search OpenAlex for candidate seed papers with DOIs."""
        receipt = (
            self.spending_ledger.reserve("openalex")
            if self.spending_ledger is not None
            else None
        )
        try:
            works = await self.openalex.search_works(query, per_page=max(1, min(limit, 10)))
        except Exception:
            if receipt is not None and self.spending_ledger is not None:
                self.spending_ledger.fail(receipt.receipt_id, reason="search_papers_failed")
            raise
        if receipt is not None and self.spending_ledger is not None:
            self.spending_ledger.complete(receipt.receipt_id)
        candidates: list[PaperCandidateSummary] = []
        for work in works:
            paper = to_paper_create(work)
            if paper is None or not paper.doi:
                continue
            candidates.append(
                PaperCandidateSummary(
                    doi=paper.doi,
                    title=paper.title,
                    year=paper.year,
                    citation_count=paper.citation_count or 0,
                    has_abstract=bool(paper.abstract and paper.abstract.strip()),
                )
            )
        return SearchPapersOutput(query=query, candidates=candidates[:limit])

    async def discover_literature(
        self,
        seed_doi: str,
        research_questions: list[str],
        max_depth: int = 2,
        similarity_threshold: float = 0.3,
    ) -> DiscoverLiteratureOutput:
        """Run GraphSelect citation discovery from a seed DOI and save a PaperCollection."""
        request = AlrsDiscoverRequest(
            seed_doi=seed_doi,
            research_questions=research_questions,
            max_depth=max(1, min(max_depth, 3)),
            similarity_threshold=similarity_threshold,
        )
        receipt = (
            self.spending_ledger.reserve("gemini_embedding")
            if self.spending_ledger is not None
            else None
        )
        try:
            result = await self.alrs_engine.discover(request)
        except Exception:
            if receipt is not None and self.spending_ledger is not None:
                self.spending_ledger.fail(receipt.receipt_id, reason="discover_failed")
            raise
        if receipt is not None and self.spending_ledger is not None:
            self.spending_ledger.complete(receipt.receipt_id)
        papers = [node.paper for node in result.nodes]
        collection: PaperCollection = build_paper_collection(
            title=f"GraphSelect Discovery: {result.seed_doi}",
            papers=papers,
            research_questions=result.research_questions,
            citation_edges=result.edges,
        )
        self.collection_store.save(collection)
        self._discover_results[collection.collection_id] = result

        ranked_summaries = [
            RankedPaperSummary(
                doi=node.paper.doi,
                title=node.paper.title,
                year=node.paper.year,
                depth=node.depth,
                similarity_score=node.ranking.similarity_score,
                pagerank_score=node.ranking.pagerank_score,
                hybrid_score=node.ranking.hybrid_score,
                can_expand=node.ranking.can_expand,
            )
            for node in result.nodes
        ]
        return DiscoverLiteratureOutput(
            collection_id=str(collection.collection_id),
            collection_hash=collection.collection_hash,
            seed_doi=result.seed_doi,
            total_papers=len(ranked_summaries),
            ranked_papers=ranked_summaries,
            reasons=result.reasons,
        )

    def get_collection(self, collection_id: str) -> GetCollectionOutput:
        """Return saved collection papers and exact sentence spans for verified quoting."""
        cid = UUID(collection_id)
        collection = self.collection_store.get(cid)
        stats = collection_statistics(collection)
        papers_ctx = [
            CollectionPaperContext(
                entry_id=str(entry.entry_id),
                doi=entry.paper.doi,
                title=entry.paper.title,
                year=entry.paper.year,
                abstract=entry.paper.abstract,
                available_sources=available_sources(collection.collection_id, entry),
            )
            for entry in collection.entries
        ]
        return GetCollectionOutput(
            collection_id=str(collection.collection_id),
            collection_hash=collection.collection_hash,
            title=collection.title,
            research_questions=collection.research_questions,
            total_papers=stats.papers,
            available_abstracts=stats.available_abstracts,
            missing_abstracts=stats.missing_abstracts,
            papers=papers_ctx,
        )

    def write_review(
        self,
        collection_id: str,
        findings: list[AnalysisFinding],
    ) -> WriteReviewOutput:
        """Verify findings against saved abstracts and assemble a cited Markdown review."""
        cid = UUID(collection_id)
        collection = self.collection_store.get(cid)
        verified = validate_sources(collection, findings)

        entries_by_id = {entry.entry_id: entry for entry in collection.entries}
        cited_entries = []
        seen_entry_ids: set[UUID] = set()

        sections: list[str] = [f"# Literature Review: {collection.title}\n"]
        for idx, item in enumerate(verified, start=1):
            citations_inline: list[str] = []
            quotes_block: list[str] = []
            for source in item.sources:
                entry = entries_by_id[source.entry_id]
                if entry.entry_id not in seen_entry_ids:
                    seen_entry_ids.add(entry.entry_id)
                    cited_entries.append(entry)
                cite_tag = f"[{entry.paper.doi or entry.paper.paper_key}]"
                if cite_tag not in citations_inline:
                    citations_inline.append(cite_tag)
                quotes_block.append(f'> "{source.quote}" — {cite_tag}')
            cite_str = " ".join(citations_inline)
            sections.append(f"## {idx}. {item.question}\n\n{item.finding} {cite_str}\n")
            if quotes_block:
                sections.append("\n".join(quotes_block) + "\n")

        apa_list = [format_apa(entry.paper) for entry in cited_entries]
        bibtex_list = [format_bibtex(entry.paper) for entry in cited_entries]
        cited_dois = [entry.paper.doi for entry in cited_entries if entry.paper.doi]

        if apa_list:
            sections.append("## References\n\n" + "\n".join(f"- {ref}" for ref in apa_list))

        return WriteReviewOutput(
            collection_id=str(collection.collection_id),
            markdown_review="\n".join(sections).strip(),
            cited_dois=cited_dois,
            apa_references=apa_list,
            bibtex_entries=bibtex_list,
            verified_findings_count=len(verified),
        )

    def verify_citations(
        self,
        collection_id: str,
        review_output: WriteReviewOutput,
    ) -> object:
        """Verify inline `[DOI]` tags in `review_output` against the saved collection."""
        from .verification import verify_review_citations

        cid = UUID(collection_id)
        collection = self.collection_store.get(cid)
        return verify_review_citations(collection, review_output)

    def build_langchain_tools(self) -> list[BaseTool]:
        """Return the 4 research agent tools as LangChain StructuredTools."""
        return [
            StructuredTool.from_function(
                coroutine=self.search_papers,
                name="search_papers",
                description="Search OpenAlex for candidate seed papers by topic query.",
            ),
            StructuredTool.from_function(
                coroutine=self.discover_literature,
                name="discover_literature",
                description="Run GraphSelect citation discovery from a seed DOI and save a collection.",
            ),
            StructuredTool.from_function(
                func=self.get_collection,
                name="get_collection",
                description="Retrieve saved collection papers and exact sentence spans for quoting.",
            ),
            StructuredTool.from_function(
                func=self.write_review,
                name="write_review",
                description="Verify findings against saved abstracts and format a cited literature review.",
            ),
        ]

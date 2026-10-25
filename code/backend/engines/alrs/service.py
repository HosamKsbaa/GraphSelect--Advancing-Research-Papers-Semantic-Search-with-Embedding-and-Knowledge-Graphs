"""Bounded BFS citation discovery and ranking orchestrator (`AlrsEngine`).

Coordinates `engines.openalex`, `engines.embeddings`, `engines.jev`, and
`engines.alrs` ranking math without any dependency on `api` or `ai`.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from engines.embeddings import document_text, query_text
from engines.errors import ProviderError
from engines.jev import (
    EpistemicGraphSelectConfig,
    JevDecisionClient,
    evaluate_candidates_with_jev,
)
from engines.openalex import OpenAlexWork, normalize_doi, to_paper_create
from engines.papers import CitationEdge, Paper

from .epistemic_pagerank import calculate_epistemic_rankings
from .ranking import PaperRanking, SimilarityObservation, calculate_rankings


class EmbeddingProvider(Protocol):
    async def embed_text(self, text: str) -> list[float]: ...


class OpenAlexProvider(Protocol):
    async def get_work_by_doi(self, doi: str) -> OpenAlexWork | None: ...

    async def get_works_batch(
        self, openalex_ids: list[str]
    ) -> tuple[list[OpenAlexWork], list[str], list[str]]: ...


def cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0
    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    return max(-1.0, min(1.0, dot))


class AlrsDiscoverRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    seed_doi: str = Field(min_length=6, max_length=512)
    research_questions: list[str] = Field(min_length=1, max_length=6)
    similarity_threshold: float = Field(default=0.3, ge=0.0, le=1.0)
    max_depth: int = Field(default=2, ge=1, le=5)
    max_neighbors_per_level: int = Field(default=25, ge=1, le=100)
    similarity_weight: float = Field(default=0.7, ge=0.0, le=1.0)
    density_gated_pagerank: bool = True


class DiscoveredPaperNode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    paper: Paper
    work: OpenAlexWork
    depth: int
    parent_doi: str | None = None
    ranking: PaperRanking


class AlrsDiscoverResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    seed_doi: str
    research_questions: list[str]
    nodes: list[DiscoveredPaperNode]
    edges: list[CitationEdge]
    similarities: list[SimilarityObservation]
    total_papers_processed: int
    reasons: list[str] = Field(default_factory=list)


ProgressHook = Callable[[str, str, int, int], None]


class AlrsEngine:
    """Deterministic GraphSelect discovery and ranking engine."""

    def __init__(
        self,
        openalex: OpenAlexProvider,
        embeddings: EmbeddingProvider,
        jev_client: JevDecisionClient | None = None,
        epistemic_config: EpistemicGraphSelectConfig | None = None,
    ) -> None:
        self.openalex = openalex
        self.embeddings = embeddings
        self.jev_client = jev_client
        self.epistemic_config = epistemic_config or EpistemicGraphSelectConfig()

    async def discover(
        self,
        request: AlrsDiscoverRequest,
        on_progress: ProgressHook | None = None,
    ) -> AlrsDiscoverResult:
        seed_doi = normalize_doi(request.seed_doi)
        if on_progress:
            on_progress("embedding_questions", "Embedding research questions...", 0, request.max_depth)

        question_vectors: dict[str, list[float]] = {}
        for question in request.research_questions:
            question_vectors[question] = await self.embeddings.embed_text(query_text(question))

        if on_progress:
            on_progress("processing_seed", f"Fetching seed paper {seed_doi}...", 0, request.max_depth)

        seed_work = await self.openalex.get_work_by_doi(seed_doi)
        if seed_work is None:
            raise ProviderError("seed_not_found", f"Seed paper '{seed_doi}' was not found in OpenAlex.")
        seed_paper = to_paper_create(seed_work)
        if seed_paper is None:
            raise ProviderError("seed_invalid", f"Seed paper '{seed_doi}' has no usable metadata.")

        papers_by_key: dict[str, Paper] = {seed_paper.paper_key: seed_paper}
        works_by_key: dict[str, OpenAlexWork] = {seed_paper.paper_key: seed_work}
        depth_by_key: dict[str, int] = {seed_paper.paper_key: 0}
        parent_by_key: dict[str, str | None] = {seed_paper.paper_key: None}
        edges: list[CitationEdge] = []
        similarities: list[SimilarityObservation] = []
        reasons: list[str] = []
        total_processed = 0

        async def score_paper(paper: Paper) -> float:
            nonlocal total_processed
            total_processed += 1
            if not paper.abstract or not paper.abstract.strip():
                reasons.append("missing_abstracts_unranked")
                return -1.0
            vec = await self.embeddings.embed_text(document_text(paper.title, paper.abstract))
            best_sim = -1.0
            for question, q_vec in question_vectors.items():
                sim = cosine_similarity(q_vec, vec)
                best_sim = max(best_sim, sim)
                similarities.append(
                    SimilarityObservation(
                        doi=paper.doi,
                        corpus_id=paper.corpus_id,
                        question=question,
                        similarity_score=sim,
                    )
                )
            return best_sim

        await score_paper(seed_paper)
        current_frontier: list[str] = [seed_paper.paper_key]

        for depth in range(1, request.max_depth + 1):
            if not current_frontier:
                break
            if on_progress:
                on_progress(
                    "exploring_level",
                    f"Exploring citation depth {depth}...",
                    depth,
                    request.max_depth,
                )
            next_frontier: list[str] = []
            for parent_key in current_frontier:
                parent_work = works_by_key[parent_key]
                ref_ids = list(dict.fromkeys(parent_work.referenced_works))[
                    : request.max_neighbors_per_level
                ]
                if not ref_ids:
                    continue
                batch_works, omitted, _ = await self.openalex.get_works_batch(ref_ids)
                if omitted:
                    reasons.append("omitted_works_without_doi")
                for ref_work in batch_works:
                    ref_paper = to_paper_create(ref_work)
                    if ref_paper is None:
                        continue
                    edges.append(
                        CitationEdge(
                            source_doi=papers_by_key[parent_key].doi,
                            source_corpus_id=papers_by_key[parent_key].corpus_id,
                            target_doi=ref_paper.doi,
                            target_corpus_id=ref_paper.corpus_id,
                        )
                    )
                    if ref_paper.paper_key in papers_by_key:
                        continue
                    best_sim = await score_paper(ref_paper)
                    if best_sim >= request.similarity_threshold:
                        papers_by_key[ref_paper.paper_key] = ref_paper
                        works_by_key[ref_paper.paper_key] = ref_work
                        depth_by_key[ref_paper.paper_key] = depth
                        parent_by_key[ref_paper.paper_key] = parent_key
                        next_frontier.append(ref_paper.paper_key)
            current_frontier = next_frontier

        if on_progress:
            on_progress(
                "calculating_pagerank",
                "Calculating GraphSelect rankings...",
                request.max_depth,
                request.max_depth,
            )

        dois = list(papers_by_key.keys())
        if self.jev_client is not None and self.jev_client.configured:
            best_map: dict[str, float] = {}
            for obs in similarities:
                best_map[obs.paper_key] = max(best_map.get(obs.paper_key, -1.0), obs.similarity_score)
            jev_report = await evaluate_candidates_with_jev(
                list(papers_by_key.values()),
                request.research_questions,
                best_map,
                self.jev_client,
                self.epistemic_config,
            )
            reasons.extend(jev_report.reasons)
            rankings = calculate_epistemic_rankings(
                dois=dois,
                edges=edges,
                similarities=similarities,
                minimum_threshold=request.similarity_threshold,
                similarity_weight=request.similarity_weight,
                assessments=jev_report.assessments,
                expanded_count=max(1, len(dois)),
                density_gated=request.density_gated_pagerank,
            )
        else:
            rankings = calculate_rankings(
                dois=dois,
                edges=edges,
                similarities=similarities,
                minimum_threshold=request.similarity_threshold,
                similarity_weight=request.similarity_weight,
                density_gated=request.density_gated_pagerank,
            )

        ordered_rankings = sorted(
            rankings,
            key=lambda r: (-(r.hybrid_score if r.hybrid_score is not None else -1.0), r.paper_key),
        )
        nodes = [
            DiscoveredPaperNode(
                paper=papers_by_key[r.paper_key],
                work=works_by_key[r.paper_key],
                depth=depth_by_key[r.paper_key],
                parent_doi=parent_by_key[r.paper_key],
                ranking=r,
            )
            for r in ordered_rankings
        ]
        if on_progress:
            on_progress("completed", "Search completed!", request.max_depth, request.max_depth)

        return AlrsDiscoverResult(
            seed_doi=seed_doi,
            research_questions=list(request.research_questions),
            nodes=nodes,
            edges=edges,
            similarities=similarities,
            total_papers_processed=total_processed,
            reasons=list(dict.fromkeys(reasons)),
        )

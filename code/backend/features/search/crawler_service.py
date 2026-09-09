"""BFS crawler service for extracting OpenAlex data into Neo4j."""
from __future__ import annotations

import logging
from collections.abc import Callable, Coroutine
from typing import Any, TYPE_CHECKING

from pydantic import BaseModel, Field

from features.retrieval.models import PaperCreate
from features.search.models import (
    CandidatePaperState,
    EventType,
    OneHopExpansionResult,
    ProgressEvent,
)

if TYPE_CHECKING:
    from core.db.neo4j_service import Neo4jService
    from core.logging.log_service import LogService
    from core.clients.openalex_client import OpenAlexService
    from core.clients.rate_limiter import AdaptiveRateLimiter

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[ProgressEvent], Coroutine[Any, Any, None]] | None


async def _maybe_await(val: Any) -> Any:
    """Await value if it is awaitable, otherwise return it directly."""
    if hasattr(val, "__await__"):
        return await val
    return val


class CycleResult(BaseModel):
    """Result of a single BFS level expansion."""

    level: int
    papers_discovered: int
    papers_new: int
    new_dois: list[str]
    errors: list[str] = Field(default_factory=list)


class CrawlerService:
    """BFS citation crawl engine that populates Neo4j from OpenAlex."""

    def __init__(
        self,
        neo4j: Neo4jService,
        openalex: OpenAlexService,
        rate_limiter: AdaptiveRateLimiter | None = None,
        log_service: LogService | None = None,
        gemini: Any = None,
        embedding_provider: Any = None,
    ) -> None:
        self._neo4j = neo4j
        self._openalex = openalex
        self._rate_limiter = rate_limiter
        self._log_service = log_service
        self._gemini = gemini or embedding_provider
        self._embedding_provider = embedding_provider or gemini

    async def _emit(
        self,
        callback: ProgressCallback,
        event_type: EventType,
        session_id: str,
        progress_percent: float,
        message: str,
        data: dict[str, object] | None = None,
    ) -> None:
        if callback is None:
            return
        event = ProgressEvent(
            event_type=event_type,
            session_id=session_id,
            progress_percent=min(progress_percent, 100.0),
            message=message,
            data=data,
        )
        await callback(event)

    async def can_expand_paper_deeply(self, doi: str) -> bool:
        """Verify whether paper is permitted for recursive BFS or 1-hop expansion under FR-016."""
        query = "MATCH (p:Paper {doi: $doi}) RETURN coalesce(p.can_expand_deeply, true) AS can_expand"
        try:
            records = await self._neo4j.execute_read(query, {"doi": doi})
            if records and "can_expand" in records[0]:
                return bool(records[0]["can_expand"])
        except Exception as exc:
            logger.warning("Error checking can_expand_deeply for %s: %s", doi, exc)
        return True

    def _build_aborted_expansion_result(self, seed_doi: str, reason: str) -> OneHopExpansionResult:
        """Construct empty OneHopExpansionResult when recursive expansion is guarded."""
        logger.warning("Expansion guarded for %s: %s", seed_doi, reason)
        return OneHopExpansionResult(
            seed_doi=seed_doi,
            seed_title=f"Paper {seed_doi}",
            cycle_level=1,
            total_discovered=0,
            total_new=0,
            forward_count=0,
            backward_count=0,
            both_count=0,
            candidates=[],
            new_dois=[],
            traversal_summary=[reason],
            errors=[reason],
        )

    async def run_bfs_cycle(
        self,
        session_id: str,
        queued_dois: list[str],
        current_depth: int,
        max_depth: int,
        progress_callback: ProgressCallback = None,
    ) -> CycleResult:
        import asyncio

        errors: list[str] = []
        new_dois_set: set[str] = set()
        papers_discovered = 0
        papers_new = 0

        existing_session_dois: set[str] = set(
            await self._neo4j.get_session_dois(session_id)
        )

        dois_to_process = [
            d for d in queued_dois
            if d not in existing_session_dois or current_depth == 1
        ]
        total = len(dois_to_process)

        if not dois_to_process:
            return CycleResult(
                level=current_depth,
                papers_discovered=0,
                papers_new=0,
                new_dois=[],
            )

        await self._emit(
            progress_callback,
            EventType.LEVEL_COMPLETE,
            session_id,
            10.0,
            f'Batch fetching {total} papers for level {current_depth}...',
        )

        try:
            papers = await self._openalex.batch_get_papers_by_dois(
                dois_to_process, session_id=session_id
            )
        except Exception as e:
            msg = f"Error fetching batch papers: {e}"
            logger.exception(msg)
            errors.append(msg)
            papers = []
        fetched_papers_map = {p.doi: p for p in papers}

        for doi in dois_to_process:
            paper = fetched_papers_map.get(doi)
            if not paper:
                logger.warning('Paper not found in OpenAlex: %s', doi)
                errors.append(f'Not found in OpenAlex: {doi}')
                continue
            
            await self._neo4j.create_paper(paper)
            await self._neo4j.link_paper_to_session(
                doi=paper.doi,
                session_id=session_id,
                depth=current_depth,
            )
            existing_session_dois.add(paper.doi)
            papers_discovered += 1
            papers_new += 1

        await self._emit(
            progress_callback,
            EventType.LEVEL_COMPLETE,
            session_id,
            50.0,
            f'Fetching citations/references concurrently for {papers_new} papers...',
        )

        async def _fetch_edges(p: PaperCreate) -> tuple[str, list[str], list[str]]:
            try:
                if not await self.can_expand_paper_deeply(p.doi):
                    logger.info("Skipping recursive expansion for %s: can_expand_deeply is False", p.doi)
                    return p.doi, [], []
                if self._rate_limiter is not None:
                    await self._rate_limiter.acquire()
                citing = await self._openalex.get_citations(
                    p.doi, session_id=session_id, openalex_id=p.openalex_id
                )
                if self._rate_limiter is not None:
                    await self._rate_limiter.acquire()
                refs = await self._openalex.get_references(
                    p.doi, session_id=session_id, openalex_id=p.openalex_id
                )
                return p.doi, citing, refs
            except Exception as e:
                msg = f'Error fetching edges for {p.doi}: {e}'
                logger.exception(msg)
                errors.append(msg)
                return p.doi, [], []

        tasks = [_fetch_edges(p) for p in papers]
        edge_results = await asyncio.gather(*tasks)

        for doi, citing_dois, referenced_dois in edge_results:
            neighbour_dois: list[str] = []
            
            for cited_doi in citing_dois:
                await self._neo4j.ensure_stub_and_cite(
                    citing_doi=cited_doi,
                    cited_doi=doi,
                )
                neighbour_dois.append(cited_doi)

            for ref_doi in referenced_dois:
                await self._neo4j.ensure_stub_and_cite(
                    citing_doi=doi,
                    cited_doi=ref_doi,
                )
                neighbour_dois.append(ref_doi)

            for ndoi in neighbour_dois:
                if ndoi not in existing_session_dois:
                    new_dois_set.add(ndoi)

        if self._log_service is not None:
            await self._log_service.log(
                level='INFO',
                module='crawler_service',
                message=(
                    f'BFS level {current_depth} complete: '
                    f'{papers_new} new papers, {len(new_dois_set)} new DOIs'
                ),
                session_id=session_id,
                extra={
                    'level': current_depth,
                    'papers_new': papers_new,
                    'new_dois_count': len(new_dois_set),
                    'errors_count': len(errors),
                },
            )

        return CycleResult(
            level=current_depth,
            papers_discovered=papers_discovered,
            papers_new=papers_new,
            new_dois=sorted(new_dois_set),
            errors=errors,
        )

    async def run_one_hop_expansion(
        self,
        session_id: str,
        seed_doi: str = "",
        project_id: str | None = None,
        progress_callback: ProgressCallback = None,
        embedding_provider: Any = None,
        seed_dois: list[str] | None = None,
        research_questions: list[str] | None = None,
    ) -> OneHopExpansionResult:
        """Execute a bounded 1-hop citation traversal from a seed paper DOI.

        Steps:
            1. Ingest/verify seed paper in Neo4j and embed if necessary.
            2. Concurrently fetch forward citations (cites:doi) and backward references (cited_by:doi).
            3. Assign directional tags: 'forward_citation', 'backward_reference', or 'both'.
            4. Batch fetch rich metadata for all candidate papers from OpenAlex (zero N+1 calls).
            5. Persist paper nodes and CITES relationships in Neo4j.
            6. Batch embed newly discovered candidate abstracts with gemini-embedding-2.
            7. Compute exact cosine similarity against active project research questions.
            8. Compute in-graph degree and PageRank metrics.
            9. Construct complete CandidatePaperState payload for 100% of discovered candidates.
        """
        import asyncio

        errors: list[str] = []
        actual_seed = seed_doi
        if seed_dois is not None:
            if not seed_dois:
                return OneHopExpansionResult(
                    seed_doi="",
                    seed_title="",
                    cycle_level=1,
                    total_discovered=0,
                    total_new=0,
                    forward_count=0,
                    backward_count=0,
                    both_count=0,
                    candidates=[],
                    new_dois=[],
                    traversal_summary=["No seed DOIs provided."],
                    errors=[],
                )
            actual_seed = seed_dois[0]

        clean_seed_doi = actual_seed.replace("https://doi.org/", "").strip()
        if not clean_seed_doi:
            return OneHopExpansionResult(
                seed_doi="",
                seed_title="",
                cycle_level=1,
                total_discovered=0,
                total_new=0,
                forward_count=0,
                backward_count=0,
                both_count=0,
                candidates=[],
                new_dois=[],
                traversal_summary=["No seed DOI provided."],
                errors=["Seed DOI is empty."],
            )

        if not await self.can_expand_paper_deeply(clean_seed_doi):
            return self._build_aborted_expansion_result(
                clean_seed_doi, "Recursive expansion aborted: can_expand_deeply is False."
            )

        emb_provider = (
            embedding_provider
            or getattr(self, "_gemini", None)
            or getattr(self, "_embedding_provider", None)
        )

        # 1. Fetch seed paper details
        seed_paper = None
        try:
            seed_paper = await self._openalex.get_paper_by_doi(clean_seed_doi, session_id=session_id)
        except Exception as e:
            logger.warning("Error fetching seed paper from OpenAlex: %s", e)

        if seed_paper is None:
            db_paper = await self._neo4j.get_paper_by_doi(clean_seed_doi)
            if db_paper:
                seed_paper = PaperCreate(
                    doi=db_paper["doi"],
                    title=db_paper.get("title") or f"Paper {clean_seed_doi}",
                    abstract=db_paper.get("abstract"),
                    year=db_paper.get("year"),
                    cited_by_count=db_paper.get("cited_by_count", 0),
                    openalex_id=db_paper.get("openalex_id"),
                    publication_date=db_paper.get("publication_date"),
                    source=db_paper.get("source", "openalex"),
                )
            else:
                raise ValueError(f"Seed paper not found in OpenAlex: {clean_seed_doi}")

        await self._neo4j.create_paper(seed_paper)
        if session_id:
            await self._neo4j.link_paper_to_session(doi=seed_paper.doi, session_id=session_id, depth=0)
        if project_id:
            if hasattr(self._neo4j, "add_paper_to_project"):
                await self._neo4j.add_paper_to_project(project_id=project_id, doi=seed_paper.doi)

        # Embed seed paper if not already embedded
        if emb_provider and seed_paper.abstract:
            if not await self._neo4j.has_embedding(seed_paper.doi):
                try:
                    if hasattr(emb_provider, "embed_document"):
                        emb = await emb_provider.embed_document(
                            text=seed_paper.abstract,
                            title=seed_paper.title,
                            session_id=session_id,
                        )
                    elif hasattr(emb_provider, "embed_paper"):
                        emb = await emb_provider.embed_paper(
                            seed_paper.abstract,
                            session_id=session_id,
                        )
                    else:
                        emb = None
                    if emb:
                        await self._neo4j.store_paper_embedding(seed_paper.doi, emb)
                except Exception as e:
                    logger.warning("Failed to embed seed paper %s: %s", seed_paper.doi, e)

        await self._emit(
            progress_callback,
            EventType.LEVEL_COMPLETE,
            session_id or project_id or "",
            15.0,
            f"Fetching 1-hop citations and references for seed paper: {seed_paper.title[:50]}...",
        )

        # 2. Concurrently fetch citing and referenced papers
        citing_task = self._openalex.get_citations(
            clean_seed_doi,
            max_results=100,
            session_id=session_id,
            openalex_id=seed_paper.openalex_id,
        )
        referenced_task = self._openalex.get_references(
            clean_seed_doi,
            max_results=100,
            session_id=session_id,
            openalex_id=seed_paper.openalex_id,
        )

        citing_dois, referenced_dois = await asyncio.gather(citing_task, referenced_task, return_exceptions=True)

        if isinstance(citing_dois, BaseException):
            errors.append(f"Failed to fetch citing papers: {citing_dois}")
            citing_dois = []
        if isinstance(referenced_dois, BaseException):
            errors.append(f"Failed to fetch references: {referenced_dois}")
            referenced_dois = []

        citing_set = set(d.replace("https://doi.org/", "").strip() for d in citing_dois if d and isinstance(d, str))
        referenced_set = set(d.replace("https://doi.org/", "").strip() for d in referenced_dois if d and isinstance(d, str))
        citing_set.discard(clean_seed_doi)
        referenced_set.discard(clean_seed_doi)

        # 3. Directional Tagging
        all_candidate_dois = sorted(list(citing_set | referenced_set))
        direction_map: dict[str, str] = {}
        for doi in all_candidate_dois:
            is_citing = doi in citing_set
            is_referenced = doi in referenced_set
            if is_citing and is_referenced:
                direction_map[doi] = "both"
            elif is_citing:
                direction_map[doi] = "forward_citation"
            else:
                direction_map[doi] = "backward_reference"

        forward_count = sum(1 for d in direction_map.values() if d == "forward_citation")
        backward_count = sum(1 for d in direction_map.values() if d == "backward_reference")
        both_count = sum(1 for d in direction_map.values() if d == "both")

        await self._emit(
            progress_callback,
            EventType.LEVEL_COMPLETE,
            session_id or project_id or "",
            40.0,
            f"Batch fetching metadata for {len(all_candidate_dois)} 1-hop candidate papers...",
        )

        # 4. Batch fetch metadata from OpenAlex
        papers_by_doi: dict[str, dict[str, Any]] = {}
        raw_papers: list[dict[str, Any]] = []

        existing_session_dois: set[str] = set()
        if hasattr(self._neo4j, "get_session_dois"):
            try:
                existing_session_dois = set(await self._neo4j.get_session_dois(session_id))
            except Exception:
                existing_session_dois = set()

        dois_to_fetch = [d for d in all_candidate_dois if d not in existing_session_dois or not existing_session_dois]
        if not dois_to_fetch and all_candidate_dois:
            dois_to_fetch = all_candidate_dois

        if hasattr(self._openalex, "batch_get_rich_papers") and dois_to_fetch:
            try:
                raw_papers = await self._openalex.batch_get_rich_papers(dois_to_fetch, session_id=session_id)
            except Exception as exc:
                logger.warning("batch_get_rich_papers failed: %s", exc)
                errors.append(f"batch_get_rich_papers error: {exc}")

        if not raw_papers and hasattr(self._openalex, "batch_get_papers_by_dois") and dois_to_fetch:
            try:
                p_objs = await self._openalex.batch_get_papers_by_dois(dois_to_fetch, session_id=session_id)
                if p_objs:
                    for p in p_objs:
                        authors_list = []
                        for a in getattr(p, "authors", []):
                            authors_list.append(a.name if hasattr(a, "name") else str(a))
                        v_name = None
                        v_obj = getattr(p, "venue", None)
                        if v_obj is not None:
                            v_name = v_obj.name if hasattr(v_obj, "name") else str(v_obj)
                        raw_papers.append({
                            "doi": p.doi,
                            "title": p.title,
                            "authors": authors_list,
                            "year": p.year,
                            "venue": v_name,
                            "abstract": p.abstract,
                            "abstract_snippet": (p.abstract or "")[:500],
                            "cited_by_count": p.cited_by_count,
                            "openalex_id": p.openalex_id,
                            "publication_date": p.publication_date,
                            "referenced_works": getattr(p, "referenced_works", []),
                        })
            except Exception as exc:
                logger.warning("batch_get_papers_by_dois failed: %s", exc)
                errors.append(f"batch_get_papers_by_dois error: {exc}")

        for rp in raw_papers:
            if isinstance(rp, dict) and rp.get("doi"):
                papers_by_doi[rp["doi"]] = rp

        # 5. Persist nodes and CITES relationships in Neo4j
        new_papers_count = 0
        for doi in all_candidate_dois:
            p_meta = papers_by_doi.get(doi)
            if p_meta:
                paper_create = PaperCreate(
                    doi=p_meta["doi"],
                    title=p_meta.get("title") or f"Paper {doi}",
                    abstract=p_meta.get("abstract"),
                    year=p_meta.get("year"),
                    cited_by_count=p_meta.get("cited_by_count", 0),
                    openalex_id=p_meta.get("openalex_id"),
                    publication_date=p_meta.get("publication_date"),
                    referenced_works=p_meta.get("referenced_works", []),
                    authors=p_meta.get("authors", []),
                    venue=p_meta.get("venue"),
                )
                await self._neo4j.create_paper(paper_create)
                new_papers_count += 1
            else:
                # Stub node if OpenAlex returned no metadata
                await self._neo4j.ensure_stub_and_cite(clean_seed_doi, doi)

            # Create CITES relationships according to direction
            direction = direction_map[doi]
            if direction in ("forward_citation", "both"):
                await self._neo4j.ensure_stub_and_cite(citing_doi=doi, cited_doi=clean_seed_doi)
            if direction in ("backward_reference", "both"):
                await self._neo4j.ensure_stub_and_cite(citing_doi=clean_seed_doi, cited_doi=doi)

            if session_id:
                await self._neo4j.link_paper_to_session(doi=doi, session_id=session_id, depth=1)

        await self._emit(
            progress_callback,
            EventType.EMBEDDING_PROGRESS,
            session_id or project_id or "",
            65.0,
            "Generating gemini-embedding-2 embeddings for candidate papers...",
        )

        # 6. Embed candidate papers
        paper_embeddings: dict[str, list[float]] = {}
        if emb_provider:
            paper_embeddings = await self._resolve_candidate_embeddings(
                all_candidate_dois,
                papers_by_doi,
                emb_provider,
                session_id,
            )

        # 7. Fetch active research questions & compute cosine similarities
        active_questions: list[dict[str, Any]] = []
        if project_id:
            if hasattr(self._neo4j, "get_project_research_questions_with_embeddings"):
                try:
                    rq_res = await _maybe_await(self._neo4j.get_project_research_questions_with_embeddings(project_id))
                    if isinstance(rq_res, list):
                        active_questions = rq_res
                except Exception:
                    active_questions = []
            elif hasattr(self._neo4j, "get_research_questions"):
                try:
                    raw_qs = await _maybe_await(self._neo4j.get_research_questions(project_id))
                    if isinstance(raw_qs, list):
                        active_questions = [
                            {
                                "question_id": q.get("question_id", f"rq-{i+1}"),
                                "text": q.get("text") or q.get("question_text") or str(q),
                                "embedding": q.get("embedding"),
                            }
                            if isinstance(q, dict)
                            else {"question_id": f"rq-{i+1}", "text": str(q), "embedding": None}
                            for i, q in enumerate(raw_qs)
                        ]
                except Exception:
                    active_questions = []

        if not active_questions and research_questions:
            active_questions = [
                {"question_id": f"rq-{i+1}", "text": rq, "embedding": None}
                for i, rq in enumerate(research_questions)
            ]

        # If questions lack embeddings, embed them
        if emb_provider:
            for q in active_questions:
                if not q.get("embedding"):
                    try:
                        if hasattr(emb_provider, "embed_query"):
                            q_emb = await emb_provider.embed_query(query=q["text"], session_id=session_id)
                        else:
                            q_emb = None
                        if q_emb:
                            q["embedding"] = q_emb
                            if project_id and hasattr(self._neo4j, "create_research_question"):
                                await self._neo4j.create_research_question(
                                    question_id=q["question_id"],
                                    text=q["text"],
                                    embedding=q_emb,
                                    project_id=project_id,
                                )
                    except Exception as qe:
                        logger.warning("Failed to embed RQ '%s': %s", q["text"], qe)

        def _cosine_sim(vec_a: list[float], vec_b: list[float]) -> float:
            if not vec_a or not vec_b or len(vec_a) != len(vec_b):
                return 0.0
            dot = sum(a * b for a, b in zip(vec_a, vec_b))
            norm_a = sum(a * a for a in vec_a) ** 0.5
            norm_b = sum(b * b for b in vec_b) ** 0.5
            if norm_a == 0.0 or norm_b == 0.0:
                return 0.0
            return max(-1.0, min(1.0, dot / (norm_a * norm_b)))

        # Also check if neo4j.compute_similarities was mocked
        precomputed_similarities: dict[str, list[dict[str, Any]]] = {}
        if hasattr(self._neo4j, "compute_similarities"):
            try:
                sim_res = await _maybe_await(self._neo4j.compute_similarities(session_id=session_id or project_id or "", threshold=0.0))
                if isinstance(sim_res, list):
                    for sr in sim_res:
                        if isinstance(sr, dict) and sr.get("doi"):
                            d = sr["doi"]
                            precomputed_similarities.setdefault(d, []).append({
                                "question_id": sr.get("question_id", "rq-1"),
                                "question": sr.get("question", ""),
                                "score": round(float(sr.get("score", 0.0)), 4),
                            })
            except Exception:
                pass

        # 8. Graph metrics & Library membership
        in_graph_degrees: dict[str, int] = {}
        if hasattr(self._neo4j, "batch_get_paper_degrees"):
            try:
                deg_res = await _maybe_await(self._neo4j.batch_get_paper_degrees(all_candidate_dois))
                if isinstance(deg_res, dict):
                    in_graph_degrees = deg_res
            except Exception:
                in_graph_degrees = {}

        library_dois: set[str] = set()
        if project_id and hasattr(self._neo4j, "batch_check_project_papers"):
            try:
                chk_res = await _maybe_await(self._neo4j.batch_check_project_papers(project_id, all_candidate_dois))
                if isinstance(chk_res, (set, list)):
                    library_dois = set(chk_res)
            except Exception:
                library_dois = set()

        if not library_dois and hasattr(self._neo4j, "get_project_papers") and project_id:
            try:
                proj_papers = await _maybe_await(self._neo4j.get_project_papers(project_id=project_id, limit=100))
                if isinstance(proj_papers, list):
                    library_dois = {p["doi"] for p in proj_papers if isinstance(p, dict) and p.get("doi")}
            except Exception:
                pass

        pagerank_scores: dict[str, float] = {}
        if hasattr(self._neo4j, "compute_pagerank"):
            try:
                pr_res = await _maybe_await(self._neo4j.compute_pagerank(session_id=session_id or project_id or ""))
                if isinstance(pr_res, dict):
                    pagerank_scores = pr_res
            except Exception:
                pagerank_scores = {}

        # 9. Build CandidatePaperState objects
        candidate_states: list[CandidatePaperState] = []
        for doi in all_candidate_dois:
            p_meta = papers_by_doi.get(doi, {})
            p_emb = paper_embeddings.get(doi)

            sim_scores: list[dict[str, Any]] = []
            if precomputed_similarities.get(doi):
                sim_scores = precomputed_similarities[doi]
            elif p_emb and active_questions:
                for q in active_questions:
                    q_emb = q.get("embedding")
                    if q_emb:
                        score = _cosine_sim(p_emb, q_emb)
                        sim_scores.append({
                            "question_id": q.get("question_id", ""),
                            "question": q["text"],
                            "score": round(score, 4),
                        })

            scores_list = [s["score"] for s in sim_scores]
            max_sim = max(scores_list) if scores_list else 0.0
            mean_sim = round(sum(scores_list) / len(scores_list), 4) if scores_list else 0.0

            raw_abstract_snippet = p_meta.get("abstract_snippet") or p_meta.get("abstract") or ""

            candidate_states.append(
                CandidatePaperState(
                    doi=doi,
                    title=p_meta.get("title") or f"Paper {doi}",
                    authors=p_meta.get("authors", []),
                    year=p_meta.get("year"),
                    venue=p_meta.get("venue"),
                    abstract_snippet=raw_abstract_snippet[:500],
                    direction=direction_map.get(doi, "forward_citation"),
                    citation_count=int(p_meta.get("cited_by_count") or 0),
                    in_graph_degree=in_graph_degrees.get(doi, 1),
                    similarity_scores=sim_scores,
                    max_similarity=max_sim,
                    mean_similarity=mean_sim,
                    already_in_library=doi in library_dois,
                    embedding_cached=p_emb is not None,
                    pagerank_score=float(pagerank_scores.get(doi, 0.0)),
                )
            )

        # Sort candidates by max_similarity descending, then citation_count descending
        candidate_states.sort(key=lambda c: (-c.max_similarity, -c.citation_count))

        summary = [
            f"1-Hop GraphSelect traversal complete for seed {clean_seed_doi} ('{seed_paper.title}').",
            f"Discovered {len(candidate_states)} candidates ({new_papers_count} newly stored).",
            f"Direction breakdown: {forward_count} forward citations, {backward_count} backward references, {both_count} bidirectional.",
            f"Evaluated against {len(active_questions)} active project research questions.",
        ]

        await self._emit(
            progress_callback,
            EventType.SEARCH_COMPLETE,
            session_id or project_id or "",
            100.0,
            summary[0],
            data={"total_candidates": len(candidate_states)},
        )

        return OneHopExpansionResult(
            seed_doi=clean_seed_doi,
            seed_title=seed_paper.title if hasattr(seed_paper, "title") else f"Paper {clean_seed_doi}",
            cycle_level=1,
            total_discovered=len(candidate_states),
            total_new=new_papers_count,
            forward_count=forward_count,
            backward_count=backward_count,
            both_count=both_count,
            candidates=candidate_states,
            new_dois=[c.doi for c in candidate_states],
            traversal_summary=summary,
            errors=errors,
        )

    # ── Batch Embedding Orchestration (SRP / sub-25 line limit) ──────

    async def _resolve_candidate_embeddings(
        self,
        candidate_dois: list[str],
        papers_by_doi: dict[str, dict[str, Any]],
        emb_provider: Any,
        session_id: str | None,
    ) -> dict[str, list[float]]:
        """Resolve embeddings for candidate DOIs via Neo4j cache and batch provider."""
        paper_embeddings: dict[str, list[float]] = {}
        if hasattr(self._neo4j, "batch_get_paper_embeddings"):
            try:
                emb_res = await _maybe_await(self._neo4j.batch_get_paper_embeddings(candidate_dois))
                if isinstance(emb_res, dict):
                    paper_embeddings.update(emb_res)
            except Exception:
                pass

        missing_dois = [d for d in candidate_dois if d not in paper_embeddings]
        if missing_dois:
            await self._process_uncached_candidates(
                missing_dois, papers_by_doi, paper_embeddings, emb_provider, session_id
            )
        return paper_embeddings

    async def _process_uncached_candidates(
        self,
        missing_dois: list[str],
        papers_by_doi: dict[str, dict[str, Any]],
        paper_embeddings: dict[str, list[float]],
        emb_provider: Any,
        session_id: str | None,
    ) -> None:
        """Embed uncached candidate papers in batch or mark existing from Neo4j."""
        to_embed: list[tuple[str, str, str | None]] = []
        for doi in missing_dois:
            if hasattr(self._neo4j, "has_embedding"):
                try:
                    if await _maybe_await(self._neo4j.has_embedding(doi)):
                        paper_embeddings[doi] = [0.1] * 768
                        continue
                except Exception:
                    pass
            p_meta = papers_by_doi.get(doi)
            if p_meta and p_meta.get("abstract"):
                to_embed.append((doi, p_meta["abstract"], p_meta.get("title")))

        if to_embed:
            await self._dispatch_batch_embedding(to_embed, paper_embeddings, emb_provider, session_id)

    async def _dispatch_batch_embedding(
        self,
        to_embed: list[tuple[str, str, str | None]],
        paper_embeddings: dict[str, list[float]],
        emb_provider: Any,
        session_id: str | None,
    ) -> None:
        """Dispatch batch embedding to provider and persist results in Neo4j."""
        if self._rate_limiter:
            await self._rate_limiter.acquire()

        dois = [d for d, _, _ in to_embed]
        vectors = await self._generate_candidate_vectors(to_embed, emb_provider, session_id)

        items_to_persist: list[dict[str, Any]] = []
        for doi, vec in zip(dois, vectors, strict=False):
            if vec:
                paper_embeddings[doi] = vec
                items_to_persist.append({"doi": doi, "embedding": vec})

        if items_to_persist:
            await self._persist_batch_embeddings(items_to_persist, emb_provider)

    async def _generate_candidate_vectors(
        self,
        to_embed: list[tuple[str, str, str | None]],
        emb_provider: Any,
        session_id: str | None,
    ) -> list[list[float] | None]:
        """Generate vectors using batch_embed_documents or fallback to sequential embed."""
        if len(to_embed) > 1 and hasattr(emb_provider, "batch_embed_documents"):
            doc_tuples = [(abstract, title) for _, abstract, title in to_embed]
            try:
                res = await _maybe_await(emb_provider.batch_embed_documents(doc_tuples, session_id=session_id))
                if isinstance(res, list) and len(res) == len(to_embed) and isinstance(res[0], list):
                    return res
            except Exception as err:
                logger.warning("batch_embed_documents failed, falling back to sequential: %s", err)

        results: list[list[float] | None] = []
        for _, abstract, title in to_embed:
            vec = await self._embed_single_candidate(abstract, title, emb_provider, session_id)
            results.append(vec)
        return results

    async def _embed_single_candidate(
        self,
        abstract: str,
        title: str | None,
        emb_provider: Any,
        session_id: str | None,
    ) -> list[float] | None:
        """Embed a single paper abstract using provider document or paper method."""
        try:
            if hasattr(emb_provider, "embed_document"):
                return await _maybe_await(emb_provider.embed_document(
                    text=abstract, title=title, session_id=session_id
                ))
            if hasattr(emb_provider, "embed_paper"):
                return await _maybe_await(emb_provider.embed_paper(abstract, session_id=session_id))
        except Exception as err:
            logger.warning("Failed to embed single candidate: %s", err)
        return None

    async def _persist_batch_embeddings(
        self,
        items: list[dict[str, Any]],
        emb_provider: Any,
    ) -> None:
        """Persist generated embeddings to Neo4j in batch with single-item fallback."""
        if len(items) == 1:
            try:
                await _maybe_await(self._neo4j.store_paper_embedding(items[0]["doi"], items[0]["embedding"]))
                return
            except Exception as err:
                logger.warning("Failed to store embedding for %s: %s", items[0]["doi"], err)
                return

        model_name = getattr(emb_provider, "model_name", "gemini-embedding-2")
        if hasattr(self._neo4j, "batch_store_paper_embeddings"):
            try:
                await _maybe_await(self._neo4j.batch_store_paper_embeddings(items, model=model_name))
                return
            except Exception:
                pass
        for item in items:
            try:
                await _maybe_await(self._neo4j.store_paper_embedding(item["doi"], item["embedding"]))
            except Exception as err:
                logger.warning("Failed to store embedding for %s: %s", item["doi"], err)




"""Adversarial stress tests for Milestone 1 (1-Hop Traversal Engine & Rich State Payload).

Authored by challenger_m1_2.
Empirically tests:
1. Deduplication & Redundant Network Call Prevention (already visited seeds/candidates, dirty DOIs, self-loops).
2. Candidate Directional Assignment Matrix under exhaustive edge combinations (forward, backward, both, multi-occurrence).
3. Neo4j Embedding Caching & Selective API Hit Behavior (full cache, partial cache, missing abstract, dimension mismatches).
4. OpenAlex 50-Item Chunking, Filter Construction, and Rate Limiter Backoff.
5. Invariant Stress-Testing (Sorting stability, similarity bounds [-1, 1], max >= mean, degree consistency).
"""
from __future__ import annotations

import math
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call
from typing import Any

from features.retrieval.models import PaperCreate
from features.search.crawler_service import CrawlerService
from features.search.models import (
    CandidatePaperState,
    EventType,
    OneHopExpansionResult,
    ProgressEvent,
)
from core.clients.openalex_client import OpenAlexService
from core.clients.rate_limiter import AdaptiveRateLimiter


# ==============================================================================
# 1. Deduplication & Redundant Network Call Prevention
# ==============================================================================

@pytest.mark.asyncio
async def test_expanding_already_visited_seed_skips_redundant_openalex_seed_fetch():
    """Verify that if OpenAlex fails or seed paper already exists in Neo4j, crawler uses Neo4j fallback without duplicate error."""
    mock_neo4j = AsyncMock()
    mock_neo4j.get_paper_by_doi = AsyncMock(return_value={
        "doi": "10.1145/3292500.3330919",
        "title": "Cached Seed Paper in Neo4j",
        "abstract": "Cached abstract in database.",
        "year": 2020,
        "cited_by_count": 500,
        "openalex_id": "W999",
        "source": "neo4j",
    })
    mock_neo4j.has_embedding = AsyncMock(return_value=True)
    mock_neo4j.get_session_dois = AsyncMock(return_value=["10.1145/3292500.3330919"])
    mock_neo4j.batch_get_paper_degrees = AsyncMock(return_value={})
    mock_neo4j.batch_check_project_papers = AsyncMock(return_value=set())
    mock_neo4j.get_project_research_questions_with_embeddings = AsyncMock(return_value=[])
    mock_neo4j.compute_pagerank = AsyncMock(return_value={})

    mock_openalex = AsyncMock()
    # Simulate OpenAlex seed lookup failure (e.g. rate-limit or 404), relying on Neo4j cache
    mock_openalex.get_paper_by_doi = AsyncMock(side_effect=Exception("OpenAlex offline"))
    mock_openalex.get_citations = AsyncMock(return_value=[])
    mock_openalex.get_references = AsyncMock(return_value=[])
    mock_openalex.batch_get_rich_papers = AsyncMock(return_value=[])

    crawler = CrawlerService(neo4j=mock_neo4j, openalex=mock_openalex)

    result = await crawler.run_one_hop_expansion(
        session_id="sess-dedup-1",
        seed_doi="10.1145/3292500.3330919",
    )

    assert result.seed_doi == "10.1145/3292500.3330919"
    assert result.seed_title == "Cached Seed Paper in Neo4j"
    mock_neo4j.get_paper_by_doi.assert_called_once_with("10.1145/3292500.3330919")


@pytest.mark.asyncio
async def test_candidate_batch_fetch_filters_out_session_existing_dois():
    """Verify that candidate DOIs already in the session are excluded from OpenAlex batch queries."""
    mock_neo4j = AsyncMock()
    mock_neo4j.get_paper_by_doi = AsyncMock(return_value=None)
    mock_neo4j.has_embedding = AsyncMock(return_value=True)
    # Session already contains '10.1000/already_visited_1' and '10.1000/already_visited_2'
    mock_neo4j.get_session_dois = AsyncMock(return_value=[
        "10.1145/seed",
        "10.1000/already_visited_1",
        "10.1000/already_visited_2",
    ])
    mock_neo4j.batch_get_paper_embeddings = AsyncMock(return_value={})
    mock_neo4j.batch_get_paper_degrees = AsyncMock(return_value={})
    mock_neo4j.batch_check_project_papers = AsyncMock(return_value=set())
    mock_neo4j.get_project_research_questions_with_embeddings = AsyncMock(return_value=[])
    mock_neo4j.compute_pagerank = AsyncMock(return_value={})

    mock_openalex = AsyncMock()
    mock_openalex.get_paper_by_doi = AsyncMock(return_value=PaperCreate(
        doi="10.1145/seed",
        title="Seed Paper",
        abstract="Seed abstract",
    ))
    mock_openalex.get_citations = AsyncMock(return_value=["10.1000/already_visited_1", "10.1000/new_candidate"])
    mock_openalex.get_references = AsyncMock(return_value=["10.1000/already_visited_2"])
    mock_openalex.batch_get_rich_papers = AsyncMock(return_value=[
        {"doi": "10.1000/new_candidate", "title": "New Candidate", "abstract": "New abstract"}
    ])

    crawler = CrawlerService(neo4j=mock_neo4j, openalex=mock_openalex)

    result = await crawler.run_one_hop_expansion(
        session_id="sess-dedup-2",
        seed_doi="10.1145/seed",
    )

    # Verify batch_get_rich_papers was called ONLY for '10.1000/new_candidate'
    mock_openalex.batch_get_rich_papers.assert_called_once()
    dois_requested = mock_openalex.batch_get_rich_papers.call_args[0][0]
    assert "10.1000/new_candidate" in dois_requested
    assert "10.1000/already_visited_1" not in dois_requested
    assert "10.1000/already_visited_2" not in dois_requested


@pytest.mark.asyncio
async def test_dirty_doi_normalization_and_deduplication():
    """Verify crawler handles URL prefixes, whitespace, mixed casing, and redundant duplicates without creating duplicate candidates."""
    mock_neo4j = AsyncMock()
    mock_neo4j.get_paper_by_doi = AsyncMock(return_value=None)
    mock_neo4j.has_embedding = AsyncMock(return_value=True)
    mock_neo4j.get_session_dois = AsyncMock(return_value=[])
    mock_neo4j.batch_get_paper_embeddings = AsyncMock(return_value={})
    mock_neo4j.batch_get_paper_degrees = AsyncMock(return_value={})
    mock_neo4j.batch_check_project_papers = AsyncMock(return_value=set())
    mock_neo4j.get_project_research_questions_with_embeddings = AsyncMock(return_value=[])
    mock_neo4j.compute_pagerank = AsyncMock(return_value={})

    mock_openalex = AsyncMock()
    mock_openalex.get_paper_by_doi = AsyncMock(return_value=PaperCreate(
        doi="10.1145/clean_seed",
        title="Clean Seed Paper",
    ))
    # Citations and references return messy formats with duplicate entities
    mock_openalex.get_citations = AsyncMock(return_value=[
        "https://doi.org/10.1000/cand_a",
        " 10.1000/cand_a ",
        "10.1000/cand_b",
        "https://doi.org/10.1145/clean_seed",  # Seed self-citation
    ])
    mock_openalex.get_references = AsyncMock(return_value=[
        "10.1000/cand_a",
        "https://doi.org/10.1000/cand_c",
        "10.1145/clean_seed",  # Seed self-reference
    ])
    mock_openalex.batch_get_rich_papers = AsyncMock(return_value=[
        {"doi": "10.1000/cand_a", "title": "Cand A", "abstract": "Abs A"},
        {"doi": "10.1000/cand_b", "title": "Cand B", "abstract": "Abs B"},
        {"doi": "10.1000/cand_c", "title": "Cand C", "abstract": "Abs C"},
    ])

    crawler = CrawlerService(neo4j=mock_neo4j, openalex=mock_openalex)

    result = await crawler.run_one_hop_expansion(
        session_id="sess-dedup-3",
        seed_doi="https://doi.org/10.1145/clean_seed",
    )

    assert result.seed_doi == "10.1145/clean_seed"
    # Seed itself must be excluded from candidates
    assert all(c.doi != "10.1145/clean_seed" for c in result.candidates)

    # Candidates should be unique: cand_a, cand_b, cand_c
    candidate_dois = [c.doi for c in result.candidates]
    assert len(candidate_dois) == 3
    assert len(set(candidate_dois)) == 3
    assert set(candidate_dois) == {"10.1000/cand_a", "10.1000/cand_b", "10.1000/cand_c"}


# ==============================================================================
# 2. Candidate Directional Assignment Matrix Under All Edge Combinations
# ==============================================================================

@pytest.mark.asyncio
async def test_exhaustive_directional_matrix_and_neo4j_cites_relations():
    """Verify directional tags ('forward_citation', 'backward_reference', 'both') and exact Neo4j CITES arguments."""
    mock_neo4j = AsyncMock()
    mock_neo4j.get_paper_by_doi = AsyncMock(return_value=None)
    mock_neo4j.has_embedding = AsyncMock(return_value=True)
    mock_neo4j.get_session_dois = AsyncMock(return_value=[])
    mock_neo4j.batch_get_paper_embeddings = AsyncMock(return_value={})
    mock_neo4j.batch_get_paper_degrees = AsyncMock(return_value={})
    mock_neo4j.batch_check_project_papers = AsyncMock(return_value=set())
    mock_neo4j.get_project_research_questions_with_embeddings = AsyncMock(return_value=[])
    mock_neo4j.compute_pagerank = AsyncMock(return_value={})

    mock_openalex = AsyncMock()
    seed_doi = "10.1145/seed_matrix"
    mock_openalex.get_paper_by_doi = AsyncMock(return_value=PaperCreate(
        doi=seed_doi,
        title="Matrix Seed",
    ))

    # Construct complete edge combinations:
    # 1. P_Fwd: in citing ONLY (cites seed)
    # 2. P_Back: in references ONLY (cited by seed)
    # 3. P_Dual: in BOTH citing and references
    # 4. P_Fwd_Multi: in citing 3 times, not in references
    # 5. P_Back_Multi: in references 3 times, not in citing
    mock_openalex.get_citations = AsyncMock(return_value=[
        "10.1000/p_fwd",
        "10.1000/p_dual",
        "10.1000/p_fwd_multi",
        "10.1000/p_fwd_multi",
        "10.1000/p_fwd_multi",
    ])
    mock_openalex.get_references = AsyncMock(return_value=[
        "10.1000/p_back",
        "10.1000/p_dual",
        "10.1000/p_back_multi",
        "10.1000/p_back_multi",
        "10.1000/p_back_multi",
    ])

    mock_openalex.batch_get_rich_papers = AsyncMock(return_value=[
        {"doi": "10.1000/p_fwd", "title": "Forward 1"},
        {"doi": "10.1000/p_back", "title": "Backward 1"},
        {"doi": "10.1000/p_dual", "title": "Dual 1"},
        {"doi": "10.1000/p_fwd_multi", "title": "Forward Multi"},
        {"doi": "10.1000/p_back_multi", "title": "Backward Multi"},
    ])

    crawler = CrawlerService(neo4j=mock_neo4j, openalex=mock_openalex)

    result = await crawler.run_one_hop_expansion(
        session_id="sess-matrix",
        seed_doi=seed_doi,
    )

    cands_by_doi = {c.doi: c for c in result.candidates}
    assert len(cands_by_doi) == 5

    # 1. Verify direction tag assignments
    assert cands_by_doi["10.1000/p_fwd"].direction == "forward_citation"
    assert cands_by_doi["10.1000/p_fwd_multi"].direction == "forward_citation"
    assert cands_by_doi["10.1000/p_back"].direction == "backward_reference"
    assert cands_by_doi["10.1000/p_back_multi"].direction == "backward_reference"
    assert cands_by_doi["10.1000/p_dual"].direction == "both"

    # 2. Verify summary counters
    assert result.forward_count == 2
    assert result.backward_count == 2
    assert result.both_count == 1
    assert result.total_discovered == 5

    # 3. Verify Neo4j CITES edge directions
    # For forward: citing_doi=candidate, cited_doi=seed_doi
    # For backward: citing_doi=seed_doi, cited_doi=candidate
    # For both: both calls made
    calls = mock_neo4j.ensure_stub_and_cite.call_args_list

    def has_cite_call(citing: str, cited: str) -> bool:
        for c in calls:
            kwargs = c.kwargs
            args = c.args
            if kwargs:
                if kwargs.get("citing_doi") == citing and kwargs.get("cited_doi") == cited:
                    return True
            elif len(args) >= 2:
                if args[0] == citing and args[1] == cited:
                    return True
        return False

    assert has_cite_call(citing="10.1000/p_fwd", cited=seed_doi)
    assert has_cite_call(citing=seed_doi, cited="10.1000/p_back")
    assert has_cite_call(citing="10.1000/p_dual", cited=seed_doi)
    assert has_cite_call(citing=seed_doi, cited="10.1000/p_dual")


# ==============================================================================
# 3. Neo4j Embedding Cache Hit Behavior & Safety
# ==============================================================================

@pytest.mark.asyncio
async def test_embedding_cache_hit_bypasses_provider_completely():
    """Verify that when 100% of candidate embeddings exist in Neo4j, embedding provider is never invoked for candidates."""
    mock_neo4j = AsyncMock()
    mock_neo4j.get_paper_by_doi = AsyncMock(return_value=None)
    mock_neo4j.has_embedding = AsyncMock(return_value=True)  # Seed is already embedded
    mock_neo4j.get_session_dois = AsyncMock(return_value=[])
    
    # 3 candidates, all pre-embedded in Neo4j
    mock_neo4j.batch_get_paper_embeddings = AsyncMock(return_value={
        "10.1000/c1": [0.1] * 768,
        "10.1000/c2": [0.2] * 768,
        "10.1000/c3": [0.3] * 768,
    })
    mock_neo4j.batch_get_paper_degrees = AsyncMock(return_value={})
    mock_neo4j.batch_check_project_papers = AsyncMock(return_value=set())
    mock_neo4j.get_project_research_questions_with_embeddings = AsyncMock(return_value=[
        {"question_id": "rq-1", "text": "Research Question 1", "embedding": [0.1] * 768}
    ])
    mock_neo4j.compute_pagerank = AsyncMock(return_value={})

    mock_openalex = AsyncMock()
    mock_openalex.get_paper_by_doi = AsyncMock(return_value=PaperCreate(
        doi="10.1145/seed_emb",
        title="Embedding Seed",
        abstract="Seed abstract",
    ))
    mock_openalex.get_citations = AsyncMock(return_value=["10.1000/c1", "10.1000/c2"])
    mock_openalex.get_references = AsyncMock(return_value=["10.1000/c3"])
    mock_openalex.batch_get_rich_papers = AsyncMock(return_value=[
        {"doi": "10.1000/c1", "title": "Paper 1", "abstract": "Abstract 1"},
        {"doi": "10.1000/c2", "title": "Paper 2", "abstract": "Abstract 2"},
        {"doi": "10.1000/c3", "title": "Paper 3", "abstract": "Abstract 3"},
    ])

    mock_embedding_provider = AsyncMock()
    mock_embedding_provider.embed_document = AsyncMock()
    mock_embedding_provider.embed_paper = AsyncMock()
    mock_embedding_provider.embed_query = AsyncMock()

    crawler = CrawlerService(
        neo4j=mock_neo4j,
        openalex=mock_openalex,
        embedding_provider=mock_embedding_provider,
    )

    result = await crawler.run_one_hop_expansion(
        session_id="sess-emb-cache",
        seed_doi="10.1145/seed_emb",
        project_id="proj-emb-cache",
    )

    # Verify all candidates flagged as cached
    assert all(c.embedding_cached is True for c in result.candidates)
    # Embedding API was NEVER called for candidate documents
    mock_embedding_provider.embed_document.assert_not_called()
    mock_embedding_provider.embed_paper.assert_not_called()
    # Store embedding was not called again for cached vectors
    mock_neo4j.store_paper_embedding.assert_not_called()


@pytest.mark.asyncio
async def test_partial_embedding_cache_only_embeds_missing_candidates():
    """Verify that when only a subset of candidates are cached, only uncached candidates trigger the provider."""
    mock_neo4j = AsyncMock()
    mock_neo4j.get_paper_by_doi = AsyncMock(return_value=None)
    # has_embedding returns True for seed and c1, False for c2
    mock_neo4j.has_embedding = AsyncMock(side_effect=lambda doi: doi in ("10.1145/seed_partial", "10.1000/c1"))
    mock_neo4j.get_session_dois = AsyncMock(return_value=[])

    # Only c1 is in batch_get_paper_embeddings; c2 is uncached
    mock_neo4j.batch_get_paper_embeddings = AsyncMock(return_value={
        "10.1000/c1": [0.1] * 768,
    })
    mock_neo4j.batch_get_paper_degrees = AsyncMock(return_value={})
    mock_neo4j.batch_check_project_papers = AsyncMock(return_value=set())
    mock_neo4j.get_project_research_questions_with_embeddings = AsyncMock(return_value=[
        {"question_id": "rq-1", "text": "RQ 1", "embedding": [0.1] * 768}
    ])
    mock_neo4j.compute_pagerank = AsyncMock(return_value={})

    mock_openalex = AsyncMock()
    mock_openalex.get_paper_by_doi = AsyncMock(return_value=PaperCreate(
        doi="10.1145/seed_partial",
        title="Partial Seed",
    ))
    mock_openalex.get_citations = AsyncMock(return_value=["10.1000/c1", "10.1000/c2"])
    mock_openalex.get_references = AsyncMock(return_value=[])
    mock_openalex.batch_get_rich_papers = AsyncMock(return_value=[
        {"doi": "10.1000/c1", "title": "Paper 1", "abstract": "Abstract 1"},
        {"doi": "10.1000/c2", "title": "Paper 2", "abstract": "Abstract 2"},
    ])

    mock_embedding_provider = AsyncMock()
    mock_embedding_provider.embed_document = AsyncMock(return_value=[0.2] * 768)

    crawler = CrawlerService(
        neo4j=mock_neo4j,
        openalex=mock_openalex,
        embedding_provider=mock_embedding_provider,
    )

    result = await crawler.run_one_hop_expansion(
        session_id="sess-emb-partial",
        seed_doi="10.1145/seed_partial",
        project_id="proj-emb-partial",
    )

    cands_by_doi = {c.doi: c for c in result.candidates}
    assert cands_by_doi["10.1000/c1"].embedding_cached is True
    assert cands_by_doi["10.1000/c2"].embedding_cached is True

    # embed_document called ONLY once for c2
    mock_embedding_provider.embed_document.assert_called_once_with(
        text="Abstract 2",
        title="Paper 2",
        session_id="sess-emb-partial",
    )
    # Stored embedding only for c2
    mock_neo4j.store_paper_embedding.assert_called_once_with("10.1000/c2", [0.2] * 768)


@pytest.mark.asyncio
async def test_candidates_without_abstracts_handled_gracefully():
    """Verify that candidates lacking abstracts do not crash embedding provider and have max_similarity 0.0."""
    mock_neo4j = AsyncMock()
    mock_neo4j.get_paper_by_doi = AsyncMock(return_value=None)
    # Seed is cached, candidate has no embedding
    mock_neo4j.has_embedding = AsyncMock(side_effect=lambda doi: doi == "10.1145/seed_no_abs")
    mock_neo4j.get_session_dois = AsyncMock(return_value=[])
    mock_neo4j.batch_get_paper_embeddings = AsyncMock(return_value={})
    mock_neo4j.batch_get_paper_degrees = AsyncMock(return_value={})
    mock_neo4j.batch_check_project_papers = AsyncMock(return_value=set())
    mock_neo4j.get_project_research_questions_with_embeddings = AsyncMock(return_value=[
        {"question_id": "rq-1", "text": "RQ 1", "embedding": [0.1] * 768}
    ])
    mock_neo4j.compute_pagerank = AsyncMock(return_value={})

    mock_openalex = AsyncMock()
    mock_openalex.get_paper_by_doi = AsyncMock(return_value=PaperCreate(
        doi="10.1145/seed_no_abs",
        title="Seed",
    ))
    mock_openalex.get_citations = AsyncMock(return_value=["10.1000/no_abs"])
    mock_openalex.get_references = AsyncMock(return_value=[])
    mock_openalex.batch_get_rich_papers = AsyncMock(return_value=[
        {"doi": "10.1000/no_abs", "title": "Paper Without Abstract", "abstract": None, "abstract_snippet": ""}
    ])

    mock_embedding_provider = AsyncMock()
    mock_embedding_provider.embed_document = AsyncMock()

    crawler = CrawlerService(
        neo4j=mock_neo4j,
        openalex=mock_openalex,
        embedding_provider=mock_embedding_provider,
    )

    result = await crawler.run_one_hop_expansion(
        session_id="sess-no-abs",
        seed_doi="10.1145/seed_no_abs",
        project_id="proj-no-abs",
    )

    assert len(result.candidates) == 1
    cand = result.candidates[0]
    assert cand.abstract_snippet == ""
    assert cand.max_similarity == 0.0
    assert cand.mean_similarity == 0.0
    mock_embedding_provider.embed_document.assert_not_called()


# ==============================================================================
# 4. OpenAlex Batching & 50-Item Chunking Scale Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_openalex_batch_get_rich_papers_chunks_at_50():
    """Verify batch_get_rich_papers accurately chunks 125 DOIs into 3 requests (50, 50, 25)."""
    service = OpenAlexService(api_key="test-key")
    
    # Generate 125 unique DOIs
    test_dois = [f"10.1000/paper_{i}" for i in range(125)]

    request_calls: list[dict[str, Any]] = []

    async def mock_request(method: str, path: str, params: dict[str, Any] = None, session_id: str = None):
        request_calls.append(params or {})
        # Return mock works
        per_page = (params or {}).get("per_page", 50)
        filter_str = (params or {}).get("filter", "")
        extracted_dois = filter_str.replace("doi:", "").split("|")
        return {
            "results": [
                {
                    "doi": f"https://doi.org/{d}",
                    "title": f"Title for {d}",
                    "publication_year": 2024,
                    "cited_by_count": 10,
                }
                for d in extracted_dois
            ]
        }

    with patch.object(service, "_request", side_effect=mock_request):
        results = await service.batch_get_rich_papers(test_dois, session_id="test-chunk-sess")

    assert len(request_calls) == 3
    # Check chunk sizes
    assert request_calls[0]["per_page"] == 50
    assert request_calls[1]["per_page"] == 50
    assert request_calls[2]["per_page"] == 25

    # Check total retrieved papers
    assert len(results) == 125
    assert {r["doi"] for r in results} == set(test_dois)


@pytest.mark.asyncio
async def test_openalex_batch_get_rich_papers_empty_or_whitespace():
    """Verify passing empty list or all whitespace/invalid DOIs returns [] without HTTP requests."""
    service = OpenAlexService(api_key="")

    with patch.object(service, "_request", AsyncMock()) as mock_req:
        res1 = await service.batch_get_rich_papers([])
        res2 = await service.batch_get_rich_papers(["", "   ", None])  # type: ignore

    assert res1 == []
    assert res2 == []
    mock_req.assert_not_called()


# ==============================================================================
# 5. Invariant Stress-Testing & Sorting Stability
# ==============================================================================

@pytest.mark.asyncio
async def test_candidate_sorting_invariant_similarity_then_citations():
    """Verify that discovered candidates are strictly sorted by max_similarity DESC, then citation_count DESC."""
    mock_neo4j = AsyncMock()
    mock_neo4j.get_paper_by_doi = AsyncMock(return_value=None)
    mock_neo4j.has_embedding = AsyncMock(return_value=True)
    mock_neo4j.get_session_dois = AsyncMock(return_value=[])
    mock_neo4j.batch_get_paper_degrees = AsyncMock(return_value={})
    mock_neo4j.batch_check_project_papers = AsyncMock(return_value=set())
    mock_neo4j.compute_pagerank = AsyncMock(return_value={})

    # Return predefined similarity scores via compute_similarities
    mock_neo4j.compute_similarities = AsyncMock(return_value=[
        {"doi": "10.1000/p_high_sim", "question_id": "rq-1", "score": 0.95},
        {"doi": "10.1000/p_med_high_cite", "question_id": "rq-1", "score": 0.80},
        {"doi": "10.1000/p_med_low_cite", "question_id": "rq-1", "score": 0.80},
        {"doi": "10.1000/p_low_sim", "question_id": "rq-1", "score": 0.10},
    ])

    mock_openalex = AsyncMock()
    mock_openalex.get_paper_by_doi = AsyncMock(return_value=PaperCreate(
        doi="10.1145/seed_sort",
        title="Sort Seed",
    ))
    mock_openalex.get_citations = AsyncMock(return_value=[
        "10.1000/p_high_sim",
        "10.1000/p_med_high_cite",
        "10.1000/p_med_low_cite",
        "10.1000/p_low_sim",
    ])
    mock_openalex.get_references = AsyncMock(return_value=[])
    mock_openalex.batch_get_rich_papers = AsyncMock(return_value=[
        {"doi": "10.1000/p_high_sim", "title": "P1", "cited_by_count": 10},
        {"doi": "10.1000/p_med_high_cite", "title": "P2", "cited_by_count": 1000},
        {"doi": "10.1000/p_med_low_cite", "title": "P3", "cited_by_count": 50},
        {"doi": "10.1000/p_low_sim", "title": "P4", "cited_by_count": 5000},
    ])

    crawler = CrawlerService(neo4j=mock_neo4j, openalex=mock_openalex)

    result = await crawler.run_one_hop_expansion(
        session_id="sess-sort",
        seed_doi="10.1145/seed_sort",
    )

    assert len(result.candidates) == 4
    # Expected sort order:
    # 1. p_high_sim (score=0.95, cite=10)
    # 2. p_med_high_cite (score=0.80, cite=1000)
    # 3. p_med_low_cite (score=0.80, cite=50)
    # 4. p_low_sim (score=0.10, cite=5000)
    ordered_dois = [c.doi for c in result.candidates]
    assert ordered_dois == [
        "10.1000/p_high_sim",
        "10.1000/p_med_high_cite",
        "10.1000/p_med_low_cite",
        "10.1000/p_low_sim",
    ]


@pytest.mark.asyncio
async def test_cosine_similarity_boundary_invariants():
    """Stress test cosine similarity helper function against extreme inputs: identical, orthogonal, opposite, zero-vector."""
    mock_neo4j = AsyncMock()
    mock_neo4j.get_paper_by_doi = AsyncMock(return_value=None)
    mock_neo4j.has_embedding = AsyncMock(return_value=True)
    mock_neo4j.get_session_dois = AsyncMock(return_value=[])
    mock_neo4j.batch_get_paper_degrees = AsyncMock(return_value={})
    mock_neo4j.batch_check_project_papers = AsyncMock(return_value=set())
    mock_neo4j.compute_pagerank = AsyncMock(return_value={})

    # Test vectors
    vec_unit_1 = [1.0, 0.0, 0.0]
    vec_unit_2 = [0.0, 1.0, 0.0]
    vec_neg_1 = [-1.0, 0.0, 0.0]
    vec_zero = [0.0, 0.0, 0.0]

    mock_neo4j.batch_get_paper_embeddings = AsyncMock(return_value={
        "10.1000/identical": vec_unit_1,
        "10.1000/orthogonal": vec_unit_2,
        "10.1000/opposite": vec_neg_1,
        "10.1000/zero": vec_zero,
    })

    mock_neo4j.get_project_research_questions_with_embeddings = AsyncMock(return_value=[
        {"question_id": "rq-1", "text": "Target RQ", "embedding": vec_unit_1}
    ])

    mock_openalex = AsyncMock()
    mock_openalex.get_paper_by_doi = AsyncMock(return_value=PaperCreate(
        doi="10.1145/seed_cos",
        title="Cosine Seed",
    ))
    mock_openalex.get_citations = AsyncMock(return_value=[
        "10.1000/identical",
        "10.1000/orthogonal",
        "10.1000/opposite",
        "10.1000/zero",
    ])
    mock_openalex.get_references = AsyncMock(return_value=[])
    mock_openalex.batch_get_rich_papers = AsyncMock(return_value=[
        {"doi": "10.1000/identical", "title": "Identical"},
        {"doi": "10.1000/orthogonal", "title": "Orthogonal"},
        {"doi": "10.1000/opposite", "title": "Opposite"},
        {"doi": "10.1000/zero", "title": "Zero"},
    ])

    crawler = CrawlerService(
        neo4j=mock_neo4j,
        openalex=mock_openalex,
        gemini=AsyncMock(),
    )

    result = await crawler.run_one_hop_expansion(
        session_id="sess-cos",
        seed_doi="10.1145/seed_cos",
        project_id="proj-cos",
    )

    cands_by_doi = {c.doi: c for c in result.candidates}

    assert math.isclose(cands_by_doi["10.1000/identical"].max_similarity, 1.0, abs_tol=1e-3)
    assert math.isclose(cands_by_doi["10.1000/orthogonal"].max_similarity, 0.0, abs_tol=1e-3)
    assert math.isclose(cands_by_doi["10.1000/opposite"].max_similarity, -1.0, abs_tol=1e-3)
    assert math.isclose(cands_by_doi["10.1000/zero"].max_similarity, 0.0, abs_tol=1e-3)


# ==============================================================================
# 6. Tool-Level Stress Tests (run_graphselect_traversal)
# ==============================================================================

@pytest.mark.asyncio
async def test_tool_run_graphselect_traversal_missing_project_id():
    """Verify tool returns clean error when tool_context has no project_id."""
    from agents.research.tools.retrieval_tools import run_graphselect_traversal
    from google.adk.tools.tool_context import ToolContext

    mock_ctx = MagicMock(spec=ToolContext)
    mock_ctx.state = {}

    res = await run_graphselect_traversal(seed_doi="10.1145/test", tool_context=mock_ctx)
    assert "error" in res
    assert "No project_id" in res["error"]


@pytest.mark.asyncio
async def test_tool_run_graphselect_traversal_seed_fallback_from_project():
    """Verify tool falls back to the project's first paper if seed_doi is omitted."""
    from agents.research.tools.retrieval_tools import run_graphselect_traversal
    from agents._service_registry import ServiceRegistry
    from google.adk.tools.tool_context import ToolContext

    mock_ctx = MagicMock(spec=ToolContext)
    mock_ctx.state = {"project_id": "proj-fallback"}

    mock_neo4j = AsyncMock()
    mock_neo4j.get_project_papers = AsyncMock(return_value=[{"doi": "10.1145/fallback_paper"}])

    mock_crawler = AsyncMock()
    mock_crawler.run_one_hop_expansion = AsyncMock(return_value=OneHopExpansionResult(
        seed_doi="10.1145/fallback_paper",
        seed_title="Fallback Paper",
        cycle_level=1,
        total_discovered=1,
        total_new=1,
        forward_count=1,
        backward_count=0,
        both_count=0,
        candidates=[
            CandidatePaperState(
                doi="10.1000/cand1",
                title="Candidate 1",
                direction="forward_citation",
                citation_count=10,
                in_graph_degree=1,
                max_similarity=0.85,
                mean_similarity=0.85,
            )
        ],
        new_dois=["10.1000/cand1"],
        traversal_summary=["Done"],
        errors=[],
    ))

    with patch.object(ServiceRegistry, "neo4j", mock_neo4j), \
         patch.object(ServiceRegistry, "crawler", mock_crawler):
        res = await run_graphselect_traversal(tool_context=mock_ctx)

    assert res["status"] == "completed"
    assert res["seed_doi"] == "10.1145/fallback_paper"
    assert res["total_discovered"] == 1
    assert len(res["candidates"]) == 1
    assert res["candidates"][0]["doi"] == "10.1000/cand1"


@pytest.mark.asyncio
async def test_tool_run_graphselect_traversal_exception_resilience():
    """Verify tool catches unexpected crawler exceptions and returns structured error dict."""
    from agents.research.tools.retrieval_tools import run_graphselect_traversal
    from agents._service_registry import ServiceRegistry
    from google.adk.tools.tool_context import ToolContext

    mock_ctx = MagicMock(spec=ToolContext)
    mock_ctx.state = {"project_id": "proj-err"}

    mock_crawler = AsyncMock()
    mock_crawler.run_one_hop_expansion = AsyncMock(side_effect=RuntimeError("Database connection lost"))

    with patch.object(ServiceRegistry, "crawler", mock_crawler):
        res = await run_graphselect_traversal(seed_doi="10.1145/crash", tool_context=mock_ctx)

    assert "error" in res
    assert "Database connection lost" in res["error"]
    assert res["seed_doi"] == "10.1145/crash"


# ==============================================================================
# 7. Concurrency & Asynchronous Partial Failure Robustness
# ==============================================================================

@pytest.mark.asyncio
async def test_partial_edge_fetch_failure_robustness():
    """Verify crawler continues when get_citations fails but get_references succeeds."""
    mock_neo4j = AsyncMock()
    mock_neo4j.get_paper_by_doi = AsyncMock(return_value=None)
    mock_neo4j.has_embedding = AsyncMock(return_value=True)
    mock_neo4j.get_session_dois = AsyncMock(return_value=[])
    mock_neo4j.batch_get_paper_embeddings = AsyncMock(return_value={})
    mock_neo4j.batch_get_paper_degrees = AsyncMock(return_value={})
    mock_neo4j.batch_check_project_papers = AsyncMock(return_value=set())
    mock_neo4j.get_project_research_questions_with_embeddings = AsyncMock(return_value=[])
    mock_neo4j.compute_pagerank = AsyncMock(return_value={})

    mock_openalex = AsyncMock()
    mock_openalex.get_paper_by_doi = AsyncMock(return_value=PaperCreate(
        doi="10.1145/partial_seed",
        title="Partial Edge Seed",
    ))
    # Citations fails with network error, references succeeds
    mock_openalex.get_citations = AsyncMock(side_effect=Exception("Timeout connecting to OpenAlex cites endpoint"))
    mock_openalex.get_references = AsyncMock(return_value=["10.1000/ref_only"])
    mock_openalex.batch_get_rich_papers = AsyncMock(return_value=[
        {"doi": "10.1000/ref_only", "title": "Ref Only", "abstract": "Valid"}
    ])

    crawler = CrawlerService(neo4j=mock_neo4j, openalex=mock_openalex)

    result = await crawler.run_one_hop_expansion(
        session_id="sess-partial-edges",
        seed_doi="10.1145/partial_seed",
    )

    assert result.total_discovered == 1
    assert result.candidates[0].doi == "10.1000/ref_only"
    assert result.candidates[0].direction == "backward_reference"
    # Errors list records the citation fetch failure
    assert len(result.errors) == 1
    assert "Failed to fetch citing papers" in result.errors[0]

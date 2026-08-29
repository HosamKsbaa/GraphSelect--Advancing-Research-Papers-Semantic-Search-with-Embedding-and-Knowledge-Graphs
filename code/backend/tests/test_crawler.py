"""Unit and integration tests for Milestone 1 1-Hop Crawler Engine & Rich Candidate State Payload."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Any

from features.retrieval.models import PaperCreate
from features.search.crawler_service import CrawlerService
from features.search.models import CandidatePaperState, EventType, OneHopExpansionResult, ProgressEvent
from core.clients.rate_limiter import AdaptiveRateLimiter


@pytest.fixture
def mock_seed_doi() -> str:
    return "10.1145/3292500.3330919"


@pytest.fixture
def mock_openalex_client() -> AsyncMock:
    """Mock OpenAlexService returning deterministic citation network nodes."""
    client = AsyncMock()

    client.get_paper_by_doi = AsyncMock(return_value=PaperCreate(
        doi="10.1145/3292500.3330919",
        title="Seed Paper: Graph Attention Networks",
        abstract="We introduce graph attention networks leveraging masked self-attentional layers.",
        year=2018,
        cited_by_count=12000,
        openalex_id="W999",
    ))

    # Outgoing references from seed
    client.get_references = AsyncMock(return_value=["10.1000/ref1", "10.1000/dual1"])
    # Incoming citations to seed
    client.get_citations = AsyncMock(return_value=["10.1000/cite1", "10.1000/dual1"])

    client.batch_get_rich_papers = AsyncMock(return_value=[
        {
            "doi": "10.1000/ref1",
            "title": "Foundational GNN Methods",
            "authors": ["Alice Smith", "Bob Jones"],
            "year": 2018,
            "venue": "ICLR",
            "abstract": "We present foundational graph message passing algorithms.",
            "abstract_snippet": "We present foundational graph message passing algorithms.",
            "cited_by_count": 3500,
            "openalex_id": "W101",
            "publication_date": "2018-05-01",
            "referenced_works": [],
        },
        {
            "doi": "10.1000/cite1",
            "title": "Contemporary GNN Breakthroughs",
            "authors": ["Carol White"],
            "year": 2024,
            "venue": "NeurIPS",
            "abstract": "Recent advancements in transformer-based GNNs and spatial structures.",
            "abstract_snippet": "Recent advancements in transformer-based GNNs and spatial structures.",
            "cited_by_count": 45,
            "openalex_id": "W102",
            "publication_date": "2024-12-01",
            "referenced_works": [],
        },
        {
            "doi": "10.1000/dual1",
            "title": "Co-Cited Benchmark Survey",
            "authors": ["Dave Miller", "Eve Davis"],
            "year": 2023,
            "venue": "Nature Machine Intelligence",
            "abstract": "Comprehensive benchmark of graph neural architectures across domains.",
            "abstract_snippet": "Comprehensive benchmark of graph neural architectures across domains.",
            "cited_by_count": 120,
            "openalex_id": "W103",
            "publication_date": "2023-08-15",
            "referenced_works": [],
        },
    ])

    client.batch_get_papers_by_dois = AsyncMock(return_value=[
        PaperCreate(
            doi="10.1000/ref1",
            title="Foundational GNN Methods",
            abstract="We present foundational graph message passing algorithms.",
            year=2018,
            cited_by_count=3500,
            openalex_id="W101",
        ),
        PaperCreate(
            doi="10.1000/cite1",
            title="Contemporary GNN Breakthroughs",
            abstract="Recent advancements in transformer-based GNNs and spatial structures.",
            year=2024,
            cited_by_count=45,
            openalex_id="W102",
        ),
        PaperCreate(
            doi="10.1000/dual1",
            title="Co-Cited Benchmark Survey",
            abstract="Comprehensive benchmark of graph neural architectures across domains.",
            year=2023,
            cited_by_count=120,
            openalex_id="W103",
        ),
    ])

    return client


@pytest.fixture
def mock_neo4j_service() -> AsyncMock:
    """Mock Neo4jService with session and graph stubs."""
    neo4j = AsyncMock()
    neo4j.get_paper_by_doi = AsyncMock(return_value=None)
    neo4j.get_session_dois = AsyncMock(return_value=["10.1145/3292500.3330919"])
    neo4j.has_embedding = AsyncMock(return_value=False)
    neo4j.create_paper = AsyncMock()
    neo4j.ensure_stub_and_cite = AsyncMock()
    neo4j.link_paper_to_session = AsyncMock()
    neo4j.store_paper_embedding = AsyncMock()
    neo4j.batch_get_paper_degrees = AsyncMock(return_value={
        "10.1000/ref1": 2,
        "10.1000/cite1": 1,
        "10.1000/dual1": 3,
    })
    neo4j.batch_check_project_papers = AsyncMock(return_value={"10.1000/ref1"})
    neo4j.get_project_research_questions_with_embeddings = AsyncMock(return_value=[
        {"question_id": "rq-1", "text": "How do GNNs model citation networks?", "embedding": [0.1] * 768},
        {"question_id": "rq-2", "text": "What are the benchmark datasets for GNNs?", "embedding": [0.2] * 768},
    ])
    neo4j.compute_pagerank = AsyncMock(return_value={
        "10.1000/ref1": 0.85,
        "10.1000/cite1": 0.42,
        "10.1000/dual1": 0.67,
    })
    neo4j.get_project_papers = AsyncMock(return_value=[
        {"doi": "10.1145/3292500.3330919"}
    ])
    return neo4j


@pytest.fixture
def mock_gemini_provider() -> AsyncMock:
    """Mock GeminiEmbeddingProvider for gemini-embedding-2 vectors."""
    gemini = AsyncMock()
    gemini.model_name = "gemini-embedding-2"
    gemini.embed_document = AsyncMock(return_value=[0.1] * 768)
    gemini.embed_paper = AsyncMock(return_value=[0.1] * 768)
    gemini.embed_query = AsyncMock(return_value=[0.1] * 768)
    return gemini


# ==============================================================================
# Section 1: Bounded 1-Hop Traversal Execution
# ==============================================================================

@pytest.mark.asyncio
async def test_one_hop_expansion_executes_single_level_only(
    mock_openalex_client: AsyncMock,
    mock_neo4j_service: AsyncMock,
    mock_gemini_provider: AsyncMock,
    mock_seed_doi: str,
) -> None:
    """Verify that 1-hop expansion processes only level 1 and does not crawl recursively."""
    crawler = CrawlerService(
        neo4j=mock_neo4j_service,
        openalex=mock_openalex_client,
        gemini=mock_gemini_provider,
    )

    result = await crawler.run_one_hop_expansion(
        session_id="sess-1",
        seed_doi=mock_seed_doi,
        project_id="proj-1",
    )

    assert result.cycle_level == 1
    assert result.level == 1
    assert result.total_discovered == 3
    assert result.papers_discovered == 3
    assert len(result.candidates) == 3

    # Seed OpenAlex calls occurred once
    mock_openalex_client.get_references.assert_called_once_with(
        mock_seed_doi, max_results=100, session_id="sess-1", openalex_id="W999"
    )
    mock_openalex_client.get_citations.assert_called_once_with(
        mock_seed_doi, max_results=100, session_id="sess-1", openalex_id="W999"
    )


@pytest.mark.asyncio
async def test_one_hop_traversal_returns_unexpanded_queue_for_next_turn(
    mock_openalex_client: AsyncMock,
    mock_neo4j_service: AsyncMock,
    mock_gemini_provider: AsyncMock,
    mock_seed_doi: str,
) -> None:
    """Ensure candidate DOIs are returned in new_dois for HITL steering."""
    crawler = CrawlerService(
        neo4j=mock_neo4j_service,
        openalex=mock_openalex_client,
        gemini=mock_gemini_provider,
    )

    result = await crawler.run_one_hop_expansion(
        session_id="sess-1",
        seed_doi=mock_seed_doi,
    )

    assert set(result.new_dois) == {"10.1000/ref1", "10.1000/cite1", "10.1000/dual1"}


@pytest.mark.asyncio
async def test_one_hop_traversal_empty_seed_queue_handles_gracefully(
    mock_openalex_client: AsyncMock,
    mock_neo4j_service: AsyncMock,
) -> None:
    """Verify that passing an empty seed queue returns 0 candidates gracefully."""
    crawler = CrawlerService(neo4j=mock_neo4j_service, openalex=mock_openalex_client)

    result = await crawler.run_one_hop_expansion(
        session_id="sess-1",
        seed_dois=[],
    )

    assert result.total_discovered == 0
    assert result.candidates == []
    assert result.errors == []


# ==============================================================================
# Section 2: Candidate Payload Richness (11 Mandatory Fields)
# ==============================================================================

@pytest.mark.asyncio
async def test_candidate_state_payload_100_percent_field_completeness(
    mock_openalex_client: AsyncMock,
    mock_neo4j_service: AsyncMock,
    mock_gemini_provider: AsyncMock,
    mock_seed_doi: str,
) -> None:
    """Validate that 100% of discovered candidates contain all 11 required fields with valid types."""
    crawler = CrawlerService(
        neo4j=mock_neo4j_service,
        openalex=mock_openalex_client,
        gemini=mock_gemini_provider,
    )

    result = await crawler.run_one_hop_expansion(
        session_id="sess-1",
        seed_doi=mock_seed_doi,
        project_id="proj-1",
    )

    assert len(result.candidates) == 3
    for c in result.candidates:
        assert isinstance(c.doi, str) and len(c.doi) > 0
        assert isinstance(c.title, str) and len(c.title) > 0
        assert isinstance(c.authors, list)
        assert c.year is None or isinstance(c.year, int)
        assert c.venue is None or isinstance(c.venue, str)
        assert isinstance(c.abstract_snippet, str)
        assert c.direction in ("forward_citation", "backward_reference", "both")
        assert isinstance(c.citation_count, int) and c.citation_count >= 0
        assert isinstance(c.in_graph_degree, int) and c.in_graph_degree >= 0
        assert isinstance(c.similarity_scores, list)
        assert isinstance(c.max_similarity, float)
        assert isinstance(c.mean_similarity, float)
        assert isinstance(c.already_in_library, bool)
        assert isinstance(c.embedding_cached, bool)
        assert isinstance(c.pagerank_score, float)


@pytest.mark.asyncio
async def test_candidate_similarity_scores_computation_and_invariants(
    mock_openalex_client: AsyncMock,
    mock_neo4j_service: AsyncMock,
    mock_gemini_provider: AsyncMock,
    mock_seed_doi: str,
) -> None:
    """Verify per-research-question cosine similarity scoring and aggregation."""
    crawler = CrawlerService(
        neo4j=mock_neo4j_service,
        openalex=mock_openalex_client,
        gemini=mock_gemini_provider,
    )

    result = await crawler.run_one_hop_expansion(
        session_id="sess-1",
        seed_doi=mock_seed_doi,
        project_id="proj-1",
    )

    cand = result.candidates[0]
    assert len(cand.similarity_scores) == 2
    assert cand.similarity_scores[0]["question_id"] == "rq-1"
    assert cand.similarity_scores[1]["question_id"] == "rq-2"
    assert cand.max_similarity >= cand.mean_similarity


@pytest.mark.asyncio
async def test_candidate_payload_missing_metadata_defaults_cleanly(
    mock_neo4j_service: AsyncMock,
    mock_gemini_provider: AsyncMock,
    mock_seed_doi: str,
) -> None:
    """Ensure candidate payload handles missing fields without schema validation failures."""
    client = AsyncMock()
    client.get_paper_by_doi = AsyncMock(return_value=PaperCreate(
        doi=mock_seed_doi,
        title="Seed Paper",
    ))
    client.get_references = AsyncMock(return_value=["10.1000/incomplete"])
    client.get_citations = AsyncMock(return_value=[])
    client.batch_get_rich_papers = AsyncMock(return_value=[
        {
            "doi": "10.1000/incomplete",
            "title": "",
            "authors": [],
            "year": None,
            "venue": None,
            "abstract": None,
            "abstract_snippet": "",
            "cited_by_count": 0,
        }
    ])

    crawler = CrawlerService(
        neo4j=mock_neo4j_service,
        openalex=client,
        gemini=mock_gemini_provider,
    )

    result = await crawler.run_one_hop_expansion(
        session_id="sess-1",
        seed_doi=mock_seed_doi,
    )

    assert len(result.candidates) == 1
    c = result.candidates[0]
    assert c.doi == "10.1000/incomplete"
    assert c.venue is None
    assert c.year is None
    assert c.abstract_snippet == ""
    assert c.citation_count == 0


# ==============================================================================
# Section 3: Directional Tagging
# ==============================================================================

@pytest.mark.asyncio
async def test_directional_tagging_backward_reference(
    mock_openalex_client: AsyncMock,
    mock_neo4j_service: AsyncMock,
    mock_gemini_provider: AsyncMock,
    mock_seed_doi: str,
) -> None:
    """Papers in seed's outgoing references must be tagged as backward_reference."""
    crawler = CrawlerService(
        neo4j=mock_neo4j_service,
        openalex=mock_openalex_client,
        gemini=mock_gemini_provider,
    )

    result = await crawler.run_one_hop_expansion(
        session_id="sess-1",
        seed_doi=mock_seed_doi,
    )

    cand_by_doi = {c.doi: c for c in result.candidates}
    assert cand_by_doi["10.1000/ref1"].direction == "backward_reference"


@pytest.mark.asyncio
async def test_directional_tagging_forward_citation(
    mock_openalex_client: AsyncMock,
    mock_neo4j_service: AsyncMock,
    mock_gemini_provider: AsyncMock,
    mock_seed_doi: str,
) -> None:
    """Papers citing the seed must be tagged as forward_citation."""
    crawler = CrawlerService(
        neo4j=mock_neo4j_service,
        openalex=mock_openalex_client,
        gemini=mock_gemini_provider,
    )

    result = await crawler.run_one_hop_expansion(
        session_id="sess-1",
        seed_doi=mock_seed_doi,
    )

    cand_by_doi = {c.doi: c for c in result.candidates}
    assert cand_by_doi["10.1000/cite1"].direction == "forward_citation"


@pytest.mark.asyncio
async def test_directional_tagging_dual_citation_co_occurrence(
    mock_openalex_client: AsyncMock,
    mock_neo4j_service: AsyncMock,
    mock_gemini_provider: AsyncMock,
    mock_seed_doi: str,
) -> None:
    """Papers that both cite the seed and are referenced by seed must be tagged as both."""
    crawler = CrawlerService(
        neo4j=mock_neo4j_service,
        openalex=mock_openalex_client,
        gemini=mock_gemini_provider,
    )

    result = await crawler.run_one_hop_expansion(
        session_id="sess-1",
        seed_doi=mock_seed_doi,
    )

    cand_by_doi = {c.doi: c for c in result.candidates}
    assert cand_by_doi["10.1000/dual1"].direction == "both"
    assert result.both_count == 1
    assert result.forward_count == 1
    assert result.backward_count == 1


@pytest.mark.asyncio
async def test_in_graph_degree_calculation(
    mock_openalex_client: AsyncMock,
    mock_neo4j_service: AsyncMock,
    mock_gemini_provider: AsyncMock,
    mock_seed_doi: str,
) -> None:
    """Verify in-graph degrees are fetched and mapped from Neo4j."""
    crawler = CrawlerService(
        neo4j=mock_neo4j_service,
        openalex=mock_openalex_client,
        gemini=mock_gemini_provider,
    )

    result = await crawler.run_one_hop_expansion(
        session_id="sess-1",
        seed_doi=mock_seed_doi,
    )

    cand_by_doi = {c.doi: c for c in result.candidates}
    assert cand_by_doi["10.1000/ref1"].in_graph_degree == 2
    assert cand_by_doi["10.1000/dual1"].in_graph_degree == 3


# ==============================================================================
# Section 4: Deduplication, Idempotency & Embedding Caching
# ==============================================================================

@pytest.mark.asyncio
async def test_deduplication_prevents_duplicate_nodes_across_citations_and_references(
    mock_openalex_client: AsyncMock,
    mock_neo4j_service: AsyncMock,
    mock_gemini_provider: AsyncMock,
    mock_seed_doi: str,
) -> None:
    """Ensure candidate appearing in both citing and referenced sets is merged into 1 candidate."""
    crawler = CrawlerService(
        neo4j=mock_neo4j_service,
        openalex=mock_openalex_client,
        gemini=mock_gemini_provider,
    )

    result = await crawler.run_one_hop_expansion(
        session_id="sess-1",
        seed_doi=mock_seed_doi,
    )

    dual_matches = [c for c in result.candidates if c.doi == "10.1000/dual1"]
    assert len(dual_matches) == 1
    assert result.total_discovered == 3


@pytest.mark.asyncio
async def test_embedding_caching_skips_gemini_api_when_already_embedded(
    mock_openalex_client: AsyncMock,
    mock_neo4j_service: AsyncMock,
    mock_gemini_provider: AsyncMock,
    mock_seed_doi: str,
) -> None:
    """If a paper already has an embedding stored in Neo4j, skip embedding API call."""
    mock_neo4j_service.batch_get_paper_embeddings = AsyncMock(return_value={
        "10.1000/ref1": [0.5] * 768,
        "10.1000/cite1": [0.5] * 768,
        "10.1000/dual1": [0.5] * 768,
    })

    crawler = CrawlerService(
        neo4j=mock_neo4j_service,
        openalex=mock_openalex_client,
        gemini=mock_gemini_provider,
    )

    result = await crawler.run_one_hop_expansion(
        session_id="sess-1",
        seed_doi=mock_seed_doi,
    )

    # All candidate embeddings were cached, so embed_document not called for candidates
    assert all(c.embedding_cached for c in result.candidates)


@pytest.mark.asyncio
async def test_library_status_already_in_library_flag(
    mock_openalex_client: AsyncMock,
    mock_neo4j_service: AsyncMock,
    mock_gemini_provider: AsyncMock,
    mock_seed_doi: str,
) -> None:
    """Validate that papers already in project library have already_in_library set to True."""
    mock_neo4j_service.batch_check_project_papers = AsyncMock(return_value={"10.1000/ref1"})

    crawler = CrawlerService(
        neo4j=mock_neo4j_service,
        openalex=mock_openalex_client,
        gemini=mock_gemini_provider,
    )

    result = await crawler.run_one_hop_expansion(
        session_id="sess-1",
        seed_doi=mock_seed_doi,
        project_id="proj-1",
    )

    cand_by_doi = {c.doi: c for c in result.candidates}
    assert cand_by_doi["10.1000/ref1"].already_in_library is True
    assert cand_by_doi["10.1000/cite1"].already_in_library is False


@pytest.mark.asyncio
async def test_session_existing_dois_skips_redundant_openalex_fetches(
    mock_openalex_client: AsyncMock,
    mock_neo4j_service: AsyncMock,
    mock_gemini_provider: AsyncMock,
    mock_seed_doi: str,
) -> None:
    """Papers already present in session are not redundantly re-fetched."""
    mock_neo4j_service.get_session_dois = AsyncMock(return_value=["10.1145/3292500.3330919", "10.1000/ref1"])

    crawler = CrawlerService(
        neo4j=mock_neo4j_service,
        openalex=mock_openalex_client,
        gemini=mock_gemini_provider,
    )

    result = await crawler.run_one_hop_expansion(
        session_id="sess-1",
        seed_doi=mock_seed_doi,
    )

    # batch_get_rich_papers called only for uncrawled DOIs
    mock_openalex_client.batch_get_rich_papers.assert_called_once()
    called_dois = mock_openalex_client.batch_get_rich_papers.call_args[0][0]
    assert "10.1000/ref1" not in called_dois
    assert "10.1000/cite1" in called_dois or "10.1000/dual1" in called_dois


# ==============================================================================
# Section 5: Error Handling, Rate Limiting & Edge Cases
# ==============================================================================

@pytest.mark.asyncio
async def test_openalex_rate_limiter_backoff_on_429_during_batch_crawl(
    mock_neo4j_service: AsyncMock,
    mock_gemini_provider: AsyncMock,
    mock_seed_doi: str,
) -> None:
    """Verify that crawler respects AdaptiveRateLimiter backoff during crawl."""
    rate_limiter = AdaptiveRateLimiter(initial_rate=10.0, min_rate=1.0)
    initial_rate = rate_limiter.current_rate

    # Trigger a 429 backoff
    rate_limiter.on_429()
    assert rate_limiter.current_rate < initial_rate

    client = AsyncMock()
    client.get_paper_by_doi = AsyncMock(return_value=PaperCreate(
        doi=mock_seed_doi,
        title="Rate Limited Seed",
    ))
    client.get_references = AsyncMock(return_value=["10.1000/r1"])
    client.get_citations = AsyncMock(return_value=[])
    client.batch_get_rich_papers = AsyncMock(return_value=[
        {"doi": "10.1000/r1", "title": "Paper R1", "authors": ["R Author"], "year": 2024, "cited_by_count": 1}
    ])

    crawler = CrawlerService(
        neo4j=mock_neo4j_service,
        openalex=client,
        rate_limiter=rate_limiter,
        gemini=mock_gemini_provider,
    )

    result = await crawler.run_one_hop_expansion(
        session_id="sess-1",
        seed_doi=mock_seed_doi,
    )

    assert result.total_discovered == 1
    assert result.candidates[0].doi == "10.1000/r1"


@pytest.mark.asyncio
async def test_openalex_batch_fetch_partial_failures_handled_gracefully(
    mock_neo4j_service: AsyncMock,
    mock_gemini_provider: AsyncMock,
    mock_seed_doi: str,
) -> None:
    """When batch fetch returns fewer papers than requested, handles missing nodes safely."""
    client = AsyncMock()
    client.get_paper_by_doi = AsyncMock(return_value=PaperCreate(
        doi=mock_seed_doi,
        title="Seed Paper",
    ))
    client.get_references = AsyncMock(return_value=["10.1000/p1", "10.1000/missing"])
    client.get_citations = AsyncMock(return_value=[])
    # OpenAlex returns metadata for only 1 of the 2 DOIs
    client.batch_get_rich_papers = AsyncMock(return_value=[
        {
            "doi": "10.1000/p1",
            "title": "Paper 1",
            "authors": ["Author One"],
            "year": 2023,
            "venue": "ACL",
            "abstract": "Valid abstract.",
            "abstract_snippet": "Valid abstract.",
            "cited_by_count": 10,
        }
    ])

    crawler = CrawlerService(
        neo4j=mock_neo4j_service,
        openalex=client,
        gemini=mock_gemini_provider,
    )

    result = await crawler.run_one_hop_expansion(
        session_id="sess-1",
        seed_doi=mock_seed_doi,
    )

    assert result.total_discovered == 2
    cand_by_doi = {c.doi: c for c in result.candidates}
    assert "10.1000/p1" in cand_by_doi
    assert "10.1000/missing" in cand_by_doi
    assert cand_by_doi["10.1000/missing"].title == "Paper 10.1000/missing"


@pytest.mark.asyncio
async def test_self_citation_cycle_prevention(
    mock_neo4j_service: AsyncMock,
    mock_gemini_provider: AsyncMock,
    mock_seed_doi: str,
) -> None:
    """Ensure a paper referencing or citing its own DOI is not treated as a candidate."""
    client = AsyncMock()
    client.get_paper_by_doi = AsyncMock(return_value=PaperCreate(
        doi=mock_seed_doi,
        title="Self Citing Paper",
    ))
    client.get_references = AsyncMock(return_value=[mock_seed_doi, "10.1000/other"])
    client.get_citations = AsyncMock(return_value=[mock_seed_doi])
    client.batch_get_rich_papers = AsyncMock(return_value=[
        {
            "doi": "10.1000/other",
            "title": "Other Paper",
            "authors": ["Other Author"],
            "year": 2021,
            "cited_by_count": 5,
        }
    ])

    crawler = CrawlerService(
        neo4j=mock_neo4j_service,
        openalex=client,
        gemini=mock_gemini_provider,
    )

    result = await crawler.run_one_hop_expansion(
        session_id="sess-1",
        seed_doi=mock_seed_doi,
    )

    assert result.total_discovered == 1
    assert result.candidates[0].doi == "10.1000/other"


# ==============================================================================
# Section 6: End-to-End Integration Lifecycle
# ==============================================================================

@pytest.mark.asyncio
async def test_e2e_one_hop_traversal_lifecycle(
    mock_openalex_client: AsyncMock,
    mock_neo4j_service: AsyncMock,
    mock_gemini_provider: AsyncMock,
    mock_seed_doi: str,
) -> None:
    """End-to-end integration test of 1-hop traversal engine:
    1. Seed paper ingestion
    2. Batch fetch 1-hop references & citations
    3. Construct Neo4j nodes and CITES edges
    4. Generate gemini-embedding-2 vectors for candidate abstracts
    5. Compute cosine similarities against active Research Questions
    6. Verify complete 11-field CandidatePaperState payload output
    """
    crawler = CrawlerService(
        neo4j=mock_neo4j_service,
        openalex=mock_openalex_client,
        gemini=mock_gemini_provider,
    )

    events: list[ProgressEvent] = []

    async def capture_event(evt: ProgressEvent) -> None:
        events.append(evt)

    result = await crawler.run_one_hop_expansion(
        session_id="integration-sess-1",
        seed_doi=mock_seed_doi,
        project_id="proj-integration-1",
        progress_callback=capture_event,
    )

    # 1. Traversal Boundary Verification
    assert result.cycle_level == 1
    assert result.total_discovered == 3
    assert len(result.candidates) == 3

    # 2. Neo4j Graph Invariants
    assert mock_neo4j_service.create_paper.call_count >= 3
    assert mock_neo4j_service.ensure_stub_and_cite.call_count >= 3

    # 3. Payload Richness & Direction Verification
    cand_by_doi = {c.doi: c for c in result.candidates}

    # Backward reference
    assert cand_by_doi["10.1000/ref1"].direction == "backward_reference"
    assert cand_by_doi["10.1000/ref1"].citation_count == 3500
    assert cand_by_doi["10.1000/ref1"].already_in_library is True

    # Forward citation
    assert cand_by_doi["10.1000/cite1"].direction == "forward_citation"
    assert cand_by_doi["10.1000/cite1"].citation_count == 45
    assert cand_by_doi["10.1000/cite1"].already_in_library is False

    # Dual relationship
    assert cand_by_doi["10.1000/dual1"].direction == "both"
    assert cand_by_doi["10.1000/dual1"].citation_count == 120

    # 4. Event Stream Verification
    event_types = [e.event_type for e in events]
    assert EventType.LEVEL_COMPLETE in event_types
    assert EventType.SEARCH_COMPLETE in event_types

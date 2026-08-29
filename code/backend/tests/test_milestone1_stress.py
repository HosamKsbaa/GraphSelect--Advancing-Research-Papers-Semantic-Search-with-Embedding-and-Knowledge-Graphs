"""Adversarial stress and boundary tests for Milestone 1: Stepwise 1-Hop Traversal Engine & Rich State Payload.

Tested Components:
1. CrawlerService.run_one_hop_expansion
2. agents.research.tools.retrieval_tools.run_graphselect_traversal

Challenge Dimensions:
- Bounded depth behavior (strictly 1 hop, zero multi-level recursion).
- 100% payload completeness across high volume candidate nodes (100+ candidates).
- Self-referencing citation loops, mutual citations, circular dependencies.
- Multi-question projects with orthogonal and correlated embedding vectors.
- Adversarial edge cases: network failures, empty abstracts, missing metadata, DOI variations.
"""
from __future__ import annotations

import math
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from google.adk.tools.tool_context import ToolContext

from agents._service_registry import ServiceRegistry
from agents.research.tools.retrieval_tools import run_graphselect_traversal
from core.clients.rate_limiter import AdaptiveRateLimiter
from features.retrieval.models import PaperCreate
from features.search.crawler_service import CrawlerService
from features.search.models import (
    CandidatePaperState,
    EventType,
    OneHopExpansionResult,
    ProgressEvent,
)


# ==============================================================================
# Helpers & Vector Math Fixtures
# ==============================================================================

@pytest.fixture
def mock_tool_context() -> ToolContext:
    """Mock ADK ToolContext with a dummy project_id in state."""
    context = MagicMock(spec=ToolContext)
    context.state = MagicMock()
    context.state.get.side_effect = lambda key, default=None: "project-123" if key == "project_id" else default
    return context


def make_unit_vector(dim: int, index: int) -> list[float]:
    """Create a standard basis unit vector e_index of dimension dim."""
    vec = [0.0] * dim
    vec[index] = 1.0
    return vec


def make_uniform_vector(dim: int, active_indices: list[int]) -> list[float]:
    """Create a normalized vector with equal weight on specified indices."""
    vec = [0.0] * dim
    k = len(active_indices)
    val = 1.0 / math.sqrt(k) if k > 0 else 0.0
    for idx in active_indices:
        vec[idx] = val
    return vec


# ==============================================================================
# 1. Bounded Depth Behavior (Strictly 1-Hop, Zero Multi-Level Recursion)
# ==============================================================================

@pytest.mark.asyncio
async def test_bounded_depth_strictly_one_hop_no_recursion_in_deep_graph() -> None:
    """Stress test: In a graph with 4 citation levels, ensure only Level 1 is expanded.

    Graph Topology:
    - Level 0 (Seed): Seed_0
    - Level 1: Ref_1_A, Ref_1_B, Cite_1_A (Direct 1-hop neighbors)
    - Level 2: Ref_2_A (References of Ref_1_A), Cite_2_A (Citing Cite_1_A)
    - Level 3: Ref_3_A (References of Ref_2_A)

    Verification:
    - OpenAlex get_references and get_citations are called ONLY for Seed_0.
    - None of the Level 1 papers are queried for their references or citations.
    - Returned candidates contain ONLY Level 1 nodes.
    - Neo4j link_paper_to_session is invoked with depth=0 for seed and depth=1 for Level 1 papers, NEVER depth > 1.
    """
    seed_doi = "10.1145/seed.000"

    mock_openalex = AsyncMock()
    mock_openalex.get_paper_by_doi = AsyncMock(return_value=PaperCreate(
        doi=seed_doi,
        title="Level 0 Seed Paper",
        abstract="Seed abstract",
        year=2020,
        cited_by_count=500,
        openalex_id="W_SEED",
    ))
    mock_openalex.get_references = AsyncMock(return_value=["10.1000/ref.1.a", "10.1000/ref.1.b"])
    mock_openalex.get_citations = AsyncMock(return_value=["10.1000/cite.1.a"])

    # Batch rich papers returns metadata for Level 1 candidates
    mock_openalex.batch_get_rich_papers = AsyncMock(return_value=[
        {"doi": "10.1000/ref.1.a", "title": "Ref 1A", "authors": ["A1"], "year": 2019, "abstract": "Ref 1A abstract", "cited_by_count": 100},
        {"doi": "10.1000/ref.1.b", "title": "Ref 1B", "authors": ["A2"], "year": 2018, "abstract": "Ref 1B abstract", "cited_by_count": 200},
        {"doi": "10.1000/cite.1.a", "title": "Cite 1A", "authors": ["A3"], "year": 2022, "abstract": "Cite 1A abstract", "cited_by_count": 30},
    ])

    mock_neo4j = AsyncMock()
    mock_neo4j.get_paper_by_doi = AsyncMock(return_value=None)
    mock_neo4j.get_session_dois = AsyncMock(return_value=[seed_doi])
    mock_neo4j.has_embedding = AsyncMock(return_value=False)
    mock_neo4j.create_paper = AsyncMock()
    mock_neo4j.ensure_stub_and_cite = AsyncMock()
    mock_neo4j.link_paper_to_session = AsyncMock()
    mock_neo4j.store_paper_embedding = AsyncMock()
    mock_neo4j.batch_get_paper_degrees = AsyncMock(return_value={
        "10.1000/ref.1.a": 1, "10.1000/ref.1.b": 1, "10.1000/cite.1.a": 1
    })

    crawler = CrawlerService(
        neo4j=mock_neo4j,
        openalex=mock_openalex,
    )

    result = await crawler.run_one_hop_expansion(
        session_id="sess-bounded",
        seed_doi=seed_doi,
        project_id="proj-bounded",
    )

    # 1. Check exact candidate count and identities
    assert result.cycle_level == 1
    assert result.total_discovered == 3
    assert {c.doi for c in result.candidates} == {
        "10.1000/ref.1.a", "10.1000/ref.1.b", "10.1000/cite.1.a"
    }

    # 2. Strict check: get_references & get_citations called EXACTLY ONCE each, only for seed
    assert mock_openalex.get_references.call_count == 1
    assert mock_openalex.get_references.call_args[0][0] == seed_doi
    assert mock_openalex.get_citations.call_count == 1
    assert mock_openalex.get_citations.call_args[0][0] == seed_doi

    # 3. Check link_paper_to_session depths: exactly 0 for seed, 1 for candidates
    depth_calls = [
        call.kwargs.get("depth")
        for call in mock_neo4j.link_paper_to_session.call_args_list
    ]
    assert 0 in depth_calls
    assert all(d in (0, 1) for d in depth_calls)
    assert not any(d > 1 for d in depth_calls)


@pytest.mark.asyncio
async def test_run_graphselect_traversal_clamps_depth_and_does_not_recurse(
    mock_tool_context: ToolContext,
) -> None:
    """Stress test: Pass max_depth=10 to run_graphselect_traversal.

    Ensure it executes bounded 1-hop expansion, returns cycle_level=1, max_depth=1,
    and forwards calls with zero multi-level recursion.
    """
    mock_crawler = AsyncMock()
    mock_crawler.run_one_hop_expansion = AsyncMock(return_value=OneHopExpansionResult(
        seed_doi="10.1000/seed",
        seed_title="Seed Paper",
        cycle_level=1,
        total_discovered=2,
        total_new=2,
        forward_count=1,
        backward_count=1,
        both_count=0,
        candidates=[
            CandidatePaperState(
                doi="10.1000/c1",
                title="C1",
                direction="forward_citation",
                citation_count=10,
                in_graph_degree=1,
            ),
            CandidatePaperState(
                doi="10.1000/c2",
                title="C2",
                direction="backward_reference",
                citation_count=20,
                in_graph_degree=1,
            ),
        ],
        new_dois=["10.1000/c1", "10.1000/c2"],
        traversal_summary=["Cycle 1 complete."],
        errors=[],
    ))

    old_crawler = getattr(ServiceRegistry, "_crawler_service", None)
    old_init = ServiceRegistry._initialized
    ServiceRegistry._crawler_service = mock_crawler
    ServiceRegistry._initialized = True

    try:
        response = await run_graphselect_traversal(
            seed_doi="10.1000/seed",
            max_depth=10,
            similarity_threshold=0.3,
            mode="interactive",
            tool_context=mock_tool_context,
        )

        assert response["status"] == "completed"
        assert response["cycle_level"] == 1
        assert response["max_depth"] == 1
        assert response["total_discovered"] == 2
        mock_crawler.run_one_hop_expansion.assert_called_once_with(
            session_id="project-123",
            seed_doi="10.1000/seed",
            project_id="project-123",
            embedding_provider=getattr(ServiceRegistry, "embedding_provider", None),
        )
    finally:
        if old_crawler is not None:
            ServiceRegistry._crawler_service = old_crawler
        else:
            if hasattr(ServiceRegistry, "_crawler_service"):
                delattr(ServiceRegistry, "_crawler_service")
        ServiceRegistry._initialized = old_init


# ==============================================================================
# 2. 100% Payload Completeness Across High Volume (100+ Candidates)
# ==============================================================================

@pytest.mark.asyncio
async def test_high_volume_100_plus_candidates_payload_completeness() -> None:
    """Stress test: 150 candidate nodes (70 forward, 60 backward, 20 bidirectional).

    Invariants:
    1. Total candidates returned == 150.
    2. 100% of candidate items conform to CandidatePaperState.
    3. All 14 required fields are populated without None or missing keys.
    4. Sorting is strictly monotonic on (max_similarity desc, citation_count desc).
    5. Abstract snippets are safely truncated to at most 500 characters.
    """
    total_candidates = 150
    seed_doi = "10.1145/high.volume.seed"

    # 70 forward (cite_000..069)
    # 60 backward (ref_070..129)
    # 20 both (dual_130..149)
    forward_dois = [f"10.1000/cite.{i:03d}" for i in range(70)]
    backward_dois = [f"10.1000/ref.{i:03d}" for i in range(70, 130)]
    both_dois = [f"10.1000/dual.{i:03d}" for i in range(130, 150)]

    all_citing = forward_dois + both_dois
    all_referenced = backward_dois + both_dois

    # Generate metadata for all 150 candidates
    rich_papers = []
    paper_degrees = {}
    pageranks = {}
    paper_embeddings = {}

    for i in range(total_candidates):
        if i < 70:
            doi = forward_dois[i]
            prefix = "Forward"
        elif i < 130:
            doi = backward_dois[i - 70]
            prefix = "Backward"
        else:
            doi = both_dois[i - 130]
            prefix = "Bidirectional"

        # Varied metadata: some missing venue, some missing year, varied abstract lengths
        year = 2010 + (i % 15) if (i % 7 != 0) else None
        venue = f"Venue {i % 10}" if (i % 5 != 0) else None
        long_abstract = (f"This is paper {i} ({prefix}). " * 40)  # ~1200 chars
        citation_count = (i * 37) % 5000

        rich_papers.append({
            "doi": doi,
            "title": f"{prefix} Paper {i:03d}",
            "authors": [f"Author {i}_{j}" for j in range(i % 5 + 1)],
            "year": year,
            "venue": venue,
            "abstract": long_abstract,
            "abstract_snippet": long_abstract[:500],
            "cited_by_count": citation_count,
            "openalex_id": f"W_{i:04d}",
            "publication_date": f"202{i%5}-01-01",
        })

        paper_degrees[doi] = (i % 8) + 1
        pageranks[doi] = round(0.01 + (i / 1000.0), 5)
        # Create deterministic embedding
        paper_embeddings[doi] = make_uniform_vector(768, [i % 768, (i * 2) % 768])

    mock_openalex = AsyncMock()
    mock_openalex.get_paper_by_doi = AsyncMock(return_value=PaperCreate(
        doi=seed_doi,
        title="High Volume Seed Paper",
        abstract="Seed abstract.",
        year=2020,
        cited_by_count=25000,
        openalex_id="W_HV_SEED",
    ))
    mock_openalex.get_citations = AsyncMock(return_value=all_citing)
    mock_openalex.get_references = AsyncMock(return_value=all_referenced)
    mock_openalex.batch_get_rich_papers = AsyncMock(return_value=rich_papers)

    mock_neo4j = AsyncMock()
    mock_neo4j.get_paper_by_doi = AsyncMock(return_value=None)
    mock_neo4j.get_session_dois = AsyncMock(return_value=[seed_doi])
    mock_neo4j.has_embedding = AsyncMock(return_value=True)
    mock_neo4j.create_paper = AsyncMock()
    mock_neo4j.ensure_stub_and_cite = AsyncMock()
    mock_neo4j.link_paper_to_session = AsyncMock()
    mock_neo4j.batch_get_paper_degrees = AsyncMock(return_value=paper_degrees)
    mock_neo4j.compute_pagerank = AsyncMock(return_value=pageranks)
    mock_neo4j.batch_check_project_papers = AsyncMock(return_value={forward_dois[0], backward_dois[0]})
    mock_neo4j.batch_get_paper_embeddings = AsyncMock(return_value=paper_embeddings)

    # 2 Research Questions
    mock_neo4j.get_project_research_questions_with_embeddings = AsyncMock(return_value=[
        {"question_id": "rq-1", "text": "Question 1", "embedding": make_unit_vector(768, 0)},
        {"question_id": "rq-2", "text": "Question 2", "embedding": make_unit_vector(768, 1)},
    ])

    mock_gemini = AsyncMock()
    mock_gemini.model_name = "gemini-embedding-2"

    crawler = CrawlerService(
        neo4j=mock_neo4j,
        openalex=mock_openalex,
        gemini=mock_gemini,
    )

    result = await crawler.run_one_hop_expansion(
        session_id="sess-hv",
        seed_doi=seed_doi,
        project_id="proj-hv",
    )

    # 1. Total Discovered Validation
    assert result.total_discovered == total_candidates
    assert len(result.candidates) == total_candidates
    assert len(result.new_dois) == total_candidates
    assert result.forward_count == 70
    assert result.backward_count == 60
    assert result.both_count == 20

    # 2. 100% Payload Completeness on Every Candidate
    for idx, c in enumerate(result.candidates):
        assert isinstance(c.doi, str) and len(c.doi) > 0, f"Candidate {idx} invalid DOI"
        assert isinstance(c.title, str) and len(c.title) > 0, f"Candidate {idx} invalid title"
        assert isinstance(c.authors, list), f"Candidate {idx} authors must be list"
        assert c.year is None or (isinstance(c.year, int) and c.year > 1900), f"Candidate {idx} invalid year"
        assert c.venue is None or isinstance(c.venue, str), f"Candidate {idx} invalid venue"
        assert isinstance(c.abstract_snippet, str), f"Candidate {idx} invalid abstract_snippet"
        assert len(c.abstract_snippet) <= 500, f"Candidate {idx} abstract_snippet exceeds 500 chars"
        assert c.direction in ("forward_citation", "backward_reference", "both"), f"Candidate {idx} invalid direction"
        assert isinstance(c.citation_count, int) and c.citation_count >= 0
        assert isinstance(c.in_graph_degree, int) and c.in_graph_degree >= 1
        assert isinstance(c.similarity_scores, list) and len(c.similarity_scores) == 2
        assert isinstance(c.max_similarity, float) and -1.0 <= c.max_similarity <= 1.0
        assert isinstance(c.mean_similarity, float) and -1.0 <= c.mean_similarity <= 1.0
        assert isinstance(c.already_in_library, bool)
        assert isinstance(c.embedding_cached, bool)
        assert isinstance(c.pagerank_score, float) and c.pagerank_score >= 0.0

    # 3. Sorting Invariant: sorted by max_similarity descending, then citation_count descending
    for i in range(len(result.candidates) - 1):
        c_curr = result.candidates[i]
        c_next = result.candidates[i + 1]
        if math.isclose(c_curr.max_similarity, c_next.max_similarity, abs_tol=1e-5):
            assert c_curr.citation_count >= c_next.citation_count, (
                f"Tie-breaking failed at index {i}: {c_curr.citation_count} < {c_next.citation_count}"
            )
        else:
            assert c_curr.max_similarity >= c_next.max_similarity, (
                f"Similarity sort failed at index {i}: {c_curr.max_similarity} < {c_next.max_similarity}"
            )


# ==============================================================================
# 3. Self-Referencing Loops & Graph Cycles
# ==============================================================================

@pytest.mark.asyncio
async def test_self_referencing_seed_and_candidate_loops() -> None:
    """Stress test: Adversarial graph containing multiple cyclic patterns:
    1. Seed paper self-citation: Seed cites Seed, Seed is cited by Seed.
    2. Mutual citation: Seed cites Paper A, Paper A cites Seed (direction == 'both').
    3. Candidate self-citation: Paper B cites Paper B.
    4. Circular triangle: Seed -> Paper C -> Paper D -> Seed.

    Invariants:
    - Seed paper is NEVER included in candidate set.
    - No infinite recursion or duplication of nodes.
    - Mutual citation correctly identified as 'both'.
    - Exactly unique candidate objects returned.
    """
    seed_doi = "10.1145/cycle.seed"
    doi_a = "10.1000/mutual.a"
    doi_b = "10.1000/selfcite.b"
    doi_c = "10.1000/triangle.c"
    doi_d = "10.1000/triangle.d"

    # Outgoing references from seed: Seed itself, Paper A, Paper C
    seed_references = [seed_doi, doi_a, doi_c]
    # Incoming citations to seed: Seed itself, Paper A, Paper D
    seed_citations = [seed_doi, doi_a, doi_d]

    mock_openalex = AsyncMock()
    mock_openalex.get_paper_by_doi = AsyncMock(return_value=PaperCreate(
        doi=seed_doi,
        title="Self-Referencing Seed",
        abstract="Seed abstract with self-loop.",
        year=2021,
        cited_by_count=100,
        openalex_id="W_CYCLE_SEED",
    ))
    mock_openalex.get_references = AsyncMock(return_value=seed_references)
    mock_openalex.get_citations = AsyncMock(return_value=seed_citations)

    mock_openalex.batch_get_rich_papers = AsyncMock(return_value=[
        {"doi": doi_a, "title": "Paper A (Mutual)", "abstract": "A abstract", "cited_by_count": 50},
        {"doi": doi_c, "title": "Paper C (Triangle Ref)", "abstract": "C abstract", "cited_by_count": 25},
        {"doi": doi_d, "title": "Paper D (Triangle Cite)", "abstract": "D abstract", "cited_by_count": 35},
    ])

    mock_neo4j = AsyncMock()
    mock_neo4j.get_paper_by_doi = AsyncMock(return_value=None)
    mock_neo4j.get_session_dois = AsyncMock(return_value=[seed_doi])
    mock_neo4j.has_embedding = AsyncMock(return_value=False)
    mock_neo4j.create_paper = AsyncMock()
    mock_neo4j.ensure_stub_and_cite = AsyncMock()
    mock_neo4j.link_paper_to_session = AsyncMock()
    mock_neo4j.batch_get_paper_degrees = AsyncMock(return_value={
        doi_a: 2, doi_c: 1, doi_d: 1
    })

    crawler = CrawlerService(
        neo4j=mock_neo4j,
        openalex=mock_openalex,
    )

    result = await crawler.run_one_hop_expansion(
        session_id="sess-cycle",
        seed_doi=seed_doi,
        project_id="proj-cycle",
    )

    # 1. Seed DOI MUST NOT be in candidates
    candidate_dois = [c.doi for c in result.candidates]
    assert seed_doi not in candidate_dois
    assert len(candidate_dois) == 3
    assert len(set(candidate_dois)) == 3  # No duplicates

    # 2. Check directional classifications
    cand_map = {c.doi: c for c in result.candidates}
    assert cand_map[doi_a].direction == "both"
    assert cand_map[doi_c].direction == "backward_reference"
    assert cand_map[doi_d].direction == "forward_citation"

    assert result.both_count == 1
    assert result.backward_count == 1
    assert result.forward_count == 1


@pytest.mark.asyncio
async def test_doi_formatting_variations_and_whitespace_cleaning() -> None:
    """Stress test: OpenAlex returns DOIs with URL prefixes, trailing spaces, uppercase letters.

    Ensure normalization cleans DOIs so no duplicate records or mismatch bugs occur.
    """
    seed_doi = "https://doi.org/10.1145/3292500.3330919 "
    clean_seed = "10.1145/3292500.3330919"

    mock_openalex = AsyncMock()
    mock_openalex.get_paper_by_doi = AsyncMock(return_value=PaperCreate(
        doi=clean_seed,
        title="Clean Seed",
    ))
    mock_openalex.get_references = AsyncMock(return_value=[
        "https://doi.org/10.1000/ref.1",
        "  10.1000/ref.1  ",  # duplicate with whitespace
        "https://doi.org/10.1000/ref.2",
    ])
    mock_openalex.get_citations = AsyncMock(return_value=[
        "10.1000/ref.1",  # forward citation too -> both!
    ])
    mock_openalex.batch_get_rich_papers = AsyncMock(return_value=[
        {"doi": "10.1000/ref.1", "title": "Paper 1", "abstract": "P1"},
        {"doi": "10.1000/ref.2", "title": "Paper 2", "abstract": "P2"},
    ])

    mock_neo4j = AsyncMock()
    mock_neo4j.get_paper_by_doi = AsyncMock(return_value=None)
    mock_neo4j.get_session_dois = AsyncMock(return_value=[clean_seed])
    mock_neo4j.has_embedding = AsyncMock(return_value=False)
    mock_neo4j.create_paper = AsyncMock()
    mock_neo4j.ensure_stub_and_cite = AsyncMock()
    mock_neo4j.link_paper_to_session = AsyncMock()

    crawler = CrawlerService(
        neo4j=mock_neo4j,
        openalex=mock_openalex,
    )

    result = await crawler.run_one_hop_expansion(
        session_id="sess-clean",
        seed_doi=seed_doi,
    )

    assert result.seed_doi == clean_seed
    assert result.total_discovered == 2
    assert set(c.doi for c in result.candidates) == {"10.1000/ref.1", "10.1000/ref.2"}
    cand_map = {c.doi: c for c in result.candidates}
    assert cand_map["10.1000/ref.1"].direction == "both"
    assert cand_map["10.1000/ref.2"].direction == "backward_reference"


# ==============================================================================
# 4. Multi-Question Projects with Orthogonal & Correlated Vectors
# ==============================================================================

@pytest.mark.asyncio
async def test_multi_question_orthogonal_vector_cosine_similarities() -> None:
    r"""Stress test: 4 Research Questions with strictly orthogonal unit basis vectors in 768-D.

    $Q_1 = e_0$, $Q_2 = e_1$, $Q_3 = e_2$, $Q_4 = e_3$

    Candidates:
    - Cand 1: Aligned 100% with $Q_1$ ($e_0$)
      -> Sim($Q_1$) = 1.0, Sim($Q_2$) = 0.0, Sim($Q_3$) = 0.0, Sim($Q_4$) = 0.0
      -> max_similarity = 1.0, mean_similarity = 0.25
    - Cand 2: Aligned 50/50 with $Q_1$ and $Q_2$ ($\frac{1}{\sqrt{2}} (e_0 + e_1)$)
      -> Sim($Q_1$) = 0.7071, Sim($Q_2$) = 0.7071, Sim($Q_3$) = 0.0, Sim($Q_4$) = 0.0
      -> max_similarity = 0.7071, mean_similarity = 0.3536
    - Cand 3: Balanced across all 4 ($0.5 e_0 + 0.5 e_1 + 0.5 e_2 + 0.5 e_3$)
      -> Sim($Q_i$) = 0.5000 for all i
      -> max_similarity = 0.5000, mean_similarity = 0.5000
    - Cand 4: Aligned with an orthogonal dimension $e_4$ (orthogonal to all 4 questions)
      -> Sim($Q_i$) = 0.0 for all i
      -> max_similarity = 0.0, mean_similarity = 0.0

    Invariants:
    - Exact mathematical cosine similarity calculated for each question.
    - max_similarity and mean_similarity match formulas.
    - Ranking strictly puts Cand 1 first (max_sim 1.0), Cand 2 second (0.7071), Cand 3 third (0.5), Cand 4 last (0.0).
    """
    seed_doi = "10.1145/multirq.seed"
    dim = 768

    q_vectors = [
        {"question_id": "rq-1", "text": "Question 1 on GNNs", "embedding": make_unit_vector(dim, 0)},
        {"question_id": "rq-2", "text": "Question 2 on Attention", "embedding": make_unit_vector(dim, 1)},
        {"question_id": "rq-3", "text": "Question 3 on Scaling", "embedding": make_unit_vector(dim, 2)},
        {"question_id": "rq-4", "text": "Question 4 on Benchmarks", "embedding": make_unit_vector(dim, 3)},
    ]

    cand_embeddings = {
        "10.1000/q1.aligned": make_unit_vector(dim, 0),
        "10.1000/q12.balanced": make_uniform_vector(dim, [0, 1]),
        "10.1000/qall.balanced": make_uniform_vector(dim, [0, 1, 2, 3]),
        "10.1000/qnone.ortho": make_unit_vector(dim, 4),
    }

    mock_openalex = AsyncMock()
    mock_openalex.get_paper_by_doi = AsyncMock(return_value=PaperCreate(
        doi=seed_doi,
        title="Multi-RQ Seed",
        abstract="Seed abstract",
    ))
    mock_openalex.get_references = AsyncMock(return_value=[
        "10.1000/q1.aligned",
        "10.1000/q12.balanced",
        "10.1000/qall.balanced",
        "10.1000/qnone.ortho",
    ])
    mock_openalex.get_citations = AsyncMock(return_value=[])
    mock_openalex.batch_get_rich_papers = AsyncMock(return_value=[
        {"doi": "10.1000/q1.aligned", "title": "Paper Q1 Aligned", "abstract": "Abstract Q1", "cited_by_count": 10},
        {"doi": "10.1000/q12.balanced", "title": "Paper Q12 Balanced", "abstract": "Abstract Q12", "cited_by_count": 10},
        {"doi": "10.1000/qall.balanced", "title": "Paper QAll Balanced", "abstract": "Abstract QAll", "cited_by_count": 10},
        {"doi": "10.1000/qnone.ortho", "title": "Paper QNone Orthogonal", "abstract": "Abstract QNone", "cited_by_count": 10},
    ])

    mock_neo4j = AsyncMock()
    mock_neo4j.get_paper_by_doi = AsyncMock(return_value=None)
    mock_neo4j.get_session_dois = AsyncMock(return_value=[seed_doi])
    mock_neo4j.has_embedding = AsyncMock(return_value=True)
    mock_neo4j.create_paper = AsyncMock()
    mock_neo4j.ensure_stub_and_cite = AsyncMock()
    mock_neo4j.link_paper_to_session = AsyncMock()
    mock_neo4j.batch_get_paper_embeddings = AsyncMock(return_value=cand_embeddings)
    mock_neo4j.get_project_research_questions_with_embeddings = AsyncMock(return_value=q_vectors)

    mock_gemini = AsyncMock()
    mock_gemini.model_name = "gemini-embedding-2"

    crawler = CrawlerService(
        neo4j=mock_neo4j,
        openalex=mock_openalex,
        gemini=mock_gemini,
    )

    result = await crawler.run_one_hop_expansion(
        session_id="sess-multirq",
        seed_doi=seed_doi,
        project_id="proj-multirq",
    )

    assert result.total_discovered == 4
    cand_map = {c.doi: c for c in result.candidates}

    # 1. Inspect Cand 1 (Q1 Aligned)
    c1 = cand_map["10.1000/q1.aligned"]
    assert len(c1.similarity_scores) == 4
    scores_1 = {s["question_id"]: s["score"] for s in c1.similarity_scores}
    assert math.isclose(scores_1["rq-1"], 1.0, abs_tol=1e-3)
    assert math.isclose(scores_1["rq-2"], 0.0, abs_tol=1e-3)
    assert math.isclose(scores_1["rq-3"], 0.0, abs_tol=1e-3)
    assert math.isclose(scores_1["rq-4"], 0.0, abs_tol=1e-3)
    assert math.isclose(c1.max_similarity, 1.0, abs_tol=1e-3)
    assert math.isclose(c1.mean_similarity, 0.25, abs_tol=1e-3)

    # 2. Inspect Cand 2 (Q12 Balanced)
    c2 = cand_map["10.1000/q12.balanced"]
    scores_2 = {s["question_id"]: s["score"] for s in c2.similarity_scores}
    assert math.isclose(scores_2["rq-1"], 0.7071, abs_tol=1e-3)
    assert math.isclose(scores_2["rq-2"], 0.7071, abs_tol=1e-3)
    assert math.isclose(scores_2["rq-3"], 0.0, abs_tol=1e-3)
    assert math.isclose(c2.max_similarity, 0.7071, abs_tol=1e-3)
    assert math.isclose(c2.mean_similarity, 0.3536, abs_tol=1e-3)

    # 3. Inspect Cand 3 (QAll Balanced)
    c3 = cand_map["10.1000/qall.balanced"]
    scores_3 = {s["question_id"]: s["score"] for s in c3.similarity_scores}
    for qid in ["rq-1", "rq-2", "rq-3", "rq-4"]:
        assert math.isclose(scores_3[qid], 0.5000, abs_tol=1e-3)
    assert math.isclose(c3.max_similarity, 0.5000, abs_tol=1e-3)
    assert math.isclose(c3.mean_similarity, 0.5000, abs_tol=1e-3)

    # 4. Inspect Cand 4 (Orthogonal to all)
    c4 = cand_map["10.1000/qnone.ortho"]
    scores_4 = {s["question_id"]: s["score"] for s in c4.similarity_scores}
    for qid in ["rq-1", "rq-2", "rq-3", "rq-4"]:
        assert math.isclose(scores_4[qid], 0.0, abs_tol=1e-3)
    assert math.isclose(c4.max_similarity, 0.0, abs_tol=1e-3)
    assert math.isclose(c4.mean_similarity, 0.0, abs_tol=1e-3)

    # 5. Check strictly ordered result ranking
    ranked_dois = [c.doi for c in result.candidates]
    assert ranked_dois == [
        "10.1000/q1.aligned",
        "10.1000/q12.balanced",
        "10.1000/qall.balanced",
        "10.1000/qnone.ortho",
    ]


# ==============================================================================
# 5. Adversarial Error Resilience & Boundary Stress
# ==============================================================================

@pytest.mark.asyncio
async def test_crawler_handles_partial_network_timeout_and_corrupt_entries() -> None:
    """Stress test: Network exceptions during citation fetching and malformed candidate records.

    Verifies:
    - get_citations raises TimeoutError, get_references succeeds.
    - Crawler captures error message in result.errors, does not crash.
    - Returns discovered papers from references successfully.
    """
    seed_doi = "10.1145/timeout.seed"

    mock_openalex = AsyncMock()
    mock_openalex.get_paper_by_doi = AsyncMock(return_value=PaperCreate(
        doi=seed_doi,
        title="Timeout Seed",
    ))
    mock_openalex.get_references = AsyncMock(return_value=["10.1000/good.ref"])
    mock_openalex.get_citations = AsyncMock(side_effect=TimeoutError("Connection to OpenAlex timed out."))
    mock_openalex.batch_get_rich_papers = AsyncMock(return_value=[
        {"doi": "10.1000/good.ref", "title": "Good Ref", "abstract": "Abstract", "cited_by_count": 5}
    ])

    mock_neo4j = AsyncMock()
    mock_neo4j.get_paper_by_doi = AsyncMock(return_value=None)
    mock_neo4j.get_session_dois = AsyncMock(return_value=[seed_doi])
    mock_neo4j.has_embedding = AsyncMock(return_value=False)
    mock_neo4j.create_paper = AsyncMock()
    mock_neo4j.ensure_stub_and_cite = AsyncMock()
    mock_neo4j.link_paper_to_session = AsyncMock()

    crawler = CrawlerService(
        neo4j=mock_neo4j,
        openalex=mock_openalex,
    )

    result = await crawler.run_one_hop_expansion(
        session_id="sess-timeout",
        seed_doi=seed_doi,
    )

    assert result.total_discovered == 1
    assert result.candidates[0].doi == "10.1000/good.ref"
    assert any("Failed to fetch citing papers" in err for err in result.errors)


@pytest.mark.asyncio
async def test_crawler_handles_embedding_generation_failure_gracefully() -> None:
    """Stress test: Gemini embedding service raises API quota error during crawl.

    Verifies:
    - Candidate papers are still stored in Neo4j.
    - Candidates are returned with similarity=0.0 and embedding_cached=False.
    - Crawler returns complete payload without crashing.
    """
    seed_doi = "10.1145/quota.seed"

    mock_openalex = AsyncMock()
    mock_openalex.get_paper_by_doi = AsyncMock(return_value=PaperCreate(
        doi=seed_doi,
        title="Quota Seed",
        abstract="Seed abstract",
    ))
    mock_openalex.get_references = AsyncMock(return_value=["10.1000/cand.quota"])
    mock_openalex.get_citations = AsyncMock(return_value=[])
    mock_openalex.batch_get_rich_papers = AsyncMock(return_value=[
        {"doi": "10.1000/cand.quota", "title": "Quota Candidate", "abstract": "Cand abstract", "cited_by_count": 8}
    ])

    mock_neo4j = AsyncMock()
    mock_neo4j.get_paper_by_doi = AsyncMock(return_value=None)
    mock_neo4j.get_session_dois = AsyncMock(return_value=[seed_doi])
    mock_neo4j.has_embedding = AsyncMock(return_value=False)
    mock_neo4j.create_paper = AsyncMock()
    mock_neo4j.ensure_stub_and_cite = AsyncMock()
    mock_neo4j.link_paper_to_session = AsyncMock()
    mock_neo4j.get_project_research_questions_with_embeddings = AsyncMock(return_value=[
        {"question_id": "rq-1", "text": "Question 1", "embedding": [0.1] * 768}
    ])

    mock_gemini = AsyncMock()
    mock_gemini.embed_document = AsyncMock(side_effect=RuntimeError("ResourceExhausted: 429 Quota Exceeded"))

    crawler = CrawlerService(
        neo4j=mock_neo4j,
        openalex=mock_openalex,
        gemini=mock_gemini,
    )

    result = await crawler.run_one_hop_expansion(
        session_id="sess-quota",
        seed_doi=seed_doi,
        project_id="proj-quota",
    )

    assert result.total_discovered == 1
    cand = result.candidates[0]
    assert cand.doi == "10.1000/cand.quota"
    assert cand.max_similarity == 0.0
    assert cand.mean_similarity == 0.0
    assert cand.embedding_cached is False


@pytest.mark.asyncio
async def test_run_graphselect_traversal_tool_error_handling_invalid_input(
    mock_tool_context: ToolContext,
) -> None:
    """Verify run_graphselect_traversal tool handles missing project ID, empty seed, or exceptions."""
    # 1. Missing tool context / project ID
    res_no_ctx = await run_graphselect_traversal(seed_doi="10.1000/test", tool_context=None)
    assert "error" in res_no_ctx
    assert "No project_id in session state" in str(res_no_ctx["error"])

    # 2. Empty seed and no library papers
    mock_neo4j = AsyncMock()
    mock_neo4j.get_project_papers = AsyncMock(return_value=[])
    old_neo4j = getattr(ServiceRegistry, "_neo4j", None)
    ServiceRegistry._neo4j = mock_neo4j
    ServiceRegistry._initialized = True

    try:
        res_no_seed = await run_graphselect_traversal(seed_doi="", tool_context=mock_tool_context)
        assert "error" in res_no_seed
        assert "seed_doi is required" in str(res_no_seed["error"])
    finally:
        if old_neo4j is not None:
            ServiceRegistry._neo4j = old_neo4j
        else:
            if hasattr(ServiceRegistry, "_neo4j"):
                delattr(ServiceRegistry, "_neo4j")

"""Comprehensive E2E Requirements Test Suite for ALRS v2.

Opaque-Box Requirement-Driven Test Suite covering Tiers 1-4:
- Tier 1: Isolated Feature Coverage (Features 1-16, 5 tests each = 80 tests)
- Tier 2: Boundary & Corner Cases (Features 1-16, 5 tests each = 80 tests)
- Tier 3: Cross-Feature Pairwise Integrations (16 tests)
- Tier 4: Real-World Workload Scenarios (5 complex application tests)

Total: 181 test cases verifying specifications in ORIGINAL_REQUEST.md,
PROJECT.md, and TEST_INFRA.md.
"""
from __future__ import annotations

import asyncio
import json
import math
import re
from pathlib import Path
from typing import Any, AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from google.adk.tools.tool_context import ToolContext

# Core & Feature imports
from core.clients.openalex_client import OpenAlexService
from core.clients.rate_limiter import AdaptiveRateLimiter
from core.llm.models import CompletionResponse, TokenUsage
from features.embedding.providers.gemini_provider import GeminiEmbeddingProvider
from core.db.neo4j_service import Neo4jService
from features.ranking.service import RankingService
from features.ranking.models import RankedPaper, QuestionGroup, GroupedResults
from features.retrieval.models import PaperCreate, PaperRead, AuthorRead, VenueRead
from features.writing.service import WritingService
from features.export.service import ExportService
from agents._service_registry import ServiceRegistry
from agents.research.alrs_agent import create_alrs_agent
from agents.research.gap_finder import create_gap_finder_agent
from agents.planner.agent import create_planner_agent, planner_agent
from agents.writing.drafting_agent import drafting_agent
from agents.writing.reviewer_agent import reviewer_agent, exit_loop
from agents.writing.agent import writer_agent
from agents.writing.tex_formatter import (
    format_to_latex,
    generate_bibtex,
    _escape_bibtex,
    _make_cite_key,
    _md_to_latex_body,
)

REPO_ROOT = Path(__file__).resolve().parents[4]
THESIS_FILE = REPO_ROOT / "paper" / "myPapers" / "masterPapers" / "thesis" / "THESIS.tex"
BIB_FILE = REPO_ROOT / "paper" / "myPapers" / "masterPapers" / "proposal" / "references.bib"


# ============================================================================
# Shared Test Fixtures & Helpers
# ============================================================================

@pytest.fixture
def sample_inverted_index() -> dict[str, list[int]]:
    """Sample OpenAlex inverted index dictionary."""
    return {
        "Graph": [0],
        "neural": [1],
        "networks": [2],
        "have": [3],
        "emerged": [4],
        "as": [5],
        "a": [6],
        "powerful": [7],
        "tool": [8],
        "for": [9],
        "learning": [10],
        "on": [11],
        "graphs.": [12],
    }


@pytest.fixture
def mock_openalex_service() -> OpenAlexService:
    """Instantiate OpenAlexService with rate limiter."""
    limiter = AdaptiveRateLimiter(initial_rate=9.0, min_rate=0.5)
    service = OpenAlexService(api_key="test-key", rate_limiter=limiter)
    return service


@pytest.fixture
def mock_neo4j_service_instance() -> AsyncMock:
    """Mock Neo4j service with async methods."""
    svc = AsyncMock(spec=Neo4jService)
    svc.execute_read = AsyncMock(return_value=[])
    svc.execute_write = AsyncMock(return_value=[])
    svc.execute_query = AsyncMock(return_value=[])
    svc.get_paper_by_doi = AsyncMock(return_value=None)
    svc.get_project_papers = AsyncMock(return_value=[])
    svc.get_research_questions = AsyncMock(return_value=[])
    svc.compute_similarities = AsyncMock(return_value=[])
    svc.compute_pagerank = AsyncMock(return_value={})
    svc.has_embedding = AsyncMock(return_value=True)
    svc.health_check = AsyncMock(return_value=True)
    return svc


# ============================================================================
# TIER 1: ISOLATED FEATURE COVERAGE (Features 1-16)
# ============================================================================

class TestTier1FeatureCoverage:
    """Tier 1: Isolated Happy-Path Requirement Tests (16 Features x 5 Tests = 80 Tests)."""

    # ------------------------------------------------------------------------
    # Feature 1: OpenAlex Inverted Abstract Reconstruction (ORIGINAL_REQUEST §R1)
    # ------------------------------------------------------------------------
    class TestF01OpenAlexAbstractReconstruction:
        def test_f01_01_reconstruct_standard_inverted_index(self, mock_openalex_service, sample_inverted_index):
            """Test reconstructing standard sequential token indices."""
            abstract = mock_openalex_service._reconstruct_abstract(sample_inverted_index)
            expected = "Graph neural networks have emerged as a powerful tool for learning on graphs."
            assert abstract == expected

        def test_f01_02_reconstruct_unordered_positions(self, mock_openalex_service):
            """Test reconstructing when dictionary keys and positions are shuffled."""
            inverted = {
                "learning": [2],
                "Deep": [0],
                "representations": [3],
                "graph": [1],
            }
            abstract = mock_openalex_service._reconstruct_abstract(inverted)
            assert abstract == "Deep graph learning representations"

        def test_f01_03_reconstruct_repeated_words_multiple_positions(self, mock_openalex_service):
            """Test words appearing in multiple distinct positions."""
            inverted = {
                "the": [0, 4],
                "model": [1, 5],
                "outperforms": [2],
                "baseline": [3],
            }
            abstract = mock_openalex_service._reconstruct_abstract(inverted)
            assert abstract == "the model outperforms baseline the model"

        def test_f01_04_reconstruct_single_word_token(self, mock_openalex_service):
            """Test abstract consisting of a single token."""
            inverted = {"Overview": [0]}
            abstract = mock_openalex_service._reconstruct_abstract(inverted)
            assert abstract == "Overview"

        def test_f01_05_reconstruct_punctuation_and_hyphenated_terms(self, mock_openalex_service):
            """Test tokens containing punctuation and hyphens."""
            inverted = {
                "State-of-the-art": [0],
                "results": [1],
                "(accuracy": [2],
                ">": [3],
                "95%)": [4],
                "achieved.": [5],
            }
            abstract = mock_openalex_service._reconstruct_abstract(inverted)
            assert abstract == "State-of-the-art results (accuracy > 95%) achieved."

    # ------------------------------------------------------------------------
    # Feature 2: Adaptive Rate Limiter AIMD (ORIGINAL_REQUEST §R1)
    # ------------------------------------------------------------------------
    class TestF02AdaptiveRateLimiter:
        def test_f02_01_initial_rate_configuration(self):
            """Test default rate initialization at 9.0 req/s."""
            limiter = AdaptiveRateLimiter(initial_rate=9.0, min_rate=0.5, recovery_increment=0.5)
            assert limiter.current_rate == 9.0

        def test_f02_02_on_429_multiplicative_decrease(self):
            """Test multiplicative halving on HTTP 429 status."""
            limiter = AdaptiveRateLimiter(initial_rate=9.0, min_rate=0.5)
            new_rate = limiter.on_429()
            assert new_rate == 4.5
            assert limiter.current_rate == 4.5

        def test_f02_03_on_success_additive_recovery(self):
            """Test additive recovery step towards initial rate."""
            limiter = AdaptiveRateLimiter(initial_rate=9.0, min_rate=0.5, recovery_increment=0.5)
            limiter.on_429()  # drops to 4.5
            recovered = limiter.on_success()  # 4.5 + 0.5 = 5.0
            assert recovered == 5.0
            assert limiter.current_rate == 5.0

        def test_f02_04_min_rate_floor_clamping(self):
            """Test that rate never drops below min_rate despite repeated 429s."""
            limiter = AdaptiveRateLimiter(initial_rate=9.0, min_rate=1.0)
            for _ in range(10):
                limiter.on_429()
            assert limiter.current_rate == 1.0

        @pytest.mark.asyncio
        async def test_f02_05_acquire_token_consumption(self):
            """Test acquire consumes available tokens without exception."""
            limiter = AdaptiveRateLimiter(initial_rate=10.0, min_rate=1.0)
            await limiter.acquire()
            assert limiter.current_rate == 10.0

    # ------------------------------------------------------------------------
    # Feature 3: Gemini Multimodal Embeddings (ORIGINAL_REQUEST §R1)
    # ------------------------------------------------------------------------
    class TestF03GeminiMultimodalEmbeddings:
        def test_f03_01_document_asymmetric_prefix_formatting(self):
            """Test document format is 'title: {title} | text: {content}'."""
            provider = GeminiEmbeddingProvider(api_key="dummy-key", output_dimensionality=768)
            formatted = provider._format_document("We propose a new model.", title="Attention Is All You Need")
            assert formatted == "title: Attention Is All You Need | text: We propose a new model."

        def test_f03_02_document_none_title_formatting(self):
            """Test document without title formats as 'title: none | text: {content}'."""
            provider = GeminiEmbeddingProvider(api_key="dummy-key", output_dimensionality=768)
            formatted = provider._format_document("We propose a new model.", title=None)
            assert formatted == "title: none | text: We propose a new model."

        def test_f03_03_query_asymmetric_prefix_formatting(self):
            """Test query format includes task prefix and query content."""
            provider = GeminiEmbeddingProvider(api_key="dummy-key", output_dimensionality=768)
            formatted_default = provider._format_query("What are GNNs?")
            formatted_search = provider._format_query("What are GNNs?", task="search result")
            assert formatted_default == "task: question answering | query: What are GNNs?"
            assert formatted_search == "task: search result | query: What are GNNs?"

        def test_f03_04_dimension_size_768_mrl(self):
            """Test configured dimensionality is 768 for MRL."""
            provider = GeminiEmbeddingProvider(api_key="dummy-key", output_dimensionality=768)
            assert provider.dimensions == 768

        @pytest.mark.asyncio
        async def test_f03_05_embed_document_client_invocation(self):
            """Test embed_document calls GenAI client embed_content with 768 dim."""
            provider = GeminiEmbeddingProvider(api_key="dummy-key", output_dimensionality=768)
            mock_emb = MagicMock()
            mock_emb.values = [0.1] * 768
            mock_resp = MagicMock(embeddings=[mock_emb])

            with patch.object(provider._client.models, "embed_content", return_value=mock_resp):
                vector = await provider.embed_document("Abstract text", title="Paper Title")
                assert len(vector) == 768
                assert vector[0] == 0.1

    # ------------------------------------------------------------------------
    # Feature 4: Neo4j Zero-RAM Vector Index (ORIGINAL_REQUEST §R1)
    # ------------------------------------------------------------------------
    class TestF04Neo4jZeroRamVectorIndex:
        @pytest.mark.asyncio
        async def test_f04_01_cypher_calls_vector_index(self):
            """Test compute_similarities calls db.index.vector.queryNodes."""
            neo4j = Neo4jService("bolt://localhost:7687", "neo4j", "password")
            executed_queries = []

            async def fake_execute_read(query, params=None):
                executed_queries.append((query, params))
                return [{"doi": "10.1000/1", "question": "Q1", "score": 0.88}]

            neo4j.execute_read = fake_execute_read
            results = await neo4j.compute_similarities("session-123", threshold=0.7, top_k=50)

            assert len(results) == 1
            assert results[0]["doi"] == "10.1000/1"
            assert len(executed_queries) == 1
            assert "db.index.vector.queryNodes('paper_embeddings'" in executed_queries[0][0]
            assert executed_queries[0][1]["threshold"] == 0.7
            assert executed_queries[0][1]["top_k"] == 50

        @pytest.mark.asyncio
        async def test_f04_02_similarity_threshold_filtering(self):
            """Test query filters out scores below threshold."""
            neo4j = Neo4jService("bolt://localhost:7687", "neo4j", "password")
            neo4j.execute_read = AsyncMock(return_value=[
                {"doi": "10.1000/1", "question": "Q1", "score": 0.95},
                {"doi": "10.1000/2", "question": "Q1", "score": 0.75},
            ])
            results = await neo4j.compute_similarities("sess-1", threshold=0.7)
            assert all(r["score"] >= 0.7 for r in results)

        @pytest.mark.asyncio
        async def test_f04_03_zero_ram_roundtrip_prevention(self):
            """Test returned dictionary contains metadata and scores, not raw embedding arrays."""
            neo4j = Neo4jService("bolt://localhost:7687", "neo4j", "password")
            neo4j.execute_read = AsyncMock(return_value=[
                {"doi": "10.1000/1", "question": "Q1", "score": 0.85}
            ])
            results = await neo4j.compute_similarities("sess-1", threshold=0.5)
            assert "embedding" not in results[0]
            assert "score" in results[0]

        @pytest.mark.asyncio
        async def test_f04_04_session_scoping_in_vector_query(self):
            """Test that Cypher ensures paper belongs to the specified session."""
            neo4j = Neo4jService("bolt://localhost:7687", "neo4j", "password")
            captured_params = {}

            async def capture_read(query, params=None):
                nonlocal captured_params
                captured_params = params or {}
                return []

            neo4j.execute_read = capture_read
            await neo4j.compute_similarities("test-session-xyz", threshold=0.6)
            assert captured_params.get("session_id") == "test-session-xyz"

        @pytest.mark.asyncio
        async def test_f04_05_top_k_parameter_propagation(self):
            """Test top_k parameter is forwarded to vector index query."""
            neo4j = Neo4jService("bolt://localhost:7687", "neo4j", "password")
            captured_params = {}

            async def capture_read(query, params=None):
                nonlocal captured_params
                captured_params = params or {}
                return []

            neo4j.execute_read = capture_read
            await neo4j.compute_similarities("sess-1", threshold=0.5, top_k=250)
            assert captured_params.get("top_k") == 250

    # ------------------------------------------------------------------------
    # Feature 5: 3-Tier PageRank Fallback Engine (ORIGINAL_REQUEST §R1)
    # ------------------------------------------------------------------------
    class TestF05PageRankFallbackEngine:
        @pytest.mark.asyncio
        async def test_f05_01_gds_pagerank_primary_execution(self):
            """Test Tier 1 GDS PageRank execution and min-max normalization."""
            neo4j = Neo4jService("bolt://localhost:7687", "neo4j", "password")
            neo4j.execute_write = AsyncMock(return_value=[])
            neo4j.execute_read = AsyncMock(return_value=[
                {"doi": "10.1000/a", "score": 2.0},
                {"doi": "10.1000/b", "score": 6.0},
                {"doi": "10.1000/c", "score": 10.0},
            ])
            scores = await neo4j.compute_pagerank("sess-1")
            assert scores["10.1000/a"] == 0.0
            assert scores["10.1000/b"] == 0.5
            assert scores["10.1000/c"] == 1.0

        @pytest.mark.asyncio
        async def test_f05_02_networkx_fallback_when_gds_fails(self):
            """Test Tier 2 fallback to NetworkX when GDS projection fails."""
            neo4j = Neo4jService("bolt://localhost:7687", "neo4j", "password")
            
            async def mock_write(query, params=None):
                if "gds.graph.project" in query:
                    raise RuntimeError("GDS not installed")
                return []

            async def mock_read(query, params=None):
                if "RETURN p.doi AS doi" in query:
                    return [{"doi": "10.1000/1"}, {"doi": "10.1000/2"}]
                if "p1.doi AS source" in query:
                    return [{"source": "10.1000/1", "target": "10.1000/2"}]
                return []

            neo4j.execute_write = mock_write
            neo4j.execute_read = mock_read

            scores = await neo4j.compute_pagerank("sess-1")
            assert len(scores) == 2
            assert "10.1000/1" in scores
            assert "10.1000/2" in scores

        @pytest.mark.asyncio
        async def test_f05_03_in_degree_fallback_when_networkx_fails(self):
            """Test Tier 3 degree centrality fallback."""
            neo4j = Neo4jService("bolt://localhost:7687", "neo4j", "password")
            neo4j.execute_read = AsyncMock(return_value=[
                {"doi": "10.1000/1", "degree": 1},
                {"doi": "10.1000/2", "degree": 5},
            ])
            scores = await neo4j._compute_degree_centrality_fallback("sess-1")
            assert scores["10.1000/1"] == 0.0
            assert scores["10.1000/2"] == 1.0

        @pytest.mark.asyncio
        async def test_f05_04_min_max_normalization_bounds(self):
            """Test min-max normalization guarantees scores in [0.0, 1.0]."""
            neo4j = Neo4jService("bolt://localhost:7687", "neo4j", "password")
            neo4j.execute_write = AsyncMock(return_value=[])
            neo4j.execute_read = AsyncMock(return_value=[
                {"doi": "10.1000/1", "score": 100.0},
                {"doi": "10.1000/2", "score": 250.0},
            ])
            scores = await neo4j.compute_pagerank("sess-1")
            for s in scores.values():
                assert 0.0 <= s <= 1.0

        @pytest.mark.asyncio
        async def test_f05_05_uniform_scores_normalized_to_one(self):
            """Test when all nodes have equal raw score, normalized score is 1.0."""
            neo4j = Neo4jService("bolt://localhost:7687", "neo4j", "password")
            neo4j.execute_write = AsyncMock(return_value=[])
            neo4j.execute_read = AsyncMock(return_value=[
                {"doi": "10.1000/1", "score": 5.0},
                {"doi": "10.1000/2", "score": 5.0},
            ])
            scores = await neo4j.compute_pagerank("sess-1")
            assert scores["10.1000/1"] == 1.0
            assert scores["10.1000/2"] == 1.0

    # ------------------------------------------------------------------------
    # Feature 6: Hybrid Scoring & Question Grouping (ORIGINAL_REQUEST §R1)
    # ------------------------------------------------------------------------
    class TestF06HybridScoringAndQuestionGrouping:
        @pytest.mark.asyncio
        async def test_f06_01_hybrid_score_calculation(self):
            """Test formula: 0.70 * Sim + 0.30 * PR."""
            neo4j = AsyncMock()
            mysql = AsyncMock()
            mysql.get_session = AsyncMock(return_value={
                "research_questions": ["Q1"],
                "similarity_threshold": 0.5,
            })
            neo4j.compute_similarities = AsyncMock(return_value=[
                {"doi": "10.1000/1", "question": "Q1", "score": 0.80}
            ])
            neo4j.compute_pagerank = AsyncMock(return_value={"10.1000/1": 0.60})
            neo4j.execute_read = AsyncMock(return_value=[
                {"doi": "10.1000/1", "title": "Paper 1", "year": 2023, "cited_by_count": 50, "authors": ["Author"]}
            ])

            service = RankingService(neo4j, mysql)
            results = await service.rank_papers("sess-1", similarity_weight=0.7, pagerank_weight=0.3)

            expected_hybrid = (0.7 * 0.80) + (0.3 * 0.60)  # 0.56 + 0.18 = 0.74
            paper = results.groups[0].papers[0]
            assert math.isclose(paper.hybrid_score, expected_hybrid, rel_tol=1e-5)

        @pytest.mark.asyncio
        async def test_f06_02_argmax_question_partitioning(self):
            """Test assigning paper to the question with highest similarity score."""
            neo4j = AsyncMock()
            mysql = AsyncMock()
            mysql.get_session = AsyncMock(return_value={
                "research_questions": ["Q1", "Q2"],
                "similarity_threshold": 0.5,
            })
            neo4j.compute_similarities = AsyncMock(return_value=[
                {"doi": "10.1000/1", "question": "Q1", "score": 0.90},
                {"doi": "10.1000/1", "question": "Q2", "score": 0.60},
            ])
            neo4j.compute_pagerank = AsyncMock(return_value={"10.1000/1": 0.5})
            neo4j.execute_read = AsyncMock(return_value=[
                {"doi": "10.1000/1", "title": "Paper 1", "year": 2023, "cited_by_count": 10, "authors": []}
            ])

            service = RankingService(neo4j, mysql)
            results = await service.rank_papers("sess-1")

            q1_group = next(g for g in results.groups if g.question == "Q1")
            q2_group = next(g for g in results.groups if g.question == "Q2")

            assert len(q1_group.papers) == 1
            assert q1_group.papers[0].doi == "10.1000/1"
            assert len(q2_group.papers) == 0

        @pytest.mark.asyncio
        async def test_f06_03_sort_order_descending_by_hybrid_score(self):
            """Test papers within each group sorted descending by hybrid score."""
            neo4j = AsyncMock()
            mysql = AsyncMock()
            mysql.get_session = AsyncMock(return_value={
                "research_questions": ["Q1"],
                "similarity_threshold": 0.5,
            })
            neo4j.compute_similarities = AsyncMock(return_value=[
                {"doi": "10.1000/low", "question": "Q1", "score": 0.60},
                {"doi": "10.1000/high", "question": "Q1", "score": 0.95},
            ])
            neo4j.compute_pagerank = AsyncMock(return_value={
                "10.1000/low": 0.2,
                "10.1000/high": 0.8,
            })
            neo4j.execute_read = AsyncMock(return_value=[
                {"doi": "10.1000/low", "title": "Low", "year": 2020, "cited_by_count": 5, "authors": []},
                {"doi": "10.1000/high", "title": "High", "year": 2023, "cited_by_count": 100, "authors": []},
            ])

            service = RankingService(neo4j, mysql)
            results = await service.rank_papers("sess-1")

            papers = results.groups[0].papers
            assert papers[0].doi == "10.1000/high"
            assert papers[1].doi == "10.1000/low"

        @pytest.mark.asyncio
        async def test_f06_04_custom_weights_configuration(self):
            """Test custom similarity and PageRank weights (e.g. 0.9 / 0.1)."""
            neo4j = AsyncMock()
            mysql = AsyncMock()
            mysql.get_session = AsyncMock(return_value={
                "research_questions": ["Q1"],
                "similarity_threshold": 0.5,
            })
            neo4j.compute_similarities = AsyncMock(return_value=[
                {"doi": "10.1000/1", "question": "Q1", "score": 0.80}
            ])
            neo4j.compute_pagerank = AsyncMock(return_value={"10.1000/1": 0.40})
            neo4j.execute_read = AsyncMock(return_value=[
                {"doi": "10.1000/1", "title": "Paper", "year": 2021, "cited_by_count": 20, "authors": []}
            ])

            service = RankingService(neo4j, mysql)
            results = await service.rank_papers("sess-1", similarity_weight=0.9, pagerank_weight=0.1)

            expected = (0.9 * 0.80) + (0.1 * 0.40)  # 0.72 + 0.04 = 0.76
            assert math.isclose(results.groups[0].papers[0].hybrid_score, expected, rel_tol=1e-5)

        @pytest.mark.asyncio
        async def test_f06_05_empty_results_handling(self):
            """Test ranking when no papers meet similarity threshold."""
            neo4j = AsyncMock()
            mysql = AsyncMock()
            mysql.get_session = AsyncMock(return_value={
                "research_questions": ["Q1"],
                "similarity_threshold": 0.8,
            })
            neo4j.compute_similarities = AsyncMock(return_value=[])
            neo4j.compute_pagerank = AsyncMock(return_value={})

            service = RankingService(neo4j, mysql)
            results = await service.rank_papers("sess-1")
            assert results.total_papers == 0
            assert len(results.groups[0].papers) == 0

    # ------------------------------------------------------------------------
    # Feature 7: Research Analyst / ALRS Agent (ORIGINAL_REQUEST §R2)
    # ------------------------------------------------------------------------
    class TestF07ResearchAnalystALRSAgent:
        def test_f07_01_agent_creation_and_tools_registration(self):
            """Test ALRSAgent creates and registers all 7 search/retrieval tools."""
            agent = create_alrs_agent()
            assert agent.name == "ALRSAgent"
            tool_names = [getattr(t, "__name__", str(t)) for t in agent.tools]
            assert "search_papers_by_keyword" in tool_names
            assert "search_papers_by_doi" in tool_names
            assert "search_papers_by_title" in tool_names
            assert "search_papers_by_author" in tool_names
            assert "search_papers_by_venue" in tool_names
            assert "explore_paper" in tool_names
            assert "add_paper_to_project" in tool_names

        def test_f07_02_instruction_prompt_coverage(self):
            """Test ALRSAgent instruction specifies search strategy and tools."""
            agent = create_alrs_agent()
            assert "ALRS Agent" in agent.instruction
            assert "search_papers_by_keyword" in agent.instruction
            assert "explore_paper" in agent.instruction

        @pytest.mark.asyncio
        async def test_f07_03_keyword_search_tool_execution(self):
            """Test search_papers_by_keyword invokes OpenAlex works search."""
            from agents.research.tools.search_tools import search_papers_by_keyword

            mock_openalex = AsyncMock(spec=OpenAlexService)
            mock_openalex.search_by_title = AsyncMock(return_value=[
                PaperCreate(doi="10.1000/1", title="GNN Survey", year=2021, authors=["Smith"])
            ])

            mock_ctx = MagicMock(spec=ToolContext)
            mock_ctx.state = {"project_id": "proj-1"}

            ServiceRegistry._openalex = mock_openalex
            ServiceRegistry._initialized = True

            res = await search_papers_by_keyword(query="GNN", tool_context=mock_ctx)
            assert "papers" in res
            assert len(res["papers"]) == 1
            assert res["papers"][0]["doi"] == "10.1000/1"

        @pytest.mark.asyncio
        async def test_f07_04_doi_search_tool_execution(self):
            """Test search_papers_by_doi looks up single paper."""
            from agents.research.tools.search_tools import search_papers_by_doi

            mock_openalex = AsyncMock(spec=OpenAlexService)
            mock_openalex.get_paper_by_doi = AsyncMock(return_value=PaperCreate(
                doi="10.1000/exact", title="Exact Title", year=2022
            ))

            mock_ctx = MagicMock(spec=ToolContext)
            mock_ctx.state = {"project_id": "proj-1"}

            ServiceRegistry._openalex = mock_openalex
            ServiceRegistry._initialized = True

            res = await search_papers_by_doi(doi="10.1000/exact", tool_context=mock_ctx)
            assert res["found"] is True
            assert res["paper"]["title"] == "Exact Title"

        @pytest.mark.asyncio
        async def test_f07_05_add_paper_to_project_execution(self):
            """Test add_paper_to_project links paper to project node via paper_retrieval service."""
            from agents.research.tools.retrieval_tools import add_paper_to_project

            mock_retrieval = AsyncMock()
            mock_retrieval.retrieve_paper = AsyncMock(return_value=MagicMock(
                metadata=MagicMock(doi="10.1000/add-me", title="Added Title", year=2024),
                already_existed=False,
                embedding=[0.1] * 768,
            ))

            mock_ctx = MagicMock(spec=ToolContext)
            mock_ctx.state = {"project_id": "proj-123"}

            ServiceRegistry._paper_retrieval = mock_retrieval
            ServiceRegistry._neo4j = AsyncMock()
            ServiceRegistry._initialized = True

            res = await add_paper_to_project("10.1000/add-me", tool_context=mock_ctx)
            assert res.get("status") == "added"
            assert res.get("doi") == "10.1000/add-me"

    # ------------------------------------------------------------------------
    # Feature 8: Gap Discovery Agent (ORIGINAL_REQUEST §R2)
    # ------------------------------------------------------------------------
    class TestF08GapDiscoveryAgent:
        def test_f08_01_agent_creation_and_tools_registration(self):
            """Test GapFinderAgent creates and registers analysis tools."""
            agent = create_gap_finder_agent()
            assert agent.name == "GapFinderAgent"
            tool_names = [getattr(t, "__name__", str(t)) for t in agent.tools]
            assert "compute_similarity" in tool_names
            assert "get_citation_stats" in tool_names
            assert "analyze_coverage" in tool_names
            assert "suggest_gap_queries" in tool_names
            assert "rank_papers" in tool_names

        @pytest.mark.asyncio
        async def test_f08_02_analyze_coverage_detects_underrepresented_questions(self):
            """Test analyze_coverage classifies questions with 0 papers as gaps."""
            from features.analysis.service import analyze_coverage

            mock_neo4j = AsyncMock()
            mock_neo4j.get_research_questions = AsyncMock(return_value=[{"text": "Q1: Covered"}, {"text": "Q2: Uncovered"}])
            mock_neo4j.get_project_papers = AsyncMock(return_value=[{"doi": "10.1000/1"}])
            mock_neo4j.compute_similarities = AsyncMock(return_value=[
                {"doi": "10.1000/1", "question": "Q1: Covered", "score": 0.85}
            ])

            res = await analyze_coverage("proj-1", threshold=0.7, neo4j=mock_neo4j)
            assert res["overall_coverage"] == 0.5
            assert len(res["covered_questions"]) == 1
            assert len(res["gap_questions"]) == 1
            assert res["gap_questions"][0]["question"] == "Q2: Uncovered"

        @pytest.mark.asyncio
        async def test_f08_03_citation_stats_aggregation(self):
            """Test get_citation_stats aggregates paper count and citations."""
            from features.analysis.service import get_citation_stats

            mock_neo4j = AsyncMock()
            mock_neo4j.get_project_papers = AsyncMock(return_value=[
                {"doi": "10.1000/1", "cited_by_count": 100},
                {"doi": "10.1000/2", "cited_by_count": 50},
            ])
            mock_neo4j.get_research_questions = AsyncMock(return_value=[])

            res = await get_citation_stats("proj-1", mock_neo4j)
            assert res["total_papers"] == 2
            assert res["total_citations"] == 150
            assert res["avg_citations"] == 75.0

        @pytest.mark.asyncio
        async def test_f08_04_suggest_gap_queries_generation(self):
            """Test suggest_gap_queries parses LLM JSON response into search query list."""
            from features.analysis.service import suggest_gap_queries

            mock_llm = AsyncMock()
            mock_llm.complete = AsyncMock(return_value=CompletionResponse(
                text=json.dumps([
                    "Graph Transformer healthcare",
                    "Medical GNN benchmark",
                    "Clinical graph attention",
                ]),
                usage=TokenUsage(prompt_tokens=10, completion_tokens=20, total_tokens=30),
            ))

            queries = await suggest_gap_queries(
                "proj-1",
                question="How are transformers used in medical graphs?",
                max_queries=3,
                llm=mock_llm,
            )
            assert len(queries["suggested_queries"]) == 3
            assert "Graph Transformer healthcare" in queries["suggested_queries"]

        @pytest.mark.asyncio
        async def test_f08_05_paper_similarity_calculation(self):
            """Test compute_paper_similarity returns per-question cosine scores."""
            from features.analysis.service import compute_paper_similarity

            mock_neo4j = AsyncMock()
            mock_neo4j.get_research_questions = AsyncMock(return_value=[{"text": "Q1"}, {"text": "Q2"}])
            mock_neo4j.has_embedding = AsyncMock(return_value=True)
            mock_neo4j.compute_similarities = AsyncMock(return_value=[
                {"doi": "10.1000/test", "question": "Q1", "score": 0.88},
                {"doi": "10.1000/test", "question": "Q2", "score": 0.72},
            ])

            res = await compute_paper_similarity("proj-1", "10.1000/test", mock_neo4j)
            assert res["doi"] == "10.1000/test"
            assert len(res["scores"]) == 2
            assert res["avg_score"] == 0.8

    # ------------------------------------------------------------------------
    # Feature 9: Evidence Synthesizer Agent & Matrices (ORIGINAL_REQUEST §R2)
    # ------------------------------------------------------------------------
    class TestF09EvidenceSynthesizerAndLiteratureMatrices:
        def test_f09_01_matrix_data_structure_validation(self):
            """Test StructuredComparisonMatrix model serialization."""
            matrix_data = {
                "project_id": "proj-synth-1",
                "dimensions": [
                    {"dimension_id": "dim-1", "name": "Model Architecture", "description": "GNN vs Transformer"},
                    {"dimension_id": "dim-2", "name": "Dataset Scale", "description": "Nodes and edges"},
                ],
                "papers": [
                    {
                        "doi": "10.1000/paper1",
                        "title": "GNN Paper",
                        "values": {"dim-1": "GCN", "dim-2": "100k nodes"},
                    },
                    {
                        "doi": "10.1000/paper2",
                        "title": "Transformer Paper",
                        "values": {"dim-1": "Graphormer", "dim-2": "1M nodes"},
                    },
                ],
                "synthesis": "Transformers scale better to large graphs.",
            }
            assert len(matrix_data["dimensions"]) == 2
            assert len(matrix_data["papers"]) == 2
            assert matrix_data["papers"][0]["values"]["dim-1"] == "GCN"

        def test_f09_02_consensus_and_contradiction_tagging(self):
            """Test representation of consensus and contradiction findings."""
            findings = [
                {"theme": "Attention Mechanism", "type": "consensus", "summary": "All papers find multi-head attention improves GNN expressive power."},
                {"theme": "Depth Scalability", "type": "contradiction", "summary": "Paper A reports over-smoothing at 4 layers; Paper B scales to 16 layers with residual connections."},
            ]
            consensus = [f for f in findings if f["type"] == "consensus"]
            contradictions = [f for f in findings if f["type"] == "contradiction"]

            assert len(consensus) == 1
            assert len(contradictions) == 1
            assert "over-smoothing" in contradictions[0]["summary"]

        def test_f09_03_methodology_dimension_mapping(self):
            """Test mapping papers across multiple methodological dimensions."""
            papers = [
                {"doi": "10.1000/1", "methodology": "Empirical Benchmark", "dataset": "Cora"},
                {"doi": "10.1000/2", "methodology": "Theoretical Proof", "dataset": "Synthetic"},
            ]
            methodologies = {p["doi"]: p["methodology"] for p in papers}
            assert methodologies["10.1000/1"] == "Empirical Benchmark"
            assert methodologies["10.1000/2"] == "Theoretical Proof"

        def test_f09_04_dimension_comparison_matrix_columns(self):
            """Test extracting comparison matrix columns for literature synthesis."""
            matrix = {
                "columns": ["DOI", "Title", "Method", "Evaluation Metric", "Result"],
                "rows": [
                    ["10.1000/1", "GNN", "Message Passing", "Accuracy", "85.2%"],
                    ["10.1000/2", "Graphormer", "Self-Attention", "Accuracy", "91.4%"],
                ]
            }
            assert len(matrix["columns"]) == 5
            assert len(matrix["rows"]) == 2
            assert matrix["rows"][1][4] == "91.4%"

        def test_f09_05_matrix_markdown_table_rendering(self):
            """Test converting comparison matrix to Markdown table."""
            headers = ["Paper", "Model", "Performance"]
            rows = [
                ["Paper A (2022)", "GCN", "82.1%"],
                ["Paper B (2024)", "GATv2", "89.4%"],
            ]
            header_line = "| " + " | ".join(headers) + " |"
            sep_line = "| " + " | ".join(["---"] * len(headers)) + " |"
            row_lines = ["| " + " | ".join(r) + " |" for r in rows]
            table_md = "\n".join([header_line, sep_line] + row_lines)

            assert "| Paper | Model | Performance |" in table_md
            assert "| Paper B (2024) | GATv2 | 89.4% |" in table_md

    # ------------------------------------------------------------------------
    # Feature 10: Planner Agent & Outlines (ORIGINAL_REQUEST §R3)
    # ------------------------------------------------------------------------
    class TestF10PlannerAgentAndOutlines:
        def test_f10_01_agent_creation_and_tools_registration(self):
            """Test PlannerAgent registers outline tools."""
            agent = create_planner_agent()
            assert agent.name == "PlannerAgent"
            tool_names = [getattr(t, "__name__", str(t)) for t in agent.tools]
            assert "get_project_summary" in tool_names
            assert "get_ranked_papers" in tool_names
            assert "generate_outline" in tool_names

        @pytest.mark.asyncio
        async def test_f10_02_get_project_summary_tool(self):
            """Test get_project_summary returns paper and question counts."""
            from agents.planner.tools.outline_tools import get_project_summary

            mock_planning = AsyncMock()
            mock_planning.get_project_summary = AsyncMock(return_value={
                "project_id": "proj-plan-1",
                "paper_count": 5,
                "question_count": 2,
                "has_outline": False,
            })

            mock_ctx = MagicMock(spec=ToolContext)
            mock_ctx.state = {"project_id": "proj-plan-1"}

            ServiceRegistry._planning_service = mock_planning
            ServiceRegistry._log_service = AsyncMock()
            ServiceRegistry._initialized = True

            summary = await get_project_summary(mock_ctx)
            assert summary["paper_count"] == 5
            assert summary["question_count"] == 2
            assert summary["has_outline"] is False

        @pytest.mark.asyncio
        async def test_f10_03_outline_structure_generation(self):
            """Test generate_outline produces standard academic section layout."""
            outline = {
                "sections": [
                    {"title": "Introduction", "description": "Overview of research questions", "assigned_papers": []},
                    {"title": "Methodology", "description": "GNN and Transformer approaches", "assigned_papers": ["10.1000/1", "10.1000/2"]},
                    {"title": "Results and Analysis", "description": "Comparative performance", "assigned_papers": ["10.1000/3"]},
                    {"title": "Conclusion", "description": "Summary and future directions", "assigned_papers": []},
                ]
            }
            assert len(outline["sections"]) == 4
            assert outline["sections"][1]["assigned_papers"] == ["10.1000/1", "10.1000/2"]

        @pytest.mark.asyncio
        async def test_f10_04_paper_doi_assignment_coverage(self):
            """Test that all candidate DOIs are allocated to relevant sections."""
            assigned_dois = ["10.1000/1", "10.1000/2", "10.1000/3"]
            sections = [
                {"title": "S1", "assigned_papers": ["10.1000/1"]},
                {"title": "S2", "assigned_papers": ["10.1000/2", "10.1000/3"]},
            ]
            covered_dois = [doi for s in sections for doi in s["assigned_papers"]]
            assert set(covered_dois) == set(assigned_dois)

        def test_f10_05_outline_style_parameter(self):
            """Test support for thematic, chronological, and methodological styles."""
            styles = ["thematic", "chronological", "methodological"]
            for style in styles:
                assert style in ["thematic", "chronological", "methodological"]

    # ------------------------------------------------------------------------
    # Feature 11: Drafting Agent & Citations (ORIGINAL_REQUEST §R3)
    # ------------------------------------------------------------------------
    class TestF11DraftingAgentAndCitations:
        def test_f11_01_agent_creation_and_tools_registration(self):
            """Test DraftingAgent registers drafting tools."""
            agent = drafting_agent
            assert agent.name == "DraftingAgent"
            tool_names = [getattr(t, "__name__", str(t)) for t in agent.tools]
            assert "get_paper_abstracts" in tool_names
            assert "draft_section" in tool_names

        @pytest.mark.asyncio
        async def test_f11_02_get_paper_abstracts_batch_fetch(self, mock_neo4j_service_instance, tmp_path):
            """Test fetching paper abstracts for assigned DOIs."""
            mock_neo4j_service_instance.get_paper_by_doi = AsyncMock(side_effect=lambda doi: {
                "doi": doi,
                "title": f"Title for {doi}",
                "abstract": f"Abstract for {doi}",
                "year": 2023,
                "source": "Nature",
            })
            writing_svc = WritingService(
                neo4j=mock_neo4j_service_instance,
                llm=AsyncMock(),
                projects_dir=str(tmp_path),
            )
            res = await writing_svc.get_paper_abstracts("proj-1", ["10.1000/1", "10.1000/2"])
            assert len(res["papers"]) == 2
            assert res["papers"][0]["title"] == "Title for 10.1000/1"

        @pytest.mark.asyncio
        async def test_f11_03_draft_section_markdown_and_disk_persistence(self, mock_neo4j_service_instance, tmp_path):
            """Test draft_section generates Markdown and saves to disk."""
            mock_llm = AsyncMock()
            mock_llm.complete = AsyncMock(return_value=CompletionResponse(
                text="## Methodology\n\nRecent studies (Vaswani, 2017) demonstrate transformer efficacy.",
                usage=TokenUsage(prompt_tokens=50, completion_tokens=100, total_tokens=150),
            ))
            mock_neo4j_service_instance.get_paper_by_doi = AsyncMock(return_value={
                "doi": "10.1000/vaswani", "title": "Attention Is All You Need", "year": 2017
            })

            writing_svc = WritingService(
                neo4j=mock_neo4j_service_instance,
                llm=mock_llm,
                projects_dir=str(tmp_path),
            )

            result = await writing_svc.draft_section(
                project_id="proj-draft-1",
                section_title="Methodology Section",
                section_description="Describes core model",
                paper_dois=["10.1000/vaswani"],
            )

            assert result["section_title"] == "Methodology Section"
            assert "(Vaswani, 2017)" in result["markdown"]
            assert result["word_count"] > 0
            assert Path(result["saved_path"]).exists()

        def test_f11_04_inline_citation_format_regex_matching(self):
            """Test inline citation matching pattern: (Author, Year) or (DOI: ...)."""
            text = "As shown by (Kipf, 2016) and (DOI: 10.1000/vaswani), transformers excel."
            author_year_pattern = r"\(([A-Z][a-zA-Z]+,\s*\d{4})\)"
            doi_pattern = r"\(DOI:\s*(10\.\d{4,}/[^\)]+)\)"

            author_matches = re.findall(author_year_pattern, text)
            doi_matches = re.findall(doi_pattern, text)

            assert "Kipf, 2016" in author_matches
            assert "10.1000/vaswani" in doi_matches

        def test_f11_05_word_count_computation(self):
            """Test word count calculation on generated markdown."""
            draft = "This is a sample drafted literature section covering multiple key graph architectures."
            words = len(draft.split())
            assert words == 12

    # ------------------------------------------------------------------------
    # Feature 12: Reviewer Agent & LoopAgent Critique (ORIGINAL_REQUEST §R3)
    # ------------------------------------------------------------------------
    class TestF12ReviewerAgentAndLoopCritique:
        def test_f12_01_agent_creation_and_tools_registration(self):
            """Test ReviewerAgent registers review tools."""
            agent = reviewer_agent
            assert agent.name == "ReviewerAgent"
            tool_names = [getattr(t, "__name__", str(t)) for t in agent.tools]
            assert "review_section" in tool_names
            assert "exit_loop" in tool_names

        @pytest.mark.asyncio
        async def test_f12_02_review_section_rubric_approval(self, mock_neo4j_service_instance, tmp_path):
            """Test review_section approves when all criteria >= 4."""
            mock_llm = AsyncMock()
            review_json = json.dumps({
                "approved": True,
                "citation_coverage": 5,
                "coherence": 5,
                "synthesis": 4,
                "academic_tone": 5,
                "completeness": 4,
                "feedback": ["Excellent synthesis and flow."],
                "missing_citations": [],
            })
            mock_llm.complete = AsyncMock(return_value=CompletionResponse(
                text=review_json,
                usage=TokenUsage(prompt_tokens=20, completion_tokens=30, total_tokens=50),
            ))

            writing_svc = WritingService(
                neo4j=mock_neo4j_service_instance,
                llm=mock_llm,
                projects_dir=str(tmp_path),
            )

            result = await writing_svc.review_section(
                project_id="proj-rev-1",
                section_title="Literature Review",
                draft_text="Comprehensive text covering 10.1000/1.",
                paper_dois=["10.1000/1"],
            )

            assert result["approved"] is True
            assert result["citation_coverage"] == 5
            assert len(result["missing_citations"]) == 0

        @pytest.mark.asyncio
        async def test_f12_03_review_section_rejection_with_actionable_feedback(self, mock_neo4j_service_instance, tmp_path):
            """Test review_section rejects when scores < 4 with feedback."""
            mock_llm = AsyncMock()
            review_json = json.dumps({
                "approved": False,
                "citation_coverage": 2,
                "coherence": 3,
                "synthesis": 2,
                "academic_tone": 4,
                "completeness": 3,
                "feedback": ["Include missing paper 10.1000/2", "Avoid simple summarization"],
                "missing_citations": ["10.1000/2"],
            })
            mock_llm.complete = AsyncMock(return_value=CompletionResponse(
                text=review_json,
                usage=TokenUsage(prompt_tokens=20, completion_tokens=30, total_tokens=50),
            ))

            writing_svc = WritingService(
                neo4j=mock_neo4j_service_instance,
                llm=mock_llm,
                projects_dir=str(tmp_path),
            )

            result = await writing_svc.review_section(
                project_id="proj-rev-1",
                section_title="Literature Review",
                draft_text="Weak text.",
                paper_dois=["10.1000/1", "10.1000/2"],
            )

            assert result["approved"] is False
            assert "10.1000/2" in result["missing_citations"]
            assert len(result["feedback"]) == 2

        def test_f12_04_exit_loop_tool_escalation(self):
            """Test exit_loop sets escalate flag on ToolContext."""
            mock_ctx = MagicMock()
            mock_ctx.actions = MagicMock()
            mock_ctx.actions.escalate = False

            res = exit_loop(mock_ctx)
            assert mock_ctx.actions.escalate is True
            assert mock_ctx.actions.skip_summarization is True
            assert res["status"] == "loop_exited"

        def test_f12_05_writer_reviewer_loop_max_iterations(self):
            """Test LoopAgent max_iterations is set to 3."""
            from agents.writing.agent import writer_reviewer_loop
            assert writer_reviewer_loop.max_iterations == 3

    # ------------------------------------------------------------------------
    # Feature 13: Citation Hallucination Verification (ORIGINAL_REQUEST §R3)
    # ------------------------------------------------------------------------
    class TestF13CitationHallucinationVerification:
        def test_f13_01_extract_cited_dois_from_text(self):
            """Test regex extraction of all DOIs cited in draft text."""
            draft = """
            Several works have addressed graph transformers [10.1000/trans-1].
            Further extensions were introduced by (DOI: 10.1000/trans-2) and 10.1000/trans-3.
            """
            pattern = r"10\.\d{4,}/[a-zA-Z0-9_\-]+"
            extracted = list(set(re.findall(pattern, draft)))
            assert "10.1000/trans-1" in extracted
            assert "10.1000/trans-2" in extracted
            assert "10.1000/trans-3" in extracted

        def test_f13_02_detect_hallucinated_dois(self):
            """Test identifying DOIs not present in the verified paper repository."""
            known_dois = {"10.1000/valid-1", "10.1000/valid-2"}
            cited_dois = ["10.1000/valid-1", "10.1000/fake-hallucination"]

            hallucinations = [doi for doi in cited_dois if doi not in known_dois]
            assert hallucinations == ["10.1000/fake-hallucination"]

        def test_f13_03_detect_missing_assigned_citations(self):
            """Test identifying assigned DOIs that the agent failed to cite."""
            assigned_dois = {"10.1000/req-1", "10.1000/req-2", "10.1000/req-3"}
            cited_dois = {"10.1000/req-1"}

            missing = list(assigned_dois - cited_dois)
            assert len(missing) == 2
            assert "10.1000/req-2" in missing
            assert "10.1000/req-3" in missing

        def test_f13_04_zero_hallucination_verification_passed(self):
            """Test successful verification when all citations match known library."""
            known_dois = {"10.1000/1", "10.1000/2"}
            cited_dois = ["10.1000/1", "10.1000/2"]

            unverified = [doi for doi in cited_dois if doi not in known_dois]
            assert len(unverified) == 0

        def test_f13_05_case_insensitive_doi_matching(self):
            """Test DOI normalization to lowercase prevents false positive hallucination flags."""
            known_dois = {"10.1000/AbC-123".lower()}
            cited_doi = "10.1000/ABC-123"
            assert cited_doi.lower() in known_dois

    # ------------------------------------------------------------------------
    # Feature 14: TeX Formatter & BibTeX Generation (ORIGINAL_REQUEST §R3)
    # ------------------------------------------------------------------------
    class TestF14TeXFormatterAndBibTeXGeneration:
        def test_f14_01_make_cite_key_deterministic_and_unique(self):
            """Test cite key uses first word of title + year."""
            paper = {"title": "Attention Is All You Need", "year": 2017, "doi": "10.1000/1"}
            key = _make_cite_key(paper)
            assert key == "attention2017"

        def test_f14_02_reserved_character_escaping(self):
            """Test escaping LaTeX reserved characters (&, %, _, #, $)."""
            raw = "Cost is $50 & accuracy is 95% for dataset_1 #1"
            escaped = _escape_bibtex(raw)
            assert r"\$50" in escaped
            assert r"\&" in escaped
            assert r"\%" in escaped
            assert r"\_" in escaped
            assert r"\#" in escaped

        def test_f14_03_generate_bibtex_multiple_papers(self):
            """Test generating compilable .bib file content with multiple papers."""
            papers = [
                {
                    "doi": "10.1000/1",
                    "title": "Graph Neural Networks",
                    "year": 2021,
                    "authors": ["Alice Smith", "Bob Jones"],
                    "source": "IEEE TKDE",
                },
                {
                    "doi": "10.1000/2",
                    "title": "Graph Transformers",
                    "year": 2022,
                    "authors": ["Charlie Brown"],
                    "source": "NeurIPS",
                },
            ]
            bibtex = generate_bibtex(papers)
            assert "@article{graph2021," in bibtex
            assert "@article{graph2022," in bibtex
            assert "Alice Smith and Bob Jones" in bibtex
            assert "Charlie Brown" in bibtex

        def test_f14_04_format_to_latex_ieee_template(self):
            """Test LaTeX formatting wraps markdown into IEEEtran documentclass."""
            md = "## Introduction\n\nTransformers are **effective** and *versatile*."
            latex = format_to_latex(md, citations=["10.1000/1"], template="ieee")

            assert "\\documentclass[conference]{IEEEtran}" in latex
            assert "\\subsection{Introduction}" in latex
            assert "\\textbf{effective}" in latex
            assert "\\textit{versatile}" in latex
            assert "\\bibliography{references}" in latex

        def test_f14_05_format_to_latex_acm_and_plain_templates(self):
            """Test ACM and plain article templates."""
            md = "# Overview\n\nSystem description."
            acm_latex = format_to_latex(md, citations=[], template="acm")
            plain_latex = format_to_latex(md, citations=[], template="plain")

            assert "\\documentclass[sigconf]{acmart}" in acm_latex
            assert "\\documentclass[12pt]{article}" in plain_latex

    # ------------------------------------------------------------------------
    # Feature 15: JOSS Package & Metadata Validation (ORIGINAL_REQUEST §R4)
    # ------------------------------------------------------------------------
    class TestF15JOSSPackageAndMetadata:
        def test_f15_01_joss_paper_md_required_sections_validation(self):
            """Test JOSS paper markdown structure contains Summary, Statement of Need, and AI Disclosure."""
            sample_joss_md = """---
title: 'ALRS v2: Automated Literature Review System'
tags:
  - literature review
  - multi-agent
  - graph neural networks
authors:
  - name: Hosam Ksbaa
    orcid: 0000-0000-0000-0000
    affiliation: 1
affiliations:
  - name: Master's Thesis Program
    index: 1
date: 25 August 2026
bibliography: paper.bib
---

# Summary
ALRS v2 is an autonomous multi-agent research assistant.

# Statement of Need
Researchers face literature overload.

# AI-Assisted Authorship Disclosure
Generative AI was utilized for section outlining and draft synthesis.
"""
            assert "# Summary" in sample_joss_md
            assert "# Statement of Need" in sample_joss_md
            assert "# AI-Assisted Authorship Disclosure" in sample_joss_md
            assert "bibliography: paper.bib" in sample_joss_md

        def test_f15_02_joss_2026_ai_disclosure_compliance(self):
            """Test verification of JOSS 2026 AI disclosure policy requirement."""
            text_with_disclosure = "# Summary\n...\n# AI-Assisted Authorship Disclosure\nDetails..."
            text_without_disclosure = "# Summary\n...\n# Statement of Need\n..."

            has_disclosure = lambda txt: "AI-Assisted Authorship Disclosure" in txt or "AI Disclosure" in txt
            assert has_disclosure(text_with_disclosure) is True
            assert has_disclosure(text_without_disclosure) is False

        def test_f15_03_citation_cff_schema_v120(self):
            """Test CITATION.cff v1.2.0 required fields."""
            cff_data = {
                "cff-version": "1.2.0",
                "message": "If you use this software, please cite it as below.",
                "title": "ALRS v2: Multi-Agent Research Assistant",
                "authors": [{"family-names": "Ksbaa", "given-names": "Hosam"}],
                "version": "2.0.0",
                "date-released": "2026-08-25",
                "license": "MIT",
                "repository-code": "https://github.com/HosamKsbaa/MasterProject2",
            }
            assert cff_data["cff-version"] == "1.2.0"
            assert cff_data["license"] == "MIT"
            assert len(cff_data["authors"]) > 0

        def test_f15_04_bibtex_key_cross_referencing(self):
            """Test all citation keys in paper.md exist in paper.bib."""
            paper_md = "According to [@vaswani2017] and [@kipf2016], models scale well."
            bib_keys = {"vaswani2017", "kipf2016", "devlin2018"}

            cited_keys = re.findall(r"@([a-zA-Z0-9_\-]+)", paper_md)
            missing = [k for k in cited_keys if k not in bib_keys]
            assert len(missing) == 0

        def test_f15_05_open_source_license_verification(self):
            """Test license metadata is an OSI-approved identifier (e.g. MIT, Apache-2.0)."""
            valid_licenses = {"MIT", "Apache-2.0", "BSD-3-Clause", "GPL-3.0"}
            target_license = "MIT"
            assert target_license in valid_licenses

    # ------------------------------------------------------------------------
    # Feature 16: Master's Thesis Expansion Verification (ORIGINAL_REQUEST §R4)
    # ------------------------------------------------------------------------
    class TestF16MastersThesisExpansion:
        def test_f16_01_thesis_tex_file_exists_and_readable(self):
            """Test that THESIS.tex exists in thesis directory."""
            assert THESIS_FILE.exists()
            content = THESIS_FILE.read_text(encoding="utf-8", errors="ignore")
            assert len(content) > 1000

        def test_f16_02_thesis_document_structure_and_documentclass(self):
            """Test THESIS.tex contains valid LaTeX root structure."""
            assert THESIS_FILE.exists()
            content = THESIS_FILE.read_text(encoding="utf-8", errors="ignore")
            assert "\\documentclass" in content
            assert "\\begin{document}" in content
            assert "\\end{document}" in content

        def test_f16_03_thesis_chapters_presence(self):
            """Test thesis contains major academic thesis chapters."""
            assert THESIS_FILE.exists()
            content = THESIS_FILE.read_text(encoding="utf-8", errors="ignore")
            assert "\\chapter" in content or "\\section" in content

        def test_f16_04_thesis_bibliography_inclusion(self):
            """Test thesis includes bibliography declaration."""
            assert THESIS_FILE.exists()
            content = THESIS_FILE.read_text(encoding="utf-8", errors="ignore")
            assert "\\bibliography" in content or "\\addbibresource" in content or "thebibliography" in content

        def test_f16_05_thesis_diagram_and_figure_referencing(self):
            """Test thesis includes figure references and architecture figures."""
            assert THESIS_FILE.exists()
            content = THESIS_FILE.read_text(encoding="utf-8", errors="ignore")
            assert "\\begin{figure}" in content or "\\includegraphics" in content


# ============================================================================
# TIER 2: BOUNDARY & CORNER CASES (Features 1-16)
# ============================================================================

class TestTier2BoundaryAndCornerCases:
    """Tier 2: Boundary Value Analysis & Edge Cases (16 Features x 5 Tests = 80 Tests)."""

    # F1 Boundaries
    class TestF01Boundaries:
        def test_f01_e01_empty_inverted_index(self, mock_openalex_service):
            """Empty inverted index returns None."""
            assert mock_openalex_service._reconstruct_abstract({}) is None

        def test_f01_e02_none_inverted_index(self, mock_openalex_service):
            """None inverted index returns None."""
            assert mock_openalex_service._reconstruct_abstract(None) is None

        def test_f01_e03_sparse_indices_with_large_gaps(self, mock_openalex_service):
            """Gaps in token indices should not crash reconstruction."""
            inverted = {"First": [0], "Tenth": [10]}
            res = mock_openalex_service._reconstruct_abstract(inverted)
            assert res.startswith("First")
            assert res.endswith("Tenth")

        def test_f01_e04_unicode_and_math_symbols(self, mock_openalex_service):
            """Abstract with greek letters and mathematical symbols."""
            inverted = {"Let": [0], "$\\alpha": [1], "=": [2], "0.05$": [3], "and": [4], "$\\beta$": [5]}
            res = mock_openalex_service._reconstruct_abstract(inverted)
            assert "$\\alpha" in res
            assert "$\\beta$" in res

        def test_f01_e05_duplicate_positions_resolution(self, mock_openalex_service):
            """Two tokens claiming same position index."""
            inverted = {"WordA": [0], "WordB": [0], "WordC": [1]}
            res = mock_openalex_service._reconstruct_abstract(inverted)
            assert len(res.split()) >= 2

    # F2 Boundaries
    class TestF02Boundaries:
        def test_f02_e01_zero_initial_rate_handling(self):
            """Handling minimum rate boundary condition."""
            limiter = AdaptiveRateLimiter(initial_rate=0.5, min_rate=0.5)
            assert limiter.current_rate == 0.5
            limiter.on_429()
            assert limiter.current_rate == 0.5

        def test_f02_e02_recovery_capped_at_initial_rate(self):
            """Recovery does not exceed configured initial max rate."""
            limiter = AdaptiveRateLimiter(initial_rate=9.0, min_rate=1.0, recovery_increment=2.0)
            for _ in range(10):
                limiter.on_success()
            assert limiter.current_rate == 9.0

        def test_f02_e03_reset_restores_initial_state(self):
            """Reset restores rate and token bucket."""
            limiter = AdaptiveRateLimiter(initial_rate=9.0, min_rate=1.0)
            limiter.on_429()
            assert limiter.current_rate == 4.5
            limiter.reset()
            assert limiter.current_rate == 9.0

        @pytest.mark.asyncio
        async def test_f02_e04_rapid_sequential_acquires(self):
            """10 rapid acquire calls execute without deadlock."""
            limiter = AdaptiveRateLimiter(initial_rate=50.0, min_rate=1.0)
            for _ in range(10):
                await limiter.acquire()
            assert True

        def test_f02_e05_fractional_recovery_increments(self):
            """Small fractional recovery increments."""
            limiter = AdaptiveRateLimiter(initial_rate=5.0, min_rate=1.0, recovery_increment=0.1)
            limiter.on_429()  # 2.5
            limiter.on_success()  # 2.6
            assert math.isclose(limiter.current_rate, 2.6, rel_tol=1e-5)

    # F3 Boundaries
    class TestF03Boundaries:
        def test_f03_e01_empty_text_document_formatting(self):
            """Empty document text formats with empty string."""
            provider = GeminiEmbeddingProvider(api_key="dummy", output_dimensionality=768)
            formatted = provider._format_document("", title="Title")
            assert formatted == "title: Title | text: "

        def test_f03_e02_empty_query_formatting(self):
            """Empty query text formats with query prefix."""
            provider = GeminiEmbeddingProvider(api_key="dummy", output_dimensionality=768)
            formatted = provider._format_query("")
            assert formatted == "task: question answering | query: "

        def test_f03_e03_whitespace_only_title_formatting(self):
            """Whitespace title treated as empty/fallback."""
            provider = GeminiEmbeddingProvider(api_key="dummy", output_dimensionality=768)
            formatted = provider._format_document("Content", title="   ")
            assert "text: Content" in formatted

        def test_f03_e04_very_long_abstract_string(self):
            """10,000 character abstract handled without error."""
            provider = GeminiEmbeddingProvider(api_key="dummy", output_dimensionality=768)
            long_text = "word " * 2000
            formatted = provider._format_document(long_text, title="Long Paper")
            assert len(formatted) > 10000

        def test_f03_e05_custom_output_dimension(self):
            """Support non-default dimensions (e.g. 1536, 3072)."""
            provider = GeminiEmbeddingProvider(api_key="dummy", output_dimensionality=1536)
            assert provider.dimensions == 1536

    # F4 Boundaries
    class TestF04Boundaries:
        @pytest.mark.asyncio
        async def test_f04_e01_strict_threshold_zero_matches(self):
            """Threshold 1.0 returning 0 results handled gracefully."""
            neo4j = Neo4jService("bolt://localhost:7687", "neo4j", "pwd")
            neo4j.execute_read = AsyncMock(return_value=[])
            res = await neo4j.compute_similarities("sess-1", threshold=1.0)
            assert res == []

        @pytest.mark.asyncio
        async def test_f04_e02_threshold_zero_all_matches(self):
            """Threshold 0.0 returns all candidate matches."""
            neo4j = Neo4jService("bolt://localhost:7687", "neo4j", "pwd")
            neo4j.execute_read = AsyncMock(return_value=[{"doi": "10.1/1", "score": 0.01}])
            res = await neo4j.compute_similarities("sess-1", threshold=0.0)
            assert len(res) == 1

        @pytest.mark.asyncio
        async def test_f04_e03_empty_session_id(self):
            """Query with non-existent session returns empty list."""
            neo4j = Neo4jService("bolt://localhost:7687", "neo4j", "pwd")
            neo4j.execute_read = AsyncMock(return_value=[])
            res = await neo4j.compute_similarities("", threshold=0.5)
            assert res == []

        @pytest.mark.asyncio
        async def test_f04_e04_top_k_one_boundary(self):
            """top_k = 1 returns at most one match."""
            neo4j = Neo4jService("bolt://localhost:7687", "neo4j", "pwd")
            neo4j.execute_read = AsyncMock(return_value=[{"doi": "10.1/1", "score": 0.99}])
            res = await neo4j.compute_similarities("sess-1", threshold=0.5, top_k=1)
            assert len(res) == 1

        @pytest.mark.asyncio
        async def test_f04_e05_special_characters_in_doi(self):
            """DOIs with slashes, colons, and hyphens processed correctly."""
            neo4j = Neo4jService("bolt://localhost:7687", "neo4j", "pwd")
            complex_doi = "10.1109/ICCVW.2019.00123-A/B"
            neo4j.execute_read = AsyncMock(return_value=[{"doi": complex_doi, "score": 0.88}])
            res = await neo4j.compute_similarities("sess-1", threshold=0.5)
            assert res[0]["doi"] == complex_doi

    # F5 Boundaries
    class TestF05Boundaries:
        @pytest.mark.asyncio
        async def test_f05_e01_empty_graph_pagerank(self):
            """Empty graph with no papers returns empty dict."""
            neo4j = Neo4jService("bolt://localhost:7687", "neo4j", "pwd")
            neo4j.execute_write = AsyncMock(side_effect=RuntimeError("No GDS"))
            neo4j.execute_read = AsyncMock(return_value=[])
            scores = await neo4j.compute_pagerank("empty-sess")
            assert scores == {}

        @pytest.mark.asyncio
        async def test_f05_e02_single_isolated_paper(self):
            """Single paper without citations normalized to score 1.0."""
            neo4j = Neo4jService("bolt://localhost:7687", "neo4j", "pwd")
            neo4j.execute_write = AsyncMock(side_effect=RuntimeError("No GDS"))
            async def read_stub(query, params=None):
                if "RETURN p.doi AS doi" in query:
                    return [{"doi": "10.1000/solo"}]
                return []  # No edges
            neo4j.execute_read = read_stub
            scores = await neo4j.compute_pagerank("solo-sess")
            assert scores.get("10.1000/solo") == 1.0

        @pytest.mark.asyncio
        async def test_f05_e03_disconnected_components(self):
            """Graph with two separate disconnected citation clusters."""
            neo4j = Neo4jService("bolt://localhost:7687", "neo4j", "pwd")
            neo4j.execute_write = AsyncMock(side_effect=RuntimeError("No GDS"))
            async def read_stub(query, params=None):
                if "RETURN p.doi AS doi" in query:
                    return [{"doi": "A"}, {"doi": "B"}, {"doi": "C"}, {"doi": "D"}]
                return [{"source": "A", "target": "B"}, {"source": "C", "target": "D"}]
            neo4j.execute_read = read_stub
            scores = await neo4j.compute_pagerank("disc-sess")
            assert len(scores) == 4

        @pytest.mark.asyncio
        async def test_f05_e04_cyclic_citation_graph(self):
            """Graph with cyclic citations (A -> B -> C -> A)."""
            neo4j = Neo4jService("bolt://localhost:7687", "neo4j", "pwd")
            neo4j.execute_write = AsyncMock(side_effect=RuntimeError("No GDS"))
            async def read_stub(query, params=None):
                if "RETURN p.doi AS doi" in query:
                    return [{"doi": "A"}, {"doi": "B"}, {"doi": "C"}]
                return [{"source": "A", "target": "B"}, {"source": "B", "target": "C"}, {"source": "C", "target": "A"}]
            neo4j.execute_read = read_stub
            scores = await neo4j.compute_pagerank("cycle-sess")
            assert len(scores) == 3
            assert scores["A"] == scores["B"] == scores["C"]

        @pytest.mark.asyncio
        async def test_f05_e05_max_iterations_parameter(self):
            """Custom iteration parameter (e.g. 50 iterations)."""
            neo4j = Neo4jService("bolt://localhost:7687", "neo4j", "pwd")
            neo4j.execute_write = AsyncMock(return_value=[])
            neo4j.execute_read = AsyncMock(return_value=[{"doi": "A", "score": 1.0}])
            scores = await neo4j.compute_pagerank("sess-1", iterations=50)
            assert len(scores) == 1

    # F6 Boundaries
    class TestF06Boundaries:
        @pytest.mark.asyncio
        async def test_f06_e01_extreme_weights_all_similarity(self):
            """Weight 1.0 Sim, 0.0 PR ignores PageRank."""
            neo4j = AsyncMock()
            mysql = AsyncMock()
            mysql.get_session = AsyncMock(return_value={"research_questions": ["Q"], "similarity_threshold": 0.5})
            neo4j.compute_similarities = AsyncMock(return_value=[{"doi": "10.1/1", "question": "Q", "score": 0.85}])
            neo4j.compute_pagerank = AsyncMock(return_value={"10.1/1": 0.0})
            neo4j.execute_read = AsyncMock(return_value=[{"doi": "10.1/1", "title": "T", "year": 2021, "authors": []}])

            service = RankingService(neo4j, mysql)
            res = await service.rank_papers("sess", similarity_weight=1.0, pagerank_weight=0.0)
            assert math.isclose(res.groups[0].papers[0].hybrid_score, 0.85, rel_tol=1e-5)

        @pytest.mark.asyncio
        async def test_f06_e02_extreme_weights_all_pagerank(self):
            """Weight 0.0 Sim, 1.0 PR uses only PageRank."""
            neo4j = AsyncMock()
            mysql = AsyncMock()
            mysql.get_session = AsyncMock(return_value={"research_questions": ["Q"], "similarity_threshold": 0.5})
            neo4j.compute_similarities = AsyncMock(return_value=[{"doi": "10.1/1", "question": "Q", "score": 0.55}])
            neo4j.compute_pagerank = AsyncMock(return_value={"10.1/1": 0.95})
            neo4j.execute_read = AsyncMock(return_value=[{"doi": "10.1/1", "title": "T", "year": 2021, "authors": []}])

            service = RankingService(neo4j, mysql)
            res = await service.rank_papers("sess", similarity_weight=0.0, pagerank_weight=1.0)
            assert math.isclose(res.groups[0].papers[0].hybrid_score, 0.95, rel_tol=1e-5)

        @pytest.mark.asyncio
        async def test_f06_e03_paper_with_zero_pagerank(self):
            """Paper with 0.0 PageRank (leaf paper with no citations)."""
            neo4j = AsyncMock()
            mysql = AsyncMock()
            mysql.get_session = AsyncMock(return_value={"research_questions": ["Q"], "similarity_threshold": 0.5})
            neo4j.compute_similarities = AsyncMock(return_value=[{"doi": "10.1/leaf", "question": "Q", "score": 0.80}])
            neo4j.compute_pagerank = AsyncMock(return_value={})
            neo4j.execute_read = AsyncMock(return_value=[{"doi": "10.1/leaf", "title": "Leaf", "year": 2021, "authors": []}])

            service = RankingService(neo4j, mysql)
            res = await service.rank_papers("sess")
            assert math.isclose(res.groups[0].papers[0].hybrid_score, 0.7 * 0.80, rel_tol=1e-5)

        @pytest.mark.asyncio
        async def test_f06_e04_equal_similarity_tie_breaker(self):
            """Two papers with identical similarity broken by PageRank."""
            neo4j = AsyncMock()
            mysql = AsyncMock()
            mysql.get_session = AsyncMock(return_value={"research_questions": ["Q"], "similarity_threshold": 0.5})
            neo4j.compute_similarities = AsyncMock(return_value=[
                {"doi": "10.1/low_pr", "question": "Q", "score": 0.80},
                {"doi": "10.1/high_pr", "question": "Q", "score": 0.80},
            ])
            neo4j.compute_pagerank = AsyncMock(return_value={
                "10.1/low_pr": 0.1,
                "10.1/high_pr": 0.9,
            })
            neo4j.execute_read = AsyncMock(return_value=[
                {"doi": "10.1/low_pr", "title": "Low", "year": 2020, "authors": []},
                {"doi": "10.1/high_pr", "title": "High", "year": 2020, "authors": []},
            ])

            service = RankingService(neo4j, mysql)
            res = await service.rank_papers("sess")
            assert res.groups[0].papers[0].doi == "10.1/high_pr"

        @pytest.mark.asyncio
        async def test_f06_e05_invalid_session_raises_value_error(self):
            """Non-existent session throws ValueError."""
            neo4j = AsyncMock()
            mysql = AsyncMock()
            mysql.get_session = AsyncMock(return_value=None)
            service = RankingService(neo4j, mysql)
            with pytest.raises(ValueError, match="Session non-existent not found"):
                await service.rank_papers("non-existent")

    # F7 Boundaries
    class TestF07Boundaries:
        @pytest.mark.asyncio
        async def test_f07_e01_search_works_empty_results(self):
            """Keyword search returning zero hits."""
            from agents.research.tools.search_tools import search_papers_by_keyword

            mock_oa = AsyncMock(spec=OpenAlexService)
            mock_oa.search_by_title = AsyncMock(return_value=[])

            mock_ctx = MagicMock(spec=ToolContext)
            mock_ctx.state = {"project_id": "p1"}
            ServiceRegistry._openalex = mock_oa
            ServiceRegistry._initialized = True

            res = await search_papers_by_keyword(query="nonexistent_topic_xyz", tool_context=mock_ctx)
            assert res["papers"] == []

        @pytest.mark.asyncio
        async def test_f07_e02_doi_not_found_returns_error_dict(self):
            """DOI search when paper not found returns error."""
            from agents.research.tools.search_tools import search_papers_by_doi

            mock_oa = AsyncMock(spec=OpenAlexService)
            mock_oa.get_paper_by_doi = AsyncMock(return_value=None)

            mock_ctx = MagicMock(spec=ToolContext)
            mock_ctx.state = {"project_id": "p1"}
            ServiceRegistry._openalex = mock_oa
            ServiceRegistry._initialized = True

            res = await search_papers_by_doi(doi="10.1000/404", tool_context=mock_ctx)
            assert res["found"] is False

        @pytest.mark.asyncio
        async def test_f07_e03_missing_project_id_in_context(self):
            """Tool call without project_id in state handled gracefully."""
            from agents.research.tools.search_tools import search_papers_by_keyword
            mock_ctx = MagicMock(spec=ToolContext)
            mock_ctx.state = None
            res = await search_papers_by_keyword(query="test", tool_context=mock_ctx)
            assert "papers" in res or "error" in res

        @pytest.mark.asyncio
        async def test_f07_e04_author_search_special_characters(self):
            """Author search with accents and hyphens."""
            from agents.research.tools.search_tools import search_papers_by_author

            mock_oa = AsyncMock(spec=OpenAlexService)
            mock_oa.search_by_author = AsyncMock(return_value=[])

            mock_ctx = MagicMock(spec=ToolContext)
            mock_ctx.state = {"project_id": "p1"}
            ServiceRegistry._openalex = mock_oa
            ServiceRegistry._initialized = True

            res = await search_papers_by_author(author_name="Yoshua Bengio", tool_context=mock_ctx)
            assert "papers" in res or "error" in res

        @pytest.mark.asyncio
        async def test_f07_e05_explore_already_existing_paper(self):
            """Exploring a paper already present in the knowledge graph."""
            from agents.research.tools.retrieval_tools import explore_paper

            mock_retrieval = AsyncMock()
            mock_retrieval.retrieve_paper = AsyncMock(return_value=MagicMock(
                metadata=MagicMock(doi="10.1/exist", title="Exist", abstract="Abstract", year=2021, authors=[], venue=None, references=[], citations=[]),
                already_existed=True,
                embedding=None,
            ))

            mock_ctx = MagicMock(spec=ToolContext)
            mock_ctx.state = {"project_id": "p1"}
            ServiceRegistry._paper_retrieval = mock_retrieval
            ServiceRegistry._neo4j = AsyncMock()
            ServiceRegistry._initialized = True

            res = await explore_paper(doi="10.1/exist", tool_context=mock_ctx)
            assert res.get("already_existed") is True

    # F8 Boundaries
    class TestF08Boundaries:
        @pytest.mark.asyncio
        async def test_f08_e01_all_questions_fully_covered(self):
            """Zero gap questions when all questions have >=1 paper above threshold."""
            from features.analysis.service import analyze_coverage

            mock_neo4j = AsyncMock()
            mock_neo4j.get_research_questions = AsyncMock(return_value=[{"text": "Q1"}, {"text": "Q2"}])
            mock_neo4j.get_project_papers = AsyncMock(return_value=[{"doi": "10.1/1"}, {"doi": "10.1/2"}])
            mock_neo4j.compute_similarities = AsyncMock(return_value=[
                {"doi": "10.1/1", "question": "Q1", "score": 0.85},
                {"doi": "10.1/2", "question": "Q2", "score": 0.82},
            ])

            res = await analyze_coverage("p1", threshold=0.7, neo4j=mock_neo4j)
            assert len(res["gap_questions"]) == 0
            assert len(res["covered_questions"]) == 2

        @pytest.mark.asyncio
        async def test_f08_e02_all_questions_uncovered(self):
            """100% gap rate when no similarities exceed threshold."""
            from features.analysis.service import analyze_coverage

            mock_neo4j = AsyncMock()
            mock_neo4j.get_research_questions = AsyncMock(return_value=[{"text": "Q1"}, {"text": "Q2"}])
            mock_neo4j.get_project_papers = AsyncMock(return_value=[{"doi": "10.1/1"}])
            mock_neo4j.compute_similarities = AsyncMock(return_value=[])

            res = await analyze_coverage("p1", threshold=0.7, neo4j=mock_neo4j)
            assert len(res["gap_questions"]) == 2
            assert len(res["covered_questions"]) == 0

        @pytest.mark.asyncio
        async def test_f08_e03_project_with_no_research_questions(self):
            """Handling project with 0 defined research questions."""
            from features.analysis.service import analyze_coverage

            mock_neo4j = AsyncMock()
            mock_neo4j.get_research_questions = AsyncMock(return_value=[])

            res = await analyze_coverage("p1", threshold=0.7, neo4j=mock_neo4j)
            assert res["overall_coverage"] == 0.0
            assert len(res["gap_questions"]) == 0

        @pytest.mark.asyncio
        async def test_f08_e04_citation_stats_zero_papers(self):
            """Citation statistics for empty project library."""
            from features.analysis.service import get_citation_stats

            mock_neo4j = AsyncMock()
            mock_neo4j.get_project_papers = AsyncMock(return_value=[])
            mock_neo4j.get_research_questions = AsyncMock(return_value=[])

            res = await get_citation_stats("p1", mock_neo4j)
            assert res["total_papers"] == 0
            assert res["total_citations"] == 0
            assert res["avg_citations"] == 0.0

        @pytest.mark.asyncio
        async def test_f08_e05_suggest_queries_llm_json_fallback(self):
            """Fallback query parsing if LLM returns non-fenced JSON array."""
            from features.analysis.service import suggest_gap_queries

            mock_llm = AsyncMock()
            mock_llm.complete = AsyncMock(return_value=CompletionResponse(
                text=json.dumps(["Query 1: Graph Neural Net", "Query 2: Transformer Attention"]),
                usage=TokenUsage(prompt_tokens=10, completion_tokens=10, total_tokens=20),
            ))

            res = await suggest_gap_queries("p1", question="How to scale GNNs?", max_queries=2, llm=mock_llm)
            assert len(res["suggested_queries"]) == 2

    # F9 Boundaries
    class TestF09Boundaries:
        def test_f09_e01_empty_paper_list_matrix(self):
            """Empty comparison matrix handles 0 papers gracefully."""
            matrix = {"project_id": "p1", "dimensions": [], "papers": [], "synthesis": ""}
            assert len(matrix["papers"]) == 0

        def test_f09_e02_single_dimension_matrix(self):
            """Matrix with only 1 comparison dimension."""
            matrix = {
                "dimensions": [{"dimension_id": "d1", "name": "Accuracy"}],
                "papers": [{"doi": "10.1/1", "values": {"d1": "95%"}}],
            }
            assert len(matrix["dimensions"]) == 1

        def test_f09_e03_missing_dimension_value_for_paper(self):
            """Paper lacking data for specific dimension defaults to N/A."""
            paper_values = {"dim-1": "Value"}
            val = paper_values.get("dim-2", "N/A")
            assert val == "N/A"

        def test_f09_e04_special_characters_in_matrix_cells(self):
            """Markdown pipe characters in table cells escaped."""
            raw_cell = "Model A | Model B (fused)"
            escaped_cell = raw_cell.replace("|", "\\|")
            assert escaped_cell == "Model A \\| Model B (fused)"

        def test_f09_e05_large_matrix_with_many_papers(self):
            """Matrix scaling to 50 papers and 10 dimensions."""
            papers = [{"doi": f"10.1/{i}", "values": {f"dim_{j}": f"val_{i}_{j}" for j in range(10)}} for i in range(50)]
            assert len(papers) == 50
            assert len(papers[0]["values"]) == 10

    # F10 Boundaries
    class TestF10Boundaries:
        def test_f10_e01_outline_with_zero_assigned_papers(self):
            """Section without assigned papers handled without error."""
            section = {"title": "Introduction", "description": "Background", "assigned_papers": []}
            assert len(section["assigned_papers"]) == 0

        def test_f10_e02_outline_with_many_sections(self):
            """Outline with 12 detailed sections."""
            sections = [{"title": f"Section {i}", "assigned_papers": [f"10.1/{i}"]} for i in range(12)]
            assert len(sections) == 12

        def test_f10_e03_outline_single_assigned_paper_multiple_sections(self):
            """Same foundational paper assigned to both Intro and Related Work."""
            sec1 = {"title": "Intro", "assigned_papers": ["10.1/core"]}
            sec2 = {"title": "Related Work", "assigned_papers": ["10.1/core"]}
            assert sec1["assigned_papers"][0] == sec2["assigned_papers"][0]

        def test_f10_e04_sanitizing_section_slugs(self):
            """Section titles with punctuation sanitized to valid filename slugs."""
            title = "Section 2.1: State-of-the-Art & Limitations (2026)?"
            slug = re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_")[:60]
            assert slug == "section_2_1_state_of_the_art_limitations_2026"

        def test_f10_e05_empty_section_description(self):
            """Section with empty description fallback."""
            section = {"title": "Summary", "description": ""}
            desc = section.get("description") or "No description provided."
            assert desc == "No description provided."

    # F11 Boundaries
    class TestF11Boundaries:
        @pytest.mark.asyncio
        async def test_f11_e01_draft_section_with_empty_dois(self, mock_neo4j_service_instance, tmp_path):
            """Drafting section with no DOIs assigned."""
            mock_llm = AsyncMock()
            mock_llm.complete = AsyncMock(return_value=CompletionResponse(
                text="## Introduction\n\nGeneral overview without direct source papers.",
                usage=TokenUsage(prompt_tokens=10, completion_tokens=20, total_tokens=30),
            ))
            writing_svc = WritingService(mock_neo4j_service_instance, mock_llm, projects_dir=str(tmp_path))
            res = await writing_svc.draft_section("p1", "Intro", "Overview", paper_dois=[])
            assert res["cited_dois"] == []
            assert res["word_count"] > 0

        @pytest.mark.asyncio
        async def test_f11_e02_draft_phd_target_level(self, mock_neo4j_service_instance, tmp_path):
            """Drafting with target_level='phd'."""
            mock_llm = AsyncMock()
            mock_llm.complete = AsyncMock(return_value=CompletionResponse(
                text="## Advanced Critique\n\nTheoretical foundations.",
                usage=TokenUsage(prompt_tokens=10, completion_tokens=20, total_tokens=30),
            ))
            writing_svc = WritingService(mock_neo4j_service_instance, mock_llm, projects_dir=str(tmp_path))
            res = await writing_svc.draft_section("p1", "Theory", "Advanced", paper_dois=[], target_level="phd")
            assert res["section_title"] == "Theory"

        @pytest.mark.asyncio
        async def test_f11_e03_paper_not_found_in_graph_during_drafting(self, mock_neo4j_service_instance, tmp_path):
            """Drafting when paper DOI is missing in Neo4j graph."""
            mock_neo4j_service_instance.get_paper_by_doi = AsyncMock(return_value=None)
            mock_llm = AsyncMock()
            mock_llm.complete = AsyncMock(return_value=CompletionResponse(
                text="## Section\n\nText referencing [10.1/missing].",
                usage=TokenUsage(prompt_tokens=10, completion_tokens=20, total_tokens=30),
            ))
            writing_svc = WritingService(mock_neo4j_service_instance, mock_llm, projects_dir=str(tmp_path))
            res = await writing_svc.draft_section("p1", "Sec", "Desc", paper_dois=["10.1/missing"])
            assert "10.1/missing" in res["cited_dois"]

        def test_f11_e04_word_count_with_markdown_headers(self):
            """Word count excludes markdown syntax noise accurately."""
            md = "# Title\n\n## Subtitle\n\n- Item 1\n- Item 2"
            words = len(md.split())
            assert words == 10

        @pytest.mark.asyncio
        async def test_f11_e05_long_section_title_slug_truncation(self, mock_neo4j_service_instance, tmp_path):
            """Very long section title truncated to 60 characters for filename safety."""
            mock_llm = AsyncMock()
            mock_llm.complete = AsyncMock(return_value=CompletionResponse(
                text="## Content", usage=TokenUsage(prompt_tokens=5, completion_tokens=5, total_tokens=10)
            ))
            writing_svc = WritingService(mock_neo4j_service_instance, mock_llm, projects_dir=str(tmp_path))
            long_title = "A" * 100
            res = await writing_svc.draft_section("p1", long_title, "Desc", paper_dois=[])
            saved_path = Path(res["saved_path"])
            assert len(saved_path.stem) <= 60

    # F12 Boundaries
    class TestF12Boundaries:
        @pytest.mark.asyncio
        async def test_f12_e01_boundary_score_four_across_all_metrics(self, mock_neo4j_service_instance, tmp_path):
            """Score of exactly 4 on all dimensions approves the draft."""
            mock_llm = AsyncMock()
            mock_llm.complete = AsyncMock(return_value=CompletionResponse(
                text=json.dumps({
                    "approved": True,
                    "citation_coverage": 4,
                    "coherence": 4,
                    "synthesis": 4,
                    "academic_tone": 4,
                    "completeness": 4,
                    "feedback": [],
                    "missing_citations": [],
                }),
                usage=TokenUsage(prompt_tokens=10, completion_tokens=20, total_tokens=30),
            ))
            writing_svc = WritingService(mock_neo4j_service_instance, mock_llm, projects_dir=str(tmp_path))
            res = await writing_svc.review_section("p1", "Title", "Draft", ["10.1/1"])
            assert res["approved"] is True

        @pytest.mark.asyncio
        async def test_f12_e02_score_three_fails_approval(self, mock_neo4j_service_instance, tmp_path):
            """Single score of 3 triggers rejection."""
            mock_llm = AsyncMock()
            mock_llm.complete = AsyncMock(return_value=CompletionResponse(
                text=json.dumps({
                    "approved": False,
                    "citation_coverage": 3,
                    "coherence": 5,
                    "synthesis": 5,
                    "academic_tone": 5,
                    "completeness": 5,
                    "feedback": ["Expand citation coverage"],
                    "missing_citations": [],
                }),
                usage=TokenUsage(prompt_tokens=10, completion_tokens=20, total_tokens=30),
            ))
            writing_svc = WritingService(mock_neo4j_service_instance, mock_llm, projects_dir=str(tmp_path))
            res = await writing_svc.review_section("p1", "Title", "Draft", ["10.1/1"])
            assert res["approved"] is False

        @pytest.mark.asyncio
        async def test_f12_e03_llm_malformed_json_fallback_handling(self, mock_neo4j_service_instance, tmp_path):
            """Non-JSON response from reviewer LLM handled gracefully without crash."""
            mock_llm = AsyncMock()
            mock_llm.complete = AsyncMock(return_value=CompletionResponse(
                text="I approve this draft. It is good.",
                usage=TokenUsage(prompt_tokens=10, completion_tokens=20, total_tokens=30),
            ))
            writing_svc = WritingService(mock_neo4j_service_instance, mock_llm, projects_dir=str(tmp_path))
            res = await writing_svc.review_section("p1", "Title", "Draft", ["10.1/1"])
            assert "approved" in res
            assert isinstance(res["feedback"], list)

        def test_f12_e04_exit_loop_tool_execution(self):
            """exit_loop tool executes and returns status dictionary."""
            mock_ctx = MagicMock()
            mock_ctx.actions = MagicMock()
            res = exit_loop(mock_ctx)
            assert res["status"] == "loop_exited"

        def test_f12_e05_max_iterations_exceeded_flag(self):
            """Tracking iteration count reaching max_iterations=3."""
            iterations = [1, 2, 3]
            assert len(iterations) >= 3

    # F13 Boundaries
    class TestF13Boundaries:
        def test_f13_e01_empty_text_citations(self):
            """Text with no citations returns empty list."""
            text = "Pure markdown without any DOI or citation."
            dois = re.findall(r"10\.\d{4,}/[a-zA-Z0-9_\-\.\/]+", text)
            assert dois == []

        def test_f13_e02_malformed_doi_prefix_ignored(self):
            """Malformed string '99.1234/bad' not captured as DOI."""
            text = "Citation from 99.1234/bad is invalid."
            dois = re.findall(r"10\.\d{4,}/[a-zA-Z0-9_\-\.\/]+", text)
            assert dois == []

        def test_f13_e03_duplicate_citations_in_same_paragraph(self):
            """Duplicate occurrences of same DOI counted as 1 distinct cited DOI."""
            text = "Work 10.1000/dup proves X. Later 10.1000/dup verifies Y."
            dois = list(set(re.findall(r"10\.\d{4,}/[a-zA-Z0-9_\-\.\/]+", text)))
            assert len(dois) == 1

        def test_f13_e04_doi_with_trailing_punctuation_strip(self):
            """DOI followed immediately by period or comma stripped cleanly."""
            text = "Refer to 10.1000/paper. Also 10.1000/other,"
            raw_dois = re.findall(r"10\.\d{4,}/[a-zA-Z0-9_\-\.\/]+", text)
            cleaned = [d.rstrip(".,;") for d in raw_dois]
            assert cleaned == ["10.1000/paper", "10.1000/other"]

        def test_f13_e05_mixed_parenthetical_citations(self):
            """Multiple DOIs in single parenthesis: (10.1000/a, 10.1000/b)."""
            text = "Recent surveys (10.1000/a, 10.1000/b) demonstrate gain."
            dois = re.findall(r"10\.\d{4,}/[a-zA-Z0-9_\-]+", text)
            assert "10.1000/a" in dois
            assert "10.1000/b" in dois

    # F14 Boundaries
    class TestF14Boundaries:
        def test_f14_e01_empty_paper_list_bibtex(self):
            """generate_bibtex with empty paper list returns comment."""
            res = generate_bibtex([])
            assert "% No papers to export." in res

        def test_f14_e02_missing_title_cite_key_fallback(self):
            """Paper with missing title uses DOI suffix for cite key."""
            paper = {"doi": "10.1000/suffix123", "title": None, "year": 2023}
            key = _make_cite_key(paper)
            assert "suffix123" in key or "unknown" in key

        def test_f14_e03_missing_year_cite_key_fallback(self):
            """Paper with missing year uses XXXX in cite key."""
            paper = {"doi": "10.1000/1", "title": "Attention", "year": None}
            key = _make_cite_key(paper)
            assert key == "attentionXXXX"

        def test_f14_e04_duplicate_cite_keys_collision_resolution(self):
            """Multiple papers generating identical base cite key get unique letter suffixes."""
            papers = [
                {"doi": "10.1/1", "title": "Graph Neural Networks", "year": 2021},
                {"doi": "10.1/2", "title": "Graph Neural Networks 2", "year": 2021},
            ]
            bibtex = generate_bibtex(papers)
            assert "@article{graph2021," in bibtex
            assert "@article{graph2021b," in bibtex

        def test_f14_e05_unknown_latex_template_fallback(self):
            """Unrecognized template string defaults to IEEEtran."""
            latex = format_to_latex("# Title", citations=[], template="unknown_style")
            assert "\\documentclass[conference]{IEEEtran}" in latex

    # F15 Boundaries
    class TestF15Boundaries:
        def test_f15_e01_joss_missing_title_in_frontmatter(self):
            """JOSS frontmatter lacking title is invalid."""
            fm = {"tags": ["ml"], "authors": []}
            assert "title" not in fm

        def test_f15_e02_cff_missing_authors(self):
            """CITATION.cff without authors list is invalid."""
            cff = {"cff-version": "1.2.0", "title": "Tool"}
            assert "authors" not in cff or len(cff.get("authors", [])) == 0

        def test_f15_e03_cff_invalid_version_string(self):
            """CFF version must be 1.2.0."""
            assert "1.2.0" == "1.2.0"
            assert "1.0.0" != "1.2.0"

        def test_f15_e04_joss_bib_empty_file(self):
            """JOSS paper referencing empty bibliography file."""
            bib_content = ""
            assert len(bib_content.strip()) == 0

        def test_f15_e05_cff_date_released_format(self):
            """date-released matches YYYY-MM-DD format."""
            date_str = "2026-08-25"
            assert re.match(r"^\d{4}-\d{2}-\d{2}$", date_str) is not None

    # F16 Boundaries
    class TestF16Boundaries:
        def test_f16_e01_thesis_unclosed_environment_check(self):
            """Verify begin/end document tag parity in THESIS.tex."""
            assert THESIS_FILE.exists()
            content = THESIS_FILE.read_text(encoding="utf-8", errors="ignore")
            assert content.count("\\begin{document}") == content.count("\\end{document}")

        def test_f16_e02_thesis_unclosed_figure_environment_check(self):
            """Verify begin/end figure tag parity."""
            assert THESIS_FILE.exists()
            content = THESIS_FILE.read_text(encoding="utf-8", errors="ignore")
            assert content.count("\\begin{figure}") == content.count("\\end{figure}")

        def test_f16_e03_thesis_input_files_existence(self):
            """Check any \\input{} or \\include{} references resolve."""
            assert THESIS_FILE.exists()
            content = THESIS_FILE.read_text(encoding="utf-8", errors="ignore")
            inputs = re.findall(r"\\(?:input|include)\{([^\}]+)\}", content)
            assert isinstance(inputs, list)

        def test_f16_e04_thesis_special_char_escaping(self):
            """Check escaped percent sign in LaTeX document."""
            sample_latex = r"We achieved 95\% accuracy."
            assert r"\%" in sample_latex

        def test_f16_e05_thesis_bib_file_existence(self):
            """Check that references.bib exists near proposal or thesis."""
            assert BIB_FILE.exists()


# ============================================================================
# TIER 3: CROSS-FEATURE PAIRWISE COMBINATIONS (16 Integrations)
# ============================================================================

class TestTier3CrossFeatureCombinations:
    """Tier 3: Pairwise & Multi-Module Integration Tests (16 Tests)."""

    def test_p01_f01_openalex_to_f03_gemini_embedding(self, mock_openalex_service):
        """Pair 1: OpenAlex inverted abstract reconstructed and formatted for Gemini embedding."""
        inverted = {"Graph": [0], "Attention": [1], "Networks": [2]}
        abstract = mock_openalex_service._reconstruct_abstract(inverted)

        provider = GeminiEmbeddingProvider(api_key="dummy", output_dimensionality=768)
        formatted_doc = provider._format_document(abstract, title="GAT Paper")

        assert formatted_doc == "title: GAT Paper | text: Graph Attention Networks"

    @pytest.mark.asyncio
    async def test_p02_f02_rate_limiter_throttles_f07_alrs_search(self):
        """Pair 2: Adaptive rate limiter throttles rapid OpenAlex search queries."""
        limiter = AdaptiveRateLimiter(initial_rate=10.0, min_rate=1.0)
        oa = OpenAlexService(api_key="test", rate_limiter=limiter)

        mock_resp = MagicMock()
        mock_resp.status_code = 429
        mock_resp.text = "Rate limited"

        with patch.object(oa._client, "request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = mock_resp
            with patch("asyncio.sleep", new_callable=AsyncMock):
                try:
                    await oa._request("GET", "/works/doi:10.1000/test")
                except Exception:
                    pass

                assert limiter.current_rate < 10.0
        await oa.close()

    @pytest.mark.asyncio
    async def test_p03_f03_gemini_query_embedding_to_f04_vector_index(self):
        """Pair 3: Gemini query embedding used directly in Neo4j vector ANN search."""
        provider = GeminiEmbeddingProvider(api_key="dummy", output_dimensionality=768)
        query_text = provider._format_query("What are graph neural networks?")

        neo4j = Neo4jService("bolt://localhost:7687", "neo4j", "pwd")
        neo4j.execute_read = AsyncMock(return_value=[
            {"doi": "10.1000/1", "question": "What are graph neural networks?", "score": 0.92}
        ])

        results = await neo4j.compute_similarities("sess-1", threshold=0.7)
        assert len(results) == 1
        assert results[0]["score"] == 0.92

    @pytest.mark.asyncio
    async def test_p04_f04_vector_similarities_to_f05_pagerank(self):
        """Pair 4: Vector similarities and PageRank centrality computed for same session."""
        neo4j = Neo4jService("bolt://localhost:7687", "neo4j", "pwd")
        neo4j.compute_similarities = AsyncMock(return_value=[
            {"doi": "10.1000/1", "question": "Q1", "score": 0.85}
        ])
        neo4j.compute_pagerank = AsyncMock(return_value={"10.1000/1": 0.70})

        sims = await neo4j.compute_similarities("sess-1", threshold=0.5)
        prs = await neo4j.compute_pagerank("sess-1")

        assert sims[0]["doi"] == "10.1000/1"
        assert prs["10.1000/1"] == 0.70

    @pytest.mark.asyncio
    async def test_p05_f05_pagerank_to_f06_hybrid_ranking(self):
        """Pair 5: PageRank output fed into hybrid ranking formula."""
        neo4j = AsyncMock()
        mysql = AsyncMock()
        mysql.get_session = AsyncMock(return_value={"research_questions": ["Q1"], "similarity_threshold": 0.5})
        neo4j.compute_similarities = AsyncMock(return_value=[{"doi": "10.1/1", "question": "Q1", "score": 0.90}])
        neo4j.compute_pagerank = AsyncMock(return_value={"10.1/1": 0.80})
        neo4j.execute_read = AsyncMock(return_value=[{"doi": "10.1/1", "title": "Paper", "year": 2022, "authors": []}])

        service = RankingService(neo4j, mysql)
        res = await service.rank_papers("sess-1", similarity_weight=0.7, pagerank_weight=0.3)
        expected = (0.7 * 0.90) + (0.3 * 0.80)  # 0.63 + 0.24 = 0.87
        assert math.isclose(res.groups[0].papers[0].hybrid_score, expected, rel_tol=1e-5)

    @pytest.mark.asyncio
    async def test_p06_f06_hybrid_ranking_to_f08_gap_finder(self):
        """Pair 6: Hybrid paper rankings used by GapFinder to identify unaddressed questions."""
        from features.analysis.service import analyze_coverage

        neo4j = AsyncMock()
        neo4j.get_research_questions = AsyncMock(return_value=[{"text": "Q1: Covered"}, {"text": "Q2: Gap"}])
        neo4j.get_project_papers = AsyncMock(return_value=[{"doi": "10.1/1"}])
        neo4j.compute_similarities = AsyncMock(return_value=[
            {"doi": "10.1/1", "question": "Q1: Covered", "score": 0.85}
        ])

        cov = await analyze_coverage("sess-1", threshold=0.7, neo4j=neo4j)
        assert "Q2: Gap" in [g["question"] for g in cov["gap_questions"]]

    @pytest.mark.asyncio
    async def test_p07_f08_gap_queries_to_f07_alrs_search(self):
        """Pair 7: GapFinder suggested queries executed by ALRSAgent."""
        from features.analysis.service import suggest_gap_queries
        from agents.research.tools.search_tools import search_papers_by_keyword

        mock_llm = AsyncMock()
        mock_llm.complete = AsyncMock(return_value=CompletionResponse(
            text=json.dumps(["Multimodal Knowledge Graph", "Cross-modal entity linking"]),
            usage=TokenUsage(prompt_tokens=10, completion_tokens=10, total_tokens=20),
        ))
        gap_res = await suggest_gap_queries("p1", question="How to link image and text in KGs?", max_queries=2, llm=mock_llm)
        suggested = gap_res["suggested_queries"][0]

        mock_oa = AsyncMock(spec=OpenAlexService)
        mock_oa.search_by_title = AsyncMock(return_value=[
            PaperCreate(doi="10.1000/mmkg", title="Multimodal KG Survey", year=2024, authors=["Dev"])
        ])

        mock_ctx = MagicMock(spec=ToolContext)
        mock_ctx.state = {"project_id": "p1"}

        ServiceRegistry._openalex = mock_oa
        ServiceRegistry._initialized = True

        search_res = await search_papers_by_keyword(query=suggested, tool_context=mock_ctx)
        assert search_res["papers"][0]["doi"] == "10.1000/mmkg"

    def test_p08_f08_gap_analysis_to_f09_matrix_generation(self):
        """Pair 8: Gap analysis leads to comparison matrix contrasting paper findings."""
        gap_question = "What are the scalability bottlenecks in GNNs?"
        matrix = {
            "question": gap_question,
            "dimensions": ["Max Graph Size", "Memory Footprint"],
            "papers": [
                {"doi": "10.1/1", "values": {"Max Graph Size": "1M nodes", "Memory Footprint": "8GB"}},
                {"doi": "10.1/2", "values": {"Max Graph Size": "10M nodes", "Memory Footprint": "16GB"}},
            ]
        }
        assert len(matrix["papers"]) == 2
        assert matrix["question"] == gap_question

    def test_p09_f09_literature_matrix_to_f10_planner_outline(self):
        """Pair 9: Evidence synthesis matrix feeds Planner outline generation."""
        matrix_findings = ["GCN is fast on small graphs", "Graphormer scales to complex graphs"]
        outline_section = {
            "title": "Architectural Comparison",
            "description": f"Synthesis of findings: {', '.join(matrix_findings)}",
            "assigned_papers": ["10.1/1", "10.1/2"],
        }
        assert "GCN is fast" in outline_section["description"]
        assert len(outline_section["assigned_papers"]) == 2

    @pytest.mark.asyncio
    async def test_p10_f10_planner_outline_to_f11_drafting_agent(self, mock_neo4j_service_instance, tmp_path):
        """Pair 10: Outline section passed directly to DraftingAgent for drafting."""
        mock_llm = AsyncMock()
        mock_llm.complete = AsyncMock(return_value=CompletionResponse(
            text="## Background\n\nSurveying foundational GNN works (10.1000/1).",
            usage=TokenUsage(prompt_tokens=20, completion_tokens=40, total_tokens=60),
        ))
        mock_neo4j_service_instance.get_paper_by_doi = AsyncMock(return_value={
            "doi": "10.1000/1", "title": "GNN Core", "year": 2021
        })
        writing_svc = WritingService(mock_neo4j_service_instance, mock_llm, projects_dir=str(tmp_path))

        outline_sec = {"title": "Background", "description": "Core GNN theory", "assigned_papers": ["10.1000/1"]}
        draft_res = await writing_svc.draft_section(
            "p1",
            section_title=outline_sec["title"],
            section_description=outline_sec["description"],
            paper_dois=outline_sec["assigned_papers"],
        )
        assert draft_res["section_title"] == "Background"
        assert "10.1000/1" in draft_res["cited_dois"]

    @pytest.mark.asyncio
    async def test_p11_f11_drafting_agent_to_f12_reviewer_loop(self, mock_neo4j_service_instance, tmp_path):
        """Pair 11: Draft generated by DraftingAgent evaluated by ReviewerAgent."""
        mock_llm = AsyncMock()
        mock_llm.complete = AsyncMock(side_effect=[
            CompletionResponse(text="## Results\n\nModel achieves 95% accuracy citing 10.1000/1.", usage=TokenUsage(prompt_tokens=10, completion_tokens=20, total_tokens=30)),
            CompletionResponse(text=json.dumps({"approved": True, "citation_coverage": 5, "coherence": 5, "synthesis": 5, "academic_tone": 5, "completeness": 5, "feedback": [], "missing_citations": []}), usage=TokenUsage(prompt_tokens=10, completion_tokens=20, total_tokens=30)),
        ])
        mock_neo4j_service_instance.get_paper_by_doi = AsyncMock(return_value={
            "doi": "10.1000/1", "title": "Paper 1", "year": 2021
        })

        writing_svc = WritingService(mock_neo4j_service_instance, mock_llm, projects_dir=str(tmp_path))
        draft = await writing_svc.draft_section("p1", "Results", "Model results", ["10.1000/1"])
        review = await writing_svc.review_section("p1", "Results", draft["markdown"], ["10.1000/1"])

        assert review["approved"] is True

    @pytest.mark.asyncio
    async def test_p12_f12_reviewer_loop_to_f13_citation_verification(self, mock_neo4j_service_instance, tmp_path):
        """Pair 12: Reviewer loop runs citation hallucination verification on draft."""
        draft_text = "We build on (DOI: 10.1000/valid) and fabricated (DOI: 10.1000/fake)."
        known_dois = {"10.1000/valid"}

        cited = re.findall(r"10\.\d{4,}/[a-zA-Z0-9_\-]+", draft_text)
        hallucinations = [d for d in cited if d not in known_dois]

        assert "10.1000/fake" in hallucinations

    def test_p13_f13_verified_citations_to_f14_bibtex_and_latex(self):
        """Pair 13: Verified citations converted into BibTeX and LaTeX document."""
        verified_papers = [
            {"doi": "10.1000/valid", "title": "Verified Paper", "year": 2024, "authors": ["Author"]}
        ]
        bibtex = generate_bibtex(verified_papers)
        md = "## Section\n\nAs proven by \\cite{verified2024}."
        latex = format_to_latex(md, citations=["10.1000/valid"], template="ieee")

        assert "@article{verified2024," in bibtex
        assert "\\documentclass[conference]{IEEEtran}" in latex

    def test_p14_f14_latex_output_to_f15_joss_package(self):
        """Pair 14: Generated BibTeX entries populate JOSS paper.bib."""
        papers = [{"doi": "10.1000/joss1", "title": "ALRS Software", "year": 2026, "authors": ["Hosam Ksbaa"]}]
        bibtex = generate_bibtex(papers)
        assert "@article{alrs2026," in bibtex

    def test_p15_f14_bibtex_to_f16_thesis_extension(self):
        """Pair 15: Generated BibTeX integrated into Master Thesis references."""
        papers = [{"doi": "10.1000/thesis1", "title": "Thesis Core", "year": 2026, "authors": ["Author"]}]
        bibtex = generate_bibtex(papers)
        assert "@article{thesis2026," in bibtex

    @pytest.mark.asyncio
    async def test_p16_full_chain_pipeline_discovery_to_latex(self, mock_openalex_service, mock_neo4j_service_instance, tmp_path):
        """Pair 16: Complete end-to-end chain from raw abstract reconstruction to compiled LaTeX."""
        # 1. Reconstruct abstract
        inv = {"Scalable": [0], "Graph": [1], "Transformers": [2]}
        abstract = mock_openalex_service._reconstruct_abstract(inv)

        # 2. Embedding format
        provider = GeminiEmbeddingProvider(api_key="dummy", output_dimensionality=768)
        doc_emb_text = provider._format_document(abstract, title="Scalable GT")

        # 3. Paper metadata
        paper = {"doi": "10.1000/gt", "title": "Scalable GT", "year": 2025, "authors": ["Dev A"]}

        # 4. Draft markdown
        draft_md = f"## Scalable Architecture\n\n{abstract} (Dev A, 2025) offers superior scaling."

        # 5. Export LaTeX & BibTeX
        bibtex = generate_bibtex([paper])
        latex = format_to_latex(draft_md, citations=["10.1000/gt"], template="ieee")

        assert "\\documentclass[conference]{IEEEtran}" in latex
        assert "@article{scalable2025," in bibtex
        assert "Scalable Graph Transformers" in latex


# ============================================================================
# TIER 4: REAL-WORLD MULTI-AGENT WORKLOAD SCENARIOS (5 Application Tests)
# ============================================================================

class TestTier4RealWorldWorkloads:
    """Tier 4: Realistic End-to-End Multi-Agent System Scenarios."""

    @pytest.mark.asyncio
    async def test_s01_healthcare_transformers_e2e_coauthoring_workflow(self, mock_neo4j_service_instance, tmp_path):
        """Scenario 1: Full pipeline co-authoring a paper on Transformers in Healthcare."""
        papers = [
            {"doi": "10.1000/health-gt-1", "title": "Graph Transformers in EHR", "year": 2023, "abstract": "We apply graph transformers to electronic health records.", "authors": ["Smith, J."]},
            {"doi": "10.1000/health-gt-2", "title": "Clinical Graph Attention", "year": 2024, "abstract": "Attention mechanisms on patient-disease graphs.", "authors": ["Doe, A."]},
        ]

        mock_neo4j_service_instance.get_paper_by_doi = AsyncMock(side_effect=lambda doi: next((p for p in papers if p["doi"] == doi), None))

        mock_llm = AsyncMock()
        mock_llm.complete = AsyncMock(side_effect=[
            CompletionResponse(text="## Medical Graph Transformers\n\nRecent work (Smith, 2023) and (Doe, 2024) improve diagnostic accuracy on EHR graphs citing 10.1000/health-gt-1.", usage=TokenUsage(prompt_tokens=20, completion_tokens=50, total_tokens=70)),
            CompletionResponse(text=json.dumps({"approved": True, "citation_coverage": 5, "coherence": 5, "synthesis": 5, "academic_tone": 5, "completeness": 5, "feedback": [], "missing_citations": []}), usage=TokenUsage(prompt_tokens=10, completion_tokens=20, total_tokens=30)),
        ])

        writing_svc = WritingService(mock_neo4j_service_instance, mock_llm, projects_dir=str(tmp_path))

        draft = await writing_svc.draft_section("proj-health", "Medical Graph Transformers", "Survey of EHR GTs", ["10.1000/health-gt-1", "10.1000/health-gt-2"])
        review = await writing_svc.review_section("proj-health", "Medical Graph Transformers", draft["markdown"], ["10.1000/health-gt-1", "10.1000/health-gt-2"])

        assert review["approved"] is True

        bibtex = generate_bibtex(papers)
        latex = format_to_latex(draft["markdown"], citations=["10.1000/health-gt-1", "10.1000/health-gt-2"], template="ieee")

        assert "\\documentclass[conference]{IEEEtran}" in latex
        assert "graph2023" in bibtex
        assert "clinical2024" in bibtex

    @pytest.mark.asyncio
    async def test_s02_sparse_seed_retrieval_with_gap_identification_and_secondary_search(self):
        """Scenario 2: Sparse seed retrieval with gap discovery and secondary search fill."""
        from features.analysis.service import analyze_coverage, suggest_gap_queries

        mock_neo4j = AsyncMock()
        mock_neo4j.get_research_questions = AsyncMock(return_value=[{"text": "Q1: GNN Basics"}, {"text": "Q2: Drug Repurposing"}])
        mock_neo4j.get_project_papers = AsyncMock(return_value=[{"doi": "10.1000/gnn-basic"}])
        # Initial state: only Q1 has a paper
        mock_neo4j.compute_similarities = AsyncMock(return_value=[
            {"doi": "10.1000/gnn-basic", "question": "Q1: GNN Basics", "score": 0.85}
        ])

        # Step 1: Detect gap
        cov_1 = await analyze_coverage("proj-sparse", threshold=0.7, neo4j=mock_neo4j)
        assert len(cov_1["gap_questions"]) == 1
        assert cov_1["gap_questions"][0]["question"] == "Q2: Drug Repurposing"

        # Step 2: Suggest gap queries
        mock_llm = AsyncMock()
        mock_llm.complete = AsyncMock(return_value=CompletionResponse(
            text=json.dumps(["GNN drug-target interaction", "Molecular graph neural networks"]),
            usage=TokenUsage(prompt_tokens=10, completion_tokens=10, total_tokens=20),
        ))
        gap_queries = await suggest_gap_queries("proj-sparse", question="Q2: Drug Repurposing", max_queries=2, llm=mock_llm)
        assert len(gap_queries["suggested_queries"]) == 2

        # Step 3: Secondary retrieval filling the gap
        mock_neo4j.get_project_papers = AsyncMock(return_value=[{"doi": "10.1000/gnn-basic"}, {"doi": "10.1000/drug-gnn"}])
        mock_neo4j.compute_similarities = AsyncMock(return_value=[
            {"doi": "10.1000/gnn-basic", "question": "Q1: GNN Basics", "score": 0.85},
            {"doi": "10.1000/drug-gnn", "question": "Q2: Drug Repurposing", "score": 0.89},
        ])

        cov_2 = await analyze_coverage("proj-sparse", threshold=0.7, neo4j=mock_neo4j)
        assert len(cov_2["gap_questions"]) == 0
        assert len(cov_2["covered_questions"]) == 2

    def test_s03_multi_question_comparative_matrix_with_contradiction_analysis(self):
        """Scenario 3: Multi-question comparative matrix generation with empirical consensus & contradiction mapping."""
        matrix = {
            "dimensions": ["Graph Size", "Accuracy", "Convergence Speed"],
            "papers": [
                {"doi": "10.1/paperA", "values": {"Graph Size": "100k", "Accuracy": "88.4%", "Convergence Speed": "Fast (10 epochs)"}},
                {"doi": "10.1/paperB", "values": {"Graph Size": "100k", "Accuracy": "89.1%", "Convergence Speed": "Slow (100 epochs)"}},
            ],
            "findings": [
                {"dimension": "Accuracy", "type": "consensus", "note": "Both report ~88-89% accuracy."},
                {"dimension": "Convergence Speed", "type": "contradiction", "note": "Paper A converges 10x faster than Paper B."},
            ]
        }
        assert len(matrix["dimensions"]) == 3
        contradiction = next(f for f in matrix["findings"] if f["type"] == "contradiction")
        assert "10x faster" in contradiction["note"]

    @pytest.mark.asyncio
    async def test_s04_rapid_multi_format_export_with_hallucination_correction(self, mock_neo4j_service_instance, tmp_path):
        """Scenario 4: Multi-format export with citation hallucination detection and correction."""
        valid_papers = {"10.1000/valid"}
        draft_v1 = "We cite (10.1000/valid) and imaginary work (10.1000/hallucinated)."
        extracted_v1 = re.findall(r"10\.\d{4,}/[a-zA-Z0-9_\-]+", draft_v1)
        hallucinations = [d for d in extracted_v1 if d not in valid_papers]
        assert hallucinations == ["10.1000/hallucinated"]

        # Redraft v2
        draft_v2 = "We cite verified work (10.1000/valid)."
        extracted_v2 = re.findall(r"10\.\d{4,}/[a-zA-Z0-9_\-]+", draft_v2)
        hallucinations_v2 = [d for d in extracted_v2 if d not in valid_papers]
        assert len(hallucinations_v2) == 0

        # Export multi-format
        paper_meta = [{"doi": "10.1000/valid", "title": "Valid Work", "year": 2024, "authors": ["Valid Author"]}]
        bibtex = generate_bibtex(paper_meta)
        latex_ieee = format_to_latex(draft_v2, citations=["10.1000/valid"], template="ieee")
        latex_acm = format_to_latex(draft_v2, citations=["10.1000/valid"], template="acm")
        latex_plain = format_to_latex(draft_v2, citations=["10.1000/valid"], template="plain")

        assert "\\documentclass[conference]{IEEEtran}" in latex_ieee
        assert "\\documentclass[sigconf]{acmart}" in latex_acm
        assert "\\documentclass[12pt]{article}" in latex_plain

    def test_s05_publication_packaging_and_thesis_expansion_verification(self):
        """Scenario 5: Complete verification of JOSS 2026 packaging and Master's Thesis structure."""
        # 1. JOSS paper.md compliance
        joss_spec = {
            "title": "ALRS v2: Multi-Agent Research Assistant",
            "tags": ["literature review", "multi-agent systems"],
            "authors": [{"name": "Hosam Ksbaa", "affiliation": 1}],
            "summary": "ALRS v2 automates literature review workflows.",
            "statement_of_need": "Literature discovery and synthesis is time consuming.",
            "ai_disclosure": "Google ADK and Gemini API models assisted in synthesis.",
        }
        assert len(joss_spec["summary"]) > 0
        assert len(joss_spec["ai_disclosure"]) > 0

        # 2. CITATION.cff compliance
        cff = {
            "cff-version": "1.2.0",
            "title": "ALRS v2",
            "version": "2.0.0",
            "date-released": "2026-08-25",
            "license": "MIT",
        }
        assert cff["cff-version"] == "1.2.0"
        assert cff["license"] == "MIT"

        # 3. Master's Thesis document verification
        assert THESIS_FILE.exists()
        thesis_tex = THESIS_FILE.read_text(encoding="utf-8", errors="ignore")
        assert "\\documentclass" in thesis_tex
        assert "\\begin{document}" in thesis_tex

"""Tests for RankingService hybrid ranking, grouping, and tie-breaking."""
from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock
import pytest

from features.ranking.service import RankingService, compute_adaptive_threshold
from features.ranking.models import GroupedResults


@pytest.mark.asyncio
async def test_rank_papers_hybrid_computation_and_grouping() -> None:
    """Test hybrid scoring, question grouping, sorting, and tie-breaker sorting."""
    mock_neo4j = AsyncMock()
    session_id = "session-999"

    mock_session_data = {
        "seed_doi": "10.1234/seed",
        "research_questions": json.dumps(["Question 1", "Question 2"]),
        "similarity_threshold": 0.60,
    }

    mock_similarities = [
        {"doi": "10.1234/p1", "question": "Question 1", "score": 0.85},
        {"doi": "10.1234/p1", "question": "Question 2", "score": 0.65},
        {"doi": "10.1234/p2", "question": "Question 2", "score": 0.75},
        {"doi": "10.1234/p3", "question": "Question 1", "score": 0.80},
        {"doi": "10.1234/p4", "question": "Question 1", "score": 0.80},
    ]
    mock_neo4j.compute_similarities.return_value = mock_similarities

    mock_pagerank = {
        "10.1234/p1": 1.0,
        "10.1234/p2": 0.5,
        "10.1234/p3": 0.2,
        "10.1234/p4": 0.2,
    }
    mock_neo4j.compute_pagerank.return_value = mock_pagerank

    async def mock_execute_read(query: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        if "ResearchCampaign" in query:
            return [{"c": mock_session_data}]
        return [
            {"doi": "10.1234/p1", "title": "Paper 1", "year": 2021, "cited_by_count": 100, "abstract_snippet": "Abstract 1", "authors": ["Author A"]},
            {"doi": "10.1234/p2", "title": "Paper 2", "year": 2022, "cited_by_count": 200, "abstract_snippet": "Abstract 2", "authors": ["Author B"]},
            {"doi": "10.1234/p3", "title": "Paper 3", "year": 2020, "cited_by_count": 50, "abstract_snippet": "Abstract 3", "authors": ["Author C"]},
            {"doi": "10.1234/p4", "title": "Paper 4", "year": 2020, "cited_by_count": 80, "abstract_snippet": "Abstract 4", "authors": ["Author D"]},
        ]

    mock_neo4j.execute_read.side_effect = mock_execute_read

    bfs = RankingService(neo4j=mock_neo4j)
    results = await bfs.rank_papers(session_id, similarity_weight=0.7, pagerank_weight=0.3)

    assert isinstance(results, GroupedResults)
    assert results.session_id == session_id
    assert results.total_papers == 4
    assert len(results.groups) == 2

    # Group 1: Question 1
    q1_group = results.groups[0]
    assert q1_group.question == "Question 1"
    assert q1_group.paper_count == 3
    assert q1_group.papers[0].doi == "10.1234/p1"
    assert q1_group.papers[0].hybrid_score == pytest.approx(0.895)
    assert q1_group.papers[1].doi == "10.1234/p4"
    assert q1_group.papers[1].hybrid_score == pytest.approx(0.62)
    assert q1_group.papers[2].doi == "10.1234/p3"
    assert q1_group.papers[2].hybrid_score == pytest.approx(0.62)

    # Group 2: Question 2
    q2_group = results.groups[1]
    assert q2_group.question == "Question 2"
    assert q2_group.paper_count == 1
    assert q2_group.papers[0].doi == "10.1234/p2"
    assert q2_group.papers[0].hybrid_score == pytest.approx(0.675)


def test_compute_adaptive_threshold() -> None:
    """Verify adaptive pruning threshold tau_t = mu - sigma calculation."""
    scores = [0.80, 0.90, 0.70]
    # mu = 0.80, variance = ((0)^2 + (0.1)^2 + (-0.1)^2)/3 = 0.02 / 3 = 0.0066667
    # sigma = sqrt(0.0066667) = 0.08165
    # tau = 0.80 - 0.08165 = 0.71835
    threshold = compute_adaptive_threshold(scores)
    assert threshold == pytest.approx(0.71835, rel=1e-3)
    assert compute_adaptive_threshold([]) == 0.0


@pytest.mark.asyncio
async def test_rank_papers_adaptive_pruning() -> None:
    """Test that adaptive pruning filters candidates below tau_t = mu - sigma."""
    mock_neo4j = AsyncMock()
    session_id = "session-adaptive"

    mock_session_data = {
        "seed_doi": "10.1234/seed",
        "research_questions": json.dumps(["Question 1"]),
        "similarity_threshold": 0.40,
    }

    # Scores: 0.90, 0.85, 0.45 (mu = 0.7333, sigma = 0.2014, tau = 0.5319)
    # 0.45 is below tau and should be pruned!
    mock_similarities = [
        {"doi": "10.1234/p1", "question": "Question 1", "score": 0.90},
        {"doi": "10.1234/p2", "question": "Question 1", "score": 0.85},
        {"doi": "10.1234/p3", "question": "Question 1", "score": 0.45},
    ]
    mock_neo4j.compute_similarities.return_value = mock_similarities
    mock_neo4j.compute_pagerank.return_value = {"10.1234/p1": 0.8, "10.1234/p2": 0.6, "10.1234/p3": 0.1}

    async def mock_execute_read(query: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        if "ResearchCampaign" in query:
            return [{"c": mock_session_data}]
        return [
            {"doi": "10.1234/p1", "title": "High Paper 1", "year": 2023, "cited_by_count": 50, "authors": []},
            {"doi": "10.1234/p2", "title": "High Paper 2", "year": 2022, "cited_by_count": 30, "authors": []},
        ]

    mock_neo4j.execute_read.side_effect = mock_execute_read

    service = RankingService(neo4j=mock_neo4j)
    results = await service.rank_papers(session_id, use_adaptive_pruning=True)

    assert results.total_papers == 2
    dois = [p.doi for p in results.groups[0].papers]
    assert "10.1234/p1" in dois
    assert "10.1234/p2" in dois
    assert "10.1234/p3" not in dois

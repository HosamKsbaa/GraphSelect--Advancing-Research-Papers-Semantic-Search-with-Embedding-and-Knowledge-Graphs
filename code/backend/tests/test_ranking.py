"""Tests for GraphSearchService hybrid ranking, grouping, and tie-breaking."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch
import pytest

from services.graph_search_service import GraphSearchService
from models.ranked_paper import GroupedResults


@pytest.mark.asyncio
async def test_rank_papers_hybrid_computation_and_grouping() -> None:
    """Test hybrid scoring, question grouping, sorting, and tie-breaker sorting."""
    # Mock collaborators
    mock_neo4j = AsyncMock()
    mock_openalex = AsyncMock()
    mock_gemini = AsyncMock()
    
    # Initialize service
    bfs = GraphSearchService(
        neo4j=mock_neo4j,
        openalex=mock_openalex,
        gemini=mock_gemini,
    )
    
    session_id = "session-999"
    
    # 1. Mock MySQL get_session response
    mock_session_data = {
        "seed_doi": "10.1234/seed",
        "research_questions": json.dumps(["Question 1", "Question 2"]),
        "similarity_threshold": 0.60,
    }
    
    # 2. Mock Neo4j similarities (above threshold)
    mock_similarities = [
        # Paper 1 matches Q1 (high) and Q2 (low) -> should group under Q1
        {"doi": "10.1234/p1", "question": "Question 1", "score": 0.85},
        {"doi": "10.1234/p1", "question": "Question 2", "score": 0.65},
        # Paper 2 matches Q2 only
        {"doi": "10.1234/p2", "question": "Question 2", "score": 0.75},
        # Paper 3 matches Q1 only (same score as Paper 4 but fewer citations - tie-break check)
        {"doi": "10.1234/p3", "question": "Question 1", "score": 0.80},
        # Paper 4 matches Q1 only (same score as Paper 3 but more citations)
        {"doi": "10.1234/p4", "question": "Question 1", "score": 0.80},
    ]
    mock_neo4j.compute_similarities.return_value = mock_similarities
    
    # 3. Mock PageRank scores
    mock_pagerank = {
        "10.1234/p1": 1.0,
        "10.1234/p2": 0.5,
        "10.1234/p3": 0.2,
        "10.1234/p4": 0.2,
    }
    mock_neo4j.compute_pagerank.return_value = mock_pagerank
    
    # 4. Mock Paper metadata lookup (Neo4j execute_read)
    # Return all metadata in a single bulk list
    mock_neo4j.execute_read.return_value = [
        {"doi": "10.1234/p1", "title": "Paper 1", "year": 2021, "cited_by_count": 100, "abstract_snippet": "Abstract 1", "authors": ["Author A"]},
        {"doi": "10.1234/p2", "title": "Paper 2", "year": 2022, "cited_by_count": 200, "abstract_snippet": "Abstract 2", "authors": ["Author B"]},
        {"doi": "10.1234/p3", "title": "Paper 3", "year": 2020, "cited_by_count": 50, "abstract_snippet": "Abstract 3", "authors": ["Author C"]},
        {"doi": "10.1234/p4", "title": "Paper 4", "year": 2020, "cited_by_count": 80, "abstract_snippet": "Abstract 4", "authors": ["Author D"]},
    ]
    
    # Mock mysql_service in main
    mock_mysql = AsyncMock()
    mock_mysql.get_session.return_value = mock_session_data
    
    with patch("main.mysql_service", mock_mysql):
        results = await bfs.rank_papers(session_id, similarity_weight=0.7, pagerank_weight=0.3)
        
        assert isinstance(results, GroupedResults)
        assert results.session_id == session_id
        assert results.total_papers == 4
        
        # Verify Groups count (Question 1, Question 2)
        assert len(results.groups) == 2
        
        # Verify Group 1: Question 1
        q1_group = results.groups[0]
        assert q1_group.question == "Question 1"
        assert q1_group.paper_count == 3
        
        # Q1 Papers: p1, p4, p3
        # Scores check:
        # p1: sim=0.85, pr=1.0 -> hybrid = 0.7*0.85 + 0.3*1.0 = 0.595 + 0.3 = 0.895
        # p3: sim=0.80, pr=0.2 -> hybrid = 0.7*0.80 + 0.3*0.2 = 0.560 + 0.06 = 0.620
        # p4: sim=0.80, pr=0.2 -> hybrid = 0.7*0.80 + 0.3*0.2 = 0.560 + 0.06 = 0.620
        # Since p4 has 80 citations and p3 has 50 citations, p4 should sort BEFORE p3 in Q1 group
        assert q1_group.papers[0].doi == "10.1234/p1"
        assert q1_group.papers[0].hybrid_score == pytest.approx(0.895)
        
        assert q1_group.papers[1].doi == "10.1234/p4"
        assert q1_group.papers[1].hybrid_score == pytest.approx(0.62)
        
        assert q1_group.papers[2].doi == "10.1234/p3"
        assert q1_group.papers[2].hybrid_score == pytest.approx(0.62)
        
        # Verify Group 2: Question 2
        q2_group = results.groups[1]
        assert q2_group.question == "Question 2"
        assert q2_group.paper_count == 1
        
        # p2: sim=0.75, pr=0.5 -> hybrid = 0.7*0.75 + 0.3*0.5 = 0.525 + 0.15 = 0.675
        assert q2_group.papers[0].doi == "10.1234/p2"
        assert q2_group.papers[0].hybrid_score == pytest.approx(0.675)

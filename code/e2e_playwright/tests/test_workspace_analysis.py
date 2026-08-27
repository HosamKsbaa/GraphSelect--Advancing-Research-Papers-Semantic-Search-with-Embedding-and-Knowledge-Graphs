"""Comprehensive Playwright E2E tests for Workspace Analysis Tab (Requirement R1.4).

Covers:
- Empty state rendering when no analysis data exists.
- Research question coverage cards with progress bars (good/ok/bad) and status badges (Covered, Partial, Gap).
- LLM gap query generation (Suggest Queries button), query list rendering, and clipboard copy action.
- Citation network statistics panel (Total Papers, Avg Similarity, Network Density).
- Ranked literature list with hybrid, similarity, and PageRank scores and per-question mini breakdown bars.
- Neo4j Polarity Subgraph consensus [SUPPORTS] (Verified Edge) and dispute [CONTRADICTS] (Controversy Edge) cards.
"""
import sys
import os
import pytest
from playwright.sync_api import Page, expect

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from e2e_playwright.conftest import mock_api_route, assert_toast_message
from e2e_playwright.pages.analysis_tab_page import AnalysisTabPage


def _mock_project_base(page: Page, project_id: str):
    """Helper to mock baseline project metadata and touch endpoint."""
    mock_api_route(page, f"**/api/projects/{project_id}*", status_code=200, json_data={
        "id": project_id,
        "name": f"Analysis Test Project {project_id}",
        "description": "Automated Playwright Analysis Tab Test",
        "topic": "Graph Neural Networks",
        "target_level": "master"
    })
    mock_api_route(page, f"**/api/projects/{project_id}/touch*", status_code=200, json_data={"message": "ok"})


def test_analysis_tab_initial_empty_state(page: Page, base_url: str):
    """Test Analysis Tab empty state when 0 coverages and 0 ranked papers exist."""
    project_id = "test-analysis-proj-empty"
    _mock_project_base(page, project_id)

    mock_api_route(page, f"**/api/analysis/{project_id}/coverage*", status_code=200, json_data={
        "covered_questions": [], "gap_questions": [], "overall_coverage": 0.0
    })
    mock_api_route(page, f"**/api/analysis/{project_id}/ranked-papers*", status_code=200, json_data={"ranked_papers": []})
    mock_api_route(page, f"**/api/analysis/{project_id}/citation-stats*", status_code=404, json_data={"detail": "Not found"})

    analysis_tab = AnalysisTabPage(page, base_url)
    analysis_tab.navigate(project_id)

    # Verify Empty state is displayed
    expect(analysis_tab.empty_state).to_be_visible()
    expect(analysis_tab.empty_state).to_contain_text("No Data for Analysis")
    expect(analysis_tab.empty_state).to_contain_text("Add papers via Research tab before running analysis.")


def test_research_question_coverage_cards_and_progress_bars(page: Page, base_url: str):
    """Test coverage cards rendering status badges and colored progress bars."""
    project_id = "test-analysis-proj-coverage"
    _mock_project_base(page, project_id)

    mock_coverage = {
        "gap_questions": [
            {
                "question_id": "q1",
                "question": "How do attention mechanisms prevent oversmoothing in heterogeneous graphs?",
                "best_score": 0.22,
                "paper_count": 1
            }
        ],
        "covered_questions": [
            {
                "question_id": "q2",
                "question": "What is the message-passing efficiency in deep GNNs?",
                "best_score": 0.88,
                "paper_count": 6
            }
        ],
        "overall_coverage": 0.55
    }

    mock_api_route(page, f"**/api/analysis/{project_id}/coverage*", status_code=200, json_data=mock_coverage)
    mock_api_route(page, f"**/api/analysis/{project_id}/ranked-papers*", status_code=200, json_data={"ranked_papers": []})
    mock_api_route(page, f"**/api/analysis/{project_id}/citation-stats*", status_code=200, json_data={
        "total_papers": 7, "average_similarity": 0.75, "network_density": 0.38
    })

    analysis_tab = AnalysisTabPage(page, base_url)
    analysis_tab.navigate(project_id)

    # Assert 2 coverage cards rendered
    expect(analysis_tab.coverage_cards).to_have_count(2)

    # Card 1: Gap Question
    card1 = analysis_tab.coverage_cards.nth(0)
    expect(card1.locator(".question-text")).to_contain_text("How do attention mechanisms prevent oversmoothing in heterogeneous graphs?")
    expect(card1.locator(".status-badge")).to_contain_text("Gap")
    expect(card1.locator(".coverage-stats")).to_contain_text("Score: 22%")
    expect(card1.locator(".coverage-stats")).to_contain_text("1 paper(s)")
    expect(card1.locator(".progress-bar")).to_have_class("progress-bar progress-bad")

    # Card 2: Covered Question
    card2 = analysis_tab.coverage_cards.nth(1)
    expect(card2.locator(".question-text")).to_contain_text("What is the message-passing efficiency in deep GNNs?")
    expect(card2.locator(".status-badge")).to_contain_text("Covered")
    expect(card2.locator(".coverage-stats")).to_contain_text("Score: 88%")
    expect(card2.locator(".coverage-stats")).to_contain_text("6 paper(s)")
    expect(card2.locator(".progress-bar")).to_have_class("progress-bar progress-good")


def test_llm_gap_query_generation_and_clipboard_copy(page: Page, base_url: str):
    """Test clicking 'Suggest Queries' triggers LLM gap generation, displays query list, and copies to clipboard."""
    project_id = "test-analysis-proj-gap"
    _mock_project_base(page, project_id)

    mock_coverage = {
        "gap_questions": [
            {
                "question_id": "q-gap-1",
                "question": "What are the asymptotic bounds for Graph Convolutional Network oversmoothing?",
                "best_score": 0.15,
                "paper_count": 0
            }
        ],
        "covered_questions": [],
        "overall_coverage": 0.15
    }

    mock_generated_queries = {
        "gap_question": "What are the asymptotic bounds for Graph Convolutional Network oversmoothing?",
        "queries": [
            "GCN oversmoothing Dirichlet energy Dirichlet dispersion bounds",
            "Exponential convergence of graph neural network feature representations",
            "Deep graph convolutional networks topological bounds and spectral gap"
        ]
    }

    mock_api_route(page, f"**/api/analysis/{project_id}/coverage*", status_code=200, json_data=mock_coverage)
    mock_api_route(page, f"**/api/analysis/{project_id}/ranked-papers*", status_code=200, json_data={"ranked_papers": []})
    mock_api_route(page, f"**/api/analysis/{project_id}/citation-stats*", status_code=200, json_data={
        "total_papers": 3, "average_similarity": 0.45, "network_density": 0.2
    })
    mock_api_route(page, f"**/api/analysis/{project_id}/gap-queries*", status_code=200, json_data=mock_generated_queries)

    # Grant clipboard permissions for browser context
    page.context.grant_permissions(["clipboard-read", "clipboard-write"])

    analysis_tab = AnalysisTabPage(page, base_url)
    analysis_tab.navigate(project_id)

    # Verify Gap card displays Suggest Queries button
    expect(analysis_tab.suggest_queries_btns).to_have_count(1)
    expect(analysis_tab.suggest_queries_btns.first).to_have_text("Suggest Queries")

    # Click Suggest Queries
    analysis_tab.click_suggest_queries(0)

    # Assert Toast message on success and zero [object Object]
    toast1 = page.locator("alrs-toast-container .toast").first
    expect(toast1).to_be_visible()
    expect(toast1.locator(".toast-title")).to_contain_text("Queries generated")
    expect(toast1.locator(".toast-message")).to_contain_text("Gap queries successfully generated")
    assert "[object Object]" not in toast1.inner_text()

    # Dismiss first toast so second toast can be tested cleanly
    toast1.locator(".toast-close").click()

    # Assert Suggested queries rendered
    queries = analysis_tab.get_suggested_queries()
    assert len(queries) == 3
    assert "GCN oversmoothing Dirichlet energy" in queries[0]
    assert "Exponential convergence" in queries[1]

    # Test copy button on first query
    analysis_tab.copy_query_btns.first.click()
    toast2 = page.locator("alrs-toast-container .toast:has-text('Copied')").first
    expect(toast2).to_be_visible()
    expect(toast2.locator(".toast-title")).to_contain_text("Copied")
    expect(toast2.locator(".toast-message")).to_contain_text("Query copied to clipboard")
    assert "[object Object]" not in toast2.inner_text()


def test_citation_network_statistics_panel(page: Page, base_url: str):
    """Test Network Statistics card displays Total Papers, Avg Similarity, and Network Density."""
    project_id = "test-analysis-proj-stats"
    _mock_project_base(page, project_id)

    mock_api_route(page, f"**/api/analysis/{project_id}/coverage*", status_code=200, json_data={
        "covered_questions": [], "gap_questions": [], "overall_coverage": 0.0
    })
    mock_api_route(page, f"**/api/analysis/{project_id}/ranked-papers*", status_code=200, json_data={"ranked_papers": [
        {"doi": "10.1145/1", "title": "Paper 1", "year": 2022, "hybrid_score": 0.9, "similarity_score": 0.9, "pagerank_score": 0.8}
    ]})
    mock_api_route(page, f"**/api/analysis/{project_id}/citation-stats*", status_code=200, json_data={
        "total_papers": 24,
        "average_similarity": 0.823,
        "network_density": 0.467
    })

    analysis_tab = AnalysisTabPage(page, base_url)
    analysis_tab.navigate(project_id)

    # Verify Stats panel is visible
    expect(analysis_tab.stats_panel).to_be_visible()
    expect(analysis_tab.total_papers_stat).to_have_text("24")
    expect(analysis_tab.avg_similarity_stat).to_have_text("0.82")
    expect(analysis_tab.network_density_stat).to_have_text("0.47")


def test_ranked_literature_list_and_scores(page: Page, base_url: str):
    """Test Ranked Literature list displays hybrid, similarity, PageRank scores and question breakdown bars."""
    project_id = "test-analysis-proj-ranked"
    _mock_project_base(page, project_id)

    mock_ranked_papers = [
        {
            "doi": "10.1145/3534678.3539078",
            "title": "GraphSelect: Embedding-Guided Traversal",
            "year": 2022,
            "similarity_score": 0.94,
            "pagerank_score": 0.86,
            "hybrid_score": 0.916,
            "question_similarities": [
                {"question_id": "q1", "question_text": "Graph Navigation", "similarity_score": 0.95},
                {"question_id": "q2", "question_text": "Spectral Properties", "similarity_score": 0.88}
            ]
        },
        {
            "doi": "10.1145/3394486.3403067",
            "title": "Scaling Graph Neural Networks for Web-Scale Graphs",
            "year": 2020,
            "similarity_score": 0.78,
            "pagerank_score": 0.72,
            "hybrid_score": 0.762,
            "question_similarities": [
                {"question_id": "q1", "question_text": "Graph Navigation", "similarity_score": 0.80},
                {"question_id": "q2", "question_text": "Spectral Properties", "similarity_score": 0.72}
            ]
        }
    ]

    mock_api_route(page, f"**/api/analysis/{project_id}/coverage*", status_code=200, json_data={
        "covered_questions": [], "gap_questions": [], "overall_coverage": 0.0
    })
    mock_api_route(page, f"**/api/analysis/{project_id}/ranked-papers*", status_code=200, json_data={"ranked_papers": mock_ranked_papers})
    mock_api_route(page, f"**/api/analysis/{project_id}/citation-stats*", status_code=200, json_data={
        "total_papers": 2, "average_similarity": 0.86, "network_density": 0.5
    })

    analysis_tab = AnalysisTabPage(page, base_url)
    analysis_tab.navigate(project_id)

    expect(analysis_tab.ranked_papers_panel).to_be_visible()
    expect(analysis_tab.ranked_paper_rows).to_have_count(2)

    # Paper 1 assertions
    p1 = analysis_tab.ranked_paper_rows.nth(0)
    expect(p1.locator(".paper-title")).to_contain_text("GraphSelect: Embedding-Guided Traversal (2022)")
    expect(p1.locator(".paper-scores")).to_contain_text("Hybrid: 0.92")
    expect(p1.locator(".paper-scores")).to_contain_text("Sim: 0.94")
    expect(p1.locator(".paper-scores")).to_contain_text("PR: 0.86")

    # Paper 1 mini similarity breakdown bars
    p1_bars = p1.locator(".similarity-breakdown .qs-bar-container")
    expect(p1_bars).to_have_count(2)
    expect(p1_bars.nth(0)).to_have_attribute("title", "Graph Navigation : 0.95")
    expect(p1_bars.nth(1)).to_have_attribute("title", "Spectral Properties : 0.88")

    # Paper 2 assertions
    p2 = analysis_tab.ranked_paper_rows.nth(1)
    expect(p2.locator(".paper-title")).to_contain_text("Scaling Graph Neural Networks for Web-Scale Graphs (2020)")
    expect(p2.locator(".paper-scores")).to_contain_text("Hybrid: 0.76")


def test_neo4j_polarity_subgraph_consensus_and_disputes(page: Page, base_url: str):
    """Test Neo4j Polarity Subgraph consensus [SUPPORTS] and dispute [CONTRADICTS] panel rendering."""
    project_id = "test-analysis-proj-polarity"
    _mock_project_base(page, project_id)

    mock_api_route(page, f"**/api/analysis/{project_id}/coverage*", status_code=200, json_data={
        "covered_questions": [], "gap_questions": [], "overall_coverage": 0.0
    })
    mock_api_route(page, f"**/api/analysis/{project_id}/ranked-papers*", status_code=200, json_data={"ranked_papers": [
        {"doi": "10.1145/1", "title": "GNN Paper", "year": 2022, "hybrid_score": 0.85, "similarity_score": 0.85, "pagerank_score": 0.8}
    ]})
    mock_api_route(page, f"**/api/analysis/{project_id}/citation-stats*", status_code=200, json_data={
        "total_papers": 1, "average_similarity": 0.85, "network_density": 0.5
    })

    analysis_tab = AnalysisTabPage(page, base_url)
    analysis_tab.navigate(project_id)

    # Verify Polarity Subgraph panel is visible
    expect(analysis_tab.polarity_panel).to_be_visible()
    expect(analysis_tab.polarity_panel).to_contain_text("Scientific Consensus & Disputes")
    expect(analysis_tab.polarity_panel).to_contain_text("Neo4j Polarity Subgraph")

    # Assert Consensus card [SUPPORTS]
    expect(analysis_tab.polarity_supports_badge).to_be_visible()
    expect(analysis_tab.polarity_supports_badge).to_have_text("[SUPPORTS] Methodological Consensus")
    expect(analysis_tab.verified_edge_badge).to_be_visible()
    expect(analysis_tab.verified_edge_badge).to_have_text("Verified Edge")

    # Assert Controversy card [CONTRADICTS]
    expect(analysis_tab.polarity_contradicts_badge).to_be_visible()
    expect(analysis_tab.polarity_contradicts_badge).to_have_text("[CONTRADICTS] Scalability & Oversmoothing Limits")
    expect(analysis_tab.controversy_edge_badge).to_be_visible()
    expect(analysis_tab.controversy_edge_badge).to_have_text("Controversy Edge")

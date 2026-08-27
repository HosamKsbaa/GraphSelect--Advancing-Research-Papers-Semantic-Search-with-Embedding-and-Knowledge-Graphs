"""Comprehensive Playwright E2E tests for Workspace Research Tab (Requirement R1.3).

Covers:
- Question addition (#inputQuestion, #btnAddQuestion) with optimistic UI update and dynamic embedding status check (✓, ⏳, ✗).
- Delete question confirmation and info toast validation.
- Author / Venue search mode toggle (.toggle-mode-btn) and search web triggering.
- Paper library table filtering, pagination, and empty state rendering.
- Expandable paper detail rows showing per-question similarity breakdown bars and DOI links.
- Top authors and top venues ranked widgets inspection.
"""
import sys
import os
import pytest
from playwright.sync_api import Page, expect

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from e2e_playwright.conftest import mock_api_route, assert_toast_message
from e2e_playwright.pages.project_workspace_page import ProjectWorkspacePage
from e2e_playwright.pages.research_tab_page import ResearchTabPage


def _mock_project_base(page: Page, project_id: str):
    """Helper to mock baseline project metadata and touch endpoint."""
    mock_api_route(page, f"**/api/projects/{project_id}*", status_code=200, json_data={
        "id": project_id,
        "name": f"Research Test Project {project_id}",
        "description": "Automated Playwright Research Tab Test",
        "topic": "Graph Neural Networks",
        "target_level": "master"
    })
    mock_api_route(page, f"**/api/projects/{project_id}/touch*", status_code=200, json_data={"message": "ok"})


def test_research_tab_initial_load_and_empty_state(page: Page, base_url: str):
    """Test Research Tab initial layout and empty states for questions and paper library."""
    project_id = "test-research-proj-empty"
    _mock_project_base(page, project_id)

    mock_api_route(page, f"**/api/research/{project_id}/questions*", status_code=200, json_data={"questions": []})
    mock_api_route(page, f"**/api/analysis/{project_id}/ranked-papers*", status_code=200, json_data={"ranked_papers": []})
    mock_api_route(page, f"**/api/research/{project_id}/top-authors*", status_code=200, json_data={"authors": []})
    mock_api_route(page, f"**/api/research/{project_id}/top-venues*", status_code=200, json_data={"venues": []})

    research_tab = ResearchTabPage(page, base_url)
    research_tab.navigate(project_id)

    # Verify Workspace Layout and container
    expect(research_tab.container).to_be_visible()

    # Verify Left Sidebar Empty State
    expect(research_tab.questions_empty_state).to_be_visible()
    expect(research_tab.questions_empty_state).to_contain_text("No Questions")
    expect(research_tab.questions_empty_state).to_contain_text("Add questions to start exploring.")

    # Verify Library Table Empty State
    expect(research_tab.library_empty_state).to_be_visible()
    expect(research_tab.library_empty_state).to_contain_text("Library Empty")
    expect(research_tab.library_empty_state).to_contain_text("Search for papers to populate your library.")

    # Verify Right Sidebar Widgets present
    expect(research_tab.top_authors_widget).to_be_visible()
    expect(research_tab.top_venues_widget).to_be_visible()


def test_research_question_addition_optimistic_update(page: Page, base_url: str):
    """Test question addition with immediate optimistic UI update and input clearing."""
    project_id = "test-research-proj-add"
    _mock_project_base(page, project_id)

    question_text = "What is the computational complexity of Graph Neural Network inference?"

    mock_api_route(page, f"**/api/research/{project_id}/questions*", status_code=200, json_data={"questions": []})
    mock_api_route(page, f"**/api/analysis/{project_id}/ranked-papers*", status_code=200, json_data={"ranked_papers": []})
    mock_api_route(page, f"**/api/research/{project_id}/top-authors*", status_code=200, json_data={"authors": []})
    mock_api_route(page, f"**/api/research/{project_id}/top-venues*", status_code=200, json_data={"venues": []})

    research_tab = ResearchTabPage(page, base_url)
    research_tab.navigate(project_id)

    # Initial state: no questions
    expect(research_tab.question_items).to_have_count(0)

    # Add question via input and click
    research_tab.add_research_question(question_text)

    # Verify optimistic update immediately renders the new question item
    expect(research_tab.question_items).to_have_count(1)
    expect(research_tab.question_texts.first).to_have_text(question_text)
    expect(research_tab.question_status_icons.first).to_have_text("✓")

    # Verify input field cleared
    expect(research_tab.question_input).to_have_value("")

    # Verify toast notification without [object Object]
    assert_toast_message(page, expected_title_substring="Success", expected_text_substring="Research question added")


def test_research_question_embedding_status_icons(page: Page, base_url: str):
    """Test dynamic embedding status icons (✓ embedded, ⏳ pending, ✗ failed)."""
    project_id = "test-research-proj-status"
    _mock_project_base(page, project_id)

    mock_questions = [
        {"id": "q1", "text": "How do GNNs handle scale?", "embedding_status": "embedded", "coverage_score": 0.85},
        {"id": "q2", "text": "What are the oversmoothing bounds?", "embedding_status": "pending", "coverage_score": 0.40},
        {"id": "q3", "text": "Which benchmark datasets are standard?", "embedding_status": "failed", "coverage_score": 0.0}
    ]

    mock_api_route(page, f"**/api/research/{project_id}/questions*", status_code=200, json_data={"questions": mock_questions})
    mock_api_route(page, f"**/api/analysis/{project_id}/ranked-papers*", status_code=200, json_data={"ranked_papers": []})
    mock_api_route(page, f"**/api/research/{project_id}/top-authors*", status_code=200, json_data={"authors": []})
    mock_api_route(page, f"**/api/research/{project_id}/top-venues*", status_code=200, json_data={"venues": []})

    research_tab = ResearchTabPage(page, base_url)
    research_tab.navigate(project_id)

    expect(research_tab.question_items).to_have_count(3)

    # Check status icons
    expect(research_tab.question_status_icons.nth(0)).to_have_text("✓")
    expect(research_tab.question_status_icons.nth(0)).to_have_attribute("title", "Status: embedded")
    expect(research_tab.question_coverage_badges.nth(0)).to_contain_text("85%")

    expect(research_tab.question_status_icons.nth(1)).to_have_text("⏳")
    expect(research_tab.question_status_icons.nth(1)).to_have_attribute("title", "Status: pending")
    expect(research_tab.question_coverage_badges.nth(1)).to_contain_text("40%")

    expect(research_tab.question_status_icons.nth(2)).to_have_text("✗")
    expect(research_tab.question_status_icons.nth(2)).to_have_attribute("title", "Status: failed")
    expect(research_tab.question_coverage_badges.nth(2)).to_contain_text("0%")


def test_research_question_delete_action_feedback(page: Page, base_url: str):
    """Test clicking question delete button triggers info toast regarding backend status."""
    project_id = "test-research-proj-delete"
    _mock_project_base(page, project_id)

    mock_questions = [
        {"id": "q1", "text": "Question to be deleted", "embedding_status": "embedded", "coverage_score": 0.5}
    ]

    mock_api_route(page, f"**/api/research/{project_id}/questions*", status_code=200, json_data={"questions": mock_questions})
    mock_api_route(page, f"**/api/analysis/{project_id}/ranked-papers*", status_code=200, json_data={"ranked_papers": []})
    mock_api_route(page, f"**/api/research/{project_id}/top-authors*", status_code=200, json_data={"authors": []})
    mock_api_route(page, f"**/api/research/{project_id}/top-venues*", status_code=200, json_data={"venues": []})

    research_tab = ResearchTabPage(page, base_url)
    research_tab.navigate(project_id)

    expect(research_tab.question_items).to_have_count(1)

    # Click delete button (X) on question
    research_tab.delete_question_btns.first.click()

    # Assert Toast message "Not Implemented" and zero [object Object]
    assert_toast_message(page, expected_title_substring="Not Implemented", expected_text_substring="Deleting questions is not supported")


def test_author_venue_search_mode_toggle_and_web_search(page: Page, base_url: str):
    """Test search mode switcher between Author and Venue, input typing, and search trigger."""
    project_id = "test-research-proj-search"
    _mock_project_base(page, project_id)

    mock_api_route(page, f"**/api/research/{project_id}/questions*", status_code=200, json_data={"questions": []})
    mock_api_route(page, f"**/api/analysis/{project_id}/ranked-papers*", status_code=200, json_data={"ranked_papers": []})
    mock_api_route(page, f"**/api/research/{project_id}/top-authors*", status_code=200, json_data={"authors": []})
    mock_api_route(page, f"**/api/research/{project_id}/top-venues*", status_code=200, json_data={"venues": []})

    # Mock Author & Venue search endpoints
    mock_api_route(page, "**/api/research/search/author*", status_code=200, json_data=[
        {"doi": "10.1145/111", "title": "Author Paper 1", "year": 2023}
    ])
    mock_api_route(page, "**/api/research/search/venue*", status_code=200, json_data=[
        {"doi": "10.1145/222", "title": "Venue Paper 1", "year": 2024}
    ])

    research_tab = ResearchTabPage(page, base_url)
    research_tab.navigate(project_id)

    # Initial mode: Author
    expect(research_tab.toggle_mode_btn).to_contain_text("Searching: Author")
    expect(research_tab.search_input).to_have_attribute("placeholder", "Search by Author...")

    # Search author
    research_tab.search_web_papers("Jure Leskovec")

    # Toggle mode to Venue
    mode_text = research_tab.toggle_search_mode()
    assert "Venue" in mode_text
    expect(research_tab.toggle_mode_btn).to_contain_text("Searching: Venue")
    expect(research_tab.search_input).to_have_attribute("placeholder", "Search by Venue...")

    # Search venue
    research_tab.search_web_papers("NeurIPS")

    # Toggle mode back to Author
    mode_text = research_tab.toggle_search_mode()
    assert "Author" in mode_text
    expect(research_tab.toggle_mode_btn).to_contain_text("Searching: Author")


def test_paper_library_table_filtering_and_details_expansion(page: Page, base_url: str):
    """Test library table filtering, row count, and expanding row details for similarity breakdown."""
    project_id = "test-research-proj-lib"
    _mock_project_base(page, project_id)

    mock_questions = [
        {"id": "q1", "text": "GNN Architectures", "embedding_status": "embedded", "coverage_score": 0.8},
        {"id": "q2", "text": "Oversmoothing mitigation", "embedding_status": "embedded", "coverage_score": 0.6}
    ]
    mock_papers = [
        {
            "doi": "10.1145/3534678.3539078",
            "title": "GraphSelect: Embedding-Guided Traversal",
            "year": 2022,
            "similarity_score": 0.92,
            "hybrid_score": 0.88,
            "pagerank_score": 0.75,
            "question_similarities": [
                {"question_id": "q1", "question_text": "GNN Architectures", "similarity_score": 0.95},
                {"question_id": "q2", "question_text": "Oversmoothing mitigation", "similarity_score": 0.82}
            ]
        },
        {
            "doi": "10.1145/3394486.3403067",
            "title": "Scaling Graph Neural Networks for Recommendation",
            "year": 2020,
            "similarity_score": 0.74,
            "hybrid_score": 0.70,
            "pagerank_score": 0.60,
            "question_similarities": [
                {"question_id": "q1", "question_text": "GNN Architectures", "similarity_score": 0.78},
                {"question_id": "q2", "question_text": "Oversmoothing mitigation", "similarity_score": 0.55}
            ]
        },
        {
            "doi": "10.1145/3447548.3467215",
            "title": "Deep Transformers in NLP and Vision",
            "year": 2021,
            "similarity_score": 0.35,
            "hybrid_score": 0.30,
            "pagerank_score": 0.20,
            "question_similarities": [
                {"question_id": "q1", "question_text": "GNN Architectures", "similarity_score": 0.30},
                {"question_id": "q2", "question_text": "Oversmoothing mitigation", "similarity_score": 0.15}
            ]
        }
    ]

    mock_api_route(page, f"**/api/research/{project_id}/questions*", status_code=200, json_data={"questions": mock_questions})
    mock_api_route(page, f"**/api/analysis/{project_id}/ranked-papers*", status_code=200, json_data={"ranked_papers": mock_papers})
    mock_api_route(page, f"**/api/research/{project_id}/top-authors*", status_code=200, json_data={"authors": []})
    mock_api_route(page, f"**/api/research/{project_id}/top-venues*", status_code=200, json_data={"venues": []})

    research_tab = ResearchTabPage(page, base_url)
    research_tab.navigate(project_id)

    # Initial table state: 3 rows
    expect(research_tab.paper_rows).to_have_count(3)

    # Filter library by "Graph"
    research_tab.filter_library("Graph")
    expect(research_tab.paper_rows).to_have_count(2)

    # Filter by "Transformers"
    research_tab.filter_library("Transformers")
    expect(research_tab.paper_rows).to_have_count(1)
    expect(research_tab.paper_rows.first).to_contain_text("Deep Transformers in NLP and Vision")

    # Clear filter
    research_tab.filter_library("")
    expect(research_tab.paper_rows).to_have_count(3)

    # Expand paper row #0 details
    detail_row = research_tab.toggle_paper_detail(0)
    expect(detail_row).to_be_visible()
    expect(detail_row.locator(".detail-header h3")).to_contain_text("GraphSelect: Embedding-Guided Traversal")
    expect(detail_row.locator(".doi-link")).to_have_text("10.1145/3534678.3539078")
    expect(detail_row.locator(".doi-link")).to_have_attribute("href", "https://doi.org/10.1145/3534678.3539078")

    # Verify per-question similarity breakdown scores
    score_items = detail_row.locator(".question-scores .score-item")
    expect(score_items).to_have_count(2)
    expect(score_items.nth(0)).to_contain_text("GNN Architectures")
    expect(score_items.nth(0).locator(".score-value")).to_contain_text("95%")
    expect(score_items.nth(1)).to_contain_text("Oversmoothing mitigation")
    expect(score_items.nth(1).locator(".score-value")).to_contain_text("82%")

    # Click again to collapse
    research_tab.toggle_paper_detail(0)
    expect(detail_row).not_to_be_visible()


def test_paper_library_pagination(page: Page, base_url: str):
    """Test pagination controls (Previous / Next / Page label) when paper count exceeds page size."""
    project_id = "test-research-proj-page"
    _mock_project_base(page, project_id)

    # Create 25 mock papers (pageSize is 20)
    mock_papers = [
        {
            "doi": f"10.1145/paper_{i:02d}",
            "title": f"Scalable GNN Benchmark Paper #{i:02d}",
            "year": 2020 + (i % 5),
            "similarity_score": 0.85 - (i * 0.02),
            "hybrid_score": 0.80,
            "pagerank_score": 0.70
        }
        for i in range(1, 26)
    ]

    mock_api_route(page, f"**/api/research/{project_id}/questions*", status_code=200, json_data={"questions": []})
    mock_api_route(page, f"**/api/analysis/{project_id}/ranked-papers*", status_code=200, json_data={"ranked_papers": mock_papers})
    mock_api_route(page, f"**/api/research/{project_id}/top-authors*", status_code=200, json_data={"authors": []})
    mock_api_route(page, f"**/api/research/{project_id}/top-venues*", status_code=200, json_data={"venues": []})

    research_tab = ResearchTabPage(page, base_url)
    research_tab.navigate(project_id)

    # Page 1: 20 rows visible
    expect(research_tab.paper_rows).to_have_count(20)
    expect(research_tab.pagination_label).to_contain_text("Page 1 of 2")
    expect(research_tab.pagination_prev_btn).to_be_disabled()
    expect(research_tab.pagination_next_btn).to_be_enabled()

    # Click Next -> Page 2: remaining 5 rows visible
    research_tab.pagination_next_btn.click()
    expect(research_tab.paper_rows).to_have_count(5)
    expect(research_tab.pagination_label).to_contain_text("Page 2 of 2")
    expect(research_tab.pagination_prev_btn).to_be_enabled()
    expect(research_tab.pagination_next_btn).to_be_disabled()

    # Click Previous -> Page 1
    research_tab.pagination_prev_btn.click()
    expect(research_tab.paper_rows).to_have_count(20)
    expect(research_tab.pagination_label).to_contain_text("Page 1 of 2")
    expect(research_tab.pagination_prev_btn).to_be_disabled()

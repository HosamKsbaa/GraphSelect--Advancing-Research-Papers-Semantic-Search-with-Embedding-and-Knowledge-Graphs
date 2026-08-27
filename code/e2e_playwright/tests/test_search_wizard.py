"""Comprehensive Playwright E2E tests for Literature Search Wizard (Requirement R1.2).

Covers 4-step Literature Search Wizard workflow:
- Step 1: Candidate resolution & seed paper selection (title search, candidate cards, metadata display).
- Step 2: Research questions addition (Q1..Q6, remove buttons), similarity threshold range slider, max depth & mode selection.
- Step 3: Real-time BFS crawl progress monitoring (progress bar, event badges, status icons, session info).
- Step 4: ResultsComponent inspection (re-ranking sliders #threshold-slider and #weight-slider, question tabs Q1..QN, expandable paper drawers with score breakdown and DOI links, project import dropdown).
"""
import sys
import os
import pytest
from playwright.sync_api import Page, expect

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from e2e_playwright.conftest import mock_api_route, mock_sse_route, assert_toast_message
from e2e_playwright.pages.search_wizard_page import SearchWizardPage


def test_step1_seed_paper_resolution_and_selection(page: Page, base_url: str):
    """Test Step 1: Search seed paper by title, display candidate cards with metadata, select seed."""
    mock_candidates = [
        {
            "doi": "10.1145/3534678.3539078",
            "title": "GraphSelect: Embedding-Guided Graph Traversal for Scalable Semantic Paper Search",
            "year": 2022,
            "cited_by_count": 48,
            "authors": ["Alice Smith", "Bob Jones", "Carol White"]
        },
        {
            "doi": "10.1145/3394486.3403067",
            "title": "Scaling Graph Neural Networks for Search and Recommendation",
            "year": 2020,
            "cited_by_count": 132,
            "authors": ["Dave Brown", "Eve Green"]
        }
    ]

    mock_api_route(page, "**/api/search/resolve*", status_code=200, json_data=mock_candidates)

    wizard = SearchWizardPage(page, base_url)
    wizard.navigate()

    # Verify Header and Step Indicators
    expect(wizard.page_title).to_contain_text("New Literature Search")
    expect(wizard.step_indicators).to_have_count(4)
    expect(wizard.step_find_paper).to_have_class("step active")
    expect(wizard.step_questions).not_to_have_class("step active")

    # Perform seed search
    wizard.search_seed_title("GraphSelect")

    # Assert candidate cards rendered with metadata
    expect(wizard.candidate_cards).to_have_count(2)

    card1 = wizard.candidate_cards.nth(0)
    expect(card1.locator(".candidate-title")).to_contain_text("GraphSelect: Embedding-Guided Graph Traversal")
    expect(card1.locator(".candidate-meta .mono")).to_contain_text("10.1145/3534678.3539078")
    expect(card1.locator(".candidate-meta .badge-info")).to_contain_text("2022")
    expect(card1.locator(".candidate-meta")).to_contain_text("48 citations")
    expect(card1.locator(".candidate-authors")).to_contain_text("Alice Smith, Bob Jones, Carol White")

    card2 = wizard.candidate_cards.nth(1)
    expect(card2.locator(".candidate-title")).to_contain_text("Scaling Graph Neural Networks")
    expect(card2.locator(".candidate-meta .mono")).to_contain_text("10.1145/3394486.3403067")
    expect(card2.locator(".candidate-meta")).to_contain_text("132 citations")

    # Click candidate to select seed paper
    wizard.select_candidate(0)

    # Asserts wizard transitioned to Step 2
    expect(wizard.step_questions).to_have_class("step active")
    expect(wizard.selected_paper_badge).to_be_visible()
    expect(wizard.selected_paper_badge.locator(".mono")).to_contain_text("10.1145/3534678.3539078")


def test_step1_empty_candidate_resolution_shows_error_banner(page: Page, base_url: str):
    """Test Step 1: Empty search results display user-friendly error banner."""
    mock_api_route(page, "**/api/search/resolve*", status_code=200, json_data=[])

    wizard = SearchWizardPage(page, base_url)
    wizard.navigate()

    wizard.search_seed_title("NonExistentPaperTitleXYZ999")

    expect(wizard.error_banner).to_be_visible()
    expect(wizard.error_banner).to_contain_text("No papers found matching that title.")
    expect(wizard.candidate_cards).to_have_count(0)


def test_step2_research_questions_addition_removal_and_limits(page: Page, base_url: str):
    """Test Step 2: Dynamic addition/removal of research questions (Q1..Q6 limit)."""
    wizard = SearchWizardPage(page, base_url)
    wizard.navigate()

    # Move to Step 2 by selecting seed
    mock_candidates = [{
        "doi": "10.1145/3534678.3539078",
        "title": "GraphSelect",
        "year": 2022,
        "cited_by_count": 48,
        "authors": ["Alice Smith"]
    }]
    mock_api_route(page, "**/api/search/resolve*", status_code=200, json_data=mock_candidates)
    wizard.search_seed_title("GraphSelect")
    wizard.select_candidate(0)

    # Step 2 starts with 2 default questions
    expect(wizard.question_rows).to_have_count(2)
    expect(wizard.question_rows.nth(0).locator(".question-number")).to_contain_text("Q1")
    expect(wizard.question_rows.nth(1).locator(".question-number")).to_contain_text("Q2")

    # Add questions up to max limit of 6
    wizard.add_question_btn.click()  # Q3
    expect(wizard.question_rows).to_have_count(3)
    expect(wizard.question_rows.nth(2).locator(".question-number")).to_contain_text("Q3")

    wizard.add_question_btn.click()  # Q4
    wizard.add_question_btn.click()  # Q5
    wizard.add_question_btn.click()  # Q6
    expect(wizard.question_rows).to_have_count(6)

    # When 6 questions exist, '+ Add Question' button is hidden
    expect(wizard.add_question_btn).not_to_be_visible()

    # Remove question rows using remove button
    expect(wizard.remove_question_btns).to_have_count(6)
    wizard.remove_question_btns.last.click()  # Remove Q6
    expect(wizard.question_rows).to_have_count(5)
    expect(wizard.add_question_btn).to_be_visible()

    # Remove down to 1 question
    wizard.remove_question_btns.last.click()  # Remove Q5 -> 4
    wizard.remove_question_btns.last.click()  # Remove Q4 -> 3
    wizard.remove_question_btns.last.click()  # Remove Q3 -> 2
    wizard.remove_question_btns.last.click()  # Remove Q2 -> 1
    expect(wizard.question_rows).to_have_count(1)

    # When only 1 question remains, remove button is not rendered
    expect(wizard.remove_question_btns).to_have_count(0)


def test_step2_settings_controls_and_back_navigation(page: Page, base_url: str):
    """Test Step 2: Settings controls (similarity slider, max depth, mode) and Back navigation."""
    wizard = SearchWizardPage(page, base_url)
    wizard.navigate()

    mock_candidates = [{
        "doi": "10.1145/3534678.3539078",
        "title": "GraphSelect",
        "year": 2022,
        "cited_by_count": 48,
        "authors": ["Alice Smith"]
    }]
    mock_api_route(page, "**/api/search/resolve*", status_code=200, json_data=mock_candidates)
    wizard.search_seed_title("GraphSelect")
    wizard.select_candidate(0)

    # Test similarity threshold slider
    expect(wizard.similarity_slider).to_be_visible()
    slider_readout = page.locator(".settings-grid .slider-row .mono")
    expect(slider_readout).to_contain_text("0.50")

    # Set slider value to 0.75
    wizard.similarity_slider.fill("0.75")
    expect(slider_readout).to_contain_text("0.75")

    # Test Max Depth dropdown select
    expect(wizard.max_depth_select).to_have_value("2")
    wizard.max_depth_select.select_option("3")
    expect(wizard.max_depth_select).to_have_value("3")

    # Test Mode dropdown select
    expect(wizard.mode_select).to_have_value("automated")
    wizard.mode_select.select_option("interactive")
    expect(wizard.mode_select).to_have_value("interactive")
    wizard.mode_select.select_option("automated")
    expect(wizard.mode_select).to_have_value("automated")

    # Test Back navigation
    wizard.step2_back_btn.click()
    expect(wizard.step_find_paper).to_have_class("step active")
    expect(wizard.candidate_cards).to_have_count(1)

    # Re-enter Step 2
    wizard.select_candidate(0)
    expect(wizard.step_questions).to_have_class("step active")

    # Validation test: empty questions display error
    for i in range(wizard.question_inputs.count()):
        wizard.question_inputs.nth(i).fill("")
    wizard.start_search()
    expect(wizard.error_banner).to_be_visible()
    expect(wizard.error_banner).to_contain_text("Please enter at least one research question.")


def test_step3_realtime_bfs_crawl_progress_monitoring(page: Page, base_url: str):
    """Test Step 3: Real-time BFS crawl progress bar, status icons, session details, event log."""
    session_id = "sess-crawl-test-777"
    seed_doi = "10.1145/3534678.3539078"

    mock_api_route(page, "**/api/search/resolve*", status_code=200, json_data=[{
        "doi": seed_doi,
        "title": "GraphSelect Seed Paper",
        "year": 2022,
        "cited_by_count": 48,
        "authors": ["Alice Smith"]
    }])

    mock_api_route(page, "**/api/search/start*", status_code=200, json_data={
        "session_id": session_id,
        "seed_paper_doi": seed_doi,
        "status": "running"
    })

    sse_events = [
        {
            "event": "search_started",
            "data": {
                "event_type": "search_started",
                "message": "Initializing graph traversal for seed paper node.",
                "progress_percent": 15
            }
        },
        {
            "event": "level_complete",
            "data": {
                "event_type": "level_complete",
                "message": "Level 1 traversal completed with 14 citation edges.",
                "progress_percent": 50
            }
        },
        {
            "event": "embedding_progress",
            "data": {
                "event_type": "embedding_progress",
                "message": "Generating Gemini embeddings and computing cosine similarity.",
                "progress_percent": 80
            }
        },
        {
            "event": "search_failed",
            "data": {
                "event_type": "search_failed",
                "message": "Traversed max depth reached with candidate pool.",
                "progress_percent": 85
            }
        }
    ]

    mock_sse_route(page, f"**/api/search/{session_id}/stream*", events=sse_events)

    wizard = SearchWizardPage(page, base_url)
    wizard.navigate()

    # Step 1 -> Step 2
    wizard.search_seed_title("GraphSelect")
    wizard.select_candidate(0)

    # Step 2 -> Start Search -> Step 3
    wizard.fill_research_questions(["How does selective graph expansion compare to full vector database indexes?"])
    wizard.start_search()

    # Step 3: Verify crawl progress and details
    page.wait_for_selector(".progress-container", timeout=10000)
    expect(wizard.step_crawl).to_have_class("step active")

    # Verify header status
    expect(page.locator(".crawl-header h2")).to_contain_text("Search Failed")
    expect(wizard.crawl_status_icon).to_have_class("crawl-status-icon failed")

    # Verify progress bar fill and readout
    expect(wizard.progress_bar_fill).to_have_class("progress-fill failed")
    expect(wizard.progress_text.locator(".mono")).to_contain_text("85%")

    # Verify session info details panel
    expect(wizard.session_info_details).to_be_visible()
    expect(wizard.session_info_details).to_contain_text(session_id)
    expect(wizard.session_info_details).to_contain_text(seed_doi)
    expect(wizard.session_info_details.locator(".badge")).to_contain_text("FAILED")

    # Verify Event Log items
    expect(wizard.event_log_items).to_have_count(4)
    expect(wizard.event_log_items.nth(0).locator(".event-badge")).to_contain_text("search_started")
    expect(wizard.event_log_items.nth(1).locator(".event-badge")).to_contain_text("level_complete")
    expect(wizard.event_log_items.nth(2).locator(".event-badge")).to_contain_text("embedding_progress")
    expect(wizard.event_log_items.nth(3).locator(".event-badge")).to_contain_text("search_failed")

    # Verify Step 3 action buttons
    expect(wizard.view_sessions_link).to_be_visible()
    expect(wizard.step3_new_search_btn).to_be_visible()


def test_step4_results_component_inspection_and_reranking(page: Page, base_url: str):
    """Test Step 4: ResultsComponent inspection (ranking sliders, question tabs, expandable paper drawers, DOI links)."""
    session_id = "sess-results-test-888"
    seed_doi = "10.1145/3534678.3539078"

    grouped_results = {
        "session_id": session_id,
        "total_papers": 3,
        "similarity_threshold": 0.50,
        "similarity_weight": 0.70,
        "pagerank_weight": 0.30,
        "groups": [
            {
                "question": "How does selective graph expansion compare to vector database indexes?",
                "avg_similarity": 0.86,
                "papers": [
                    {
                        "doi": "10.1145/1001",
                        "title": "Scalable Graph Embeddings in Literature Search",
                        "authors": ["Alice Smith", "Bob Jones"],
                        "year": 2023,
                        "cited_by_count": 58,
                        "similarity_score": 0.88,
                        "pagerank_score": 0.72,
                        "hybrid_score": 0.832,
                        "abstract_snippet": "This paper presents a novel selective graph expansion method for citation graphs."
                    },
                    {
                        "doi": "10.1145/1002",
                        "title": "Vector Databases vs Graph Traversal for Citation Networks",
                        "authors": ["Carol White", "Dave Brown"],
                        "year": 2024,
                        "cited_by_count": 21,
                        "similarity_score": 0.82,
                        "pagerank_score": 0.65,
                        "hybrid_score": 0.769,
                        "abstract_snippet": "We compare pure dense vector search against citation-guided graph traversal."
                    }
                ]
            },
            {
                "question": "What is the performance benefit of combining cosine similarity with PageRank?",
                "avg_similarity": 0.79,
                "papers": [
                    {
                        "doi": "10.1145/1003",
                        "title": "Hybrid PageRank and Semantic Ranking for Academic Search",
                        "authors": ["Eve Green"],
                        "year": 2022,
                        "cited_by_count": 94,
                        "similarity_score": 0.79,
                        "pagerank_score": 0.88,
                        "hybrid_score": 0.817,
                        "abstract_snippet": "Combining PageRank with semantic similarity yields significantly higher retrieval relevance."
                    }
                ]
            }
        ]
    }

    reranked_results = dict(grouped_results)
    reranked_results["similarity_threshold"] = 0.60
    reranked_results["similarity_weight"] = 0.50
    reranked_results["pagerank_weight"] = 0.50

    mock_api_route(page, "**/api/search/resolve*", status_code=200, json_data=[{
        "doi": seed_doi, "title": "GraphSelect", "year": 2022, "cited_by_count": 48, "authors": ["Alice Smith"]
    }])
    mock_api_route(page, "**/api/search/start*", status_code=200, json_data={
        "session_id": session_id, "seed_paper_doi": seed_doi, "status": "running"
    })
    mock_sse_route(page, f"**/api/search/{session_id}/stream*", events=[{
        "event": "search_complete",
        "data": {"event_type": "search_complete", "message": "Done", "progress_percent": 100}
    }])
    mock_api_route(page, f"**/api/search/{session_id}/results*", status_code=200, json_data=grouped_results)
    mock_api_route(page, f"**/api/search/{session_id}/rerank*", status_code=200, json_data=reranked_results)
    mock_api_route(page, "**/api/projects*", status_code=200, json_data=[
        {"id": "proj-import-1", "name": "AI Literature Review"}
    ])

    wizard = SearchWizardPage(page, base_url)
    wizard.navigate()

    # Step 1 -> 2 -> 3 -> 4 (auto advances on search_complete)
    wizard.search_seed_title("GraphSelect")
    wizard.select_candidate(0)
    wizard.start_search()

    # Verify Results View (alrs-results)
    expect(wizard.results_view).to_be_visible(timeout=10000)
    expect(wizard.results_session_id).to_contain_text(session_id)

    # Verify Quick Stats
    expect(wizard.total_relevant_stat).to_contain_text("3")

    # Verify Ranking Sliders
    expect(wizard.threshold_slider).to_be_visible()
    expect(wizard.weight_slider).to_be_visible()

    threshold_readout = page.locator(".sliders-section .control-group:has(#threshold-slider) .value-readout")
    expect(threshold_readout).to_contain_text("0.50")

    weight_readout = page.locator(".sliders-section .control-group:has(#weight-slider) .value-readout")
    expect(weight_readout).to_contain_text("70% / 30%")

    # Test Question Tabs (Q1, Q2)
    expect(wizard.question_tabs).to_have_count(2)
    expect(wizard.question_tabs.nth(0)).to_have_class("tab-btn active")
    expect(wizard.question_tabs.nth(0).locator(".tab-index")).to_contain_text("Q1")
    expect(wizard.question_tabs.nth(0).locator(".tab-badge")).to_contain_text("2")
    expect(wizard.question_tabs.nth(1).locator(".tab-index")).to_contain_text("Q2")
    expect(wizard.question_tabs.nth(1).locator(".tab-badge")).to_contain_text("1")

    # Verify Papers in active Tab Q1
    expect(wizard.results_paper_cards).to_have_count(2)
    paper1 = wizard.results_paper_cards.nth(0)
    expect(paper1.locator(".score-val")).to_contain_text("83")
    expect(paper1.locator(".rank-label")).to_contain_text("#1")
    expect(paper1.locator(".paper-title")).to_contain_text("Scalable Graph Embeddings in Literature Search")
    expect(paper1.locator(".paper-authors-row .authors")).to_contain_text("Alice Smith, Bob Jones")
    expect(paper1.locator(".scores-row")).to_contain_text("Sim: 0.880")
    expect(paper1.locator(".scores-row")).to_contain_text("PageRank: 0.720")
    expect(paper1.locator(".scores-row")).to_contain_text("Citations: 58")

    # Test Expandable Paper Drawer
    paper1.click()
    expect(paper1.locator(".abstract-section .abstract")).to_contain_text("novel selective graph expansion method")

    # Verify DOI external link
    doi_link = paper1.locator(".doi-row a.doi-link")
    expect(doi_link).to_have_attribute("href", "https://doi.org/10.1145/1001")
    expect(doi_link).to_have_attribute("target", "_blank")

    # Switch to Question Tab Q2
    wizard.select_question_tab(1)
    expect(wizard.question_tabs.nth(1)).to_have_class("tab-btn active")
    expect(page.locator(".group-header h2")).to_contain_text("Research Question 2")
    expect(wizard.results_paper_cards).to_have_count(1)
    expect(wizard.results_paper_cards.nth(0).locator(".paper-title")).to_contain_text("Hybrid PageRank and Semantic Ranking")


def test_step4_paper_selection_and_project_import(page: Page, base_url: str):
    """Test Step 4: Paper selection checkboxes and importing papers to an existing project."""
    session_id = "sess-import-test-999"
    project_id = "proj-target-456"

    grouped_results = {
        "session_id": session_id,
        "total_papers": 2,
        "similarity_threshold": 0.50,
        "similarity_weight": 0.70,
        "pagerank_weight": 0.30,
        "groups": [
            {
                "question": "Research question 1",
                "avg_similarity": 0.85,
                "papers": [
                    {
                        "doi": "10.1145/2001",
                        "title": "Paper One For Import",
                        "authors": ["Author One"],
                        "year": 2023,
                        "cited_by_count": 10,
                        "similarity_score": 0.90,
                        "pagerank_score": 0.80,
                        "hybrid_score": 0.87,
                        "abstract_snippet": "First candidate abstract."
                    },
                    {
                        "doi": "10.1145/2002",
                        "title": "Paper Two For Import",
                        "authors": ["Author Two"],
                        "year": 2024,
                        "cited_by_count": 5,
                        "similarity_score": 0.85,
                        "pagerank_score": 0.75,
                        "hybrid_score": 0.82,
                        "abstract_snippet": "Second candidate abstract."
                    }
                ]
            }
        ]
    }

    mock_api_route(page, "**/api/search/resolve*", status_code=200, json_data=[{
        "doi": "10.1145/seed", "title": "Seed", "year": 2022, "cited_by_count": 1, "authors": ["A"]
    }])
    mock_api_route(page, "**/api/search/start*", status_code=200, json_data={
        "session_id": session_id, "seed_paper_doi": "10.1145/seed", "status": "running"
    })
    mock_sse_route(page, f"**/api/search/{session_id}/stream*", events=[{
        "event": "search_complete", "data": {"event_type": "search_complete", "message": "Done", "progress_percent": 100}
    }])
    mock_api_route(page, f"**/api/search/{session_id}/results*", status_code=200, json_data=grouped_results)
    mock_api_route(page, "**/api/projects*", status_code=200, json_data=[
        {"id": project_id, "name": "Deep Learning Survey Project"}
    ])

    import_called = []

    def handle_import_papers(route):
        import_called.append(route.request.post_data_json)
        route.fulfill(
            status=200,
            headers={"Content-Type": "application/json"},
            body='{"message": "Successfully imported 2 papers to project."}'
        )

    page.route(f"**/api/projects/{project_id}/papers*", handle_import_papers)

    wizard = SearchWizardPage(page, base_url)
    wizard.navigate()

    # Fast forward to Step 4
    wizard.search_seed_title("Seed")
    wizard.select_candidate(0)
    wizard.start_search()

    # Verify Results View loaded
    expect(wizard.results_view).to_be_visible(timeout=10000)

    # Verify project selector populated
    expect(wizard.project_selector).to_be_visible()
    expect(wizard.project_selector.locator(f"option[value='{project_id}']")).to_contain_text("Deep Learning Survey Project")

    # Import button disabled when no project or papers selected
    expect(wizard.import_selected_btn).to_be_disabled()

    # Select project
    wizard.project_selector.select_option(project_id)
    expect(wizard.import_selected_btn).to_be_disabled()  # 0 papers selected

    # Check paper 1
    wizard.toggle_paper_selection(0)
    expect(wizard.import_selected_btn).to_be_enabled()
    expect(wizard.import_selected_btn).to_contain_text("Import Selected (1)")

    # Check paper 2
    wizard.toggle_paper_selection(1)
    expect(wizard.import_selected_btn).to_contain_text("Import Selected (2)")

    # Click Import Selected
    wizard.import_selected_btn.click()

    # Toast validation (zero [object Object] guarantee)
    assert_toast_message(
        page,
        expected_title_substring="Import Successful",
        expected_text_substring="Successfully imported 2 papers to project."
    )

    # Verify payload sent to API
    assert len(import_called) == 1
    assert import_called[0]["project_id"] == project_id
    assert "10.1145/2001" in import_called[0]["dois"]
    assert "10.1145/2002" in import_called[0]["dois"]

    # Verify checkboxes cleared
    expect(wizard.import_selected_btn).to_be_disabled()


def test_search_wizard_reset_flow(page: Page, base_url: str):
    """Test resetting search wizard from Results (Step 4) back to Step 1."""
    session_id = "sess-reset-123"

    mock_api_route(page, "**/api/search/resolve*", status_code=200, json_data=[{
        "doi": "10.1145/reset", "title": "Reset Seed", "year": 2023, "cited_by_count": 5, "authors": ["Author"]
    }])
    mock_api_route(page, "**/api/search/start*", status_code=200, json_data={
        "session_id": session_id, "seed_paper_doi": "10.1145/reset", "status": "running"
    })
    mock_sse_route(page, f"**/api/search/{session_id}/stream*", events=[{
        "event": "search_complete", "data": {"event_type": "search_complete", "message": "Done", "progress_percent": 100}
    }])
    mock_api_route(page, f"**/api/search/{session_id}/results*", status_code=200, json_data={
        "session_id": session_id,
        "total_papers": 1,
        "similarity_threshold": 0.5,
        "similarity_weight": 0.7,
        "pagerank_weight": 0.3,
        "groups": [{
            "question": "Q1",
            "avg_similarity": 0.8,
            "papers": [{
                "doi": "10.1145/r1", "title": "Paper R1", "authors": ["A"], "year": 2023,
                "cited_by_count": 1, "similarity_score": 0.8, "pagerank_score": 0.8, "hybrid_score": 0.8,
                "abstract_snippet": "Abstract"
            }]
        }]
    })

    wizard = SearchWizardPage(page, base_url)
    wizard.navigate()

    wizard.search_seed_title("Reset Seed")
    wizard.select_candidate(0)
    wizard.start_search()

    expect(wizard.results_view).to_be_visible(timeout=10000)

    # Click Reset / New Search in Results view sidebar
    wizard.step4_reset_btn.click()

    # Wizard returns to Step 1
    expect(wizard.step_find_paper).to_have_class("step active")
    expect(wizard.seed_title_input).to_be_visible()

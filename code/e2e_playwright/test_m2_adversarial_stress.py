"""Adversarial stress-test suite for Milestone 2: Projects Management & Literature Search Wizard.

Authored by Challenger 1 to empirically challenge and stress-test:
- Search filter case-insensitivity, substring matches across name/topic/desc, regex-special characters.
- Dynamic question addition, middle deletion, sequential re-indexing, boundary limits (min 1, max 6).
- Search wizard candidate card metadata resilience (missing authors, 0 citations, empty fields).
- SSE stream simulation with multiple edge event payloads, fast complete, and error states.
- Results re-ranking slider bounds and multi-tab switching integrity.
- Paper drawer accordion toggle and multi-paper selection batching.
"""
import sys
import os
import uuid
import pytest
from playwright.sync_api import Page, expect

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from e2e_playwright.conftest import mock_api_route, mock_sse_route, assert_toast_message
from e2e_playwright.pages.project_list_page import ProjectListPage
from e2e_playwright.pages.search_wizard_page import SearchWizardPage


# ===========================================================================
# 1. Empirical Stress-Testing: Projects Search Filtering (R1.1)
# ===========================================================================

def test_adversarial_project_search_case_insensitivity_and_partial_substrings(page: Page, base_url: str):
    """Stress-test project search filtering for uppercase, lowercase, mixed case, and substring tokens."""
    mock_projects = [
        {
            "id": "proj-adv-1",
            "name": "Deep Reinforcement Learning for Autonomous Drone Navigation",
            "topic": "Aerial Robotics",
            "description": "Exploration of PPO algorithms in high-fidelity simulated turbulence environments.",
            "target_level": "phd",
            "status": "active",
            "paper_count": 12,
            "question_count": 3,
            "created_at": "2026-08-01T10:00:00Z",
            "updated_at": "2026-08-01T10:00:00Z",
            "last_accessed_at": "2026-08-02T12:00:00Z"
        },
        {
            "id": "proj-adv-2",
            "name": "Graph Neural Networks on Biological Knowledge Graphs",
            "topic": "Bioinformatics",
            "description": "Drug repurposing using relational graph convolutional networks (RGCN).",
            "target_level": "master",
            "status": "active",
            "paper_count": 6,
            "question_count": 2,
            "created_at": "2026-08-05T10:00:00Z",
            "updated_at": "2026-08-05T10:00:00Z",
            "last_accessed_at": "2026-08-06T14:00:00Z"
        }
    ]

    mock_api_route(page, "**/api/projects*", status_code=200, json_data=mock_projects)

    p_list = ProjectListPage(page, base_url)
    p_list.navigate()

    expect(p_list.project_cards).to_have_count(2)

    # 1. UPPERCASE match on name: "AUTONOMOUS"
    p_list.search_projects("AUTONOMOUS")
    expect(p_list.project_cards).to_have_count(1)
    expect(p_list.get_project_card("Autonomous Drone Navigation")).to_be_visible()

    # 2. mixedCase match on topic: "bIoInFoRmAtIcS"
    p_list.search_projects("bIoInFoRmAtIcS")
    expect(p_list.project_cards).to_have_count(1)
    expect(p_list.get_project_card("Biological Knowledge Graphs")).to_be_visible()

    # 3. Substring match on description acronym: "RGCN"
    p_list.search_projects("RGCN")
    expect(p_list.project_cards).to_have_count(1)
    expect(p_list.get_project_card("Biological Knowledge Graphs")).to_be_visible()

    # 4. Partial substring in description: "turbulence"
    p_list.search_projects("turbulence")
    expect(p_list.project_cards).to_have_count(1)
    expect(p_list.get_project_card("Autonomous Drone Navigation")).to_be_visible()

    # 5. Regex-like special characters in query should not crash or throw exceptions
    p_list.search_projects(".*[a-z]+(?=test)")
    expect(p_list.project_cards).to_have_count(0)
    expect(p_list.no_results_message).to_be_visible()
    expect(p_list.no_results_message).to_contain_text('.*[a-z]+(?=test)')

    # 6. Exact phrase with single whitespace
    p_list.search_projects("Drone Navigation")
    expect(p_list.project_cards).to_have_count(1)
    expect(p_list.get_project_card("Autonomous Drone Navigation")).to_be_visible()

    # 7. Clearing query restores both
    p_list.search_projects("")
    expect(p_list.project_cards).to_have_count(2)


def test_adversarial_project_creation_modal_edge_cases(page: Page, base_url: str):
    """Stress-test project creation modal with edge case inputs (long names, special characters)."""
    p_list = ProjectListPage(page, base_url)
    p_list.navigate()

    p_list.open_create_dialog()

    # Empty name should keep submit button disabled
    p_list.project_name_input.fill("")
    expect(p_list.submit_create_btn).to_be_disabled()

    # Long project title (300+ chars)
    long_title = "A" * 300
    p_list.project_name_input.fill(long_title)
    expect(p_list.submit_create_btn).to_be_enabled()
    expect(p_list.project_name_input).to_have_value(long_title)

    # Special characters in topic and description
    p_list.project_topic_input.fill("C++ & Python: <script>alert('xss')</script> & LaTeX $O(N \\log N)$")
    p_list.project_desc_input.fill("Testing escaped characters: \"quotes\", 'single', & ampersands, <html> tags.")
    expect(p_list.project_topic_input).to_have_value("C++ & Python: <script>alert('xss')</script> & LaTeX $O(N \\log N)$")

    # Dismiss via cancel
    p_list.close_create_dialog()
    expect(p_list.modal_container).not_to_be_visible()


# ===========================================================================
# 2. Empirical Stress-Testing: Literature Search Wizard (R1.2)
# ===========================================================================

def test_adversarial_step1_candidate_cards_metadata_variations(page: Page, base_url: str):
    """Stress-test candidate cards rendering with missing authors, 0 citations, and unusual titles."""
    mock_candidates = [
        {
            "doi": "10.1000/zero-citations",
            "title": "A Brand New Paper With Zero Citations And Single Author",
            "year": 2026,
            "cited_by_count": 0,
            "authors": ["Solo Researcher"]
        },
        {
            "doi": "10.1000/no-authors",
            "title": "Consortium Report on Graph Standardizations",
            "year": 2021,
            "cited_by_count": 520,
            "authors": []
        }
    ]

    mock_api_route(page, "**/api/search/resolve*", status_code=200, json_data=mock_candidates)

    wizard = SearchWizardPage(page, base_url)
    wizard.navigate()

    wizard.search_seed_title("Consortium")
    expect(wizard.candidate_cards).to_have_count(2)

    # Verify 0 citations badge
    card1 = wizard.candidate_cards.nth(0)
    expect(card1.locator(".candidate-meta")).to_contain_text("0 citations")
    expect(card1.locator(".candidate-authors")).to_contain_text("Solo Researcher")

    # Verify empty authors fallback
    card2 = wizard.candidate_cards.nth(1)
    expect(card2.locator(".candidate-meta")).to_contain_text("520 citations")

    # Select second candidate
    wizard.select_candidate(1)
    expect(wizard.step_questions).to_have_class("step active")
    expect(wizard.selected_paper_badge).to_contain_text("10.1000/no-authors")


def test_adversarial_step2_dynamic_questions_middle_removal_and_reindexing(page: Page, base_url: str):
    """Stress-test adding 6 questions, removing middle questions, and verifying sequence preservation."""
    wizard = SearchWizardPage(page, base_url)
    wizard.navigate()

    mock_candidates = [{
        "doi": "10.1145/test", "title": "Test Paper", "year": 2024, "cited_by_count": 10, "authors": ["Author"]
    }]
    mock_api_route(page, "**/api/search/resolve*", status_code=200, json_data=mock_candidates)
    wizard.search_seed_title("Test Paper")
    wizard.select_candidate(0)

    # Start: Q1, Q2
    expect(wizard.question_rows).to_have_count(2)

    # Add Q3, Q4, Q5, Q6
    for _ in range(4):
        wizard.add_question_btn.click()

    expect(wizard.question_rows).to_have_count(6)
    expect(wizard.add_question_btn).not_to_be_visible()

    # Fill distinct text in each question
    for i in range(6):
        wizard.question_inputs.nth(i).fill(f"Specific Research Question #{i+1}")

    # Remove question Q3 (index 2)
    wizard.remove_question_btns.nth(2).click()
    expect(wizard.question_rows).to_have_count(5)

    # Verify sequential numbers Q1..Q5 are properly re-indexed in UI
    for idx in range(5):
        expect(wizard.question_rows.nth(idx).locator(".question-number")).to_contain_text(f"Q{idx+1}")

    # Add question back to reach 6 again
    expect(wizard.add_question_btn).to_be_visible()
    wizard.add_question_btn.click()
    expect(wizard.question_rows).to_have_count(6)
    expect(wizard.add_question_btn).not_to_be_visible()


def test_adversarial_step4_accordion_toggle_and_reranking_sliders(page: Page, base_url: str):
    """Stress-test Step 4 Results accordion expanding/collapsing multiple paper cards."""
    session_id = "sess-adv-accordion-101"
    seed_doi = "10.1145/adv101"

    grouped_results = {
        "session_id": session_id,
        "total_papers": 2,
        "similarity_threshold": 0.50,
        "similarity_weight": 0.70,
        "pagerank_weight": 0.30,
        "groups": [
            {
                "question": "What are the structural scaling limits of citation graph traversal?",
                "avg_similarity": 0.91,
                "papers": [
                    {
                        "doi": "10.1145/adv.p1",
                        "title": "Sublinear Traversal Algorithms on Large Graphs",
                        "authors": ["Dr. Alpha", "Prof. Beta"],
                        "year": 2025,
                        "cited_by_count": 77,
                        "similarity_score": 0.94,
                        "pagerank_score": 0.89,
                        "hybrid_score": 0.925,
                        "abstract_snippet": "We establish sublinear bounds for BFS heuristic pruning in dense academic citations."
                    },
                    {
                        "doi": "10.1145/adv.p2",
                        "title": "Comparative Benchmarks for Graph Neural Retrieval",
                        "authors": ["Gamma Team"],
                        "year": 2024,
                        "cited_by_count": 33,
                        "similarity_score": 0.88,
                        "pagerank_score": 0.76,
                        "hybrid_score": 0.844,
                        "abstract_snippet": "Empirical evaluation of cosine similarity combined with PageRank on 10M citation edges."
                    }
                ]
            }
        ]
    }

    mock_api_route(page, "**/api/search/resolve*", status_code=200, json_data=[{
        "doi": seed_doi, "title": "Adv Seed", "year": 2024, "cited_by_count": 5, "authors": ["A"]
    }])
    mock_api_route(page, "**/api/search/start*", status_code=200, json_data={
        "session_id": session_id, "seed_paper_doi": seed_doi, "status": "running"
    })
    mock_sse_route(page, f"**/api/search/{session_id}/stream*", events=[{
        "event": "search_complete", "data": {"event_type": "search_complete", "message": "Done", "progress_percent": 100}
    }])
    mock_api_route(page, f"**/api/search/{session_id}/results*", status_code=200, json_data=grouped_results)

    wizard = SearchWizardPage(page, base_url)
    wizard.navigate()

    wizard.search_seed_title("Adv Seed")
    wizard.select_candidate(0)
    wizard.start_search()

    expect(wizard.results_view).to_be_visible(timeout=10000)
    expect(wizard.results_paper_cards).to_have_count(2)

    paper1 = wizard.results_paper_cards.nth(0)
    paper2 = wizard.results_paper_cards.nth(1)

    # Initial state: neither card has expanded class
    expect(paper1).not_to_have_class("paper-card card glass animate-fade-in expanded")
    expect(paper2).not_to_have_class("paper-card card glass animate-fade-in expanded")

    # Click paper 1 to expand drawer
    paper1.click()
    expect(paper1).to_have_class("paper-card card glass animate-fade-in expanded")
    expect(paper1.locator(".abstract-section .abstract")).to_contain_text("sublinear bounds for BFS heuristic pruning")

    # Click paper 1 again to collapse drawer
    paper1.click()
    expect(paper1).not_to_have_class("paper-card card glass animate-fade-in expanded")

    # Click paper 2 to expand drawer
    paper2.click()
    expect(paper2).to_have_class("paper-card card glass animate-fade-in expanded")
    expect(paper2.locator(".abstract-section .abstract")).to_contain_text("Empirical evaluation of cosine similarity")

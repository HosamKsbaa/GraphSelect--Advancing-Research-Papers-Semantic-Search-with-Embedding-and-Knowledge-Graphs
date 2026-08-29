"""Comprehensive Playwright E2E test suite for the ALRS GraphSelect 1-Hop HITL Exploration Cycle.

Covers:
- Step 1 -> Step 2 Pre-flight verification summary (seed metadata, depth=1, active RQs).
- Bounded 1-Hop traversal execution & SSE stream cycle_results event handling.
- Rich candidate paper cards (direction badges, cosine similarity, PageRank, in-graph degree, RQ score bars, abstracts).
- Interactive steering actions ([Add to Project], [Expand 1 Hop Deeper], [Branch to New Seed], [Conclude & Synthesize]).
- Multi-Agent strategic appraisal rendering and interactive chat action chips.
"""
import sys
import os
import json
import pytest
from playwright.sync_api import Page, expect

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from e2e_playwright.conftest import mock_api_route, mock_sse_route, assert_toast_message
from e2e_playwright.pages.one_hop_inspection_page import OneHopInspectionPage
from e2e_playwright.pages.search_wizard_page import SearchWizardPage


@pytest.fixture
def mock_1hop_candidate_pool():
    return [
        {
            "doi": "10.1145/3394486.3403067",
            "title": "Scaling Graph Neural Networks for Search and Recommendation",
            "authors": ["Dave Brown", "Eve Green"],
            "year": 2020,
            "venue": "KDD",
            "abstract_snippet": "We propose a scalable neighborhood sampling approach for graph neural networks in large citation and item graphs.",
            "direction": "forward_citation",
            "citation_count": 142,
            "in_graph_degree": 4,
            "similarity_scores": [
                {"question_id": "Q1", "similarity_score": 0.92},
                {"question_id": "Q2", "similarity_score": 0.84}
            ],
            "max_similarity": 0.92,
            "mean_similarity": 0.88,
            "already_in_library": False,
            "embedding_cached": True,
            "pagerank_score": 0.85,
            "partition": "contemporary_breakthroughs",
            "recommendation_rationale": "High empirical relevance with state-of-the-art benchmark results for GNN scaling."
        },
        {
            "doi": "10.1145/3447548.3467219",
            "title": "Theoretical Bounds on Oversmoothing in Deep Graph Networks",
            "authors": ["Frank Miller", "Grace Hopper"],
            "year": 2019,
            "venue": "ICML",
            "abstract_snippet": "This paper establishes formal Dirichlet energy bounds preventing representation collapse in deep message passing.",
            "direction": "backward_reference",
            "citation_count": 310,
            "in_graph_degree": 7,
            "similarity_scores": [
                {"question_id": "Q1", "similarity_score": 0.81},
                {"question_id": "Q2", "similarity_score": 0.76}
            ],
            "max_similarity": 0.81,
            "mean_similarity": 0.785,
            "already_in_library": False,
            "embedding_cached": True,
            "pagerank_score": 0.65,
            "partition": "foundational_prior_art",
            "recommendation_rationale": "Foundational prior art establishing the theoretical limits of selective depth expansion."
        },
        {
            "doi": "10.1145/3534678.3539099",
            "title": "Cross-Domain Topological Bridges in Heterogeneous Citation Graphs",
            "authors": ["Heidi Stone", "Ivan Vance"],
            "year": 2023,
            "venue": "NeurIPS",
            "abstract_snippet": "We investigate bridging nodes connecting computer science literature with information retrieval benchmarks.",
            "direction": "forward_citation",
            "citation_count": 45,
            "in_graph_degree": 9,
            "similarity_scores": [
                {"question_id": "Q1", "similarity_score": 0.89},
                {"question_id": "Q2", "similarity_score": 0.91}
            ],
            "max_similarity": 0.91,
            "mean_similarity": 0.90,
            "already_in_library": True,
            "embedding_cached": True,
            "pagerank_score": 0.92,
            "partition": "topological_bridges",
            "recommendation_rationale": "Key topological bridge bridging theoretical GNN bounds with practical vector indexing."
        }
    ]


def test_1hop_preflight_summary_display(page: Page, base_url: str):
    """Test R3: Pre-flight verification summary renders seed metadata, depth=1, and active RQs."""
    seed_doi = "10.1145/3534678.3539078"
    mock_candidates = [{
        "doi": seed_doi,
        "title": "GraphSelect: Embedding-Guided Graph Traversal for Scalable Semantic Paper Search",
        "year": 2022,
        "cited_by_count": 48,
        "authors": ["Alice Smith", "Bob Jones"]
    }]

    mock_api_route(page, "**/api/search/resolve*", status_code=200, json_data=mock_candidates)
    mock_api_route(page, "**/api/projects*", status_code=200, json_data=[])

    hop_page = OneHopInspectionPage(page, base_url)
    hop_page.navigate_search()

    wizard = SearchWizardPage(page, base_url)
    wizard.search_seed_title("GraphSelect")
    wizard.select_candidate(0)

    # Asserts pre-flight card is visible in Step 2
    expect(hop_page.preflight_container).to_be_visible()
    expect(hop_page.preflight_seed_title).to_contain_text("GraphSelect: Embedding-Guided Graph Traversal")
    expect(hop_page.preflight_seed_doi).to_contain_text(seed_doi)
    expect(hop_page.preflight_container).to_contain_text("Step 1 (1-Hop BFS)")
    expect(hop_page.preflight_container).to_contain_text("Threshold: 0.50")
    expect(hop_page.preflight_active_rqs).to_contain_text("How does selective graph expansion compare")


def test_1hop_sse_stream_cycle_results(page: Page, base_url: str, mock_1hop_candidate_pool):
    """Test R1 & R3: SSE stream emits cycle_results at Level 1, rendering 1-hop inspection cards."""
    session_id = "sess-1hop-hitl-101"
    seed_doi = "10.1145/3534678.3539078"

    mock_api_route(page, "**/api/search/resolve*", status_code=200, json_data=[{
        "doi": seed_doi,
        "title": "GraphSelect",
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
                "message": "Initializing 1-hop graph traversal for seed paper node.",
                "progress_percent": 15
            }
        },
        {
            "event": "cycle_results",
            "data": {
                "event_type": "cycle_results",
                "message": "Level 1 traversal complete: 3 candidate papers evaluated.",
                "progress_percent": 60,
                "data": {
                    "level": 1,
                    "papers_discovered": 3,
                    "papers_new": 2,
                    "candidates": mock_1hop_candidate_pool,
                    "strategic_recommendation": "Identified 1 foundational theoretical paper, 1 contemporary empirical breakthrough, and 1 topological bridge.",
                    "steering_options": [
                        {
                            "option_id": "opt-1",
                            "action_type": "expand_deeper",
                            "target_doi": "10.1145/3394486.3403067",
                            "label": "⚡ Expand 10.1145/3394486 for Benchmarks",
                            "rationale": "High empirical relevance"
                        }
                    ]
                }
            }
        }
    ]

    mock_sse_route(page, f"**/api/search/{session_id}/stream*", events=sse_events)
    mock_api_route(page, "**/api/projects*", status_code=200, json_data=[{"id": "p1", "name": "Survey"}])

    hop_page = OneHopInspectionPage(page, base_url)
    hop_page.navigate_search()

    wizard = SearchWizardPage(page, base_url)
    wizard.search_seed_title("GraphSelect")
    wizard.select_candidate(0)
    wizard.start_search()

    # Verify 1-Hop Inspection UI is rendered
    expect(hop_page.inspection_container).to_be_visible(timeout=10000)
    expect(hop_page.level_badge).to_contain_text("Level 1 Complete")
    expect(hop_page.stat_discovered).to_contain_text("3")
    expect(hop_page.stat_new).to_contain_text("2")

    # Assert 3 candidate cards are present
    expect(hop_page.candidate_cards).to_have_count(3)


def test_1hop_candidate_card_state_richness(page: Page, base_url: str, mock_1hop_candidate_pool):
    """Test R1: Verify candidate cards display 100% complete state payload (direction, sim %, PR, deg, RQ breakdown, abstract)."""
    session_id = "sess-richness-202"
    seed_doi = "10.1145/3534678.3539078"

    mock_api_route(page, "**/api/search/resolve*", status_code=200, json_data=[{
        "doi": seed_doi, "title": "GraphSelect", "year": 2022, "cited_by_count": 48, "authors": ["A"]
    }])
    mock_api_route(page, "**/api/search/start*", status_code=200, json_data={
        "session_id": session_id, "seed_paper_doi": seed_doi, "status": "running"
    })
    mock_sse_route(page, f"**/api/search/{session_id}/stream*", events=[{
        "event": "cycle_results",
        "data": {
            "event_type": "cycle_results",
            "message": "Level 1 results ready",
            "progress_percent": 60,
            "data": {
                "level": 1,
                "papers_discovered": 3,
                "papers_new": 2,
                "candidates": mock_1hop_candidate_pool
            }
        }
    }])
    mock_api_route(page, "**/api/projects*", status_code=200, json_data=[])

    hop_page = OneHopInspectionPage(page, base_url)
    hop_page.navigate_search()

    wizard = SearchWizardPage(page, base_url)
    wizard.search_seed_title("GraphSelect")
    wizard.select_candidate(0)
    wizard.start_search()

    expect(hop_page.inspection_container).to_be_visible(timeout=10000)

    # Card 1: Forward citation
    card1 = hop_page.get_card(0)
    expect(card1.locator(".card-title")).to_contain_text("Scaling Graph Neural Networks for Search")
    expect(card1.locator(".card-doi")).to_contain_text("10.1145/3394486.3403067")
    expect(card1.locator(".direction-badge")).to_contain_text("Forward Citation ▲")
    expect(card1.locator(".similarity-badge")).to_contain_text("92% Sim")
    expect(card1.locator(".pagerank-badge")).to_contain_text("PR: 0.850")
    expect(card1.locator(".degree-badge")).to_contain_text("Deg: 4")
    expect(card1.locator(".badge-discovered")).to_contain_text("Discovered Candidate")
    expect(card1.locator(".badge-cached")).to_contain_text("Embedding Cached ✔")
    expect(card1.locator(".rq-score-bar")).to_have_count(2)

    # Expand abstract preview
    hop_page.toggle_abstract(0)
    expect(card1.locator(".abstract-preview")).to_contain_text("scalable neighborhood sampling approach")

    # Card 3 (index 2): Backward reference
    card3 = hop_page.get_card(2)
    expect(card3.locator(".card-title")).to_contain_text("Theoretical Bounds on Oversmoothing")
    expect(card3.locator(".direction-badge")).to_contain_text("Backward Reference ▼")
    expect(card3.locator(".similarity-badge")).to_contain_text("81% Sim")


def test_1hop_steering_add_to_project(page: Page, base_url: str, mock_1hop_candidate_pool):
    """Test R3: User clicks [+ Add to Project] on candidate card, updating library status & calling API."""
    session_id = "sess-add-proj-303"
    project_id = "proj-target-111"

    mock_api_route(page, "**/api/search/resolve*", status_code=200, json_data=[{
        "doi": "10.1145/seed", "title": "Seed", "year": 2022, "cited_by_count": 1, "authors": ["A"]
    }])
    mock_api_route(page, "**/api/search/start*", status_code=200, json_data={
        "session_id": session_id, "seed_paper_doi": "10.1145/seed", "status": "running"
    })
    mock_sse_route(page, f"**/api/search/{session_id}/stream*", events=[{
        "event": "cycle_results",
        "data": {
            "event_type": "cycle_results",
            "message": "Level 1 ready",
            "data": {"level": 1, "papers_discovered": 3, "papers_new": 2, "candidates": mock_1hop_candidate_pool}
        }
    }])
    mock_api_route(page, "**/api/projects*", status_code=200, json_data=[{"id": project_id, "name": "Survey Proj"}])

    import_requests = []

    def handle_add_paper(route):
        import_requests.append(route.request.post_data_json)
        route.fulfill(
            status=200,
            headers={"Content-Type": "application/json"},
            body='{"message": "Successfully imported paper."}'
        )

    page.route(f"**/api/projects/{project_id}/papers*", handle_add_paper)

    hop_page = OneHopInspectionPage(page, base_url)
    hop_page.navigate_search()

    wizard = SearchWizardPage(page, base_url)
    wizard.search_seed_title("Seed")
    wizard.select_candidate(0)
    wizard.start_search()

    expect(hop_page.inspection_container).to_be_visible(timeout=10000)

    # Click Add to Project on first card
    hop_page.add_candidate_to_project(0)

    # Assert Toast notification appeared
    assert_toast_message(
        page,
        expected_title_substring="Import Successful",
        expected_text_substring="Added"
    )

    # Verify API request payload
    assert len(import_requests) == 1
    assert "10.1145/3394486.3403067" in import_requests[0]["dois"]


def test_1hop_steering_expand_1hop_deeper(page: Page, base_url: str, mock_1hop_candidate_pool):
    """Test R3: User clicks [⚡ Expand 1 Hop Deeper] on candidate card, enqueuing DOI for next cycle."""
    session_id = "sess-expand-404"

    mock_api_route(page, "**/api/search/resolve*", status_code=200, json_data=[{
        "doi": "10.1145/seed", "title": "Seed", "year": 2022, "cited_by_count": 1, "authors": ["A"]
    }])
    mock_api_route(page, "**/api/search/start*", status_code=200, json_data={
        "session_id": session_id, "seed_paper_doi": "10.1145/seed", "status": "running"
    })
    mock_sse_route(page, f"**/api/search/{session_id}/stream*", events=[{
        "event": "cycle_results",
        "data": {
            "event_type": "cycle_results",
            "message": "Level 1 ready",
            "data": {"level": 1, "papers_discovered": 3, "papers_new": 2, "candidates": mock_1hop_candidate_pool}
        }
    }])
    mock_api_route(page, "**/api/projects*", status_code=200, json_data=[])

    enqueue_requests = []

    def handle_enqueue(route):
        enqueue_requests.append(route.request.post_data_json)
        route.fulfill(
            status=200,
            headers={"Content-Type": "application/json"},
            body=json.dumps({"enqueued": 1, "status": "running", "session_id": session_id})
        )

    page.route(f"**/api/search/{session_id}/enqueue*", handle_enqueue)

    hop_page = OneHopInspectionPage(page, base_url)
    hop_page.navigate_search()

    wizard = SearchWizardPage(page, base_url)
    wizard.search_seed_title("Seed")
    wizard.select_candidate(0)
    wizard.start_search()

    expect(hop_page.inspection_container).to_be_visible(timeout=10000)

    # Click Expand 1 Hop Deeper on card 0
    hop_page.expand_deeper_on_paper(0)

    # Assert Toast message
    assert_toast_message(page, expected_title_substring="Expanding 1-Hop")

    # Verify DOI was enqueued
    assert len(enqueue_requests) == 1
    assert "10.1145/3394486.3403067" in enqueue_requests[0]


def test_1hop_steering_branch_new_seed(page: Page, base_url: str, mock_1hop_candidate_pool):
    """Test R3: User clicks [🌱 Branch to New Seed], updating active seed and returning to step 2."""
    session_id = "sess-branch-505"

    mock_api_route(page, "**/api/search/resolve*", status_code=200, json_data=[{
        "doi": "10.1145/seed", "title": "Seed", "year": 2022, "cited_by_count": 1, "authors": ["A"]
    }])
    mock_api_route(page, "**/api/search/start*", status_code=200, json_data={
        "session_id": session_id, "seed_paper_doi": "10.1145/seed", "status": "running"
    })
    mock_sse_route(page, f"**/api/search/{session_id}/stream*", events=[{
        "event": "cycle_results",
        "data": {
            "event_type": "cycle_results",
            "message": "Level 1 ready",
            "data": {"level": 1, "papers_discovered": 3, "papers_new": 2, "candidates": mock_1hop_candidate_pool}
        }
    }])
    mock_api_route(page, "**/api/projects*", status_code=200, json_data=[])

    hop_page = OneHopInspectionPage(page, base_url)
    hop_page.navigate_search()

    wizard = SearchWizardPage(page, base_url)
    wizard.search_seed_title("Seed")
    wizard.select_candidate(0)
    wizard.start_search()

    expect(hop_page.inspection_container).to_be_visible(timeout=10000)

    # Branch as new seed on Card 0
    hop_page.branch_as_new_seed(0)

    # Asserts transitioned back to Step 2 with new seed info
    expect(wizard.step_questions).to_have_class("step active")
    expect(wizard.selected_paper_badge).to_contain_text("10.1145/3394486.3403067")


def test_1hop_steering_conclude_and_synthesize(page: Page, base_url: str, mock_1hop_candidate_pool):
    """Test R3: User clicks [📊 Conclude & Synthesize], transitioning to Results & Synthesis view."""
    session_id = "sess-conclude-606"

    mock_api_route(page, "**/api/search/resolve*", status_code=200, json_data=[{
        "doi": "10.1145/seed", "title": "Seed", "year": 2022, "cited_by_count": 1, "authors": ["A"]
    }])
    mock_api_route(page, "**/api/search/start*", status_code=200, json_data={
        "session_id": session_id, "seed_paper_doi": "10.1145/seed", "status": "running"
    })
    mock_sse_route(page, f"**/api/search/{session_id}/stream*", events=[{
        "event": "cycle_results",
        "data": {
            "event_type": "cycle_results",
            "message": "Level 1 ready",
            "data": {"level": 1, "papers_discovered": 3, "papers_new": 2, "candidates": mock_1hop_candidate_pool}
        }
    }])
    mock_api_route(page, f"**/api/search/{session_id}/results*", status_code=200, json_data={
        "session_id": session_id,
        "total_papers": 1,
        "similarity_threshold": 0.5,
        "similarity_weight": 0.7,
        "pagerank_weight": 0.3,
        "groups": [{
            "question": "Q1",
            "avg_similarity": 0.9,
            "papers": [{
                "doi": "10.1145/3394486.3403067",
                "title": "Scaling GNNs",
                "authors": ["Dave"],
                "year": 2020,
                "cited_by_count": 142,
                "similarity_score": 0.92,
                "pagerank_score": 0.85,
                "hybrid_score": 0.899,
                "abstract_snippet": "Abstract"
            }]
        }]
    })
    mock_api_route(page, "**/api/projects*", status_code=200, json_data=[])

    hop_page = OneHopInspectionPage(page, base_url)
    hop_page.navigate_search()

    wizard = SearchWizardPage(page, base_url)
    wizard.search_seed_title("Seed")
    wizard.select_candidate(0)
    wizard.start_search()

    expect(hop_page.inspection_container).to_be_visible(timeout=10000)

    # Click Conclude & Synthesize
    hop_page.conclude_and_synthesize()

    # Asserts Step 4 Results view is visible
    expect(wizard.results_view).to_be_visible(timeout=10000)


def test_1hop_filtering_and_sorting(page: Page, base_url: str, mock_1hop_candidate_pool):
    """Test filtering by Direction and sorting by Citations in 1-hop inspection."""
    session_id = "sess-filter-707"

    mock_api_route(page, "**/api/search/resolve*", status_code=200, json_data=[{
        "doi": "10.1145/seed", "title": "Seed", "year": 2022, "cited_by_count": 1, "authors": ["A"]
    }])
    mock_api_route(page, "**/api/search/start*", status_code=200, json_data={
        "session_id": session_id, "seed_paper_doi": "10.1145/seed", "status": "running"
    })
    mock_sse_route(page, f"**/api/search/{session_id}/stream*", events=[{
        "event": "cycle_results",
        "data": {
            "event_type": "cycle_results",
            "message": "Level 1 ready",
            "data": {"level": 1, "papers_discovered": 3, "papers_new": 2, "candidates": mock_1hop_candidate_pool}
        }
    }])
    mock_api_route(page, "**/api/projects*", status_code=200, json_data=[])

    hop_page = OneHopInspectionPage(page, base_url)
    hop_page.navigate_search()

    wizard = SearchWizardPage(page, base_url)
    wizard.search_seed_title("Seed")
    wizard.select_candidate(0)
    wizard.start_search()

    expect(hop_page.inspection_container).to_be_visible(timeout=10000)
    expect(hop_page.candidate_cards).to_have_count(3)

    # Filter to Backward references only
    hop_page.direction_select.select_option("backward")
    expect(hop_page.candidate_cards).to_have_count(1)
    expect(hop_page.get_card(0).locator(".card-title")).to_contain_text("Theoretical Bounds on Oversmoothing")

    # Reset filter to All
    hop_page.direction_select.select_option("all")
    expect(hop_page.candidate_cards).to_have_count(3)


def test_chat_1hop_agent_appraisal_and_chips(page: Page, base_url: str):
    """Test R2 & R3: Chat renders agent appraisal recommendations and interactive action chips."""
    project_id = "proj-chat-hitl-808"
    chat_id = "chat-session-1"

    assistant_msg = {
        "id": "msg-assistant-1",
        "chat_id": chat_id,
        "sender": "assistant",
        "content": (
            "### 1-Hop GraphSelect Appraisal\n\n"
            "Here is the strategic partition of discovered papers:\n"
            "- **Foundational Prior Art**: 10.1145/3447548 (Core theoretical bounds on GNN oversmoothing)\n"
            "- **Contemporary Breakthrough**: 10.1145/3394486 (High empirical relevance for GNN scaling)\n\n"
            "Would you like to expand 1 hop deeper into 10.1145/3394486 for benchmarks?"
        ),
        "timestamp": "2026-08-29T12:00:00Z",
        "citations": [
            {"doi": "10.1145/3394486", "title": "Scaling GNNs", "authors": ["Dave"], "verified_in_graph": True},
            {"doi": "10.1145/3447548", "title": "Theoretical Bounds", "authors": ["Frank"], "verified_in_graph": True}
        ]
    }

    mock_api_route(page, f"**/api/projects/{project_id}", status_code=200, json_data={"id": project_id, "name": "HITL Project"})
    mock_api_route(page, f"**/api/projects/{project_id}/chats", status_code=200, json_data={"chats": [{"id": chat_id, "project_id": project_id, "title": "Research Thread #1", "updated_at": "2026-08-29T12:00:00Z", "message_count": 2}]})
    mock_api_route(page, f"**/api/projects/{project_id}/chats/{chat_id}/messages", status_code=200, json_data={"messages": [
        {"id": "msg-user-1", "chat_id": chat_id, "sender": "user", "content": "Execute 1-hop GraphSelect traversal", "timestamp": "2026-08-29T11:59:00Z"},
        assistant_msg
    ]})
    mock_api_route(page, "**/api/settings/auth*", status_code=200, json_data={"mode": "studio", "has_credentials": True, "gemini_api_key_set": True, "use_vertex_ai": False})

    page.goto(f"{base_url}/projects/{project_id}/chat")
    expect(page.locator("h3.active-title")).to_contain_text("Research Thread #1", timeout=15000)

    # Verify action chips are rendered beneath assistant message
    action_chips = page.locator(".message-action-chips .btn-action-chip")
    expect(action_chips).to_have_count(7)
    expect(action_chips.nth(0)).to_contain_text("10.1145/3447548 for Methodology")
    expect(action_chips.nth(1)).to_contain_text("10.1145/3447548 for Benchmarks")
    expect(action_chips.nth(2)).to_contain_text("Add 10.1145/3447548 to Project")


def test_chat_action_chip_click_dispatches_prompt(page: Page, base_url: str):
    """Test R3: Clicking an action chip dispatches the continuation prompt to the ADK agent."""
    project_id = "proj-chip-dispatch-909"
    chat_id = "chat-session-2"

    assistant_msg = {
        "id": "msg-asst-1",
        "chat_id": chat_id,
        "sender": "assistant",
        "content": "Discovered candidate: 10.1145/3394486",
        "timestamp": "2026-08-29T12:00:00Z"
    }

    mock_api_route(page, f"**/api/projects/{project_id}", status_code=200, json_data={"id": project_id, "name": "HITL Project"})
    mock_api_route(page, f"**/api/projects/{project_id}/chats", status_code=200, json_data={"chats": [{"id": chat_id, "project_id": project_id, "title": "Research Thread #1", "updated_at": "2026-08-29T12:00:00Z", "message_count": 1}]})
    mock_api_route(page, f"**/api/projects/{project_id}/touch*", status_code=200, json_data={"message": "ok"})
    mock_api_route(page, "**/api/settings/auth*", status_code=200, json_data={"mode": "studio", "has_credentials": True, "gemini_api_key_set": True, "use_vertex_ai": False})

    dispatched_messages = []

    def handle_send_message(route):
        if route.request.method.upper() == "GET":
            route.fulfill(
                status=200,
                headers={"Content-Type": "application/json"},
                body=json.dumps({"messages": [assistant_msg]})
            )
            return
        body = route.request.post_data_json or {}
        dispatched_messages.append(body)
        route.fulfill(
            status=200,
            headers={"Content-Type": "application/json"},
            body=json.dumps({
                "user_message": {"id": "um-2", "chat_id": chat_id, "sender": "user", "content": body.get("message", ""), "timestamp": "2026-08-29T12:01:00Z"},
                "assistant_message": {"id": "am-2", "chat_id": chat_id, "sender": "assistant", "content": "Expanding next 1-hop level...", "timestamp": "2026-08-29T12:01:05Z"}
            })
        )

    page.route(f"**/api/projects/{project_id}/chats/{chat_id}/messages*", handle_send_message)

    page.goto(f"{base_url}/projects/{project_id}/chat")
    expect(page.locator("h3.active-title")).to_contain_text("Research Thread #1", timeout=15000)

    # Click action chip: "⚡ Expand 10.1145/3394486 for Methodology"
    chip = page.locator(".message-action-chips .btn-action-chip").first
    expect(chip).to_be_visible()
    chip.click()

    # Verify message was dispatched
    expect(page.locator(".message-row:has-text('Expanding next 1-hop level...')")).to_be_visible(timeout=10000)
    assert len(dispatched_messages) == 1
    assert "Expand 1 hop deeper on paper 10.1145/3394486" in dispatched_messages[0]["message"]

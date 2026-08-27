"""Challenger 2 Empirical Adversarial Suite for Milestone 3.

Empirically challenges:
1. Workspace Banner Presence and Modal Triggering across multiple sub-routes:
   - /projects/:id/research, /projects/:id/analysis, /projects/:id/planning, /projects/:id/writing, /projects/:id/export
   - Clicking 'Configure Credentials' opens the ApiKeyModal pop-up cleanly across all routes.
2. Action Interceptors when Unconfigured (Pre-network dispatch guard):
   - Writing Tab: Attempting to draft a section when unconfigured triggers warning toast and opens modal without dispatching draft request.
   - Writing Tab: Attempting to review a section when unconfigured triggers warning toast and opens modal without dispatching review request.
   - Analysis Tab: Attempting to suggest gap queries when unconfigured triggers warning toast and opens modal without dispatching query generation request.
   - Chat Tab: Attempting to send message or prompt chip when unconfigured triggers modal and preserves input without network dispatch.
3. Action Interceptor Recovery & Feature Unlocking Flow:
   - Modal opened via intercepted action -> configure credentials -> test connection -> save & apply.
   - Modal dismisses cleanly, workspace banner disappears, and subsequent actions proceed without interception.
"""
from __future__ import annotations

import json
import os
import re
import sys
import pytest
from playwright.sync_api import Page, expect

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from e2e_playwright.conftest import mock_api_route, assert_toast_message
from e2e_playwright.pages.api_key_modal_page import ApiKeyModalPage
from e2e_playwright.pages.project_workspace_page import ProjectWorkspacePage
from e2e_playwright.pages.writing_tab_page import WritingTabPage
from e2e_playwright.pages.analysis_tab_page import AnalysisTabPage
from e2e_playwright.pages.chat_tab_page import ChatTabPage


def _mock_workspace_stateful(page: Page, project_id: str = "test-adv-proj"):
    """Helper to mock workspace endpoints with exact regex patterns and stateful auth tracking."""
    auth_state = {
        "mode": "google_ai_studio",
        "has_credentials": False,
        "gemini_api_key_preview": None,
        "gemini_api_key_set": False,
        "vertex_project": None,
        "vertex_location": "us-central1",
        "use_vertex_ai": False,
    }

    settings_state = {
        "gemini_api_key_set": False,
        "gemini_api_key_preview": "Not set",
        "openalex_api_key_set": True,
        "openalex_api_key_preview": "••••••••••••9999",
        "openalex_email": "researcher@university.edu",
        "embedding_model": "gemini-embedding-2",
        "embedding_dimensions": 768,
    }

    mock_api_route(
        page,
        f"**/api/projects/{project_id}",
        status_code=200,
        json_data={
            "id": project_id,
            "name": "Empirical Adversarial Test Project",
            "description": "Multi-action interceptor verification workspace",
            "topic": "Graph Neural Networks Literature Survey",
            "target_level": "master",
        },
        method="GET",
    )
    mock_api_route(
        page,
        f"**/api/projects/{project_id}/touch*",
        status_code=200,
        json_data={"message": "ok"},
        method="POST",
    )
    mock_api_route(
        page,
        f"**/api/projects/{project_id}/chats",
        status_code=200,
        json_data={"chats": [{"id": "c-1", "project_id": project_id, "title": "Initial Chat", "message_count": 0, "created_at": "2026-08-28T00:00:00Z", "updated_at": "2026-08-28T00:00:00Z"}]},
        method="GET",
    )
    mock_api_route(
        page,
        f"**/api/research/{project_id}/questions*",
        status_code=200,
        json_data={"questions": [{"id": "q-1", "text": "How do GNNs handle oversmoothing?", "status": "completed"}]},
        method="GET",
    )
    mock_api_route(
        page,
        f"**/api/research/{project_id}/top-authors*",
        status_code=200,
        json_data={"authors": []},
        method="GET",
    )
    mock_api_route(
        page,
        f"**/api/research/{project_id}/top-venues*",
        status_code=200,
        json_data={"venues": []},
        method="GET",
    )
    mock_api_route(
        page,
        f"**/api/analysis/{project_id}/ranked-papers*",
        status_code=200,
        json_data={"ranked_papers": [
            {
                "id": "p-1",
                "doi": "10.1000/1",
                "title": "Tackling Oversmoothing in Deep Graph Neural Networks",
                "year": 2024,
                "hybrid_score": 0.92,
                "similarity_score": 0.88,
                "pagerank_score": 0.04,
                "question_similarities": [{"question_id": "q-1", "question_text": "How do GNNs handle oversmoothing?", "similarity_score": 0.88}]
            }
        ]},
        method="GET",
    )
    mock_api_route(
        page,
        f"**/api/analysis/{project_id}/coverage*",
        status_code=200,
        json_data={
            "gap_questions": [
                {
                    "question_id": "q-gap-101",
                    "question": "What are the empirical scalability boundaries of GAT on 100M+ edge graphs?",
                    "best_score": 0.25,
                    "paper_count": 0
                }
            ],
            "covered_questions": [
                {
                    "question_id": "q-1",
                    "question": "How do GNNs handle oversmoothing?",
                    "best_score": 0.88,
                    "paper_count": 1
                }
            ]
        },
        method="GET",
    )
    mock_api_route(
        page,
        f"**/api/analysis/{project_id}/citation-stats*",
        status_code=200,
        json_data={"total_papers": 1, "average_similarity": 0.88, "network_density": 0.0},
        method="GET",
    )
    mock_api_route(
        page,
        f"**/api/planning/{project_id}/summary*",
        status_code=200,
        json_data={"project_id": project_id, "project_name": "Empirical Test", "paper_count": 1, "question_count": 2, "has_drafts": False},
        method="GET",
    )
    mock_api_route(
        page,
        f"**/api/planning/{project_id}/outline*",
        status_code=200,
        json_data={
            "sections": [
                {
                    "section_id": "sec-1",
                    "order": 1,
                    "title": "Introduction to Graph Representation Learning",
                    "description": "Foundational concepts and spectral graph theory overview",
                    "paper_dois": ["10.1000/1"],
                    "subsections": []
                },
                {
                    "section_id": "sec-2",
                    "order": 2,
                    "title": "Deep Architecture Scalability & Oversmoothing Limits",
                    "description": "Comparative analysis of multi-hop propagation cascades",
                    "paper_dois": ["10.1000/1"],
                    "subsections": []
                }
            ]
        },
        method="GET",
    )

    def auth_get_handler(route):
        route.fulfill(
            status=200,
            headers={"Content-Type": "application/json"},
            body=json.dumps(auth_state),
        )

    def settings_handler(route):
        nonlocal auth_state, settings_state
        if route.request.method == "PUT":
            req_data = json.loads(route.request.post_data or "{}")
            is_vertex = req_data.get("use_vertex_ai", False) or req_data.get("mode") == "vertex"
            
            if is_vertex:
                auth_state["mode"] = "vertex"
                auth_state["use_vertex_ai"] = True
                auth_state["vertex_project"] = req_data.get("vertex_project", "gcp-project")
                auth_state["vertex_location"] = req_data.get("vertex_location", "us-central1")
                auth_state["has_credentials"] = True
                auth_state["gemini_api_key_set"] = False
                settings_state["gemini_api_key_set"] = False
            else:
                auth_state["mode"] = "google_ai_studio"
                auth_state["use_vertex_ai"] = False
                auth_state["gemini_api_key_preview"] = "••••••••••••1234"
                auth_state["gemini_api_key_set"] = True
                auth_state["has_credentials"] = True
                settings_state["gemini_api_key_set"] = True
                settings_state["gemini_api_key_preview"] = "••••••••••••1234"

            route.fulfill(
                status=200,
                headers={"Content-Type": "application/json"},
                body=json.dumps({"success": True, "message": "Credentials saved", "restart_required": False}),
            )
        else:
            route.fulfill(
                status=200,
                headers={"Content-Type": "application/json"},
                body=json.dumps(settings_state),
            )

    page.route(re.compile(r".*/api/settings/auth(\?.*)?$"), auth_get_handler)
    page.route(re.compile(r".*/api/settings(\?.*)?$"), settings_handler)

    return auth_state, settings_state


# ==============================================================================
# TEST 1: WORKSPACE BANNER MODAL OPENING ACROSS ALL TABS
# ==============================================================================

def test_workspace_banner_modal_trigger_across_multiple_tabs(page: Page, base_url: str) -> None:
    """Verify workspace alert banner is present across sub-tabs when unconfigured and opens modal."""
    project_id = "test-ws-banner-all-tabs"
    _mock_workspace_stateful(page, project_id)

    modal_page = ApiKeyModalPage(page, base_url)
    ws_page = ProjectWorkspacePage(page, base_url)

    tabs_to_test = ["research", "analysis", "planning", "writing", "export"]

    for tab in tabs_to_test:
        ws_page.goto(f"/projects/{project_id}/{tab}")
        
        # Verify banner is visible
        expect(modal_page.btn_workspace_warning_configure.first).to_be_visible(timeout=5000)
        
        # Click Configure Credentials
        modal_page.btn_workspace_warning_configure.first.click()
        
        # Verify modal dialog opens
        expect(modal_page.modal_dialog.first).to_be_visible(timeout=5000)
        expect(modal_page.tab_ai_studio.first).to_be_visible()
        expect(modal_page.tab_vertex_ai.first).to_be_visible()
        
        # Dismiss via Escape
        modal_page.dismiss_via_escape()
        modal_page.wait_for_closed()


# ==============================================================================
# TEST 2: WRITING TAB ACTION INTERCEPTOR (DRAFT SECTION)
# ==============================================================================

def test_writing_tab_action_interceptor_draft_unconfigured(page: Page, base_url: str) -> None:
    """Attempting to draft a section when unconfigured triggers warning toast and opens modal without network call."""
    project_id = "test-writing-draft-intercept"
    _mock_workspace_stateful(page, project_id)

    draft_call_count = 0

    def draft_route_handler(route):
        nonlocal draft_call_count
        draft_call_count += 1
        route.fulfill(
            status=200,
            headers={"Content-Type": "application/json"},
            body='{"draft_text": "Fake draft content"}',
        )

    page.route(f"**/api/writing/{project_id}/draft*", draft_route_handler)

    modal_page = ApiKeyModalPage(page, base_url)
    writing_page = WritingTabPage(page, base_url)

    writing_page.navigate(project_id)

    # Select first section
    writing_page.select_section(0)
    expect(writing_page.workspace_title).to_have_text("Introduction to Graph Representation Learning")

    # Click Draft Section
    writing_page.click_draft_section()

    # 1. ApiKeyModal must open immediately
    expect(modal_page.modal_dialog.first).to_be_visible(timeout=5000)

    # 2. Warning toast must be displayed
    assert_toast_message(page, expected_title_substring="Credentials Required")

    # 3. Verify backend draft endpoint was NEVER called
    assert draft_call_count == 0, f"Expected 0 draft network calls, but got {draft_call_count}"

    # Dismiss modal
    modal_page.dismiss_via_escape()
    modal_page.wait_for_closed()


# ==============================================================================
# TEST 3: WRITING TAB ACTION INTERCEPTOR (REVIEW SECTION)
# ==============================================================================

def test_writing_tab_action_interceptor_review_unconfigured(page: Page, base_url: str) -> None:
    """Attempting to review a section when unconfigured triggers warning toast and opens modal without network call."""
    project_id = "test-writing-review-intercept"
    auth_state, _ = _mock_workspace_stateful(page, project_id)

    # Initially configured to allow drafting
    auth_state["has_credentials"] = True
    auth_state["gemini_api_key_preview"] = "••••••••••••1234"
    auth_state["gemini_api_key_set"] = True

    mock_api_route(
        page,
        f"**/api/writing/{project_id}/draft*",
        status_code=200,
        json_data={"draft_text": "## Initial Draft\nGraph neural networks propagate node features.", "status": "drafted"},
        method="POST",
    )

    review_call_count = 0

    def review_route_handler(route):
        nonlocal review_call_count
        review_call_count += 1
        route.fulfill(
            status=200,
            headers={"Content-Type": "application/json"},
            body='{"approved": true, "feedback": [], "missing_citations": []}',
        )

    page.route(f"**/api/writing/{project_id}/review*", review_route_handler)

    modal_page = ApiKeyModalPage(page, base_url)
    writing_page = WritingTabPage(page, base_url)

    writing_page.navigate(project_id)
    writing_page.select_section(0)

    # 1. Draft section while configured
    writing_page.click_draft_section()
    expect(writing_page.review_section_btn).to_be_visible(timeout=5000)

    # 2. Now simulate credentials unconfigured / expired
    auth_state["has_credentials"] = False
    auth_state["gemini_api_key_preview"] = None
    auth_state["gemini_api_key_set"] = False

    # Force component service credentials state to false
    page.evaluate("() => { const el = document.querySelector('app-writing-tab'); if (el) { const comp = ng.getComponent(el); if (comp && comp.authModalService) comp.authModalService.setCredentialsState(false); } }")

    # 3. Click Review button while unconfigured
    writing_page.click_review_section()

    # 4. ApiKeyModal must open immediately
    expect(modal_page.modal_dialog.first).to_be_visible(timeout=5000)

    # 5. Warning toast must be displayed
    assert_toast_message(page, expected_title_substring="Credentials Required")

    # 6. Verify backend review endpoint was NEVER called
    assert review_call_count == 0, f"Expected 0 review network calls, but got {review_call_count}"


# ==============================================================================
# TEST 4: ANALYSIS TAB ACTION INTERCEPTOR (SUGGEST GAP QUERIES)
# ==============================================================================

def test_analysis_tab_action_interceptor_suggest_queries_unconfigured(page: Page, base_url: str) -> None:
    """Attempting to suggest gap queries when unconfigured triggers warning toast and opens modal without network call."""
    project_id = "test-analysis-gap-intercept"
    _mock_workspace_stateful(page, project_id)

    gap_query_call_count = 0

    def gap_query_route_handler(route):
        nonlocal gap_query_call_count
        gap_query_call_count += 1
        route.fulfill(
            status=200,
            headers={"Content-Type": "application/json"},
            body='{"queries": ["GNN benchmark 2024", "Graph attention scaling limits"]}',
        )

    page.route(f"**/api/analysis/{project_id}/gap-queries*", gap_query_route_handler)

    modal_page = ApiKeyModalPage(page, base_url)
    analysis_page = AnalysisTabPage(page, base_url)

    analysis_page.navigate(project_id)

    # Click Suggest Queries on gap card
    analysis_page.click_suggest_queries(0)

    # 1. ApiKeyModal must open immediately
    expect(modal_page.modal_dialog.first).to_be_visible(timeout=5000)

    # 2. Warning toast must be displayed
    assert_toast_message(page, expected_title_substring="Credentials Required")

    # 3. Verify backend gap-queries endpoint was NEVER called
    assert gap_query_call_count == 0, f"Expected 0 gap query network calls, but got {gap_query_call_count}"


# ==============================================================================
# TEST 5: FULL INTERCEPTOR RECOVERY FLOW (WRITING TAB)
# ==============================================================================

def test_writing_tab_interceptor_recovery_and_draft_execution(page: Page, base_url: str) -> None:
    """Intercepted draft action -> modal opens -> save credentials -> banner vanishes -> drafting executes successfully."""
    project_id = "test-writing-recovery"
    _mock_workspace_stateful(page, project_id)

    # Mock Test Connection
    mock_api_route(
        page,
        "**/api/settings/test-connection*",
        status_code=200,
        json_data={"success": True, "message": "Connection verified with Gemini API", "latency_ms": 98},
        method="POST",
    )

    draft_called = False

    def draft_handler(route):
        nonlocal draft_called
        draft_called = True
        route.fulfill(
            status=200,
            headers={"Content-Type": "application/json"},
            body='{"draft_text": "## Introduction\\n\\nGraph Neural Networks (GNNs) have emerged as the foundational paradigm for structured geometric representations.", "status": "drafted"}',
        )

    page.route(f"**/api/writing/{project_id}/draft*", draft_handler)

    modal_page = ApiKeyModalPage(page, base_url)
    writing_page = WritingTabPage(page, base_url)

    writing_page.navigate(project_id)
    writing_page.select_section(0)

    # 1. Trigger draft -> intercepted
    writing_page.click_draft_section()
    expect(modal_page.modal_dialog.first).to_be_visible()

    # 2. Configure credentials in modal
    modal_page.select_studio_mode()
    modal_page.fill_gemini_key("AIzaSyEmpiricalChallengerKey123")
    modal_page.click_test_connection()
    modal_page.wait_for_test_feedback(expect_success=True)

    # 3. Save & Apply
    modal_page.save_and_apply()
    modal_page.wait_for_closed()

    # 4. Workspace banner should now be hidden
    expect(modal_page.btn_workspace_warning_configure).to_have_count(0)

    # 5. Re-trigger Draft Section -> should now execute network request without modal pop-up
    writing_page.click_draft_section()
    expect(modal_page.modal_dialog).to_have_count(0)

    # Verify generated draft rendered in markdown preview
    expect(writing_page.markdown_preview).to_be_visible(timeout=5000)
    expect(writing_page.markdown_preview).to_contain_text("Graph Neural Networks (GNNs) have emerged")
    assert draft_called is True, "Expected draft API to be called after credential recovery"


# ==============================================================================
# TEST 6: FULL INTERCEPTOR RECOVERY FLOW (ANALYSIS TAB)
# ==============================================================================

def test_analysis_tab_interceptor_recovery_and_query_generation(page: Page, base_url: str) -> None:
    """Intercepted query suggestion -> modal opens -> save credentials -> banner vanishes -> query suggestion executes."""
    project_id = "test-analysis-recovery"
    _mock_workspace_stateful(page, project_id)

    mock_api_route(
        page,
        "**/api/settings/test-connection*",
        status_code=200,
        json_data={"success": True, "message": "Vertex AI connection verified", "latency_ms": 135},
        method="POST",
    )

    gap_called = False

    def gap_query_handler(route):
        nonlocal gap_called
        gap_called = True
        route.fulfill(
            status=200,
            headers={"Content-Type": "application/json"},
            body='{"queries": ["GNN oversmoothing mitigation survey 2024", "Graph attention scaling benchmark on large graphs"]}',
        )

    page.route(f"**/api/analysis/{project_id}/gap-queries*", gap_query_handler)

    modal_page = ApiKeyModalPage(page, base_url)
    analysis_page = AnalysisTabPage(page, base_url)

    analysis_page.navigate(project_id)

    # 1. Trigger suggest queries -> intercepted
    analysis_page.click_suggest_queries(0)
    expect(modal_page.modal_dialog.first).to_be_visible()

    # 2. Configure credentials with Vertex AI mode
    modal_page.select_vertex_mode()
    modal_page.fill_vertex_project("gcp-alrs-prod-research")
    modal_page.fill_vertex_location("us-central1")
    modal_page.click_test_connection()
    modal_page.wait_for_test_feedback(expect_success=True)

    # 3. Save & Apply
    modal_page.save_and_apply()
    modal_page.wait_for_closed()

    # 4. Workspace banner should now be hidden
    expect(modal_page.btn_workspace_warning_configure).to_have_count(0)

    # 5. Re-trigger Suggest Queries -> should now execute network request without modal pop-up
    analysis_page.click_suggest_queries(0)
    expect(modal_page.modal_dialog).to_have_count(0)

    # Verify suggested queries rendered
    queries = analysis_page.get_suggested_queries()
    assert len(queries) == 2
    assert "GNN oversmoothing mitigation survey 2024" in queries[0]
    assert "Graph attention scaling benchmark on large graphs" in queries[1]
    assert gap_called is True, "Expected gap-queries API to be called after credential recovery"


# ==============================================================================
# TEST 7: CHAT TAB INTERCEPTOR AND INPUT RETENTION
# ==============================================================================

def test_chat_tab_action_interceptor_and_input_preservation(page: Page, base_url: str) -> None:
    """Attempting to send message or prompt chip in chat tab opens modal, preserves input, blocks network dispatch."""
    project_id = "test-chat-intercept-retention"
    _mock_workspace_stateful(page, project_id)

    chat_message_post_count = 0

    def chat_message_handler(route):
        nonlocal chat_message_post_count
        if route.request.method == "POST":
            chat_message_post_count += 1
            route.fulfill(
                status=200,
                headers={"Content-Type": "application/json"},
                body='{"user_message": {"id": "1", "sender": "user", "content": "test"}, "assistant_message": {"id": "2", "sender": "assistant", "content": "resp"}}',
            )
        else:
            route.fulfill(
                status=200,
                headers={"Content-Type": "application/json"},
                body='{"messages": []}',
            )

    page.route(f"**/api/projects/{project_id}/chats/c-1/messages*", chat_message_handler)

    modal_page = ApiKeyModalPage(page, base_url)
    chat_page = ChatTabPage(page, base_url)

    chat_page.navigate(project_id)

    # 1. Enter message and click send
    user_prompt = "What is the spectral clustering formulation of GCNs?"
    chat_page.fill_message_input(user_prompt)
    chat_page.click_send()

    # Verify modal opens, input is preserved, 0 POST API calls
    expect(modal_page.modal_dialog.first).to_be_visible(timeout=5000)
    expect(chat_page.chat_input).to_have_value(user_prompt)
    assert chat_message_post_count == 0, f"Expected 0 chat POST API calls, got {chat_message_post_count}"

    # Dismiss modal
    modal_page.dismiss_via_escape()
    modal_page.wait_for_closed()

    # 2. Click quick prompt chip
    chip = page.locator(".btn-chip").first
    expect(chip).to_be_visible()
    chip_text = chip.inner_text().strip()
    chip.click()

    # Verify modal opens and input is populated with chip text
    expect(modal_page.modal_dialog.first).to_be_visible(timeout=5000)
    expect(chat_page.chat_input).to_have_value(chip_text)
    assert chat_message_post_count == 0

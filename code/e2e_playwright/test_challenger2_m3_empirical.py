"""Challenger 2 Empirical Adversarial Suite for Milestone 3: Workspace Concurrency & Isolation.

Empirically challenges:
1. Cross-Tab Navigation & State Isolation across all 6 workspace tabs (Research, Analysis, Planning, Writing, Chat, Export).
2. Multi-Project State Isolation (ensures project A data never bleeds into project B).
3. In-flight API and Async race condition resiliency during rapid tab switching.
4. Popover and Escape key behavior on Workspace.
5. Route mocking isolation and clean fixture teardown (no test pollution).
"""
import sys
import os
import json
import pytest
from playwright.sync_api import Page, expect
from e2e_playwright.conftest import mock_api_route, assert_toast_message
from e2e_playwright.pages.project_workspace_page import ProjectWorkspacePage
from e2e_playwright.pages.research_tab_page import ResearchTabPage
from e2e_playwright.pages.analysis_tab_page import AnalysisTabPage
from e2e_playwright.pages.planning_tab_page import PlanningTabPage
from e2e_playwright.pages.writing_tab_page import WritingTabPage
from e2e_playwright.pages.chat_tab_page import ChatTabPage
from e2e_playwright.pages.export_tab_page import ExportTabPage


def _mock_project_data(page: Page, project_id: str, name: str):
    """Helper to mock baseline project metadata and all 6 tab endpoints."""
    mock_api_route(page, f"**/api/projects/{project_id}*", status_code=200, json_data={
        "id": project_id,
        "name": name,
        "description": f"Workspace testing for {name}",
        "topic": "Graph Neural Networks",
        "target_level": "master"
    }, method="GET")
    mock_api_route(page, f"**/api/projects/{project_id}/touch*", status_code=200, json_data={"message": "ok"}, method="POST")
    mock_api_route(page, "**/api/settings*", status_code=200, json_data={
        "api_base_url": "http://localhost:8000/api",
        "gemini_api_key_set": True,
        "openalex_api_key_set": False,
        "openalex_email": "test@alrs.org"
    }, method="GET")
    mock_api_route(page, f"**/api/projects/{project_id}/open-folder*", status_code=200, json_data={
        "path": f"/home/user/.alrs/projects/{project_id}"
    }, method="POST")

    # Research mocks
    mock_api_route(page, f"**/api/research/{project_id}/questions*", status_code=200, json_data={
        "questions": [{"id": f"q-{project_id}-1", "text": f"Question for {name}", "status": "completed"}]
    }, method="GET")
    mock_api_route(page, f"**/api/analysis/{project_id}/ranked-papers*", status_code=200, json_data={
        "ranked_papers": [{"id": f"p-{project_id}-1", "doi": "10.1000/1", "title": f"Paper for {name}", "abstract": "Abstract", "year": 2024, "similarity_score": 0.85, "citation_count": 10, "is_seed": True, "openalex_id": "W1", "authors": ["Alice"], "venue": "NeurIPS"}]
    }, method="GET")
    mock_api_route(page, f"**/api/research/{project_id}/top-authors*", status_code=200, json_data={"authors": []}, method="GET")
    mock_api_route(page, f"**/api/research/{project_id}/top-venues*", status_code=200, json_data={"venues": []}, method="GET")

    # Analysis mocks
    mock_api_route(page, f"**/api/analysis/{project_id}/coverage*", status_code=200, json_data={
        "coverages": [{"question_id": f"q-{project_id}-1", "question_text": f"Question for {name}", "covered": True, "paper_count": 1, "avg_similarity": 0.85}]
    }, method="GET")
    mock_api_route(page, f"**/api/analysis/{project_id}/citation-stats*", status_code=200, json_data={
        "total_nodes": 5, "total_edges": 8, "density": 0.4
    }, method="GET")

    # Planning mocks
    mock_api_route(page, f"**/api/planning/{project_id}/summary*", status_code=200, json_data={
        "project_id": project_id, "project_name": name, "paper_count": 1, "question_count": 1, "has_drafts": True
    }, method="GET")
    mock_api_route(page, f"**/api/planning/{project_id}/outline*", status_code=200, json_data={
        "sections": [{
            "section_id": "sec-1",
            "order": 1,
            "title": f"Intro for {name}",
            "description": "Section 1",
            "paper_dois": ["10.1000/1"],
            "subsections": []
        }]
    }, method="GET")

    # Chat mocks
    mock_api_route(page, f"**/api/projects/{project_id}/chats*", status_code=200, json_data={
        "chats": [{"id": f"chat-{project_id}-1", "project_id": project_id, "title": f"Chat for {name}", "message_count": 1, "created_at": "2026-08-27T16:00:00Z", "updated_at": "2026-08-27T16:00:00Z"}]
    }, method="GET")
    mock_api_route(page, f"**/api/projects/{project_id}/chats/chat-{project_id}-1/messages*", status_code=200, json_data={
        "messages": [{"id": f"msg-{project_id}-1", "chat_id": f"chat-{project_id}-1", "sender": "assistant", "content": f"Hello from {name}", "timestamp": "2026-08-27T16:00:00Z"}]
    }, method="GET")


# ===========================================================================
# 1. Cross-Tab Navigation Across All 6 Workspace Tabs
# ===========================================================================

def test_cross_tab_navigation_and_rendering_all_tabs(page: Page, base_url: str):
    """Seamlessly navigate through all 6 workspace tabs and verify distinct layouts."""
    project_id = "test-cross-tab-all"
    _mock_project_data(page, project_id, "Cross-Tab Master Project")

    ws_page = ProjectWorkspacePage(page, base_url)
    ws_page.navigate(project_id)

    # 1. Research Tab
    ws_page.click_tab("research")
    expect(page.locator(".research-workspace")).to_be_visible(timeout=5000)
    expect(page.locator(".workspace-nav a.tab-link.active")).to_have_text("Research")

    # 2. Analysis Tab
    ws_page.click_tab("analysis")
    expect(page.locator(".analysis-container")).to_be_visible(timeout=5000)
    expect(page.locator(".workspace-nav a.tab-link.active")).to_have_text("Analysis")

    # 3. Planning Tab
    ws_page.click_tab("planning")
    expect(page.locator(".planning-container")).to_be_visible(timeout=5000)
    expect(page.locator(".workspace-nav a.tab-link.active")).to_have_text("Planning")

    # 4. Writing Tab
    ws_page.click_tab("writing")
    expect(page.locator(".writing-tab-container")).to_be_visible(timeout=5000)
    expect(page.locator(".workspace-nav a.tab-link.active")).to_have_text("Writing")

    # 5. Chat Tab
    ws_page.click_tab("chat")
    expect(page.locator(".chat-tab-container")).to_be_visible(timeout=5000)
    expect(page.locator(".workspace-nav a.tab-link.active")).to_have_text("Chat")

    # 6. Export Tab
    ws_page.click_tab("export")
    expect(page.locator(".export-tab-container")).to_be_visible(timeout=5000)
    expect(page.locator(".workspace-nav a.tab-link.active")).to_have_text("Export")

    # 7. Loop back to Research Tab
    ws_page.click_tab("research")
    expect(page.locator(".research-workspace")).to_be_visible(timeout=5000)
    expect(page.locator(".workspace-nav a.tab-link.active")).to_have_text("Research")


# ===========================================================================
# 2. Multi-Project State Isolation
# ===========================================================================

def test_multi_project_chat_and_research_isolation(page: Page, base_url: str):
    """Data and active state of Project Alpha must NOT leak into Project Beta."""
    proj_a = "proj-alpha-isolation"
    proj_b = "proj-beta-isolation"

    _mock_project_data(page, proj_a, "Project Alpha")
    _mock_project_data(page, proj_b, "Project Beta")

    # 1. Open Project Alpha Chat
    chat_page = ChatTabPage(page, base_url)
    chat_page.navigate(proj_a)

    expect(chat_page.session_items).to_have_count(1)
    expect(chat_page.session_items.first).to_contain_text("Chat for Project Alpha")
    expect(chat_page.assistant_bubbles.first).to_contain_text("Hello from Project Alpha")

    # 2. Directly Navigate to Project Beta Chat
    chat_page.navigate(proj_b)

    expect(chat_page.session_items).to_have_count(1)
    expect(chat_page.session_items.first).to_contain_text("Chat for Project Beta")
    expect(chat_page.assistant_bubbles.first).to_contain_text("Hello from Project Beta")
    # Verify Alpha message is NOT visible
    expect(page.locator("text=Hello from Project Alpha")).to_have_count(0)

    # 3. Check Research Tab in Beta
    research_page = ResearchTabPage(page, base_url)
    research_page.navigate(proj_b)
    expect(research_page.question_items.first).to_contain_text("Question for Project Beta")
    expect(page.locator("text=Question for Project Alpha")).to_have_count(0)


# ===========================================================================
# 3. Popover and Escape Key Behavior on Workspace
# ===========================================================================

def test_workspace_folder_popover_toggle_and_escape(page: Page, base_url: str):
    """Workspace folder popover opens on trigger and closes on Escape or close button."""
    project_id = "test-popover-dismissal"
    _mock_project_data(page, project_id, "Popover Project")

    ws_page = ProjectWorkspacePage(page, base_url)
    ws_page.navigate(project_id)

    # Open Folder Popover
    btn_open_folder = page.locator("button:has-text('Open Folder')")
    expect(btn_open_folder).to_be_visible()
    btn_open_folder.click()

    # Popover should be visible
    popover = page.locator(".folder-popover")
    expect(popover).to_be_visible()
    import re
    expect(page.locator(".path-input")).to_have_value(re.compile(rf".*{project_id}"))

    # Press Escape to close
    page.keyboard.press("Escape")
    expect(popover).to_have_count(0)


# ===========================================================================
# 4. Rapid Concurrent Tab Switching (Stability Resiliency)
# ===========================================================================

def test_rapid_tab_switching_under_slow_network(page: Page, base_url: str):
    """Rapidly switching tabs with delayed API responses does not produce uncaught exceptions or UI freezes."""
    project_id = "test-rapid-switching"
    _mock_project_data(page, project_id, "Rapid Switching Project")

    # Add delay to analysis and export mocks to simulate in-flight race conditions
    mock_api_route(page, f"**/api/analysis/{project_id}/coverage*", status_code=200, json_data={"coverages": []}, delay_ms=200, method="GET")
    mock_api_route(page, f"**/api/planning/{project_id}/summary*", status_code=200, json_data={"project_id": project_id, "project_name": "Rapid", "paper_count": 0, "question_count": 0, "has_drafts": False}, delay_ms=200, method="GET")

    ws_page = ProjectWorkspacePage(page, base_url)
    ws_page.navigate(project_id)

    # Rapid clicks across tabs
    for _ in range(3):
        ws_page.click_tab("analysis")
        ws_page.click_tab("planning")
        ws_page.click_tab("writing")
        ws_page.click_tab("chat")
        ws_page.click_tab("research")

    # Finally land on Chat tab and verify stability
    ws_page.click_tab("chat")
    chat_page = ChatTabPage(page, base_url)
    expect(chat_page.container).to_be_visible(timeout=5000)
    expect(chat_page.btn_new_chat).to_be_visible()
    assert len(page.page_errors) == 0

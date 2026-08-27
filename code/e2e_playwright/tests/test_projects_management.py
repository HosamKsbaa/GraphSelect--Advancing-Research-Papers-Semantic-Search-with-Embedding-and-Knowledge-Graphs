"""Comprehensive Playwright E2E tests for Projects Management (Requirement R1.1).

Covers:
- Project creation modal validation (required fields, target level master/phd, description, cancel vs submit).
- Empty states (verify empty state illustration and CTA when 0 projects exist).
- Live query search filtering (typing in search bar filters visible project cards).
- Project card navigation (clicking card navigates to /projects/:id/research).
- Archiving toggle and archive action (archiving a project soft-deletes and moves to archived section).
- Last accessed timestamp updates (touch verification).
"""
import sys
import os
import uuid
import pytest
from playwright.sync_api import Page, expect

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from e2e_playwright.conftest import mock_api_route, assert_toast_message
from e2e_playwright.pages.project_list_page import ProjectListPage
from e2e_playwright.pages.project_workspace_page import ProjectWorkspacePage


def test_project_creation_modal_validation_and_form_controls(page: Page, base_url: str):
    """Test project creation modal validation: required fields, level select, cancel vs submit."""
    project_list = ProjectListPage(page, base_url)
    project_list.navigate()

    # Open modal dialog
    project_list.open_create_dialog()
    expect(project_list.modal_container).to_be_visible()

    # Required field verification: submit button disabled when name is empty
    expect(project_list.project_name_input).to_have_value("")
    expect(project_list.submit_create_btn).to_be_disabled()

    # Whitespace only should remain disabled
    project_list.project_name_input.fill("   ")
    expect(project_list.submit_create_btn).to_be_disabled()

    # Valid name enables submit button
    project_list.project_name_input.fill("Autonomous Multi-Agent Architecture")
    expect(project_list.submit_create_btn).to_be_enabled()

    # Target level dropdown validation (master vs phd)
    expect(project_list.target_level_select).to_have_value("master")
    project_list.target_level_select.select_option("phd")
    expect(project_list.target_level_select).to_have_value("phd")
    project_list.target_level_select.select_option("master")
    expect(project_list.target_level_select).to_have_value("master")

    # Topic and Description inputs
    project_list.project_topic_input.fill("Agentic AI")
    expect(project_list.project_topic_input).to_have_value("Agentic AI")

    project_list.project_desc_input.fill("Investigation of multi-agent reasoning loops and tools.")
    expect(project_list.project_desc_input).to_have_value("Investigation of multi-agent reasoning loops and tools.")

    # Cancel button should dismiss modal without creating
    project_list.close_create_dialog()
    expect(project_list.modal_container).not_to_be_visible()

    # Re-open and verify form resets
    project_list.open_create_dialog()
    expect(project_list.project_name_input).to_have_value("")
    expect(project_list.project_topic_input).to_have_value("")
    expect(project_list.project_desc_input).to_have_value("")
    expect(project_list.submit_create_btn).to_be_disabled()

    # Close via modal-header close button
    close_btn = page.locator(".modal-header button.btn-ghost")
    close_btn.click()
    expect(project_list.modal_container).not_to_be_visible()


def test_projects_empty_state_and_cta_trigger(page: Page, base_url: str):
    """Test empty state rendering and CTA button trigger when 0 projects exist."""
    # Mock empty projects list API response
    mock_api_route(page, "**/api/projects*", status_code=200, json_data=[])

    project_list = ProjectListPage(page, base_url)
    project_list.navigate()

    # Verify empty state component is visible
    expect(project_list.empty_state).to_be_visible()
    expect(project_list.empty_state).to_contain_text("No Projects Yet")
    expect(project_list.empty_state).to_contain_text("Start by creating a new research project")

    # Verify CTA button
    expect(project_list.empty_state_cta).to_be_visible()
    expect(project_list.empty_state_cta).to_contain_text("Create Your First Project")

    # Click CTA button to open create dialog
    project_list.empty_state_cta.click()
    expect(project_list.modal_container).to_be_visible()
    expect(project_list.modal_container.locator("h2")).to_contain_text("New Project")


def test_projects_live_query_search_filtering(page: Page, base_url: str):
    """Test live search query filtering across project names, topics, and descriptions."""
    mock_projects = [
        {
            "id": "proj-master-1",
            "name": "Knowledge Graph Embeddings in Healthcare",
            "topic": "Biomedical Informatics",
            "description": "Evaluating graph neural network representations on medical ontologies.",
            "target_level": "master",
            "status": "active",
            "paper_count": 8,
            "question_count": 2,
            "created_at": "2026-08-01T10:00:00Z",
            "updated_at": "2026-08-01T10:00:00Z",
            "last_accessed_at": "2026-08-02T12:00:00Z"
        },
        {
            "id": "proj-phd-1",
            "name": "Quantum Circuit Compilation for NISQ Devices",
            "topic": "Quantum Computing",
            "description": "Optimizing pulse sequences and routing algorithms for superconducting qubits.",
            "target_level": "phd",
            "status": "active",
            "paper_count": 15,
            "question_count": 5,
            "created_at": "2026-08-05T10:00:00Z",
            "updated_at": "2026-08-05T10:00:00Z",
            "last_accessed_at": "2026-08-06T14:00:00Z"
        },
        {
            "id": "proj-phd-2",
            "name": "Reinforcement Learning for Autonomous Robotics",
            "topic": "Embodied AI",
            "description": "Policy gradient methods for quadrupeds navigating irregular terrain.",
            "target_level": "phd",
            "status": "active",
            "paper_count": 20,
            "question_count": 4,
            "created_at": "2026-08-10T10:00:00Z",
            "updated_at": "2026-08-10T10:00:00Z",
            "last_accessed_at": "2026-08-11T16:00:00Z"
        }
    ]

    mock_api_route(page, "**/api/projects*", status_code=200, json_data=mock_projects)

    project_list = ProjectListPage(page, base_url)
    project_list.navigate()

    # Initial state: 1 master project and 2 PhD projects
    expect(project_list.project_cards).to_have_count(3)
    expect(project_list.master_group).to_be_visible()
    expect(project_list.phd_group).to_be_visible()

    # Filter by name: "Quantum"
    project_list.search_projects("Quantum")
    expect(project_list.project_cards).to_have_count(1)
    expect(project_list.get_project_card("Quantum Circuit Compilation")).to_be_visible()
    expect(project_list.master_group).not_to_be_visible()
    expect(project_list.phd_group).to_be_visible()

    # Filter by topic: "Biomedical"
    project_list.search_projects("Biomedical")
    expect(project_list.project_cards).to_have_count(1)
    expect(project_list.get_project_card("Knowledge Graph Embeddings")).to_be_visible()
    expect(project_list.master_group).to_be_visible()
    expect(project_list.phd_group).not_to_be_visible()

    # Filter by description: "irregular terrain"
    project_list.search_projects("irregular terrain")
    expect(project_list.project_cards).to_have_count(1)
    expect(project_list.get_project_card("Reinforcement Learning")).to_be_visible()

    # Non-matching query: triggers empty results message
    project_list.search_projects("nonexistent_research_topic_xyz_999")
    expect(project_list.project_cards).to_have_count(0)
    expect(project_list.no_results_message).to_be_visible()
    expect(project_list.no_results_message).to_contain_text('No projects matching "nonexistent_research_topic_xyz_999"')

    # Clear query: restores all cards
    project_list.search_projects("")
    expect(project_list.project_cards).to_have_count(3)
    expect(project_list.no_results_message).not_to_be_visible()


def test_project_card_navigation_and_workspace_loading(page: Page, base_url: str):
    """Test clicking project card navigates to /projects/:id/research and loads workspace."""
    project_id = f"proj-nav-{uuid.uuid4().hex[:6]}"
    project_data = {
        "id": project_id,
        "name": "Neural Semantic Search Engine",
        "topic": "Information Retrieval",
        "description": "Dense vector retrieval coupled with graph re-ranking algorithms.",
        "target_level": "master",
        "status": "active",
        "paper_count": 4,
        "question_count": 2,
        "created_at": "2026-08-15T10:00:00Z",
        "updated_at": "2026-08-15T10:00:00Z",
        "last_accessed_at": "2026-08-15T10:00:00Z"
    }

    mock_api_route(page, "**/api/projects*", status_code=200, json_data=[project_data])
    mock_api_route(page, f"**/api/projects/{project_id}", status_code=200, json_data=project_data)
    mock_api_route(page, f"**/api/projects/{project_id}/touch", status_code=200, json_data=project_data)

    project_list = ProjectListPage(page, base_url)
    project_list.navigate()

    # Verify project card details
    card = project_list.get_project_card("Neural Semantic Search Engine")
    expect(card).to_be_visible()
    expect(card.locator(".project-name")).to_contain_text("Neural Semantic Search Engine")
    expect(card.locator(".project-topic")).to_contain_text("Information Retrieval")
    expect(card.locator(".badges .badge-success")).to_contain_text("4 Papers")
    expect(card.locator(".badges .badge-warning")).to_contain_text("2 Questions")

    # Click card to navigate to workspace
    project_list.click_project("Neural Semantic Search Engine")

    # Assert navigation to workspace route
    workspace = ProjectWorkspacePage(page, base_url)
    page.wait_for_url(f"**/projects/{project_id}**", timeout=10000)
    expect(workspace.workspace_layout).to_be_visible()
    expect(workspace.workspace_nav).to_be_visible()

    # All 5 workspace tabs are visible
    expect(workspace.tab_research).to_be_visible()
    expect(workspace.tab_analysis).to_be_visible()
    expect(workspace.tab_planning).to_be_visible()
    expect(workspace.tab_writing).to_be_visible()
    expect(workspace.tab_export).to_be_visible()

    # Default active child tab is research
    expect(page).to_have_url(f"{base_url}/projects/{project_id}/research")


def test_project_archiving_action_and_toggle_switch(page: Page, base_url: str):
    """Test soft-deleting/archiving a project and toggling the Show Archived view."""
    active_project = {
        "id": "proj-archive-101",
        "name": "Legacy Graph Traversal Framework",
        "topic": "Graph Algorithms",
        "description": "Early research on breadth-first search heuristics.",
        "target_level": "master",
        "status": "active",
        "paper_count": 2,
        "question_count": 1,
        "created_at": "2026-08-01T10:00:00Z",
        "updated_at": "2026-08-01T10:00:00Z",
        "last_accessed_at": "2026-08-01T10:00:00Z"
    }

    archived_project = dict(active_project)
    archived_project["status"] = "archived"

    projects_state = [active_project]

    def handle_projects_route(route):
        url = route.request.url
        if "include_archived=true" in url or "include_archived=True" in url:
            route.fulfill(status=200, headers={"Content-Type": "application/json"}, json=projects_state)
        else:
            active_only = [p for p in projects_state if p.get("status") != "archived"]
            route.fulfill(status=200, headers={"Content-Type": "application/json"}, json=active_only)

    page.route("**/api/projects?*", handle_projects_route)
    page.route("**/api/projects", handle_projects_route)

    def handle_archive_route(route):
        active_project["status"] = "archived"
        route.fulfill(status=200, headers={"Content-Type": "application/json"}, json=archived_project)

    page.route("**/api/projects/proj-archive-101/archive", handle_archive_route)

    project_list = ProjectListPage(page, base_url)
    project_list.navigate()

    # Initial state: active project in Master Level
    expect(project_list.get_project_card("Legacy Graph Traversal Framework")).to_be_visible()
    expect(project_list.archived_group).not_to_be_visible()

    # Accept confirmation dialog automatically
    page.on("dialog", lambda dialog: dialog.accept())

    # Archive project
    project_list.archive_project("Legacy Graph Traversal Framework")

    # Project is removed from active list (empty state rendered since 0 active projects remain)
    expect(project_list.empty_state).to_be_visible()

    # Toggle "Show Archived" checkbox
    project_list.toggle_show_archived()

    # Archived section is now rendered with archived card
    expect(project_list.archived_group).to_be_visible()
    archived_card = project_list.archived_group.locator(".project-card")
    expect(archived_card).to_contain_text("Legacy Graph Traversal Framework")
    expect(archived_card.locator(".badge")).to_contain_text("Archived")


def test_project_last_accessed_timestamp_updates(page: Page, base_url: str):
    """Test project card last accessed timestamp rendering and touch updates."""
    project_data = {
        "id": "proj-touch-202",
        "name": "Transformer Attention Mechanisms",
        "topic": "NLP",
        "description": "Multi-head attention efficiency studies.",
        "target_level": "master",
        "status": "active",
        "paper_count": 3,
        "question_count": 1,
        "created_at": "2026-08-01T10:00:00Z",
        "updated_at": "2026-08-01T10:00:00Z",
        "last_accessed_at": None
    }

    mock_api_route(page, "**/api/projects*", status_code=200, json_data=[project_data])

    project_list = ProjectListPage(page, base_url)
    project_list.navigate()

    card = project_list.get_project_card("Transformer Attention Mechanisms")
    expect(card).to_be_visible()
    # When last_accessed_at is None, displays 'Never'
    expect(card.locator(".card-actions")).to_contain_text("Last accessed: Never")

    # Update last_accessed_at to timestamp
    project_data["last_accessed_at"] = "2026-08-27T14:00:00Z"
    mock_api_route(page, "**/api/projects*", status_code=200, json_data=[project_data])
    project_list.navigate()

    card = project_list.get_project_card("Transformer Attention Mechanisms")
    expect(card).to_be_visible()
    expect(card.locator(".card-actions")).to_contain_text("Last accessed:")
    expect(card.locator(".card-actions")).not_to_contain_text("Last accessed: Never")


def test_project_creation_e2e_full_flow(page: Page, base_url: str):
    """Full E2E test creating a new genuine project and navigating to its workspace."""
    project_title = f"Playwright M2 Project {uuid.uuid4().hex[:6]}"
    project_topic = "Literature Synthesis Agents"
    project_desc = "Testing full end-to-end project creation via modal submission."

    project_list = ProjectListPage(page, base_url)
    project_list.navigate()

    # Perform full creation flow
    project_list.create_project(
        name=project_title,
        topic=project_topic,
        target_level="master",
        description=project_desc
    )

    # Verifies automatic navigation to the newly created project workspace
    page.wait_for_url("**/projects/**", timeout=10000)
    workspace = ProjectWorkspacePage(page, base_url)
    expect(workspace.workspace_layout).to_be_visible()
    expect(workspace.tab_research).to_be_visible()

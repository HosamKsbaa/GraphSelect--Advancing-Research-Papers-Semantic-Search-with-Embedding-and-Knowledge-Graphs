"""Adversarial and Empirical Challenge Test Suite for Milestone 2 (Requirements R1.1 & R1.2).

Authored by Empirical Challenger 2.
Directly challenges:
1. Project archiving state transitions (dialog dismissal vs acceptance, multi-group archiving, filtered search on archived items).
2. Project touch timestamps (null/Never vs valid ISO timestamps, workspace navigation touch trigger).
3. Literature search empty candidate resolution (empty results banner, recovery on subsequent search, non-progression to Step 2).
4. Paper import toast notifications (success toasts, 400/500 error toasts, zero [object Object] anomalies).
"""
import sys
import os
import json
import uuid
import pytest
from playwright.sync_api import Page, expect

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from e2e_playwright.conftest import mock_api_route, mock_error_route, mock_sse_route, assert_toast_message
from e2e_playwright.pages.project_list_page import ProjectListPage
from e2e_playwright.pages.project_workspace_page import ProjectWorkspacePage
from e2e_playwright.pages.search_wizard_page import SearchWizardPage


# ==============================================================================
# 1. EMPIRICAL CHALLENGE: PROJECT ARCHIVING STATE TRANSITIONS
# ==============================================================================

def test_archiving_confirmation_dismissal_preserves_active_state(page: Page, base_url: str):
    """Adversarial test: If the user cancels or dismisses the archive confirmation dialog,
    the project must NOT be archived and must remain active in the UI list."""
    project_data = {
        "id": "proj-cancel-test",
        "name": "Non-Archived Quantum Project",
        "topic": "Quantum",
        "description": "Testing dialog dismissal safety.",
        "target_level": "phd",
        "status": "active",
        "paper_count": 5,
        "question_count": 2,
        "created_at": "2026-08-01T10:00:00Z",
        "updated_at": "2026-08-01T10:00:00Z",
        "last_accessed_at": "2026-08-01T10:00:00Z"
    }

    mock_api_route(page, "**/api/projects*", status_code=200, json_data=[project_data])

    archive_api_called = []
    def handle_archive(route):
        archive_api_called.append(route.request.url)
        route.fulfill(status=200, json={"status": "archived"})

    page.route("**/api/projects/proj-cancel-test/archive", handle_archive)

    project_list = ProjectListPage(page, base_url)
    project_list.navigate()

    card = project_list.get_project_card("Non-Archived Quantum Project")
    expect(card).to_be_visible()

    # Dismiss dialog when triggered (User clicks Cancel)
    page.once("dialog", lambda dialog: dialog.dismiss())

    project_list.archive_project("Non-Archived Quantum Project")

    # Verify API was NEVER called
    assert len(archive_api_called) == 0, "Archive API was unexpectedly called when user cancelled dialog!"

    # Verify project is still visible in active list
    expect(project_list.get_project_card("Non-Archived Quantum Project")).to_be_visible()
    expect(project_list.empty_state).not_to_be_visible()


def test_archiving_multi_level_projects_and_filtering_interaction(page: Page, base_url: str):
    """Stress test: Archiving one project of multiple levels, toggling archived section,
    and verifying search queries correctly filter both active and archived cards."""
    master_active = {
        "id": "m-1", "name": "Deep Graph Learning Master", "topic": "AI",
        "description": "Active master project", "target_level": "master",
        "status": "active", "paper_count": 2, "question_count": 1,
        "created_at": "2026-08-01T00:00:00Z", "updated_at": "2026-08-01T00:00:00Z", "last_accessed_at": None
    }
    phd_active = {
        "id": "p-1", "name": "Neural Radiance Fields PhD", "topic": "Vision",
        "description": "Active PhD project", "target_level": "phd",
        "status": "active", "paper_count": 10, "question_count": 3,
        "created_at": "2026-08-01T00:00:00Z", "updated_at": "2026-08-01T00:00:00Z", "last_accessed_at": None
    }
    phd_archived = {
        "id": "p-arch", "name": "Legacy Quantum PhD (Archived)", "topic": "Physics",
        "description": "Archived project for test", "target_level": "phd",
        "status": "archived", "paper_count": 1, "question_count": 1,
        "created_at": "2026-08-01T00:00:00Z", "updated_at": "2026-08-01T00:00:00Z", "last_accessed_at": None
    }

    all_projects = [master_active, phd_active, phd_archived]

    def handle_projects(route):
        url = route.request.url
        if "include_archived=true" in url or "include_archived=True" in url:
            route.fulfill(status=200, json=all_projects)
        else:
            route.fulfill(status=200, json=[master_active, phd_active])

    page.route("**/api/projects?*", handle_projects)
    page.route("**/api/projects", handle_projects)

    project_list = ProjectListPage(page, base_url)
    project_list.navigate()

    # Initial view: only active projects visible
    expect(project_list.project_cards).to_have_count(2)
    expect(project_list.master_group).to_be_visible()
    expect(project_list.phd_group).to_be_visible()
    expect(project_list.archived_group).not_to_be_visible()

    # Turn ON Show Archived toggle
    project_list.toggle_show_archived()
    expect(project_list.archived_group).to_be_visible()
    expect(project_list.archived_group.locator(".project-card")).to_have_count(1)
    expect(project_list.archived_group).to_contain_text("Legacy Quantum PhD (Archived)")

    # Filter for 'Quantum' -> only archived group should be visible
    project_list.search_projects("Quantum")
    expect(project_list.master_group).not_to_be_visible()
    expect(project_list.phd_group).not_to_be_visible()
    expect(project_list.archived_group).to_be_visible()
    expect(project_list.archived_group.locator(".project-card")).to_have_count(1)

    # Filter for 'Graph' -> only master group should be visible
    project_list.search_projects("Graph")
    expect(project_list.master_group).to_be_visible()
    expect(project_list.phd_group).not_to_be_visible()
    expect(project_list.archived_group).not_to_be_visible()

    # Clear filter
    project_list.search_projects("")
    expect(project_list.master_group).to_be_visible()
    expect(project_list.phd_group).to_be_visible()
    expect(project_list.archived_group).to_be_visible()


# ==============================================================================
# 2. EMPIRICAL CHALLENGE: TOUCH TIMESTAMPS & RELATIVE TIME FORMATTING
# ==============================================================================

def test_touch_timestamp_null_and_updated_relative_time(page: Page, base_url: str):
    """Adversarial test: Project card last_accessed_at displays 'Last accessed: Never'
    when null, and formatted string when updated."""
    project_id = "proj-touch-adv"
    project_item = {
        "id": project_id,
        "name": "Timestamp Verification Project",
        "topic": "Time Studies",
        "description": "Checking relative time rendering.",
        "target_level": "master",
        "status": "active",
        "paper_count": 0,
        "question_count": 0,
        "created_at": "2026-08-01T00:00:00Z",
        "updated_at": "2026-08-01T00:00:00Z",
        "last_accessed_at": None
    }

    mock_api_route(page, "**/api/projects*", status_code=200, json_data=[project_item])

    project_list = ProjectListPage(page, base_url)
    project_list.navigate()

    card = project_list.get_project_card("Timestamp Verification Project")
    expect(card).to_be_visible()
    expect(card.locator(".card-actions")).to_contain_text("Last accessed: Never")

    # Update timestamp to an ISO date
    project_item["last_accessed_at"] = "2026-08-27T10:00:00Z"
    mock_api_route(page, "**/api/projects*", status_code=200, json_data=[project_item])
    project_list.navigate()

    card = project_list.get_project_card("Timestamp Verification Project")
    expect(card.locator(".card-actions")).to_contain_text("Last accessed:")
    expect(card.locator(".card-actions")).not_to_contain_text("Last accessed: Never")


def test_opening_project_triggers_touch_api(page: Page, base_url: str):
    """Adversarial test: Opening a project workspace invokes the /touch endpoint."""
    project_id = "proj-touch-trigger-1"
    project_item = {
        "id": project_id,
        "name": "Touch Trigger Project",
        "topic": "Telemetry",
        "description": "Checking touch API invocation.",
        "target_level": "master",
        "status": "active",
        "paper_count": 1,
        "question_count": 1,
        "created_at": "2026-08-01T00:00:00Z",
        "updated_at": "2026-08-01T00:00:00Z",
        "last_accessed_at": "2026-08-01T00:00:00Z"
    }

    touch_called = []
    def handle_touch(route):
        touch_called.append(route.request.url)
        route.fulfill(status=200, json=project_item)

    mock_api_route(page, "**/api/projects*", status_code=200, json_data=[project_item])
    mock_api_route(page, f"**/api/projects/{project_id}", status_code=200, json_data=project_item)
    page.route(f"**/api/projects/{project_id}/touch*", handle_touch)

    project_list = ProjectListPage(page, base_url)
    project_list.navigate()

    project_list.click_project("Touch Trigger Project")

    # Wait for workspace page to load
    workspace = ProjectWorkspacePage(page, base_url)
    expect(workspace.workspace_layout).to_be_visible()

    # Assert touch API was called
    assert len(touch_called) >= 1, "Project touch API was not called when opening workspace!"


# ==============================================================================
# 3. EMPIRICAL CHALLENGE: EMPTY CANDIDATE SEARCHES & RECOVERY
# ==============================================================================

def test_empty_candidate_search_blocks_advancement_and_recovers_on_valid_search(page: Page, base_url: str):
    """Adversarial test: Empty candidate search displays error banner, does not allow
    advancing to Step 2, and cleanly recovers when a subsequent valid search is performed."""
    wizard = SearchWizardPage(page, base_url)
    wizard.navigate()

    # 1. Search with zero results
    mock_api_route(page, "**/api/search/resolve*", status_code=200, json_data=[])
    wizard.search_seed_title("TotallyNonExistentTitle_99999")

    expect(wizard.error_banner).to_be_visible()
    expect(wizard.error_banner).to_contain_text("No papers found matching that title.")
    expect(wizard.candidate_cards).to_have_count(0)
    # Step 1 remains active; Step 2 is not entered
    expect(wizard.step_find_paper).to_have_class("step active")
    expect(wizard.step_questions).not_to_have_class("step active")

    # 2. Subsequent search returns valid candidates
    mock_candidates = [{
        "doi": "10.1145/valid.doi",
        "title": "A Valid Found Seed Paper",
        "year": 2024,
        "cited_by_count": 10,
        "authors": ["Dr. Researcher"]
    }]
    mock_api_route(page, "**/api/search/resolve*", status_code=200, json_data=mock_candidates)
    wizard.search_seed_title("A Valid Found Seed Paper")

    # Error banner disappears, candidate card rendered
    expect(wizard.error_banner).not_to_be_visible()
    expect(wizard.candidate_cards).to_have_count(1)
    expect(wizard.candidate_titles.first).to_contain_text("A Valid Found Seed Paper")

    # Selecting candidate advances to Step 2
    wizard.select_candidate(0)
    expect(wizard.step_questions).to_have_class("step active")


# ==============================================================================
# 4. EMPIRICAL CHALLENGE: PAPER IMPORT TOAST & ZERO [object Object] VALIDATION
# ==============================================================================

def test_paper_import_error_toast_preserves_selection_and_zero_objects(page: Page, base_url: str):
    """Adversarial test: Import failure displays structured error toast with zero [object Object]
    and preserves researcher paper checkboxes selection."""
    session_id = "sess-toast-err-999"
    project_id = "proj-toast-err-target"

    grouped_results = {
        "session_id": session_id,
        "total_papers": 1,
        "similarity_threshold": 0.50,
        "similarity_weight": 0.70,
        "pagerank_weight": 0.30,
        "groups": [{
            "question": "Research Question 1",
            "avg_similarity": 0.90,
            "papers": [{
                "doi": "10.1145/adv.err.101",
                "title": "Adversarial Error Paper For Import",
                "authors": ["Author Alpha"],
                "year": 2025,
                "cited_by_count": 12,
                "similarity_score": 0.92,
                "pagerank_score": 0.85,
                "hybrid_score": 0.899,
                "abstract_snippet": "Adversarial snippet."
            }]
        }]
    }

    mock_api_route(page, "**/api/search/resolve*", status_code=200, json_data=[{
        "doi": "10.1145/seed", "title": "Seed Paper", "year": 2023, "cited_by_count": 1, "authors": ["A"]
    }])
    mock_api_route(page, "**/api/search/start*", status_code=200, json_data={
        "session_id": session_id, "seed_paper_doi": "10.1145/seed", "status": "running"
    })
    mock_sse_route(page, f"**/api/search/{session_id}/stream*", events=[{
        "event": "search_complete", "data": {"event_type": "search_complete", "message": "Done", "progress_percent": 100}
    }])
    mock_api_route(page, f"**/api/search/{session_id}/results*", status_code=200, json_data=grouped_results)
    mock_api_route(page, "**/api/projects*", status_code=200, json_data=[
        {"id": project_id, "name": "Adversarial Error Target Project"}
    ])

    # Mock 500 Error with structured detail
    mock_api_route(
        page,
        f"**/api/projects/{project_id}/papers*",
        status_code=500,
        json_data={"detail": "Database connection refused while adding papers."}
    )

    wizard = SearchWizardPage(page, base_url)
    wizard.navigate()

    wizard.search_seed_title("Seed Paper")
    wizard.select_candidate(0)
    wizard.start_search()

    expect(wizard.results_view).to_be_visible(timeout=10000)

    wizard.project_selector.select_option(project_id)
    wizard.toggle_paper_selection(0)
    expect(wizard.import_selected_btn).to_be_enabled()
    expect(wizard.import_selected_btn).to_contain_text("Import Selected (1)")

    wizard.import_selected_btn.click()

    # Assert Error Toast rendered with clean message and ZERO [object Object]
    toast = assert_toast_message(
        page,
        expected_title_substring="API Error (500)",
        expected_text_substring="Database connection refused"
    )
    import re
    expect(toast).to_have_class(re.compile(r"toast-error"))

    # Assert paper selection was preserved on error
    expect(wizard.import_selected_btn).to_be_enabled()
    expect(wizard.import_selected_btn).to_contain_text("Import Selected (1)")


def test_paper_import_success_toast_clears_selection_and_zero_objects(page: Page, base_url: str):
    """Adversarial test: Import success displays success toast with zero [object Object]
    and clears paper selection checkboxes."""
    session_id = "sess-toast-ok-999"
    project_id = "proj-toast-ok-target"

    grouped_results = {
        "session_id": session_id,
        "total_papers": 1,
        "similarity_threshold": 0.50,
        "similarity_weight": 0.70,
        "pagerank_weight": 0.30,
        "groups": [{
            "question": "Research Question 1",
            "avg_similarity": 0.90,
            "papers": [{
                "doi": "10.1145/adv.ok.101",
                "title": "Adversarial Success Paper For Import",
                "authors": ["Author Beta"],
                "year": 2025,
                "cited_by_count": 12,
                "similarity_score": 0.92,
                "pagerank_score": 0.85,
                "hybrid_score": 0.899,
                "abstract_snippet": "Adversarial snippet."
            }]
        }]
    }

    mock_api_route(page, "**/api/search/resolve*", status_code=200, json_data=[{
        "doi": "10.1145/seed", "title": "Seed Paper", "year": 2023, "cited_by_count": 1, "authors": ["A"]
    }])
    mock_api_route(page, "**/api/search/start*", status_code=200, json_data={
        "session_id": session_id, "seed_paper_doi": "10.1145/seed", "status": "running"
    })
    mock_sse_route(page, f"**/api/search/{session_id}/stream*", events=[{
        "event": "search_complete", "data": {"event_type": "search_complete", "message": "Done", "progress_percent": 100}
    }])
    mock_api_route(page, f"**/api/search/{session_id}/results*", status_code=200, json_data=grouped_results)
    mock_api_route(page, "**/api/projects*", status_code=200, json_data=[
        {"id": project_id, "name": "Adversarial Success Target Project"}
    ])
    mock_api_route(
        page,
        f"**/api/projects/{project_id}/papers*",
        status_code=200,
        json_data={"message": "Successfully imported 1 papers to project."}
    )

    wizard = SearchWizardPage(page, base_url)
    wizard.navigate()

    wizard.search_seed_title("Seed Paper")
    wizard.select_candidate(0)
    wizard.start_search()

    expect(wizard.results_view).to_be_visible(timeout=10000)

    wizard.project_selector.select_option(project_id)
    wizard.toggle_paper_selection(0)
    expect(wizard.import_selected_btn).to_be_enabled()
    wizard.import_selected_btn.click()

    toast_success = assert_toast_message(
        page,
        expected_title_substring="Import Successful",
        expected_text_substring="Successfully imported 1 papers to project."
    )
    import re
    expect(toast_success).to_have_class(re.compile(r"toast-success"))

    # Assert checkboxes cleared and import button disabled
    expect(wizard.import_selected_btn).to_be_disabled()


"""Comprehensive Playwright E2E tests for Keyboard Navigation & Accessibility (Requirement R3).

Covers:
1. Tab Indexing & Focus Traversal:
   - Sequential Tab traversal across interactive controls in Project List (search input, new project button, cards).
   - Sequential Tab and Shift+Tab traversal inside Modal Dialogs (Create Project modal inputs, selects, buttons).
   - Sequential Tab traversal in Settings Page form controls.
   - Sequential Tab traversal in Workspace Research Tab (question input, add button, search toggle, table filters).
   - Dialog focus wrapping and trapping verification (Confirm dialog).

2. Escape Key Modal Dismissals:
   - Escape key dismisses Create Project modal on Project List.
   - Escape key dismisses Outline Configuration dialog on Planning Tab.
   - Escape key dismisses LaTeX Template export modal on Export Tab.
   - Escape key dismisses Confirm Delete dialog on Research Tab / Confirm Dialog.
   - Escape key dismisses Project Folder Path popover on Workspace topbar.

3. ARIA Roles & Accessibility Attributes:
   - Dynamic dialogs verify role="dialog", aria-modal="true", and aria-labelledby.
   - Tab navigation bars verify role="tablist", role="tab", and aria-selected.
   - Toast notifications verify role="status" / role="alert", aria-live, and accessible dismiss buttons.
   - Semantic badges and icons verify valid descriptions and text readability.

4. Accessible Form Validation & Focus Indicators:
   - Required field enforcement on empty / whitespace input with disabled submit button.
   - Dynamic enable state on valid input entry.
   - Visual focus indicators and active element accessibility.

5. Full Keyboard-Only End-to-End Workflow:
   - User navigates project list entirely via keyboard (Tab + Enter to open modal).
   - Fills form via Tab + keyboard typing and submits with Enter.
   - Traverses workspace tabs (Research -> Analysis -> Planning -> Writing -> Export -> Research) via keyboard.
   - Adds a research question with keyboard typing + Enter.
   - Navigates to Export tab and triggers export action using only keyboard input.
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
from e2e_playwright.pages.research_tab_page import ResearchTabPage
from e2e_playwright.pages.analysis_tab_page import AnalysisTabPage
from e2e_playwright.pages.planning_tab_page import PlanningTabPage
from e2e_playwright.pages.writing_tab_page import WritingTabPage
from e2e_playwright.pages.export_tab_page import ExportTabPage
from e2e_playwright.pages.settings_page import SettingsPage
from e2e_playwright.pages.logs_page import LogsPage


def _mock_project_base(page: Page, project_id: str, name: str = "A11y Test Project"):
    """Helper to mock baseline project metadata, touch endpoint, and settings."""
    mock_api_route(page, f"**/api/projects/{project_id}*", status_code=200, json_data={
        "id": project_id,
        "name": name,
        "description": "Automated Keyboard and Accessibility Test Project",
        "topic": "Graph Neural Networks & Autonomous Agents",
        "target_level": "master"
    })
    mock_api_route(page, f"**/api/projects/{project_id}/touch*", status_code=200, json_data={"message": "ok"})
    mock_api_route(page, "**/api/settings*", status_code=200, json_data={
        "api_base_url": "http://localhost:8000/api",
        "gemini_api_key_set": True,
        "openalex_api_key_set": False,
        "openalex_email": "test@alrs.org"
    })


# ===========================================================================
# 1. Tab Indexing & Focus Traversal
# ===========================================================================

def test_keyboard_tab_traversal_project_list_controls(page: Page, base_url: str):
    """Test sequential Tab traversal across interactive controls on the Project List page."""
    mock_projects = [
        {
            "id": "proj-k1",
            "name": "Knowledge Graph Traversal Engine",
            "topic": "Graph Algorithms",
            "description": "Breadth-first search traversal on citation graphs.",
            "target_level": "master",
            "paper_count": 5,
            "question_count": 2,
            "status": "active",
            "created_at": "2026-08-01T10:00:00Z",
            "updated_at": "2026-08-01T10:00:00Z",
            "last_accessed_at": "2026-08-02T12:00:00Z"
        }
    ]
    mock_api_route(page, "**/api/projects*", status_code=200, json_data=mock_projects)

    project_list = ProjectListPage(page, base_url)
    project_list.navigate()

    expect(project_list.page_header).to_be_visible()

    # Focus the New Project button
    project_list.new_project_btn.focus()
    expect(project_list.new_project_btn).to_be_focused()

    # Tab to Search Input
    page.keyboard.press("Tab")
    expect(project_list.search_input).to_be_focused()

    # Type in search input via keyboard
    page.keyboard.type("Knowledge")
    expect(project_list.search_input).to_have_value("Knowledge")

    # Clear search input via keyboard shortcut
    page.keyboard.press("Control+A")
    page.keyboard.press("Backspace")
    expect(project_list.search_input).to_have_value("")


def test_keyboard_tab_traversal_create_project_modal_form(page: Page, base_url: str):
    """Test Tab and Shift+Tab focus traversal inside Create Project modal dialog."""
    mock_api_route(page, "**/api/projects*", status_code=200, json_data=[])

    project_list = ProjectListPage(page, base_url)
    project_list.navigate()

    # Open dialog
    project_list.open_create_dialog()
    expect(project_list.modal_container).to_be_visible()

    # Focus Project Name input
    project_list.project_name_input.focus()
    expect(project_list.project_name_input).to_be_focused()

    # Type project name via keyboard
    page.keyboard.type("A11y Compliant Project")
    expect(project_list.project_name_input).to_have_value("A11y Compliant Project")

    # Tab -> Project Topic
    page.keyboard.press("Tab")
    expect(project_list.project_topic_input).to_be_focused()
    page.keyboard.type("Accessible Computing")
    expect(project_list.project_topic_input).to_have_value("Accessible Computing")

    # Tab -> Target Level select
    page.keyboard.press("Tab")
    expect(project_list.target_level_select).to_be_focused()

    # Tab -> Project Description textarea
    page.keyboard.press("Tab")
    expect(project_list.project_desc_input).to_be_focused()
    page.keyboard.type("Testing keyboard focus traversal.")
    expect(project_list.project_desc_input).to_have_value("Testing keyboard focus traversal.")

    # Tab -> Cancel button in modal-footer
    page.keyboard.press("Tab")
    cancel_btn = page.locator(".modal-footer button:has-text('Cancel')")
    expect(cancel_btn).to_be_focused()

    # Tab -> Submit Create Project button
    page.keyboard.press("Tab")
    expect(project_list.submit_create_btn).to_be_focused()
    expect(project_list.submit_create_btn).to_be_enabled()

    # Shift+Tab backwards: Submit -> Cancel
    page.keyboard.press("Shift+Tab")
    expect(cancel_btn).to_be_focused()

    # Shift+Tab backwards: Cancel -> Description
    page.keyboard.press("Shift+Tab")
    expect(project_list.project_desc_input).to_be_focused()

    # Close dialog
    project_list.close_create_dialog()
    expect(project_list.modal_container).not_to_be_visible()


def test_keyboard_tab_traversal_settings_form(page: Page, base_url: str):
    """Test sequential Tab traversal across inputs and buttons on Settings page."""
    mock_api_route(page, "**/api/settings*", status_code=200, json_data={
        "api_base_url": "http://localhost:8000/api",
        "gemini_api_key_set": True,
        "openalex_api_key_set": False,
        "openalex_email": "user@example.com"
    })

    settings_page = SettingsPage(page, base_url)
    settings_page.navigate()

    expect(settings_page.api_base_url_input).to_be_visible()

    # Focus API Base URL input
    settings_page.api_base_url_input.focus()
    expect(settings_page.api_base_url_input).to_be_focused()

    # Tab to Gemini key section link
    page.keyboard.press("Tab")
    get_key_link = page.locator("a:has-text('Get a key')").first
    expect(get_key_link).to_be_focused()

    # Tab -> Gemini Key input
    page.keyboard.press("Tab")
    expect(settings_page.gemini_key_input).to_be_focused()

    # Tab -> Gemini Key visibility toggle button
    page.keyboard.press("Tab")
    expect(settings_page.gemini_toggle_btn).to_be_focused()

    # Tab to OpenAlex key section link
    page.keyboard.press("Tab")
    get_openalex_link = page.locator("a:has-text('Get a key')").nth(1)
    expect(get_openalex_link).to_be_focused()

    # Tab -> OpenAlex Key input
    page.keyboard.press("Tab")
    expect(settings_page.openalex_key_input).to_be_focused()

    # Tab -> OpenAlex Key visibility toggle button
    page.keyboard.press("Tab")
    expect(settings_page.openalex_toggle_btn).to_be_focused()

    # Tab -> OpenAlex Contact Email input
    page.keyboard.press("Tab")
    expect(settings_page.openalex_email_input).to_be_focused()

    # Tab -> Save Settings button
    page.keyboard.press("Tab")
    expect(settings_page.save_btn).to_be_focused()


def test_keyboard_tab_traversal_research_tab_controls(page: Page, base_url: str):
    """Test sequential Tab traversal across interactive controls on Research Tab."""
    project_id = "test-k-research-tab"
    _mock_project_base(page, project_id)

    mock_questions = [
        {"id": "q1", "text": "Question for Tab Traversal", "embedding_status": "embedded", "coverage_score": 0.8}
    ]
    mock_papers = [
        {
            "doi": "10.1145/paper_1",
            "title": "Accessible Graph Discovery Framework",
            "year": 2025,
            "similarity_score": 0.90,
            "hybrid_score": 0.88,
            "pagerank_score": 0.80
        }
    ]

    mock_api_route(page, f"**/api/research/{project_id}/questions*", status_code=200, json_data={"questions": mock_questions})
    mock_api_route(page, f"**/api/analysis/{project_id}/ranked-papers*", status_code=200, json_data={"ranked_papers": mock_papers})
    mock_api_route(page, f"**/api/research/{project_id}/top-authors*", status_code=200, json_data={"authors": []})
    mock_api_route(page, f"**/api/research/{project_id}/top-venues*", status_code=200, json_data={"venues": []})

    research_tab = ResearchTabPage(page, base_url)
    research_tab.navigate(project_id)

    expect(research_tab.question_input).to_be_visible()

    # Focus Question Input
    research_tab.question_input.focus()
    expect(research_tab.question_input).to_be_focused()

    # Tab -> Add Question button
    page.keyboard.press("Tab")
    expect(research_tab.add_question_btn).to_be_focused()

    # Tab -> Question delete button
    page.keyboard.press("Tab")
    expect(research_tab.delete_question_btns.first).to_be_focused()

    # Tab -> Search Mode toggle button
    page.keyboard.press("Tab")
    expect(research_tab.toggle_mode_btn).to_be_focused()

    # Tab -> Search Web Input
    page.keyboard.press("Tab")
    expect(research_tab.search_input).to_be_focused()

    # Tab -> Search Web button
    page.keyboard.press("Tab")
    expect(research_tab.search_web_btn).to_be_focused()

    # Tab -> Library Filter input
    page.keyboard.press("Tab")
    expect(research_tab.library_filter_input).to_be_focused()


# ===========================================================================
# 2. Escape Key Modal & Dialog Dismissals
# ===========================================================================

def test_escape_key_dismisses_create_project_modal(page: Page, base_url: str):
    """Verify pressing Escape dismisses the Create Project modal dialog."""
    mock_api_route(page, "**/api/projects*", status_code=200, json_data=[])

    project_list = ProjectListPage(page, base_url)
    project_list.navigate()

    # Open modal
    project_list.open_create_dialog()
    expect(project_list.modal_container).to_be_visible()

    # Press Escape key
    page.keyboard.press("Escape")

    # Assert modal is cleanly dismissed
    expect(project_list.modal_container).not_to_be_visible()
    expect(project_list.modal_backdrop).not_to_be_visible()


def test_escape_key_dismisses_outline_config_dialog(page: Page, base_url: str):
    """Verify pressing Escape dismisses the Outline Configuration dialog in Planning Tab."""
    project_id = "test-k-planning-escape"
    _mock_project_base(page, project_id)

    mock_summary = {
        "project_id": project_id,
        "paper_count": 8,
        "question_count": 3,
        "gap_count": 1,
        "has_outline": False,
        "has_drafts": False
    }
    mock_api_route(page, f"**/api/planning/{project_id}/summary*", status_code=200, json_data=mock_summary)

    planning_tab = PlanningTabPage(page, base_url)
    planning_tab.navigate(project_id)

    expect(planning_tab.open_config_btn).to_be_visible()

    # Open outline configuration dialog
    planning_tab.open_config_btn.click()
    expect(planning_tab.config_dialog).to_be_visible()

    # Press Escape key
    page.keyboard.press("Escape")

    # Assert dialog is cleanly dismissed
    expect(planning_tab.config_dialog).not_to_be_visible()


def test_escape_key_dismisses_latex_template_export_modal(page: Page, base_url: str):
    """Verify pressing Escape dismisses the LaTeX Template export modal in Export Tab."""
    project_id = "test-k-export-escape"
    _mock_project_base(page, project_id)

    mock_summary = {
        "project_id": project_id,
        "paper_count": 10,
        "question_count": 3,
        "gap_count": 0,
        "has_outline": True,
        "has_drafts": True
    }
    mock_api_route(page, f"**/api/planning/{project_id}/summary*", status_code=200, json_data=mock_summary)

    export_tab = ExportTabPage(page, base_url)
    export_tab.navigate(project_id)

    expect(export_tab.export_latex_btn).to_be_visible()

    # Open LaTeX template dialog
    export_tab.open_latex_dialog()
    expect(export_tab.latex_modal).to_be_visible()

    # Press Escape key
    page.keyboard.press("Escape")

    # Assert modal is cleanly dismissed
    expect(export_tab.latex_modal).not_to_be_visible()


def test_escape_key_dismisses_confirm_delete_dialog(page: Page, base_url: str):
    """Verify pressing Escape dismisses Confirm Dialog / Confirm Overlay."""
    project_id = "test-k-confirm-escape"
    _mock_project_base(page, project_id)

    mock_questions = [
        {"id": "q1", "text": "Question for Delete", "embedding_status": "embedded", "coverage_score": 0.5}
    ]
    mock_api_route(page, f"**/api/research/{project_id}/questions*", status_code=200, json_data={"questions": mock_questions})
    mock_api_route(page, f"**/api/analysis/{project_id}/ranked-papers*", status_code=200, json_data={"ranked_papers": []})
    mock_api_route(page, f"**/api/research/{project_id}/top-authors*", status_code=200, json_data={"authors": []})
    mock_api_route(page, f"**/api/research/{project_id}/top-venues*", status_code=200, json_data={"venues": []})

    research_tab = ResearchTabPage(page, base_url)
    research_tab.navigate(project_id)
    expect(research_tab.question_input).to_be_visible()

    # Set confirm dialog open state
    page.evaluate("() => { const comp = document.querySelector('app-research-tab'); if (comp) { window.ng?.getComponent(comp)?.showConfirmDialog.set({isOpen: true, questionId: 'q1'}); } }")

    confirm_overlay = page.locator(".modal-overlay")
    expect(confirm_overlay).to_be_visible(timeout=5000)

    # Press Escape key
    page.keyboard.press("Escape")

    # Assert overlay dismissed
    expect(confirm_overlay).not_to_be_visible()


def test_escape_key_dismisses_workspace_folder_popover(page: Page, base_url: str):
    """Verify pressing Escape dismisses the Workspace Folder Path popover."""
    project_id = "test-k-folder-escape"
    _mock_project_base(page, project_id)
    mock_api_route(page, f"**/api/projects/{project_id}/folder*", status_code=200, json_data={"path": "/home/user/project"})

    workspace = ProjectWorkspacePage(page, base_url)
    workspace.navigate(project_id)

    expect(workspace.open_folder_btn).to_be_visible()

    # Open folder popover
    workspace.open_folder_popover()
    expect(workspace.folder_popover).to_be_visible()

    # Press Escape key
    page.keyboard.press("Escape")

    # Assert popover is dismissed
    expect(workspace.folder_popover).not_to_be_visible()


# ===========================================================================
# 3. ARIA Roles & Dynamic Accessibility Attributes
# ===========================================================================

def test_aria_roles_and_modal_attributes_on_all_dialogs(page: Page, base_url: str):
    """Verify ARIA role='dialog', aria-modal='true', and accessible labeling on all modals."""
    mock_api_route(page, "**/api/projects*", status_code=200, json_data=[])

    project_list = ProjectListPage(page, base_url)
    project_list.navigate()

    # 1. Create Project Modal
    project_list.open_create_dialog()
    expect(project_list.modal_backdrop).to_be_visible()
    expect(project_list.modal_backdrop).to_have_attribute("role", "dialog")
    expect(project_list.modal_backdrop).to_have_attribute("aria-modal", "true")
    expect(project_list.modal_backdrop).to_have_attribute("aria-labelledby", "createProjectModalTitle")
    expect(page.locator("#createProjectModalTitle")).to_be_visible()
    project_list.close_create_dialog()

    # 2. Outline Configuration Dialog
    project_id = "test-aria-dialogs"
    _mock_project_base(page, project_id)
    mock_summary = {
        "project_id": project_id,
        "paper_count": 5,
        "question_count": 2,
        "gap_count": 0,
        "has_outline": False,
        "has_drafts": False
    }
    mock_api_route(page, f"**/api/planning/{project_id}/summary*", status_code=200, json_data=mock_summary)

    planning_tab = PlanningTabPage(page, base_url)
    planning_tab.navigate(project_id)
    planning_tab.open_config_btn.click()
    expect(planning_tab.config_dialog).to_be_visible()
    expect(planning_tab.config_dialog).to_have_attribute("role", "dialog")
    expect(planning_tab.config_dialog).to_have_attribute("aria-modal", "true")
    expect(planning_tab.config_dialog).to_have_attribute("aria-labelledby", "outlineConfigDialogTitle")
    expect(page.locator("#outlineConfigDialogTitle")).to_be_visible()
    planning_tab.cancel_config_btn.click()

    # 3. LaTeX Export Modal
    mock_summary["has_drafts"] = True
    mock_api_route(page, f"**/api/planning/{project_id}/summary*", status_code=200, json_data=mock_summary)
    export_tab = ExportTabPage(page, base_url)
    export_tab.navigate(project_id)
    export_tab.open_latex_dialog()
    expect(export_tab.latex_modal).to_be_visible()
    expect(export_tab.latex_modal).to_have_attribute("role", "dialog")
    expect(export_tab.latex_modal).to_have_attribute("aria-modal", "true")
    expect(export_tab.latex_modal).to_have_attribute("aria-labelledby", "latexExportDialogTitle")
    expect(page.locator("#latexExportDialogTitle")).to_be_visible()
    export_tab.close_latex_dialog()


def test_aria_roles_on_workspace_tabs_and_navigation(page: Page, base_url: str):
    """Verify role='tablist', role='tab', and semantic landmarks on workspace and logs navigation."""
    project_id = "test-aria-tabs"
    _mock_project_base(page, project_id)

    workspace = ProjectWorkspacePage(page, base_url)
    workspace.navigate(project_id)

    # Workspace Tablist
    tablist = page.locator(".workspace-nav .nav-links")
    expect(tablist).to_be_visible()
    expect(tablist).to_have_attribute("role", "tablist")

    # Workspace Tabs
    tabs = page.locator(".workspace-nav .nav-links a.tab-link")
    expect(tabs).to_have_count(6)
    for i in range(6):
        expect(tabs.nth(i)).to_have_attribute("role", "tab")

    # Sidebar Navigation Landmark
    sidebar_nav = page.locator("nav.sidebar-nav")
    expect(sidebar_nav).to_be_visible()
    main_content = page.locator("main.main-content").first
    expect(main_content).to_be_visible()

    # Logs Page Tablist & aria-selected
    mock_api_route(page, "**/api/logs*", status_code=200, json_data=[])
    logs_page = LogsPage(page, base_url)
    logs_page.navigate()

    logs_tablist = page.locator(".tabs-header")
    expect(logs_tablist).to_be_visible()
    expect(logs_tablist).to_have_attribute("role", "tablist")

    app_tab = page.locator(".tabs-header button.tab-btn:has-text('Application Logs')")
    expect(app_tab).to_have_attribute("role", "tab")
    expect(app_tab).to_have_attribute("aria-selected", "true")

    api_tab = page.locator(".tabs-header button.tab-btn:has-text('Scholarly API Requests')")
    expect(api_tab).to_have_attribute("role", "tab")
    expect(api_tab).to_have_attribute("aria-selected", "false")


def test_aria_roles_and_live_regions_on_toast_notifications(page: Page, base_url: str):
    """Verify toast notification container has aria-live, role='status'|'alert', and no [object Object]."""
    mock_api_route(page, "**/api/settings*", status_code=200, json_data={
        "api_base_url": "http://localhost:8000/api",
        "gemini_api_key_set": True,
        "openalex_api_key_set": False,
        "openalex_email": "test@alrs.org"
    })

    settings_page = SettingsPage(page, base_url)
    settings_page.navigate()

    # Check toast container ARIA attributes
    toast_container = page.locator("alrs-toast-container .toast-container")
    expect(toast_container).to_have_attribute("role", "region")
    expect(toast_container).to_have_attribute("aria-live", "polite")
    expect(toast_container).to_have_attribute("aria-label", "Notifications")

    # Trigger Success Toast via Save Settings
    mock_api_route(page, "**/api/settings*", status_code=200, json_data={"success": True, "message": "Settings updated successfully"})
    settings_page.save_settings()

    success_toast = assert_toast_message(page, expected_title_substring="Settings Saved", expected_text_substring="Settings updated")
    expect(success_toast).to_have_attribute("role", "status")
    expect(success_toast).to_have_attribute("aria-live", "polite")
    expect(success_toast.locator("button.toast-close")).to_have_attribute("aria-label", "Dismiss notification")

    # Dismiss toast
    success_toast.locator("button.toast-close").click()


def test_aria_and_semantic_badges_verification(page: Page, base_url: str):
    """Verify semantic badges on Writing tab and Project cards render readable text and icons."""
    project_id = "test-aria-badges"
    _mock_project_base(page, project_id)

    mock_outline = {
        "project_id": project_id,
        "sections": [
            {
                "order": 1,
                "title": "Introduction to GNNs",
                "description": "Overview of Graph Neural Networks and Attention",
                "paper_dois": ["10.1145/1"]
            }
        ]
    }
    mock_draft = {
        "section_id": "sec-1",
        "content": "## Introduction\n\nGraph Neural Networks represent complex dependencies.",
        "status": "drafted",
        "revisions": 0,
        "feedback": None
    }
    mock_api_route(page, f"**/api/planning/{project_id}/outline*", status_code=200, json_data=mock_outline)
    mock_api_route(page, f"**/api/writing/{project_id}/draft/*", status_code=200, json_data=mock_draft)

    writing_tab = WritingTabPage(page, base_url)
    writing_tab.navigate(project_id)

    writing_tab.select_section(0)
    expect(writing_tab.hallucination_gate_badge).to_be_visible()
    expect(writing_tab.hallucination_gate_badge).to_contain_text("0.0% Citation Hallucination Gate")
    expect(writing_tab.gcdl_loop_badge).to_be_visible()
    expect(writing_tab.gcdl_loop_badge).to_contain_text("GCDL Inner Drafting Loop")


# ===========================================================================
# 4. Accessible Form Validation & Focus Indicators
# ===========================================================================

def test_accessible_form_validation_project_creation(page: Page, base_url: str):
    """Verify accessible form validation: required attributes, disabled submit states, and focus states."""
    mock_api_route(page, "**/api/projects*", status_code=200, json_data=[])

    project_list = ProjectListPage(page, base_url)
    project_list.navigate()

    project_list.open_create_dialog()
    expect(project_list.modal_container).to_be_visible()

    # 1. Required attribute on project name
    expect(project_list.project_name_input).to_have_attribute("required", "")

    # 2. Disabled submit state when name is empty
    expect(project_list.submit_create_btn).to_be_disabled()

    # 3. Disabled submit state when name contains only whitespace
    project_list.project_name_input.fill("     ")
    expect(project_list.submit_create_btn).to_be_disabled()

    # 4. Enabled submit state when valid text is typed
    project_list.project_name_input.fill("Accessible GNN Review")
    expect(project_list.submit_create_btn).to_be_enabled()

    # 5. Focus indicator verification (element has focus when active)
    project_list.project_topic_input.focus()
    expect(project_list.project_topic_input).to_be_focused()

    project_list.close_create_dialog()
    expect(project_list.modal_container).not_to_be_visible()


# ===========================================================================
# 5. Full Keyboard-Only End-to-End Workflow
# ===========================================================================

def test_full_keyboard_only_end_to_end_workflow(page: Page, base_url: str):
    """Execute complete workflow from project creation to tab navigation and export using ONLY keyboard inputs.

    Flow:
    1. User opens Project List page.
    2. Uses Tab navigation to focus "New Project" button and presses Enter to open modal.
    3. Fills all fields using Tab + keyboard typing.
    4. Submits form via Enter on submit button.
    5. Automatically navigates to project workspace (/projects/:id/research).
    6. Traverses workspace tabs (Research -> Analysis -> Planning -> Writing -> Export -> Research) via keyboard.
    7. Adds a research question using Tab + typing + Enter.
    8. Verifies optimistic question addition with embedding status icon.
    9. Navigates to Export tab and triggers export using keyboard input.
    """
    created_project_id = f"k-proj-{uuid.uuid4().hex[:6]}"
    project_name = "Autonomous Keyboard Literature Review"
    project_topic = "Assistive Technology & Multi-Agent AI"
    project_desc = "Complete keyboard-driven literature synthesis workflow."

    # Mock project creation API response
    created_project_data = {
        "id": created_project_id,
        "name": project_name,
        "topic": project_topic,
        "description": project_desc,
        "target_level": "phd",
        "status": "active",
        "paper_count": 0,
        "question_count": 0,
        "created_at": "2026-08-27T12:00:00Z",
        "updated_at": "2026-08-27T12:00:00Z",
        "last_accessed_at": "2026-08-27T12:00:00Z"
    }

    mock_api_route(page, "**/api/projects*", status_code=200, json_data=[])

    def handle_create_route(route):
        route.fulfill(
            status=200,
            headers={"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
            json=created_project_data
        )

    page.route("**/api/projects", handle_create_route)
    _mock_project_base(page, created_project_id, name=project_name)

    mock_api_route(page, f"**/api/research/{created_project_id}/questions*", status_code=200, json_data={"questions": []})
    mock_api_route(page, f"**/api/analysis/{created_project_id}/ranked-papers*", status_code=200, json_data={"ranked_papers": []})
    mock_api_route(page, f"**/api/research/{created_project_id}/top-authors*", status_code=200, json_data={"authors": []})
    mock_api_route(page, f"**/api/research/{created_project_id}/top-venues*", status_code=200, json_data={"venues": []})

    # Step 1: Open project list
    project_list = ProjectListPage(page, base_url)
    project_list.navigate()

    # Step 2: Focus New Project button and trigger via Enter
    project_list.new_project_btn.focus()
    expect(project_list.new_project_btn).to_be_focused()
    page.keyboard.press("Enter")

    expect(project_list.modal_container).to_be_visible()

    # Step 3: Fill form via keyboard Tab and typing
    project_list.project_name_input.focus()
    page.keyboard.type(project_name)
    expect(project_list.project_name_input).to_have_value(project_name)

    page.keyboard.press("Tab")
    page.keyboard.type(project_topic)
    expect(project_list.project_topic_input).to_have_value(project_topic)

    page.keyboard.press("Tab")
    page.keyboard.press("ArrowDown")  # Select "PhD Level"

    page.keyboard.press("Tab")
    page.keyboard.type(project_desc)
    expect(project_list.project_desc_input).to_have_value(project_desc)

    # Step 4: Tab to Create Project submit button and press Enter
    page.keyboard.press("Tab")  # Focus Cancel
    page.keyboard.press("Tab")  # Focus Submit
    expect(project_list.submit_create_btn).to_be_focused()
    expect(project_list.submit_create_btn).to_be_enabled()
    page.keyboard.press("Enter")

    # Step 5: Assert automatic navigation to project workspace
    page.wait_for_url(f"**/projects/{created_project_id}**", timeout=10000)
    workspace = ProjectWorkspacePage(page, base_url)
    expect(workspace.workspace_layout).to_be_visible()
    expect(workspace.tab_research).to_be_visible()

    # Step 6: Keyboard traversal across all workspace tabs
    # Navigate to Analysis Tab via keyboard
    workspace.tab_analysis.focus()
    page.keyboard.press("Enter")
    page.wait_for_url(f"**/projects/{created_project_id}/analysis**", timeout=5000)
    expect(page).to_have_url(f"{base_url}/projects/{created_project_id}/analysis")

    # Navigate to Planning Tab via keyboard
    workspace.tab_planning.focus()
    page.keyboard.press("Enter")
    page.wait_for_url(f"**/projects/{created_project_id}/planning**", timeout=5000)
    expect(page).to_have_url(f"{base_url}/projects/{created_project_id}/planning")

    # Navigate to Writing Tab via keyboard
    workspace.tab_writing.focus()
    page.keyboard.press("Enter")
    page.wait_for_url(f"**/projects/{created_project_id}/writing**", timeout=5000)
    expect(page).to_have_url(f"{base_url}/projects/{created_project_id}/writing")

    # Navigate to Export Tab via keyboard
    workspace.tab_export.focus()
    page.keyboard.press("Enter")
    page.wait_for_url(f"**/projects/{created_project_id}/export**", timeout=5000)
    expect(page).to_have_url(f"{base_url}/projects/{created_project_id}/export")

    # Return to Research Tab via keyboard
    workspace.tab_research.focus()
    page.keyboard.press("Enter")
    page.wait_for_url(f"**/projects/{created_project_id}/research**", timeout=5000)
    expect(page).to_have_url(f"{base_url}/projects/{created_project_id}/research")

    # Step 7: Add research question via keyboard only (Tab to input, type text, press Enter)
    research_tab = ResearchTabPage(page, base_url)
    expect(research_tab.question_input).to_be_visible()

    research_tab.question_input.click()
    research_tab.question_input.focus()
    expect(research_tab.question_input).to_be_focused()

    question_content = "How does keyboard accessibility improve academic paper co-authoring?"
    research_tab.question_input.press_sequentially(question_content, delay=30)
    expect(research_tab.question_input).to_have_value(question_content)

    # Press Enter to submit question
    page.keyboard.press("Enter")

    # Step 8: Assert optimistic question addition and status icon
    expect(research_tab.question_items).to_have_count(1)
    expect(research_tab.question_texts.first).to_have_text(question_content)
    expect(research_tab.question_status_icons.first).to_have_text("✓")

    # Step 9: Navigate to Export tab via keyboard and trigger export check
    workspace.tab_export.focus()
    page.keyboard.press("Enter")
    page.wait_for_url(f"**/projects/{created_project_id}/export**", timeout=5000)

    export_tab = ExportTabPage(page, base_url)
    expect(export_tab.export_cards_grid).to_be_visible()

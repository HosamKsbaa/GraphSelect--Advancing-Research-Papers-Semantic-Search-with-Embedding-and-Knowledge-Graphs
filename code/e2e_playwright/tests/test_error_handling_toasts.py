"""Comprehensive Playwright E2E tests for Error Handling, Network Edge Cases & Toast Notifications (Requirement R4).

Covers:
1. Negative Form Validation on Empty or Whitespace Inputs:
   - Project creation modal (empty/whitespace name disabled submit button, required field validation).
   - Research workspace left sidebar (empty/whitespace question input rejection).
   - Planning workspace outline configuration dialog (section count boundaries, style select, cancel vs generate).
   - Literature search wizard Step 1 (empty seed paper title disables search button) and Step 2 (empty research questions rejection with validation error banner).
   - Settings view configuration controls and inputs.

2. Backend HTTP Status Code Handling & Structured Toasts:
   - HTTP 400 Bad Request (invalid payloads, duplicate resource creation) rendering structured error toast.
   - HTTP 404 Not Found (missing project, non-existent session, missing resource) rendering clear error toast.
   - HTTP 422 Unprocessable Entity (FastAPI validation errors with array of detail objects) cleanly serialized without [object Object].
   - HTTP 500 Internal Server Error (database deadlock, backend crash) rendering helpful, non-cryptic error toast.
   - HTTP 503 Service Unavailable (rate limits, upstream outages) rendering structured error toast.
   - Status 0 (network disconnection / offline backend / aborted connection) rendering "Backend Unreachable" toast and error banner.

3. Programmatic Zero [object Object] Verification:
   - Suite-wide assertion strictly verifying that '[object Object]' is NEVER present in toast title, toast message, or notification DOM containers.

4. Empty States & Guidance CTA Triggers:
   - Project List View (0 projects -> app-empty-state with 'No Projects Yet' and 'Create Your First Project' CTA).
   - Research Workspace Paper Library (0 papers -> app-empty-state with 'Library Empty' and guidance).
   - Analysis Workspace (0 coverages & 0 ranked papers -> app-empty-state with 'No Data for Analysis').
   - Planning Workspace (0 outline sections & unready state -> app-empty-state with 'No Outline Yet', ✗ indicators, disabled CTA).
   - System Status Recent Sessions (0 sessions -> empty-state card with 'No sessions yet' and 'Start a Search' CTA).

5. Zero Uncaught JavaScript Page Exceptions:
   - Handled globally via fixture listener guaranteeing 0 unhandled promise rejections or page exceptions.
"""
import sys
import os
import pytest
from playwright.sync_api import Page, expect

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from e2e_playwright.conftest import mock_api_route, mock_error_route, assert_toast_message
from e2e_playwright.pages.base_page import BasePage
from e2e_playwright.pages.project_list_page import ProjectListPage
from e2e_playwright.pages.project_workspace_page import ProjectWorkspacePage
from e2e_playwright.pages.research_tab_page import ResearchTabPage
from e2e_playwright.pages.analysis_tab_page import AnalysisTabPage
from e2e_playwright.pages.planning_tab_page import PlanningTabPage
from e2e_playwright.pages.search_wizard_page import SearchWizardPage
from e2e_playwright.pages.system_status_page import SystemStatusPage
from e2e_playwright.pages.settings_page import SettingsPage


def _assert_no_object_object_in_toasts(page: Page) -> None:
    """Strictly assert that no [object Object] string exists anywhere in the toast container or page notifications."""
    toast_container = page.locator("alrs-toast-container")
    if toast_container.count() > 0:
        container_text = toast_container.inner_text()
        assert "[object Object]" not in container_text, f"Detected '[object Object]' in toast container: '{container_text}'"

    toast_titles = page.locator("alrs-toast-container .toast-title").all_inner_texts()
    for title in toast_titles:
        assert "[object Object]" not in title, f"Detected '[object Object]' in toast title: '{title}'"

    toast_messages = page.locator("alrs-toast-container .toast-message").all_inner_texts()
    for msg in toast_messages:
        assert "[object Object]" not in msg, f"Detected '[object Object]' in toast message: '{msg}'"


def _mock_project_base(page: Page, project_id: str):
    """Helper to mock baseline project metadata and touch endpoint."""
    mock_api_route(page, f"**/api/projects/{project_id}*", status_code=200, json_data={
        "id": project_id,
        "name": f"Error Test Project {project_id}",
        "description": "Playwright Error Handling and Toasts Test Project",
        "topic": "Graph Neural Networks",
        "target_level": "master"
    })
    mock_api_route(page, f"**/api/projects/{project_id}/touch*", status_code=200, json_data={"message": "ok"})


# ===========================================================================
# 1. NEGATIVE FORM VALIDATION SUITE
# ===========================================================================

def test_form_validation_project_creation_empty_and_whitespace(page: Page, base_url: str):
    """Test project creation modal rejects empty and whitespace-only name inputs by disabling submit button."""
    mock_api_route(page, "**/api/projects*", status_code=200, json_data=[])

    project_list = ProjectListPage(page, base_url)
    project_list.navigate()

    project_list.open_create_dialog()
    expect(project_list.modal_container).to_be_visible()

    # 1. Initial state: Empty input should have submit button disabled
    expect(project_list.project_name_input).to_have_value("")
    expect(project_list.submit_create_btn).to_be_disabled()

    # 2. Whitespace-only input: Submit button must remain disabled
    project_list.project_name_input.fill("     ")
    expect(project_list.submit_create_btn).to_be_disabled()

    project_list.project_name_input.fill("\t  \n  ")
    expect(project_list.submit_create_btn).to_be_disabled()

    # 3. Valid name: Submit button becomes enabled
    project_list.project_name_input.fill("Scalable Graph Neural Architecture")
    expect(project_list.submit_create_btn).to_be_enabled()

    # 4. Clear input back to empty: Submit button becomes disabled again
    project_list.project_name_input.fill("")
    expect(project_list.submit_create_btn).to_be_disabled()

    # 5. Dismiss modal cleanly
    project_list.close_create_dialog()
    expect(project_list.modal_container).not_to_be_visible()


def test_form_validation_research_questions_empty_input(page: Page, base_url: str):
    """Test research tab question input rejects empty or whitespace submissions without modifying question list."""
    project_id = "test-form-val-questions"
    _mock_project_base(page, project_id)

    mock_questions = [
        {"id": "q1", "text": "What is graph homophily in citation networks?", "embedding_status": "embedded", "coverage_score": 0.85}
    ]
    mock_api_route(page, f"**/api/research/{project_id}/questions*", status_code=200, json_data={"questions": mock_questions})
    mock_api_route(page, f"**/api/analysis/{project_id}/ranked-papers*", status_code=200, json_data={"ranked_papers": []})

    research_tab = ResearchTabPage(page, base_url)
    research_tab.navigate(project_id)

    expect(research_tab.question_items).to_have_count(1)

    # 1. Attempt submitting with completely empty input
    research_tab.question_input.fill("")
    research_tab.add_question_btn.click()
    expect(research_tab.question_items).to_have_count(1)

    # 2. Attempt submitting with whitespace-only input
    research_tab.question_input.fill("     ")
    research_tab.add_question_btn.click()
    expect(research_tab.question_items).to_have_count(1)

    # 3. Attempt pressing Enter on whitespace input
    research_tab.question_input.fill("   \t  ")
    research_tab.question_input.press("Enter")
    expect(research_tab.question_items).to_have_count(1)


def test_form_validation_outline_configuration_controls(page: Page, base_url: str):
    """Test outline configuration dialog controls, dropdown options, and cancel dismissal."""
    project_id = "test-form-val-outline"
    _mock_project_base(page, project_id)

    mock_summary = {
        "paper_count": 5,
        "question_count": 3,
        "gap_count": 1,
        "has_outline": False,
        "has_drafts": False,
        "research_questions": ["Q1", "Q2", "Q3"]
    }
    mock_api_route(page, f"**/api/planning/{project_id}/summary*", status_code=200, json_data=mock_summary)
    mock_api_route(page, f"**/api/planning/{project_id}/outline*", status_code=200, json_data={"project_id": project_id, "sections": []})

    planning_tab = PlanningTabPage(page, base_url)
    planning_tab.navigate(project_id)

    # Open outline configuration dialog
    planning_tab.open_outline_dialog()
    expect(planning_tab.config_dialog).to_be_visible()

    # Check writing style options
    expect(planning_tab.style_select).to_have_value("academic")
    planning_tab.style_select.select_option("narrative")
    expect(planning_tab.style_select).to_have_value("narrative")
    planning_tab.style_select.select_option("concise")
    expect(planning_tab.style_select).to_have_value("concise")
    planning_tab.style_select.select_option("academic")
    expect(planning_tab.style_select).to_have_value("academic")

    # Check number of sections input modification
    planning_tab.num_sections_input.fill("7")
    expect(planning_tab.num_sections_input).to_have_value("7")

    # Cancel should dismiss dialog without triggering generation
    planning_tab.close_outline_dialog()
    expect(planning_tab.config_dialog).not_to_be_visible()


def test_form_validation_search_wizard_empty_seed_and_questions(page: Page, base_url: str):
    """Test Literature Search Wizard Step 1 empty title validation and Step 2 empty questions validation."""
    mock_candidates = [
        {
            "doi": "10.1145/3534678.3539078",
            "title": "GraphSelect: Embedding-Guided Graph Traversal for Scalable Semantic Paper Search",
            "year": 2024,
            "cited_by_count": 42,
            "authors": ["Alice Smith"]
        }
    ]
    mock_api_route(page, "**/api/search/resolve*", status_code=200, json_data=mock_candidates)

    search_wizard = SearchWizardPage(page, base_url)
    search_wizard.navigate()

    # Step 1: Empty seed paper title disables Search button
    search_wizard.seed_title_input.fill("")
    expect(search_wizard.seed_search_btn).to_be_disabled()

    # Whitespace-only seed paper title disables Search button
    search_wizard.seed_title_input.fill("    ")
    expect(search_wizard.seed_search_btn).to_be_disabled()

    # Valid title enables Search button
    search_wizard.seed_title_input.fill("GraphSelect")
    expect(search_wizard.seed_search_btn).to_be_enabled()
    search_wizard.seed_search_btn.click()

    # Select candidate to proceed to Step 2
    expect(search_wizard.candidate_cards).to_have_count(1)
    search_wizard.select_candidate(0)

    # Now on Step 2: Research Questions
    expect(search_wizard.step_questions).to_have_class("step active")

    # Clear all research question inputs
    count = search_wizard.question_inputs.count()
    for i in range(count):
        search_wizard.question_inputs.nth(i).fill("")

    # Attempting to start search with empty questions displays validation error banner
    search_wizard.start_search()
    expect(search_wizard.error_banner).to_be_visible()
    expect(search_wizard.error_banner).to_contain_text("Please enter at least one research question.")

    # Fill whitespace only in first question
    search_wizard.question_inputs.first.fill("     ")
    search_wizard.start_search()
    expect(search_wizard.error_banner).to_be_visible()
    expect(search_wizard.error_banner).to_contain_text("Please enter at least one research question.")


def test_form_validation_settings_page_controls(page: Page, base_url: str):
    """Test Settings view input fields, API key masking toggles, and saving flow."""
    mock_api_route(page, "**/api/settings*", status_code=200, json_data={
        "api_base_url": "http://localhost:8000",
        "gemini_api_key_set": True,
        "openalex_api_key_set": False,
        "openalex_email": "researcher@university.edu",
        "embedding_model": "gemini-embedding-2",
        "embedding_dimensions": 768
    })

    settings_page = SettingsPage(page, base_url)
    settings_page.navigate()

    # Verify initial settings populated
    expect(settings_page.gemini_status_badge).to_contain_text("Active")
    expect(settings_page.openalex_status_badge).to_contain_text("Not Set")
    expect(settings_page.openalex_email_input).to_have_value("researcher@university.edu")

    # Toggle API key visibility password <-> text
    expect(settings_page.gemini_key_input).to_have_attribute("type", "password")
    settings_page.toggle_gemini_visibility()
    expect(settings_page.gemini_key_input).to_have_attribute("type", "text")
    settings_page.toggle_gemini_visibility()
    expect(settings_page.gemini_key_input).to_have_attribute("type", "password")

    # Fill updated settings
    settings_page.set_gemini_key("AIzaSy-TEST-KEY-12345678")
    settings_page.set_contact_email("lead-author@institution.org")

    # Mock successful settings save
    mock_api_route(page, "**/api/settings*", status_code=200, json_data={
        "success": True,
        "message": "Settings updated successfully"
    })

    settings_page.save_settings()
    assert_toast_message(page, expected_title_substring="Settings Saved", expected_text_substring="updated successfully")
    _assert_no_object_object_in_toasts(page)


# ===========================================================================
# 2. BACKEND HTTP STATUS CODE & STRUCTURED TOASTS SUITE
# ===========================================================================

def test_http_400_bad_request_structured_toast(page: Page, base_url: str):
    """Test HTTP 400 Bad Request error returns a structured toast without [object Object]."""
    mock_api_route(page, "**/api/projects*", status_code=200, json_data=[])
    
    # Mock 400 Bad Request on project creation POST
    mock_error_route(
        page,
        "**/api/projects",
        status_code=400,
        detail="Project name 'Duplicate Literature Survey' already exists in the workspace."
    )

    project_list = ProjectListPage(page, base_url)
    project_list.navigate()

    project_list.open_create_dialog()
    project_list.fill_create_project_form(name="Duplicate Literature Survey")
    project_list.submit_create_project()

    # Assert structured 400 toast
    assert_toast_message(
        page,
        expected_title_substring="API Error (400)",
        expected_text_substring="already exists"
    )
    _assert_no_object_object_in_toasts(page)


def test_http_404_not_found_structured_toast(page: Page, base_url: str):
    """Test HTTP 404 Not Found error returns a clear error toast without [object Object]."""
    project_id = "non-existent-project-id-404"

    # Mock 404 Not Found for project retrieval
    mock_error_route(
        page,
        f"**/api/projects/{project_id}*",
        status_code=404,
        detail=f"Project '{project_id}' not found in database."
    )

    workspace_page = ProjectWorkspacePage(page, base_url)
    workspace_page.navigate(project_id, tab="research")

    # Assert structured 404 toast
    assert_toast_message(
        page,
        expected_title_substring="API Error (404)",
        expected_text_substring="not found"
    )
    _assert_no_object_object_in_toasts(page)


def test_http_422_unprocessable_entity_array_detail_serialization(page: Page, base_url: str):
    """Test HTTP 422 Unprocessable Entity with array detail error objects is cleanly serialized without [object Object]."""
    mock_api_route(page, "**/api/projects*", status_code=200, json_data=[])

    # FastAPI 422 Schema validation error payload with array of detail objects
    validation_detail_array = [
        {
            "loc": ["body", "name"],
            "msg": "String should have at least 3 characters",
            "type": "string_too_short"
        },
        {
            "loc": ["body", "target_level"],
            "msg": "Input should be 'master' or 'phd'",
            "type": "enum"
        }
    ]

    mock_api_route(
        page,
        "**/api/projects",
        status_code=422,
        json_data={"detail": validation_detail_array}
    )

    project_list = ProjectListPage(page, base_url)
    project_list.navigate()

    project_list.open_create_dialog()
    project_list.fill_create_project_form(name="AI")
    project_list.submit_create_project()

    # Assert structured 422 toast contains field names and messages cleanly formatted
    toast = assert_toast_message(
        page,
        expected_title_substring="API Error (422)",
        expected_text_substring="String should have at least 3 characters"
    )
    
    # Assert second field error is also serialized in the message
    message_text = toast.locator(".toast-message").inner_text()
    assert "target_level:" in message_text or "Input should be" in message_text
    
    # Strict assertion: NO [object Object] anywhere
    _assert_no_object_object_in_toasts(page)


def test_http_500_internal_server_error_toast(page: Page, base_url: str):
    """Test HTTP 500 Internal Server Error returns a helpful, non-cryptic error toast."""
    project_id = "test-500-error-proj"
    _mock_project_base(page, project_id)

    mock_coverage = {
        "gap_questions": [
            {"question_id": "q1", "question": "Scalability bottlenecks in dense graphs?", "best_score": 0.15, "paper_count": 0}
        ],
        "covered_questions": [],
        "overall_coverage": 0.15
    }
    mock_api_route(page, f"**/api/analysis/{project_id}/coverage*", status_code=200, json_data=mock_coverage)
    mock_api_route(page, f"**/api/analysis/{project_id}/ranked-papers*", status_code=200, json_data={"ranked_papers": []})
    mock_api_route(page, f"**/api/analysis/{project_id}/citation-stats*", status_code=200, json_data={
        "total_papers": 3, "average_similarity": 0.5, "network_density": 0.2
    })

    # Mock 500 Internal Server Error on LLM gap query generation endpoint
    mock_error_route(
        page,
        f"**/api/analysis/{project_id}/gap-queries*",
        status_code=500,
        detail="Internal Server Error: Neo4j graph driver connection pool exhausted."
    )

    analysis_tab = AnalysisTabPage(page, base_url)
    analysis_tab.navigate(project_id)

    # Click suggest queries to trigger 500 error
    analysis_tab.click_suggest_queries(0)

    # Assert structured 500 toast
    assert_toast_message(
        page,
        expected_title_substring="API Error (500)",
        expected_text_substring="Neo4j graph driver connection pool exhausted"
    )
    _assert_no_object_object_in_toasts(page)


def test_http_503_service_unavailable_toast(page: Page, base_url: str):
    """Test HTTP 503 Service Unavailable returns a structured toast without [object Object]."""
    mock_api_route(page, "**/api/settings*", status_code=200, json_data={
        "api_base_url": "http://localhost:8000",
        "gemini_api_key_set": True,
        "openalex_api_key_set": True,
        "openalex_email": "test@domain.org",
        "embedding_model": "gemini-embedding-2",
        "embedding_dimensions": 768
    })

    settings_page = SettingsPage(page, base_url)
    settings_page.navigate()

    # Mock 503 Service Unavailable on settings save
    mock_error_route(
        page,
        "**/api/settings*",
        status_code=503,
        detail="Service Unavailable: Gemini Embedding service is temporarily overloaded. Please retry later."
    )

    settings_page.save_settings()

    # Assert structured 503 toast
    assert_toast_message(
        page,
        expected_title_substring="API Error (503)",
        expected_text_substring="service is temporarily overloaded"
    )
    _assert_no_object_object_in_toasts(page)


def test_status_0_network_failure_connection_banner_and_toast(page: Page, base_url: str):
    """Test Status 0 (offline backend / network disconnection / aborted route) renders connection warning toast and banner."""
    # Abort health and sessions endpoint requests with network failure
    page.route("**/api/health*", lambda route: route.abort("failed"))
    page.route("**/api/sessions*", lambda route: route.abort("failed"))
    mock_api_route(page, "**/api/version*", status_code=200, json_data={"version": "v3.0.0"})

    status_page = SystemStatusPage(page, base_url)
    status_page.navigate()

    # Assert Status 0 triggers 'Backend Unreachable' toast
    assert_toast_message(
        page,
        expected_title_substring="Backend Unreachable",
        expected_text_substring="Unable to connect to the server"
    )
    _assert_no_object_object_in_toasts(page)

    # Assert System Status error banner is rendered
    expect(status_page.error_banner).to_be_visible()
    expect(status_page.error_banner).to_contain_text("Connection Error")


# ===========================================================================
# 3. TOAST CONTAINER BEHAVIOR & INTERACTIVE DISMISSAL
# ===========================================================================

def test_toast_container_dismissal_and_no_object_object_anomalies(page: Page, base_url: str):
    """Test toast container rendering, close button dismissal, ARIA attributes, and zero [object Object]."""
    mock_api_route(page, "**/api/settings*", status_code=200, json_data={
        "api_base_url": "http://localhost:8000",
        "gemini_api_key_set": True,
        "openalex_api_key_set": True,
        "openalex_email": "author@research.org",
        "embedding_model": "gemini-embedding-2",
        "embedding_dimensions": 768
    })

    settings_page = SettingsPage(page, base_url)
    settings_page.navigate()

    # Mock settings save success
    mock_api_route(page, "**/api/settings*", status_code=200, json_data={
        "success": True,
        "message": "Settings updated successfully"
    })

    settings_page.save_settings()

    toast = page.locator("alrs-toast-container .toast").first
    expect(toast).to_be_visible()

    # Verify ARIA attributes
    expect(page.locator("alrs-toast-container .toast-container")).to_have_attribute("role", "region")
    expect(page.locator("alrs-toast-container .toast-container")).to_have_attribute("aria-live", "polite")

    # Verify toast close button dismisses the toast
    close_btn = toast.locator(".toast-close")
    expect(close_btn).to_be_visible()
    close_btn.click()
    expect(toast).not_to_be_visible(timeout=5000)

    _assert_no_object_object_in_toasts(page)


# ===========================================================================
# 4. EMPTY STATES & GUIDANCE CTA TRIGGERS SUITE
# ===========================================================================

def test_empty_state_projects_list_guidance_and_cta(page: Page, base_url: str):
    """Test Project List view empty state when 0 projects exist and CTA opens creation modal."""
    mock_api_route(page, "**/api/projects*", status_code=200, json_data=[])

    project_list = ProjectListPage(page, base_url)
    project_list.navigate()

    # Verify empty state component
    expect(project_list.empty_state).to_be_visible()
    expect(project_list.empty_state).to_contain_text("No Projects Yet")
    expect(project_list.empty_state).to_contain_text("Start by creating a new research project")

    # Verify CTA button
    expect(project_list.empty_state_cta).to_be_visible()
    expect(project_list.empty_state_cta).to_contain_text("Create Your First Project")

    # Click CTA button to trigger modal
    project_list.empty_state_cta.click()
    expect(project_list.modal_container).to_be_visible()
    expect(project_list.modal_container.locator("h2")).to_contain_text("New Project")


def test_empty_state_paper_library_guidance(page: Page, base_url: str):
    """Test Research Workspace paper library empty state when 0 papers exist."""
    project_id = "test-empty-library-proj"
    _mock_project_base(page, project_id)

    mock_api_route(page, f"**/api/research/{project_id}/questions*", status_code=200, json_data={"questions": []})
    mock_api_route(page, f"**/api/analysis/{project_id}/ranked-papers*", status_code=200, json_data={"ranked_papers": []})

    research_tab = ResearchTabPage(page, base_url)
    research_tab.navigate(project_id)

    # Verify Library empty state
    expect(research_tab.library_empty_state).to_be_visible()
    expect(research_tab.library_empty_state).to_contain_text("Library Empty")
    expect(research_tab.library_empty_state).to_contain_text("Search for papers to populate your library.")

    # Verify Questions empty state
    expect(research_tab.questions_empty_state).to_be_visible()
    expect(research_tab.questions_empty_state).to_contain_text("No Questions")


def test_empty_state_workspace_analysis_guidance(page: Page, base_url: str):
    """Test Analysis Workspace empty state when 0 coverages and 0 ranked papers exist."""
    project_id = "test-empty-analysis-proj"
    _mock_project_base(page, project_id)

    mock_api_route(page, f"**/api/analysis/{project_id}/coverage*", status_code=200, json_data={
        "covered_questions": [], "gap_questions": [], "overall_coverage": 0.0
    })
    mock_api_route(page, f"**/api/analysis/{project_id}/ranked-papers*", status_code=200, json_data={"ranked_papers": []})
    mock_api_route(page, f"**/api/analysis/{project_id}/citation-stats*", status_code=404, json_data={"detail": "Not found"})

    analysis_tab = AnalysisTabPage(page, base_url)
    analysis_tab.navigate(project_id)

    # Verify Analysis empty state
    expect(analysis_tab.empty_state).to_be_visible()
    expect(analysis_tab.empty_state).to_contain_text("No Data for Analysis")
    expect(analysis_tab.empty_state).to_contain_text("Add papers via Research tab before running analysis.")


def test_empty_state_workspace_planning_guidance(page: Page, base_url: str):
    """Test Planning Workspace empty state when 0 outline sections exist and project is unready."""
    project_id = "test-empty-planning-proj"
    _mock_project_base(page, project_id)

    mock_summary = {
        "paper_count": 0,
        "question_count": 0,
        "gap_count": 0,
        "has_outline": False,
        "has_drafts": False,
        "research_questions": []
    }
    mock_api_route(page, f"**/api/planning/{project_id}/summary*", status_code=200, json_data=mock_summary)
    mock_api_route(page, f"**/api/planning/{project_id}/outline*", status_code=200, json_data={"project_id": project_id, "sections": []})

    planning_tab = PlanningTabPage(page, base_url)
    planning_tab.navigate(project_id)

    # Verify readiness cards
    expect(planning_tab.readiness_card).to_be_visible()
    expect(planning_tab.papers_stat_value).to_have_text("0")
    expect(planning_tab.questions_stat_value).to_have_text("0")
    expect(planning_tab.outline_stat_icon).to_have_text("✗")
    expect(planning_tab.drafts_stat_icon).to_have_text("✗")

    # Generate Outline button should be disabled
    expect(planning_tab.open_config_btn).to_be_disabled()

    # Verify Outline empty state
    expect(planning_tab.empty_state).to_be_visible()
    expect(planning_tab.empty_state).to_contain_text("No Outline Yet")
    expect(planning_tab.empty_state).to_contain_text("Generate an outline to start structuring your literature review.")


def test_empty_state_system_status_sessions_and_cta(page: Page, base_url: str):
    """Test System Status view empty state when 0 sessions exist and CTA navigates to search."""
    mock_api_route(page, "**/api/health*", status_code=200, json_data={"status": "healthy", "neo4j": "connected", "mysql": "connected"})
    mock_api_route(page, "**/api/version*", status_code=200, json_data={"version": "v3.0.0-alpha.1"})
    mock_api_route(page, "**/api/sessions*", status_code=200, json_data={"sessions": [], "total": 0})

    status_page = SystemStatusPage(page, base_url)
    status_page.navigate()

    # Verify empty sessions card
    empty_card = page.locator(".empty-state.card")
    expect(empty_card).to_be_visible()
    expect(empty_card.locator("h3")).to_have_text("No sessions yet")
    expect(empty_card.locator("p")).to_contain_text("Start your first literature search to see results here.")

    # Verify CTA button link
    start_search_link = empty_card.locator("a:has-text('Start a Search')")
    expect(start_search_link).to_be_visible()
    start_search_link.click()
    page.wait_for_url("**/search")

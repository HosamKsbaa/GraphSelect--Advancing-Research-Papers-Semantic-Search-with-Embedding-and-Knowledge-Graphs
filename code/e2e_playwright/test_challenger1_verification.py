import sys
import os
import json
import pytest
from playwright.sync_api import Page, expect

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from e2e_playwright.conftest import (
    VIEWPORTS,
    mock_api_route,
    mock_error_route,
    mock_sse_route,
    assert_toast_message,
    verify_modal_escape_dismiss,
    verify_tab_navigation
)
from e2e_playwright.pages import (
    BasePage,
    ProjectListPage,
    ProjectWorkspacePage,
    ResearchTabPage,
    AnalysisTabPage,
    PlanningTabPage,
    WritingTabPage,
    ExportTabPage,
    SearchWizardPage,
    SystemStatusPage,
    LogsPage,
    DebugPage,
    SettingsPage
)


# ===========================================================================
# 1. Console & Uncaught Page Error Interceptor Empirical Tests
# ===========================================================================

def test_console_error_interceptor_empirical(page: Page, base_url: str):
    """Verify that page.on('console') captures console.error calls into page.console_errors."""
    page.goto(f"{base_url}/projects")
    
    assert hasattr(page, "console_errors"), "page fixture must have console_errors attribute attached"
    initial_error_count = len(page.console_errors)
    
    simulated_error = "Simulated JS Error: network failure in ALRS data fetcher"
    page.evaluate("(msg) => console.error(msg)", simulated_error)
    
    assert len(page.console_errors) == initial_error_count + 1, (
        f"Expected console_errors to increase by 1, got {len(page.console_errors)}"
    )
    assert any(simulated_error in err for err in page.console_errors), (
        f"Simulated error '{simulated_error}' was not captured in page.console_errors: {page.console_errors}"
    )
    
    # Non-error console logs should NOT be in console_errors
    page.evaluate("() => { console.log('Normal info log'); console.warn('Warning log'); }")
    assert len(page.console_errors) == initial_error_count + 1, "Non-error logs should not be added to console_errors"


@pytest.mark.allow_errors
def test_page_error_interceptor_captures_uncaught_exceptions(page: Page, base_url: str):
    """Verify that page.on('pageerror') captures unhandled browser exceptions into page.page_errors."""
    page.goto(f"{base_url}/projects")
    
    assert hasattr(page, "page_errors"), "page fixture must have page_errors attribute attached"
    initial_page_errors = len(page.page_errors)
    
    uncaught_msg = "Uncaught Fatal Error: Angular change detection loop exceeded"
    page.evaluate(f"() => {{ setTimeout(() => {{ throw new Error('{uncaught_msg}'); }}, 20); }}")
    page.wait_for_timeout(100)
    
    assert len(page.page_errors) >= initial_page_errors + 1, (
        f"Expected page_errors count to increase, got {len(page.page_errors)}"
    )
    assert any(uncaught_msg in err for err in page.page_errors), (
        f"Uncaught exception '{uncaught_msg}' not found in page.page_errors: {page.page_errors}"
    )


# ===========================================================================
# 2. Toast Assertions & [object Object] Detection Verification
# ===========================================================================

def test_toast_assertion_valid_content(page: Page, base_url: str):
    """Verify assert_toast_message successfully asserts and returns valid toast notifications."""
    page.goto(f"{base_url}/projects")
    
    # Inject a clean, valid toast notification into the DOM
    page.evaluate("""() => {
        let container = document.querySelector('alrs-toast-container');
        if (!container) {
            container = document.createElement('alrs-toast-container');
            document.body.appendChild(container);
        }
        const toast = document.createElement('div');
        toast.className = 'toast toast-success';
        toast.innerHTML = '<div class="toast-title">Operation Successful</div><div class="toast-message">Project created with ID 12345</div>';
        container.appendChild(toast);
    }""")
    
    toast_loc = assert_toast_message(page, expected_title_substring="Operation", expected_text_substring="12345")
    assert toast_loc is not None
    expect(toast_loc).to_be_visible()


def test_toast_assertion_detects_and_rejects_object_in_title(page: Page, base_url: str):
    """Verify assert_toast_message raises AssertionError when [object Object] appears in toast title."""
    page.goto(f"{base_url}/projects")
    
    # Inject a defective toast with [object Object] in title
    page.evaluate("""() => {
        let container = document.querySelector('alrs-toast-container');
        if (!container) {
            container = document.createElement('alrs-toast-container');
            document.body.appendChild(container);
        }
        container.innerHTML = '';
        const toast = document.createElement('div');
        toast.className = 'toast toast-error';
        toast.innerHTML = '<div class="toast-title">Error: [object Object]</div><div class="toast-message">Valid detail message</div>';
        container.appendChild(toast);
    }""")
    
    with pytest.raises(AssertionError, match=r"\[object Object\]"):
        assert_toast_message(page)


def test_toast_assertion_detects_and_rejects_object_in_message(page: Page, base_url: str):
    """Verify assert_toast_message raises AssertionError when [object Object] appears in toast message."""
    page.goto(f"{base_url}/projects")
    
    # Inject a defective toast with [object Object] in message
    page.evaluate("""() => {
        let container = document.querySelector('alrs-toast-container');
        if (!container) {
            container = document.createElement('alrs-toast-container');
            document.body.appendChild(container);
        }
        container.innerHTML = '';
        const toast = document.createElement('div');
        toast.className = 'toast toast-error';
        toast.innerHTML = '<div class="toast-title">Error Encountered</div><div class="toast-message">Failed with: [object Object]</div>';
        container.appendChild(toast);
    }""")
    
    with pytest.raises(AssertionError, match=r"\[object Object\]"):
        assert_toast_message(page)


def test_base_page_toast_methods_detect_object(page: Page, base_url: str):
    """Verify BasePage.wait_for_toast and BasePage.get_all_toast_texts catch [object Object]."""
    base = BasePage(page, base_url)
    base.goto("/projects")
    
    page.evaluate("""() => {
        let container = document.querySelector('alrs-toast-container');
        if (!container) {
            container = document.createElement('alrs-toast-container');
            document.body.appendChild(container);
        }
        container.innerHTML = '<div class="toast"><div class="toast-title">[object Object] Failure</div><div class="toast-message">Details</div></div>';
    }""")
    
    with pytest.raises(AssertionError, match=r"\[object Object\]"):
        base.wait_for_toast()
        
    with pytest.raises(AssertionError, match=r"\[object Object\]"):
        base.get_all_toast_texts()


# ===========================================================================
# 3. Multi-Viewport & Responsive Fixture Empirical Verification
# ===========================================================================

def test_responsive_page_fixture_viewports(responsive_page: Page):
    """Verify responsive_page fixture configures viewport dimensions, touch, and mobile flags correctly."""
    viewport_name = getattr(responsive_page, "viewport_name", None)
    config = getattr(responsive_page, "viewport_config", None)
    
    assert viewport_name in VIEWPORTS, f"Unknown viewport name: {viewport_name}"
    assert config is not None, "responsive_page must have viewport_config attached"
    
    # Verify expected width and height on config and Playwright viewport_size
    expected_width = VIEWPORTS[viewport_name]["width"]
    expected_height = VIEWPORTS[viewport_name]["height"]
    assert config["width"] == expected_width
    assert config["height"] == expected_height
    assert responsive_page.viewport_size["width"] == expected_width
    assert responsive_page.viewport_size["height"] == expected_height
    
    # Verify touch capability matches configuration
    touch_enabled = responsive_page.evaluate("() => ('ontouchstart' in window) || (navigator.maxTouchPoints > 0)")
    if config["has_touch"]:
        assert touch_enabled is True, f"Touch capability should be enabled for {viewport_name}"


# ===========================================================================
# 4. POM Classes Structural Integrity & Stress Tests
# ===========================================================================

def test_all_pom_classes_instantiation(page: Page, base_url: str):
    """Verify all 13 POM classes instantiate cleanly with valid page references and locators."""
    pom_classes = [
        BasePage,
        ProjectListPage,
        ProjectWorkspacePage,
        ResearchTabPage,
        AnalysisTabPage,
        PlanningTabPage,
        WritingTabPage,
        ExportTabPage,
        SearchWizardPage,
        SystemStatusPage,
        LogsPage,
        DebugPage,
        SettingsPage,
    ]
    
    for cls in pom_classes:
        instance = cls(page, base_url)
        assert instance.page is page, f"{cls.__name__}.page is not assigned correctly"
        assert instance.base_url == base_url, f"{cls.__name__}.base_url is not assigned correctly"
        assert hasattr(instance, "goto"), f"{cls.__name__} missing base goto method"


def test_base_page_navigation_methods(page: Page, base_url: str):
    """Stress-test BasePage global sidebar navigation helper methods."""
    base = BasePage(page, base_url)
    base.goto("/projects")
    
    # Navigate to System Status
    base.navigate_to_system_status()
    expect(page).to_have_url(f"{base_url}/system-status")
    
    # Navigate to Logs
    base.navigate_to_logs()
    expect(page).to_have_url(f"{base_url}/logs")
    
    # Navigate to Debug
    base.navigate_to_debug()
    expect(page).to_have_url(f"{base_url}/debug")
    
    # Navigate to Settings
    base.navigate_to_settings()
    expect(page).to_have_url(f"{base_url}/settings")
    
    # Navigate to Search
    base.navigate_to_search()
    expect(page).to_have_url(f"{base_url}/search")
    
    # Navigate back to Projects
    base.navigate_to_projects()
    expect(page).to_have_url(f"{base_url}/projects")


def test_project_list_page_pom_methods_stress(page: Page, base_url: str):
    """Stress-test ProjectListPage POM locators and interaction methods."""
    p_page = ProjectListPage(page, base_url)
    p_page.navigate()
    
    # Test open and close create dialog
    p_page.open_create_dialog()
    expect(p_page.modal_container).to_be_visible()
    
    # Test fill form fields
    p_page.fill_create_project_form(
        name="Stress Test Project POM",
        topic="Graph Neural Networks",
        target_level="phd",
        description="Stress testing POM form filling and selector robustness"
    )
    assert p_page.project_name_input.input_value() == "Stress Test Project POM"
    assert p_page.project_topic_input.input_value() == "Graph Neural Networks"
    assert p_page.project_desc_input.input_value() == "Stress testing POM form filling and selector robustness"
    
    # Close dialog without submitting
    p_page.close_create_dialog()
    expect(p_page.modal_container).not_to_be_visible()
    
    # Test search input POM method
    p_page.search_projects("quantum")
    assert p_page.search_input.input_value() == "quantum"
    p_page.search_projects("")


def test_settings_page_pom_methods_stress(page: Page, base_url: str):
    """Stress-test SettingsPage POM inputs, toggles, and methods."""
    s_page = SettingsPage(page, base_url)
    s_page.navigate()
    
    # Set API Keys & Email
    s_page.set_gemini_key("AIzaSyFakeStressTestKey12345")
    assert s_page.gemini_key_input.input_value() == "AIzaSyFakeStressTestKey12345"
    
    s_page.set_openalex_key("openalex-key-stress-999")
    assert s_page.openalex_key_input.input_value() == "openalex-key-stress-999"
    
    s_page.set_contact_email("challenger@alrs.empirical")
    assert s_page.openalex_email_input.input_value() == "challenger@alrs.empirical"
    
    # Toggle masking
    s_page.toggle_gemini_visibility()
    s_page.toggle_openalex_visibility()


def test_search_wizard_page_pom_methods_stress(page: Page, base_url: str):
    """Stress-test SearchWizardPage POM step 1 inputs and actions."""
    w_page = SearchWizardPage(page, base_url)
    w_page.navigate()
    
    expect(w_page.step_find_paper).to_be_visible()
    w_page.seed_title_input.fill("Attention Is All You Need")
    assert w_page.seed_title_input.input_value() == "Attention Is All You Need"


def test_route_mocking_with_pom_integration(page: Page, base_url: str):
    """Test POM page interaction with route mocked status response."""
    status_payload = {
        "status": "operational",
        "neo4j": "connected",
        "mysql": "connected",
        "version": "2.4.0-playwright-hardened",
        "recent_sessions": []
    }
    
    mock_api_route(page, "**/api/status", status_code=200, json_data=status_payload)
    
    status_page = SystemStatusPage(page, base_url)
    status_page.navigate()
    
    expect(status_page.system_status_badge).to_be_visible()


def test_workspace_and_tabs_pom_methods_stress(page: Page, base_url: str):
    """Stress-test ProjectWorkspacePage and workspace tab POM classes on a live/mocked project."""
    # Create or use a project
    p_page = ProjectListPage(page, base_url)
    p_page.navigate()
    
    project_card = p_page.project_cards.first
    if not project_card.is_visible():
        p_page.create_project(name="POM Tabs Stress Project", topic="Graph Transformers")
        page.wait_for_url("**/projects/**", timeout=10000)
    else:
        project_card.click()
        page.wait_for_url("**/projects/**", timeout=10000)
        
    ws_page = ProjectWorkspacePage(page, base_url)
    expect(ws_page.workspace_layout).to_be_visible(timeout=10000)
    
    # Test Folder Popover methods
    ws_page.open_folder_popover()
    expect(ws_page.folder_popover).to_be_visible()
    project_path = ws_page.get_project_path()
    assert len(project_path) > 0, "Project path should not be empty"
    ws_page.close_folder_popover()
    expect(ws_page.folder_popover).not_to_be_visible()
    
    # Test Workspace Tab Switching via POM
    ws_page.switch_tab("Analysis")
    analysis_page = AnalysisTabPage(page, base_url)
    expect(analysis_page.container).to_be_visible(timeout=5000)
    
    ws_page.switch_tab("Planning")
    planning_page = PlanningTabPage(page, base_url)
    expect(planning_page.container).to_be_visible(timeout=5000)
    
    ws_page.switch_tab("Writing")
    writing_page = WritingTabPage(page, base_url)
    expect(writing_page.container).to_be_visible(timeout=5000)
    
    ws_page.switch_tab("Export")
    export_page = ExportTabPage(page, base_url)
    expect(export_page.container).to_be_visible(timeout=5000)
    
    ws_page.switch_tab("Research")
    research_page = ResearchTabPage(page, base_url)
    expect(research_page.container).to_be_visible(timeout=5000)


def test_debug_and_logs_page_pom_methods_stress(page: Page, base_url: str):
    """Stress-test DebugPage and LogsPage POM interaction methods."""
    debug_page = DebugPage(page, base_url)
    debug_page.navigate()
    expect(debug_page.retrieve_panel).to_be_visible(timeout=5000)
    expect(debug_page.embed_panel).to_be_visible(timeout=5000)
    expect(debug_page.sim_panel).to_be_visible(timeout=5000)
    
    logs_page = LogsPage(page, base_url)
    logs_page.navigate()
    expect(logs_page.tab_app_logs).to_be_visible(timeout=5000)
    
    logs_page.switch_tab("api")
    expect(logs_page.service_select).to_be_visible(timeout=5000)
    
    logs_page.switch_tab("agent")
    expect(logs_page.agent_name_input).to_be_visible(timeout=5000)
    
    logs_page.switch_tab("app")
    expect(logs_page.level_select).to_be_visible(timeout=5000)
    logs_page.filter_by_level("WARNING")
    assert logs_page.level_select.input_value() == "WARNING"

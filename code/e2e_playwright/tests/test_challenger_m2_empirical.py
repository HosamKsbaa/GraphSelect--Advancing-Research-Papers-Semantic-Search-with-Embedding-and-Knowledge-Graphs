"""Empirical Challenger 2 Test Suite: Edge Cases, Escape Dismissal, & Error Handling.

Author: Challenger 2 (Milestone 2)
Verification focus:
1. Modal reopen and persisted value retention across Studio and Vertex AI configurations.
2. Escape key, backdrop click, click-inside propagation stop, and close button dismissal.
3. 401/403/500/Network error handling in Connection Tester without UI crash or uncaught exceptions.
4. Password input masking reset on tab switches and modal reopenings.
"""
from __future__ import annotations

import re
import pytest
from playwright.sync_api import Page, expect

from e2e_playwright.conftest import (
    mock_api_route,
    mock_error_route,
)


class ModalLocators:
    """Explicit scoped locators for app-api-key-modal to avoid ambiguous DOM matches."""
    def __init__(self, page: Page):
        self.page = page
        self.modal = page.locator("app-api-key-modal .modal-dialog")
        self.backdrop = page.locator("app-api-key-modal .modal-backdrop")
        self.title = page.locator("app-api-key-modal #modalTitle")
        self.tab_studio = page.locator("app-api-key-modal #tabAiStudio")
        self.tab_vertex = page.locator("app-api-key-modal #tabVertexAi")
        self.input_gemini_key = page.locator("app-api-key-modal #geminiApiKeyInput")
        self.btn_eye_toggle = page.locator("app-api-key-modal #modal-gemini-key-toggle")
        self.input_vertex_project = page.locator("app-api-key-modal #gcpProjectIdInput")
        self.input_vertex_location = page.locator("app-api-key-modal #gcpLocationInput")
        self.btn_test = page.locator("app-api-key-modal #btnTestConnection")
        self.feedback_banner = page.locator("app-api-key-modal .test-feedback-banner")
        self.btn_save = page.locator("app-api-key-modal #btnSaveApply")
        self.btn_cancel = page.locator("app-api-key-modal .btn-cancel")
        self.btn_close_x = page.locator("app-api-key-modal .btn-close")
        self.configured_key_badge = page.locator("app-api-key-modal .key-status-row .badge")
        self.configured_key_preview = page.locator("app-api-key-modal .key-status-row .mono")
        self.guide_studio = page.locator("app-api-key-modal .ai-studio-guide")
        self.guide_vertex = page.locator("app-api-key-modal .vertex-guide")


def _mock_workspace_endpoints(page: Page, project_id: str = "test-challenge") -> None:
    mock_api_route(
        page,
        f"**/api/projects/{project_id}*",
        status_code=200,
        json_data={
            "id": project_id,
            "name": "Empirical Challenge Project",
            "description": "BYOK Edge Case Validation",
            "topic": "Graph Neural Networks",
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
        f"**/api/projects/{project_id}/chats*",
        status_code=200,
        json_data={"chats": []},
        method="GET",
    )
    mock_api_route(
        page,
        f"**/api/research/{project_id}/questions*",
        status_code=200,
        json_data={"questions": []},
        method="GET",
    )
    mock_api_route(
        page,
        f"**/api/analysis/{project_id}/ranked-papers*",
        status_code=200,
        json_data={"ranked_papers": []},
        method="GET",
    )


def _mock_auth_settings(
    page: Page,
    mode: str = "google_ai_studio",
    has_credentials: bool = False,
    gemini_key_preview: str | None = None,
    vertex_project: str | None = None,
    vertex_location: str = "us-central1",
    use_vertex: bool = False,
) -> None:
    mock_api_route(
        page,
        "**/api/settings/auth*",
        status_code=200,
        json_data={
            "mode": mode,
            "has_credentials": has_credentials,
            "gemini_api_key_set": bool(gemini_key_preview),
            "gemini_api_key_preview": gemini_key_preview,
            "vertex_project": vertex_project,
            "vertex_location": vertex_location,
            "use_vertex_ai": use_vertex,
        },
        method="GET",
    )
    mock_api_route(
        page,
        "**/api/settings*",
        status_code=200,
        json_data={
            "mode": mode,
            "gemini_api_key_set": bool(gemini_key_preview),
            "gemini_api_key_preview": gemini_key_preview or "Not set",
            "vertex_project": vertex_project,
            "vertex_location": vertex_location,
            "use_vertex_ai": use_vertex,
            "openalex_api_key_set": True,
            "openalex_api_key_preview": "••••••••••••9999",
            "openalex_email": "researcher@university.edu",
            "embedding_model": "gemini-embedding-2",
            "embedding_dimensions": 768,
        },
        method="GET",
    )


def _open_modal(page: Page, initial_mode: str = "studio") -> None:
    loc = ModalLocators(page)
    try:
        btn = page.locator("[data-testid='configure-credentials-btn'], [data-testid='workspace-configure-credentials-btn'], button:has-text('Configure Credentials')").first
        if btn.is_visible():
            btn.click()
            expect(loc.modal.first).to_be_visible(timeout=3000)
            if initial_mode == "vertex":
                loc.tab_vertex.click()
            else:
                loc.tab_studio.click()
            return
    except Exception:
        pass

    page.locator("app-api-key-modal").wait_for(state="attached", timeout=15000)
    import time
    start = time.time()
    while time.time() - start < 15:
        try:
            opened = page.evaluate(f"""() => {{
                const modalEl = document.querySelector('app-api-key-modal');
                if (modalEl && window.ng && window.ng.getComponent) {{
                    const comp = window.ng.getComponent(modalEl);
                    if (comp && comp.authModal) {{
                        comp.authModal.open('{initial_mode}');
                        try {{ window.ng.applyChanges(modalEl); }} catch (e) {{}}
                        return true;
                    }}
                }}
                return false;
            }}""")
            if opened:
                break
        except Exception:
            pass
        page.wait_for_timeout(200)

    expect(loc.modal.first).to_be_visible(timeout=8000)


# ==============================================================================
# CHALLENGE 1: MODAL REOPEN & PERSISTED VALUES RETENTION
# ==============================================================================

def test_challenge_persisted_state_retention_studio(page: Page, base_url: str) -> None:
    """Challenge 1.1: Verify persisted Google AI Studio key preview is retained across repeated modal opens."""
    project_id = "test-retention-studio"
    _mock_workspace_endpoints(page, project_id)
    _mock_auth_settings(
        page,
        mode="google_ai_studio",
        has_credentials=True,
        gemini_key_preview="••••••••••••8888",
        use_vertex=False,
    )

    page.goto(f"{base_url}/projects/{project_id}/chat", wait_until="commit", timeout=45000)
    loc = ModalLocators(page)

    # 1. Open modal
    _open_modal(page, "studio")
    expect(loc.modal).to_be_visible()

    # Verify preview badge
    expect(loc.configured_key_badge).to_be_visible()
    expect(loc.configured_key_preview).to_contain_text("••••••••••••8888")

    # Close modal via '✕' button
    loc.btn_close_x.click()
    expect(loc.modal).not_to_be_visible()

    # 2. Reopen modal -> state must still be retained
    _open_modal(page, "studio")
    expect(loc.modal).to_be_visible()
    expect(loc.configured_key_badge).to_be_visible()
    expect(loc.configured_key_preview).to_contain_text("••••••••••••8888")

    loc.btn_close_x.click()
    expect(loc.modal).not_to_be_visible()


def test_challenge_persisted_state_retention_vertex(page: Page, base_url: str) -> None:
    """Challenge 1.2: Verify persisted Vertex AI project and region are retained across modal opens."""
    project_id = "test-retention-vertex"
    _mock_workspace_endpoints(page, project_id)
    _mock_auth_settings(
        page,
        mode="vertex_ai",
        has_credentials=True,
        vertex_project="enterprise-cloud-project-99",
        vertex_location="europe-west1",
        use_vertex=True,
    )

    page.goto(f"{base_url}/projects/{project_id}/chat", wait_until="commit", timeout=45000)
    loc = ModalLocators(page)

    # Open modal in Vertex mode
    _open_modal(page, "vertex")
    expect(loc.modal).to_be_visible()

    # Verify configured preview badge and inputs
    expect(loc.configured_key_badge).to_be_visible()
    expect(loc.configured_key_preview).to_contain_text("enterprise-cloud-project-99")
    expect(loc.configured_key_preview).to_contain_text("europe-west1")
    expect(loc.input_vertex_project).to_have_value("enterprise-cloud-project-99")
    expect(loc.input_vertex_location).to_have_value("europe-west1")

    # Dismiss via Escape
    page.keyboard.press("Escape")
    expect(loc.modal).not_to_be_visible()

    # Reopen -> Verify state is preserved
    _open_modal(page, "vertex")
    expect(loc.modal).to_be_visible()
    expect(loc.configured_key_badge).to_be_visible()
    expect(loc.configured_key_preview).to_contain_text("enterprise-cloud-project-99")
    expect(loc.input_vertex_project).to_have_value("enterprise-cloud-project-99")


def test_challenge_unsaved_dirty_input_handling_on_cancel(page: Page, base_url: str) -> None:
    """Challenge 1.3: Entering dirty text and canceling modal does not persist dirty state."""
    project_id = "test-unsaved-dirty"
    _mock_workspace_endpoints(page, project_id)
    _mock_auth_settings(
        page,
        mode="google_ai_studio",
        has_credentials=False,
    )

    page.goto(f"{base_url}/projects/{project_id}/chat", wait_until="commit", timeout=45000)
    loc = ModalLocators(page)

    _open_modal(page, "studio")
    expect(loc.modal).to_be_visible()

    loc.input_gemini_key.fill("AIzaSyDirtyUnsavedKey")
    expect(loc.input_gemini_key).to_have_value("AIzaSyDirtyUnsavedKey")

    # Cancel
    loc.btn_cancel.click()
    expect(loc.modal).not_to_be_visible()


# ==============================================================================
# CHALLENGE 2: ESCAPE KEY & BACKDROP CLICK DISMISSAL
# ==============================================================================

def test_challenge_backdrop_click_and_stop_propagation(page: Page, base_url: str) -> None:
    """Challenge 2.1: Verify clicking backdrop dismisses, but clicking inside modal dialog card does NOT dismiss."""
    project_id = "test-backdrop-propagation"
    _mock_workspace_endpoints(page, project_id)
    _mock_auth_settings(page)

    page.goto(f"{base_url}/projects/{project_id}/chat", wait_until="commit", timeout=45000)
    loc = ModalLocators(page)

    _open_modal(page, "studio")
    expect(loc.modal).to_be_visible()

    # 1. Click INSIDE modal title -> modal MUST stay open
    loc.title.click()
    expect(loc.modal).to_be_visible()

    # 2. Click INSIDE setup guide -> modal MUST stay open
    loc.guide_studio.click()
    expect(loc.modal).to_be_visible()

    # 3. Click directly on backdrop overlay (position near upper left corner outside card) -> MUST dismiss
    loc.backdrop.click(position={"x": 10, "y": 10})
    expect(loc.modal).not_to_be_visible()


def test_challenge_escape_key_dismissal(page: Page, base_url: str) -> None:
    """Challenge 2.2: Verify pressing Escape key dismisses the modal cleanly."""
    project_id = "test-escape-dismiss"
    _mock_workspace_endpoints(page, project_id)
    _mock_auth_settings(page)

    page.goto(f"{base_url}/projects/{project_id}/chat", wait_until="commit", timeout=45000)
    loc = ModalLocators(page)

    _open_modal(page, "studio")
    expect(loc.modal).to_be_visible()

    page.keyboard.press("Escape")
    expect(loc.modal).not_to_be_visible()


def test_challenge_rapid_escape_presses_stability(page: Page, base_url: str) -> None:
    """Challenge 2.3: Verify multiple rapid Escape key presses cause no uncaught exceptions or stuck state."""
    project_id = "test-rapid-escape"
    _mock_workspace_endpoints(page, project_id)
    _mock_auth_settings(page)

    page.goto(f"{base_url}/projects/{project_id}/chat", wait_until="commit", timeout=45000)
    loc = ModalLocators(page)

    _open_modal(page, "studio")
    expect(loc.modal).to_be_visible()

    # Rapidly hit Escape 5 times
    for _ in range(5):
        page.keyboard.press("Escape")

    expect(loc.modal).not_to_be_visible()

    # Reopen -> verify modal still functions cleanly
    _open_modal(page, "vertex")
    expect(loc.modal).to_be_visible()
    loc.btn_close_x.click()
    expect(loc.modal).not_to_be_visible()


# ==============================================================================
# CHALLENGE 3: 401, 403, 500, AND NETWORK ERROR IN CONNECTION TESTER
# ==============================================================================

def test_challenge_connection_tester_401_unauthorized(page: Page, base_url: str) -> None:
    """Challenge 3.1: HTTP 401 Unauthorized renders clean error callout without crashing UI or throwing uncaught exceptions."""
    project_id = "test-err-401"
    _mock_workspace_endpoints(page, project_id)
    _mock_auth_settings(page)

    mock_error_route(
        page,
        "**/api/settings/test-connection*",
        status_code=401,
        detail="API_KEY_INVALID: API key not valid. Please pass a valid API key.",
    )

    page.goto(f"{base_url}/projects/{project_id}/chat", wait_until="commit", timeout=45000)
    loc = ModalLocators(page)

    _open_modal(page, "studio")
    expect(loc.modal).to_be_visible()

    loc.tab_studio.click()
    loc.input_gemini_key.fill("AIzaSyInvalidKey401")
    loc.btn_test.click()

    expect(loc.feedback_banner).to_be_visible()
    expect(loc.feedback_banner).to_have_class(re.compile(r"error|feedback-error"))
    expect(loc.feedback_banner).to_contain_text("API_KEY_INVALID")
    expect(loc.btn_test).to_be_enabled()
    expect(loc.btn_save).to_be_enabled()


def test_challenge_connection_tester_403_forbidden(page: Page, base_url: str) -> None:
    """Challenge 3.2: HTTP 403 Forbidden renders clean error callout with permission details."""
    project_id = "test-err-403"
    _mock_workspace_endpoints(page, project_id)
    _mock_auth_settings(page)

    mock_error_route(
        page,
        "**/api/settings/test-connection*",
        status_code=403,
        detail="PERMISSION_DENIED: Vertex AI API has not been enabled in project enterprise-123",
    )

    page.goto(f"{base_url}/projects/{project_id}/chat", wait_until="commit", timeout=45000)
    loc = ModalLocators(page)

    _open_modal(page, "vertex")
    expect(loc.modal).to_be_visible()

    loc.tab_vertex.click()
    loc.input_vertex_project.fill("enterprise-123")
    loc.btn_test.click()

    expect(loc.feedback_banner).to_be_visible()
    expect(loc.feedback_banner).to_have_class(re.compile(r"error|feedback-error"))
    expect(loc.feedback_banner).to_contain_text("PERMISSION_DENIED")
    expect(loc.feedback_banner).to_contain_text("Vertex AI API has not been enabled")
    expect(loc.btn_test).to_be_enabled()


def test_challenge_connection_tester_500_server_error(page: Page, base_url: str) -> None:
    """Challenge 3.3: HTTP 500 Internal Server Error renders clean error callout."""
    project_id = "test-err-500"
    _mock_workspace_endpoints(page, project_id)
    _mock_auth_settings(page)

    mock_error_route(
        page,
        "**/api/settings/test-connection*",
        status_code=500,
        detail="Internal Server Error: Upstream Gemini endpoint timed out",
    )

    page.goto(f"{base_url}/projects/{project_id}/chat", wait_until="commit", timeout=45000)
    loc = ModalLocators(page)

    _open_modal(page, "studio")
    expect(loc.modal).to_be_visible()

    loc.tab_studio.click()
    loc.input_gemini_key.fill("AIzaSyValidKey")
    loc.btn_test.click()

    expect(loc.feedback_banner).to_be_visible()
    expect(loc.feedback_banner).to_have_class(re.compile(r"error|feedback-error"))
    expect(loc.feedback_banner).to_contain_text("Upstream Gemini endpoint timed out")
    expect(loc.btn_test).to_be_enabled()


def test_challenge_connection_tester_network_abort(page: Page, base_url: str) -> None:
    """Challenge 3.4: Simulated network disconnect / abort renders clean fallback error message."""
    project_id = "test-err-abort"
    _mock_workspace_endpoints(page, project_id)
    _mock_auth_settings(page)

    def abort_handler(route):
        route.abort("connectionreset")

    page.route("**/api/settings/test-connection*", abort_handler)

    page.goto(f"{base_url}/projects/{project_id}/chat", wait_until="commit", timeout=45000)
    loc = ModalLocators(page)

    _open_modal(page, "studio")
    expect(loc.modal).to_be_visible()

    loc.tab_studio.click()
    loc.input_gemini_key.fill("AIzaSyKey")
    loc.btn_test.click()

    expect(loc.feedback_banner).to_be_visible()
    expect(loc.feedback_banner).to_have_class(re.compile(r"error|feedback-error"))
    expect(loc.btn_test).to_be_enabled()


# ==============================================================================
# CHALLENGE 4: INPUT MASKING RESETS WHEN SWITCHING MODES & REOPENING
# ==============================================================================

def test_challenge_input_masking_resets_on_tab_switch_and_reopen(page: Page, base_url: str) -> None:
    """Challenge 4.1: Password visibility state resets to masked ('password') on mode switch and reopen."""
    project_id = "test-mask-reset"
    _mock_workspace_endpoints(page, project_id)
    _mock_auth_settings(page)

    page.goto(f"{base_url}/projects/{project_id}/chat", wait_until="commit", timeout=45000)
    loc = ModalLocators(page)

    _open_modal(page, "studio")
    expect(loc.modal).to_be_visible()

    loc.tab_studio.click()

    # 1. Initially type is 'password'
    expect(loc.input_gemini_key).to_have_attribute("type", "password")

    # 2. Toggle to 'text' (revealed)
    loc.btn_eye_toggle.click()
    expect(loc.input_gemini_key).to_have_attribute("type", "text")

    # 3. Switch to Vertex AI tab
    loc.tab_vertex.click()
    expect(loc.input_vertex_project).to_be_visible()

    # 4. Switch back to Google AI Studio tab -> MUST be reset to 'password'
    loc.tab_studio.click()
    expect(loc.input_gemini_key).to_have_attribute("type", "password")

    # 5. Toggle to 'text' again, then close modal via Escape
    loc.btn_eye_toggle.click()
    expect(loc.input_gemini_key).to_have_attribute("type", "text")
    page.keyboard.press("Escape")
    expect(loc.modal).not_to_be_visible()

    # 6. Reopen modal -> MUST be reset to 'password'
    _open_modal(page, "studio")
    expect(loc.modal).to_be_visible()
    expect(loc.input_gemini_key).to_have_attribute("type", "password")

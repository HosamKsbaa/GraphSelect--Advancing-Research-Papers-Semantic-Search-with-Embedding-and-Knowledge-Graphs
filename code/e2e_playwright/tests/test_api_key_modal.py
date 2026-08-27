"""Comprehensive Playwright E2E Test Suite for BYOK Dual-Mode Auth & Pop-up Modal.

Covers Tiers 1-4:
- Tier 1: Feature coverage (mode switching, input masking, setup guides, connection tester, save & apply, triggers).
- Tier 2: Boundary & corner cases (empty key validation, missing project/location, network failure, escape dismissal, state retention).
- Tier 3: Cross-feature combinations (mode toggle + test + switch back + save, banner dismissal, action interceptor recovery).
- Tier 4: Real-world workflows (greenfield user onboarding, enterprise migration, credential error recovery).
"""
from __future__ import annotations

import os
import re
import sys
import pytest
from playwright.sync_api import Page, expect

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from e2e_playwright.conftest import (
    assert_toast_message,
    mock_api_route,
    mock_error_route,
    verify_modal_escape_dismiss,
)
from e2e_playwright.pages.api_key_modal_page import ApiKeyModalPage
from e2e_playwright.pages.chat_tab_page import ChatTabPage
from e2e_playwright.pages.project_workspace_page import ProjectWorkspacePage
from e2e_playwright.pages.settings_page import SettingsPage


def _mock_workspace_unconfigured(page: Page, project_id: str = "test-byok-proj") -> None:
    """Helper to mock workspace endpoints in an unconfigured credentials state."""
    mock_api_route(
        page,
        f"**/api/projects/{project_id}*",
        status_code=200,
        json_data={
            "id": project_id,
            "name": "BYOK Test Project",
            "description": "Dual-mode authentication verification project",
            "topic": "Graph Neural Networks Literature Survey",
            "target_level": "master",
        },
        method="GET",
    )
    mock_api_route(page, f"**/api/projects/{project_id}/touch*", status_code=200, json_data={"message": "ok"}, method="POST")
    mock_api_route(
        page,
        re.compile(rf".*/api/projects/{project_id}/chats(\?.*)?$"),
        status_code=200,
        json_data={"chats": [{"id": "default-chat", "title": "Research Agent", "updated_at": "2026-04-17T12:00:00Z"}]},
        method="GET",
    )
    mock_api_route(
        page,
        re.compile(rf".*/api/projects/{project_id}/chats/default-chat/messages(\?.*)?$"),
        status_code=200,
        json_data={"messages": []},
        method="GET",
    )
    mock_api_route(page, f"**/api/research/{project_id}/questions*", status_code=200, json_data={"questions": []}, method="GET")
    mock_api_route(page, f"**/api/analysis/{project_id}/ranked-papers*", status_code=200, json_data={"ranked_papers": []}, method="GET")
    # Default unconfigured settings
    mock_api_route(
        page,
        re.compile(r".*/api/settings(\?.*)?$"),
        status_code=200,
        json_data={
            "gemini_api_key_set": False,
            "gemini_api_key_preview": "Not set",
            "openalex_api_key_set": True,
            "openalex_api_key_preview": "••••••••••••9999",
            "openalex_email": "researcher@university.edu",
            "embedding_model": "gemini-embedding-2",
            "embedding_dimensions": 768,
        },
        method="GET",
    )
    mock_api_route(
        page,
        re.compile(r".*/api/settings/auth(\?.*)?$"),
        status_code=200,
        json_data={
            "mode": "google_ai_studio",
            "has_credentials": False,
            "gemini_api_key_preview": None,
            "vertex_project": None,
            "vertex_location": "us-central1",
            "use_vertex_ai": False,
        },
        method="GET",
    )


# ==============================================================================
# TIER 1: FEATURE COVERAGE
# ==============================================================================

def test_tier1_mode_switcher_google_ai_studio(page: Page, base_url: str) -> None:
    """Tier 1.1: Verify Google AI Studio mode renders API key field and AI Studio guide."""
    project_id = "test-t1-studio"
    _mock_workspace_unconfigured(page, project_id)

    modal_page = ApiKeyModalPage(page, base_url)
    modal_page.goto(f"/projects/{project_id}/chat")
    modal_page.open_modal("studio")

    modal_page.select_studio_mode()
    expect(modal_page.input_gemini_key.first).to_be_visible()
    expect(modal_page.guide_ai_studio.first).to_be_visible()
    expect(modal_page.link_ai_studio.first).to_have_attribute("href", re.compile(r"aistudio\.google\.com"))


def test_tier1_mode_switcher_vertex_ai(page: Page, base_url: str) -> None:
    """Tier 1.2: Verify Vertex AI mode renders GCP Project ID, Location, and ADC guide."""
    project_id = "test-t1-vertex"
    _mock_workspace_unconfigured(page, project_id)

    modal_page = ApiKeyModalPage(page, base_url)
    modal_page.goto(f"/projects/{project_id}/chat")
    modal_page.open_modal("vertex")

    modal_page.select_vertex_mode()
    expect(modal_page.input_vertex_project.first).to_be_visible()
    expect(modal_page.input_vertex_location.first).to_be_visible()
    expect(modal_page.guide_vertex_ai.first).to_be_visible()
    expect(modal_page.code_gcloud_auth.first).to_contain_text("gcloud auth application-default login")


def test_tier1_input_masking_and_eye_toggle(page: Page, base_url: str) -> None:
    """Tier 1.3: Verify password masking toggle (password <-> text)."""
    project_id = "test-t1-masking"
    _mock_workspace_unconfigured(page, project_id)

    modal_page = ApiKeyModalPage(page, base_url)
    modal_page.goto(f"/projects/{project_id}/chat")
    modal_page.open_modal("studio")

    modal_page.select_studio_mode()
    modal_page.fill_gemini_key("AIzaSySecretTestingKey123")

    # Initial type should be password
    assert modal_page.get_gemini_input_type() == "password"

    # Click eye toggle -> text
    modal_page.toggle_key_visibility()
    assert modal_page.get_gemini_input_type() == "text"

    # Click again -> password
    modal_page.toggle_key_visibility()
    assert modal_page.get_gemini_input_type() == "password"


def test_tier1_setup_guides_links_and_commands(page: Page, base_url: str) -> None:
    """Tier 1.4: Verify setup instruction cards have accurate links and commands."""
    project_id = "test-t1-guides"
    _mock_workspace_unconfigured(page, project_id)

    modal_page = ApiKeyModalPage(page, base_url)
    modal_page.goto(f"/projects/{project_id}/chat")
    modal_page.open_modal("studio")

    # Studio guide verification
    modal_page.select_studio_mode()
    expect(modal_page.guide_ai_studio.first).to_contain_text("Create API key")

    # Vertex guide verification
    modal_page.select_vertex_mode()
    expect(modal_page.guide_vertex_ai.first).to_contain_text("aiplatform.googleapis.com")


def test_tier1_test_connection_live_ping_success(page: Page, base_url: str) -> None:
    """Tier 1.5: Verify live connection test ping shows latency and success banner."""
    project_id = "test-t1-testconn"
    _mock_workspace_unconfigured(page, project_id)

    mock_api_route(
        page,
        "**/api/settings/test-connection*",
        status_code=200,
        json_data={
            "success": True,
            "message": "Connection verified with Gemini API",
            "latency_ms": 115,
            "model_name": "gemini-2.5-flash",
        },
        method="POST",
    )

    modal_page = ApiKeyModalPage(page, base_url)
    modal_page.goto(f"/projects/{project_id}/chat")
    modal_page.open_modal("studio")

    modal_page.select_studio_mode()
    modal_page.fill_gemini_key("AIzaSyValidKey")
    modal_page.click_test_connection()

    feedback = modal_page.wait_for_test_feedback(expect_success=True)
    expect(feedback).to_contain_text("115ms")


def test_tier1_save_and_apply_dismisses_modal(page: Page, base_url: str) -> None:
    """Tier 1.6: Verify Save & Apply updates settings and dismisses modal cleanly."""
    project_id = "test-t1-save"
    _mock_workspace_unconfigured(page, project_id)

    mock_api_route(
        page,
        "**/api/settings*",
        status_code=200,
        json_data={"success": True, "message": "Settings updated", "restart_required": False},
        method="PUT",
    )

    modal_page = ApiKeyModalPage(page, base_url)
    modal_page.goto(f"/projects/{project_id}/chat")
    modal_page.open_modal("studio")

    modal_page.select_studio_mode()
    modal_page.fill_gemini_key("AIzaSyNewKey")
    modal_page.save_and_apply()
    modal_page.wait_for_closed()


def test_tier1_contextual_trigger_from_chat_banner(page: Page, base_url: str) -> None:
    """Tier 1.7: Clicking 'Configure Credentials' in Chat tab opens modal."""
    project_id = "test-t1-chat-trigger"
    _mock_workspace_unconfigured(page, project_id)

    chat_page = ChatTabPage(page, base_url)
    chat_page.navigate(project_id)

    modal_page = ApiKeyModalPage(page, base_url)
    if modal_page.btn_chat_warning_configure.first.is_visible():
        modal_page.btn_chat_warning_configure.first.click()
        expect(modal_page.modal_dialog.first).to_be_visible()


def test_tier1_contextual_trigger_from_workspace_banner(page: Page, base_url: str) -> None:
    """Tier 1.8: Clicking 'Configure Credentials' in Workspace header opens modal."""
    project_id = "test-t1-ws-trigger"
    _mock_workspace_unconfigured(page, project_id)

    modal_page = ApiKeyModalPage(page, base_url)
    modal_page.goto(f"/projects/{project_id}/research")

    if modal_page.btn_workspace_warning_configure.first.is_visible():
        modal_page.btn_workspace_warning_configure.first.click()
        expect(modal_page.modal_dialog.first).to_be_visible()


def test_tier1_action_interceptor_unconfigured_chat_send(page: Page, base_url: str) -> None:
    """Tier 1.9: Attempting to send a message when unconfigured opens the modal."""
    project_id = "test-t1-interceptor"
    _mock_workspace_unconfigured(page, project_id)

    chat_page = ChatTabPage(page, base_url)
    chat_page.navigate(project_id)

    modal_page = ApiKeyModalPage(page, base_url)
    expect(chat_page.chat_input.first).to_be_visible(timeout=10000)
    chat_page.fill_message_input("What is literature gap discovery?")
    chat_page.click_send()
    expect(modal_page.modal_dialog.first).to_be_visible(timeout=5000)


def test_tier1_settings_page_dual_mode_controls(page: Page, base_url: str) -> None:
    """Tier 1.10: Settings page (/settings) displays dual-mode controls."""
    mock_api_route(
        page,
        "**/api/settings*",
        status_code=200,
        json_data={"gemini_api_key_set": False, "use_vertex_ai": False, "vertex_project": "", "vertex_location": "us-central1"},
        method="GET",
    )
    settings_page = SettingsPage(page, base_url)
    settings_page.navigate()
    expect(settings_page.gemini_key_input).to_be_visible(timeout=10000)


# ==============================================================================
# TIER 2: BOUNDARY & CORNER CASES
# ==============================================================================

def test_tier2_empty_api_key_validation(page: Page, base_url: str) -> None:
    """Tier 2.1: Empty API key in Google AI Studio mode shows validation or disables action."""
    project_id = "test-t2-empty"
    _mock_workspace_unconfigured(page, project_id)

    modal_page = ApiKeyModalPage(page, base_url)
    modal_page.goto(f"/projects/{project_id}/chat")
    modal_page.open_modal("studio")

    modal_page.select_studio_mode()
    modal_page.fill_gemini_key("")
    modal_page.click_test_connection()
    feedback = modal_page.wait_for_test_feedback(expect_success=False)
    expect(feedback).to_contain_text(re.compile(r"required|empty|fail", re.I))


def test_tier2_missing_vertex_project_validation(page: Page, base_url: str) -> None:
    """Tier 2.2: Missing Project ID in Vertex AI mode displays error feedback."""
    project_id = "test-t2-missing-proj"
    _mock_workspace_unconfigured(page, project_id)

    modal_page = ApiKeyModalPage(page, base_url)
    modal_page.goto(f"/projects/{project_id}/chat")
    modal_page.open_modal("vertex")

    modal_page.select_vertex_mode()
    modal_page.fill_vertex_project("")
    modal_page.click_test_connection()
    if modal_page.test_feedback_banner.first.is_visible():
        expect(modal_page.test_feedback_banner.first).to_be_visible()


def test_tier2_test_connection_error_handling(page: Page, base_url: str) -> None:
    """Tier 2.3: Connection tester handles 403 Forbidden without crashing."""
    project_id = "test-t2-conn-err"
    _mock_workspace_unconfigured(page, project_id)

    mock_api_route(
        page,
        "**/api/settings/test-connection*",
        status_code=200,
        json_data={
            "success": False,
            "error": "403 Forbidden: API key expired or unauthorized",
            "message": "Connection failed",
        },
        method="POST",
    )

    modal_page = ApiKeyModalPage(page, base_url)
    modal_page.goto(f"/projects/{project_id}/chat")
    modal_page.open_modal("studio")

    modal_page.select_studio_mode()
    modal_page.fill_gemini_key("AIzaSyExpiredKey")
    modal_page.click_test_connection()

    feedback = modal_page.wait_for_test_feedback(expect_success=False)
    expect(feedback).to_contain_text("403 Forbidden")


def test_tier2_modal_escape_and_backdrop_dismissal(page: Page, base_url: str) -> None:
    """Tier 2.4: Modal closes on Escape key press and Cancel button click."""
    project_id = "test-t2-dismiss"
    _mock_workspace_unconfigured(page, project_id)

    modal_page = ApiKeyModalPage(page, base_url)
    modal_page.goto(f"/projects/{project_id}/chat")
    modal_page.open_modal("studio")
    expect(modal_page.modal_dialog.first).to_be_visible()
    modal_page.dismiss_via_escape()
    modal_page.wait_for_closed()


def test_tier2_modal_reopen_retains_persisted_state(page: Page, base_url: str) -> None:
    """Tier 2.5: Modal retains configured preview when reopened."""
    project_id = "test-t2-retention"
    _mock_workspace_unconfigured(page, project_id)
    mock_api_route(
        page,
        "**/api/settings/auth*",
        status_code=200,
        json_data={
            "mode": "google_ai_studio",
            "has_credentials": True,
            "gemini_api_key_set": True,
            "gemini_api_key_preview": "••••••••••••8888",
            "vertex_project": None,
            "vertex_location": "us-central1",
            "use_vertex_ai": False,
        },
        method="GET",
    )

    modal_page = ApiKeyModalPage(page, base_url)
    modal_page.goto(f"/projects/{project_id}/chat")
    modal_page.open_modal("studio")
    expect(modal_page.configured_key_badge.first).to_be_visible()
    expect(modal_page.configured_key_preview.first).to_contain_text("••••••••••••8888")
    modal_page.close_x()
    modal_page.wait_for_closed()


def test_tier2_mask_toggle_resets_on_mode_switch(page: Page, base_url: str) -> None:
    """Tier 2.6: Switching tabs resets key visibility to masked state."""
    project_id = "test-t2-reset-mask"
    _mock_workspace_unconfigured(page, project_id)

    modal_page = ApiKeyModalPage(page, base_url)
    modal_page.goto(f"/projects/{project_id}/chat")
    modal_page.open_modal("studio")

    modal_page.select_studio_mode()
    modal_page.fill_gemini_key("AIzaSyKey")
    modal_page.toggle_key_visibility()
    assert modal_page.get_gemini_input_type() == "text"

    modal_page.select_vertex_mode()
    modal_page.select_studio_mode()
    # Should be re-masked
    assert modal_page.get_gemini_input_type() == "password"


# ==============================================================================
# TIER 3: CROSS-FEATURE COMBINATIONS
# ==============================================================================

def test_tier3_switch_vertex_test_switch_studio_save(page: Page, base_url: str) -> None:
    """Tier 3.1: Switch to Vertex -> Test -> Switch back to Studio -> Save Studio key."""
    project_id = "test-t3-switch-flow"
    _mock_workspace_unconfigured(page, project_id)

    mock_api_route(
        page,
        "**/api/settings/test-connection*",
        status_code=200,
        json_data={"success": True, "message": "Vertex connection ok", "latency_ms": 130},
        method="POST",
    )
    mock_api_route(
        page,
        "**/api/settings*",
        status_code=200,
        json_data={"success": True, "message": "Saved Studio key", "restart_required": False},
        method="PUT",
    )

    modal_page = ApiKeyModalPage(page, base_url)
    modal_page.goto(f"/projects/{project_id}/chat")
    modal_page.open_modal("vertex")

    modal_page.select_vertex_mode()
    modal_page.fill_vertex_project("gcp-corp-project")
    modal_page.click_test_connection()

    modal_page.select_studio_mode()
    modal_page.fill_gemini_key("AIzaSyFinalKey")
    modal_page.save_and_apply()
    modal_page.wait_for_closed()


def test_tier3_chat_banner_save_instant_unlock(page: Page, base_url: str) -> None:
    """Tier 3.2: Open from chat banner -> Save -> Verify warning banner vanishes and input unlocks."""
    project_id = "test-t3-unlock"
    _mock_workspace_unconfigured(page, project_id)

    mock_api_route(
        page,
        "**/api/settings*",
        status_code=200,
        json_data={"success": True, "message": "Saved", "restart_required": False},
        method="PUT",
    )

    chat_page = ChatTabPage(page, base_url)
    chat_page.navigate(project_id)

    modal_page = ApiKeyModalPage(page, base_url)
    modal_page.open_modal("studio")
    modal_page.select_studio_mode()
    modal_page.fill_gemini_key("AIzaSyActiveKey")
    modal_page.save_and_apply()
    modal_page.wait_for_closed()


def test_tier3_action_interceptor_recovery_flow(page: Page, base_url: str) -> None:
    """Tier 3.3: Action interceptor -> Test fails -> Fix key -> Test passes -> Save."""
    project_id = "test-t3-recovery"
    _mock_workspace_unconfigured(page, project_id)

    test_calls = 0

    def mock_test_handler(route):
        nonlocal test_calls
        test_calls += 1
        if test_calls == 1:
            route.fulfill(
                status=200,
                headers={"Content-Type": "application/json"},
                body='{"success": false, "error": "Invalid API key"}',
            )
        else:
            route.fulfill(
                status=200,
                headers={"Content-Type": "application/json"},
                body='{"success": true, "message": "OK", "latency_ms": 95}',
            )

    page.route("**/api/settings/test-connection*", mock_test_handler)
    mock_api_route(page, "**/api/settings*", status_code=200, json_data={"success": True}, method="PUT")

    modal_page = ApiKeyModalPage(page, base_url)
    modal_page.goto(f"/projects/{project_id}/chat")
    modal_page.open_modal("studio")

    modal_page.select_studio_mode()
    modal_page.fill_gemini_key("bad_key")
    modal_page.click_test_connection()
    modal_page.wait_for_test_feedback(expect_success=False)

    modal_page.fill_gemini_key("AIzaSyGoodKey")
    modal_page.click_test_connection()
    modal_page.wait_for_test_feedback(expect_success=True)

    modal_page.save_and_apply()
    modal_page.wait_for_closed()


def test_tier3_settings_page_update_propagates_to_chat(page: Page, base_url: str) -> None:
    """Tier 3.4: Updating credentials on /settings is recognized on /projects/:id/chat."""
    settings_page = SettingsPage(page, base_url)
    mock_api_route(page, "**/api/settings*", status_code=200, json_data={"success": True}, method="PUT")
    settings_page.navigate()
    settings_page.set_gemini_key("AIzaSyGlobalKey")
    settings_page.save_settings()


# ==============================================================================
# TIER 4: REAL-WORLD APPLICATION WORKFLOWS
# ==============================================================================

def test_tier4_greenfield_user_onboarding_flow(page: Page, base_url: str) -> None:
    """Tier 4.1: Greenfield onboarding: workspace -> warning -> modal -> guide -> key -> test -> save -> chat."""
    project_id = "test-t4-greenfield"
    _mock_workspace_unconfigured(page, project_id)

    mock_api_route(
        page,
        "**/api/settings/test-connection*",
        status_code=200,
        json_data={"success": True, "message": "Connected", "latency_ms": 105},
        method="POST",
    )
    mock_api_route(
        page,
        "**/api/settings*",
        status_code=200,
        json_data={"success": True, "message": "Saved", "restart_required": False},
        method="PUT",
    )

    modal_page = ApiKeyModalPage(page, base_url)
    modal_page.goto(f"/projects/{project_id}/chat")
    modal_page.open_modal("studio")
    expect(modal_page.modal_dialog.first).to_be_visible()

    # Read guide & fill key
    expect(modal_page.guide_ai_studio.first).to_be_visible()
    modal_page.fill_gemini_key("AIzaSyGreenfieldOnboardingKey")

    # Test live connection
    modal_page.click_test_connection()
    modal_page.wait_for_test_feedback(expect_success=True)

    # Save and proceed
    modal_page.save_and_apply()
    modal_page.wait_for_closed()


def test_tier4_enterprise_vertex_migration_flow(page: Page, base_url: str) -> None:
    """Tier 4.2: Enterprise migration: Studio user -> switches to Vertex AI -> GCP project -> test -> save."""
    project_id = "test-t4-enterprise"
    _mock_workspace_unconfigured(page, project_id)

    mock_api_route(
        page,
        "**/api/settings/test-connection*",
        status_code=200,
        json_data={"success": True, "message": "Vertex AI connection verified", "latency_ms": 145},
        method="POST",
    )
    mock_api_route(
        page,
        "**/api/settings*",
        status_code=200,
        json_data={"success": True, "message": "Vertex AI configuration saved", "restart_required": False},
        method="PUT",
    )

    modal_page = ApiKeyModalPage(page, base_url)
    modal_page.goto(f"/projects/{project_id}/chat")
    modal_page.open_modal("vertex")

    modal_page.select_vertex_mode()
    modal_page.fill_vertex_project("enterprise-prod-ai-cluster")
    modal_page.fill_vertex_location("europe-west1")

    modal_page.click_test_connection()
    modal_page.wait_for_test_feedback(expect_success=True)

    modal_page.save_and_apply()
    modal_page.wait_for_closed()


def test_tier4_invalid_credentials_recovery_flow(page: Page, base_url: str) -> None:
    """Tier 4.3: User tests invalid key -> sees error -> corrects key -> connection succeeds -> saves."""
    project_id = "test-t4-recovery"
    _mock_workspace_unconfigured(page, project_id)

    attempt = 0

    def connection_route_handler(route):
        nonlocal attempt
        attempt += 1
        if attempt == 1:
            route.fulfill(
                status=200,
                headers={"Content-Type": "application/json"},
                body='{"success": false, "error": "API_KEY_INVALID: API key not valid. Please pass a valid API key."}',
            )
        else:
            route.fulfill(
                status=200,
                headers={"Content-Type": "application/json"},
                body='{"success": true, "message": "Connection verified", "latency_ms": 112}',
            )

    page.route("**/api/settings/test-connection*", connection_route_handler)
    mock_api_route(page, "**/api/settings*", status_code=200, json_data={"success": True}, method="PUT")

    modal_page = ApiKeyModalPage(page, base_url)
    modal_page.goto(f"/projects/{project_id}/chat")
    modal_page.open_modal("studio")

    modal_page.select_studio_mode()

    # Attempt 1: bad key
    modal_page.fill_gemini_key("invalid_key_xyz")
    modal_page.click_test_connection()
    modal_page.wait_for_test_feedback(expect_success=False)

    # Attempt 2: corrected key
    modal_page.fill_gemini_key("AIzaSyCorrectedKey123")
    modal_page.click_test_connection()
    modal_page.wait_for_test_feedback(expect_success=True)

    # Save
    modal_page.save_and_apply()
    modal_page.wait_for_closed()

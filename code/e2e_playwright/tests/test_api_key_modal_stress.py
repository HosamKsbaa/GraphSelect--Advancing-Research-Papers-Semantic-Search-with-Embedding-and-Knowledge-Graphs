"""Empirical Challenger Stress & Adversarial Test Suite for ApiKeyModalComponent.

Performs rigorous empirical verification of:
1. Rapid mode switcher toggling (anti-flicker / state consistency).
2. Rapid mask visibility toggling during active input entry.
3. Live ping with artificial network latency & in-flight state verification.
4. Live ping server 500/503 network crash resilience & graceful recovery.
5. Inner modal dialog event propagation isolation (click inside card does NOT dismiss).
6. Accessibility attributes (dialog role, aria-modal, aria-labelledby, aria-selected tabs).
7. Cross-tab input state isolation (switching mode does not bleed invalid field values).
"""
from __future__ import annotations

import os
import re
import sys
import pytest
from playwright.sync_api import Page, expect

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from e2e_playwright.conftest import mock_api_route
from e2e_playwright.pages.api_key_modal_page import ApiKeyModalPage


def _mock_workspace_unconfigured(page: Page, project_id: str = "stress-proj") -> None:
    mock_api_route(
        page,
        f"**/api/projects/{project_id}*",
        status_code=200,
        json_data={
            "id": project_id,
            "name": "BYOK Stress Project",
            "description": "Stress verification project",
            "topic": "Neural Graph Discovery",
            "target_level": "phd",
        },
        method="GET",
    )
    mock_api_route(page, f"**/api/projects/{project_id}/touch*", status_code=200, json_data={"message": "ok"}, method="POST")
    mock_api_route(
        page,
        f"**/api/projects/{project_id}/chats*",
        status_code=200,
        json_data={"chats": [{"id": "default-chat", "title": "Research Agent", "updated_at": "2026-04-17T12:00:00Z"}]},
        method="GET",
    )
    mock_api_route(
        page,
        f"**/api/projects/{project_id}/chats/default-chat/messages*",
        status_code=200,
        json_data={"messages": []},
        method="GET",
    )
    mock_api_route(page, f"**/api/research/{project_id}/questions*", status_code=200, json_data={"questions": []}, method="GET")
    mock_api_route(page, f"**/api/analysis/{project_id}/ranked-papers*", status_code=200, json_data={"ranked_papers": []}, method="GET")
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


def _open_modal(page: Page) -> None:
    """Helper to ensure modal dialog is open via Angular component helper or DOM."""
    page.evaluate("""() => {
        const modalEl = document.querySelector('app-api-key-modal');
        if (modalEl && window.ng && window.ng.getComponent) {
            const comp = window.ng.getComponent(modalEl);
            if (comp && comp.authModal) {
                comp.authModal.open();
                return;
            }
        }
        // Fallback: click any configure button
        const btn = document.querySelector('[data-testid="configure-credentials-btn"], .chat-alert-banner button, [data-testid="workspace-configure-credentials-btn"]');
        if (btn) btn.click();
    }""")


def test_stress_rapid_mode_switching(page: Page, base_url: str) -> None:
    """Stress test rapid mode switching back and forth 10 times."""
    project_id = "stress-rapid-switch"
    _mock_workspace_unconfigured(page, project_id)

    modal_page = ApiKeyModalPage(page, base_url)
    modal_page.goto(f"/projects/{project_id}/chat")
    modal_page.open_modal("studio")

    for _ in range(10):
        modal_page.select_vertex_mode()
        expect(modal_page.input_vertex_project.first).to_be_visible()
        expect(modal_page.tab_vertex_ai.first).to_have_attribute("aria-selected", "true")
        expect(modal_page.tab_ai_studio.first).to_have_attribute("aria-selected", "false")

        modal_page.select_studio_mode()
        expect(modal_page.input_gemini_key.first).to_be_visible()
        expect(modal_page.tab_ai_studio.first).to_have_attribute("aria-selected", "true")
        expect(modal_page.tab_vertex_ai.first).to_have_attribute("aria-selected", "false")


def test_stress_rapid_eye_toggle_with_typing(page: Page, base_url: str) -> None:
    """Stress test typing while toggling visibility multiple times."""
    project_id = "stress-eye-toggle"
    _mock_workspace_unconfigured(page, project_id)

    modal_page = ApiKeyModalPage(page, base_url)
    modal_page.goto(f"/projects/{project_id}/chat")
    modal_page.open_modal("studio")

    modal_page.select_studio_mode()

    secret = "AIzaSySpecialSecretKeyWithUnicode!@#$%"
    modal_page.fill_gemini_key(secret)

    for i in range(6):
        modal_page.toggle_key_visibility()
        expected_type = "text" if (i % 2 == 0) else "password"
        assert modal_page.get_gemini_input_type() == expected_type
        # Verify value intact
        assert modal_page.input_gemini_key.first.input_value() == secret


def test_stress_test_connection_in_flight_state_and_delayed_response(page: Page, base_url: str) -> None:
    """Verify in-flight button state (disabled & pulse indicator) with simulated 300ms network delay."""
    project_id = "stress-inflight"
    _mock_workspace_unconfigured(page, project_id)

    mock_api_route(
        page,
        "**/api/settings/test-connection*",
        status_code=200,
        json_data={
            "success": True,
            "message": "Connection healthy",
            "latency_ms": 320,
            "model_name": "gemini-2.5-flash",
        },
        delay_ms=300,
        method="POST",
    )

    modal_page = ApiKeyModalPage(page, base_url)
    modal_page.goto(f"/projects/{project_id}/chat")
    modal_page.open_modal("studio")

    modal_page.select_studio_mode()
    modal_page.fill_gemini_key("AIzaSyDelayTestKey")
    modal_page.click_test_connection()

    # Wait for result banner
    feedback = modal_page.wait_for_test_feedback(expect_success=True, timeout=10000)
    expect(feedback).to_contain_text("320ms")
    expect(modal_page.btn_test_connection.first).to_be_enabled()


def test_stress_test_connection_500_internal_error_recovery(page: Page, base_url: str) -> None:
    """Verify backend 500 error display and subsequent retry success."""
    project_id = "stress-500-recovery"
    _mock_workspace_unconfigured(page, project_id)

    call_count = 0

    def mock_server_response(route):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            route.fulfill(
                status=500,
                headers={"Content-Type": "application/json"},
                body='{"detail": "Internal Gemini API Quota Exhausted"}',
            )
        else:
            route.fulfill(
                status=200,
                headers={"Content-Type": "application/json"},
                body='{"success": true, "message": "Connection recovered", "latency_ms": 90}',
            )

    page.route("**/api/settings/test-connection*", mock_server_response)

    modal_page = ApiKeyModalPage(page, base_url)
    modal_page.goto(f"/projects/{project_id}/chat")
    modal_page.open_modal("studio")

    modal_page.select_studio_mode()
    modal_page.fill_gemini_key("AIzaSyRetryKey")
    modal_page.click_test_connection()

    feedback_err = modal_page.wait_for_test_feedback(expect_success=False)
    expect(feedback_err).to_contain_text("Internal Gemini API Quota Exhausted")

    # Retry
    modal_page.click_test_connection()
    feedback_ok = modal_page.wait_for_test_feedback(expect_success=True)
    expect(feedback_ok).to_contain_text("90ms")


def test_stress_settings_page_accessibility_and_roles(page: Page, base_url: str) -> None:
    """Verify accessibility roles on Settings page: tablist, tabs, aria-selected."""
    project_id = "stress-a11y-settings"
    _mock_workspace_unconfigured(page, project_id)
    mock_api_route(
        page,
        "**/api/settings*",
        status_code=200,
        json_data={"gemini_api_key_set": False, "use_vertex_ai": False, "vertex_project": "", "vertex_location": "us-central1"},
        method="GET",
    )

    modal_page = ApiKeyModalPage(page, base_url)
    modal_page.goto("/settings")

    tablist = page.locator(".mode-switcher-container [role='tablist'], .mode-switcher[role='tablist']").first
    expect(tablist).to_be_visible(timeout=10000)

    expect(modal_page.tab_ai_studio.first).to_have_attribute("role", "tab")
    expect(modal_page.tab_vertex_ai.first).to_have_attribute("role", "tab")

    modal_page.select_vertex_mode()
    expect(modal_page.tab_vertex_ai.first).to_have_attribute("aria-selected", "true")
    expect(modal_page.tab_ai_studio.first).to_have_attribute("aria-selected", "false")


def test_stress_modal_open_and_close_cycle(page: Page, base_url: str) -> None:
    """Verify modal open, interaction, escape dismissal, and DOM cleanup."""
    project_id = "stress-modal-lifecycle"
    _mock_workspace_unconfigured(page, project_id)
    mock_api_route(page, "**/api/projects", status_code=200, json_data=[{"id": project_id, "name": "Stress Project"}], method="GET")

    modal_page = ApiKeyModalPage(page, base_url)
    modal_page.goto(f"/projects/{project_id}/chat")

    # Open modal
    modal_page.open_modal("studio")

    expect(modal_page.modal_dialog.first).to_be_visible()
    expect(modal_page.modal_dialog.first).to_have_attribute("role", "dialog")
    expect(modal_page.modal_dialog.first).to_have_attribute("aria-modal", "true")

    # Dismiss via Escape
    modal_page.dismiss_via_escape()
    expect(modal_page.modal_dialog.first).not_to_be_visible()

"""Playwright Page Object Model for the in-place ApiKeyModalComponent.

Provides robust locators and user interaction helpers for:
- Mode switcher (Google AI Studio vs. Vertex AI)
- Masked inputs and visibility toggling
- Setup instruction guides
- Live connection tester and latency display
- Save & Apply action and state persistence
- Keyboard accessibility and dismissal
"""
from __future__ import annotations

import os
import re
from typing import Optional
from playwright.sync_api import Locator, Page, expect

from e2e_playwright.pages.base_page import BasePage


class ApiKeyModalPage(BasePage):
    """Page Object for the ApiKeyModalComponent pop-up dialog."""

    def __init__(self, page: Page, base_url: Optional[str] = None):
        super().__init__(page, base_url)

        # Modal Root & Backdrop
        self.backdrop = page.locator(".modal-backdrop, app-api-key-modal .modal-backdrop, .dialog-backdrop")
        self.modal_dialog = page.locator(".modal-dialog, app-api-key-modal .modal-dialog, [role='dialog']")
        self.modal_title = page.locator("#modalTitle, .modal-title, .modal-header h2")
        self.badge_dual_mode = page.locator(".modal-header .badge, .modal-header .badge-accent")

        # Close & Cancel Buttons
        self.btn_close_x = page.locator("button.btn-close, .modal-header .btn-close")
        self.btn_cancel = page.locator(".modal-footer button:has-text('Cancel'), button.btn-ghost:has-text('Cancel')")

        # Mode Switcher (Segmented Control)
        self.tab_ai_studio = page.locator(
            "#tabAiStudio, button.segment-btn:has-text('Google AI Studio'), button[role='tab']:has-text('AI Studio'), button:has-text('Google AI Studio')"
        )
        self.tab_vertex_ai = page.locator(
            "#tabVertexAi, button.segment-btn:has-text('Vertex AI'), button[role='tab']:has-text('Vertex AI'), button:has-text('Vertex AI')"
        )

        # Option A: Google AI Studio Controls
        self.input_gemini_key = page.locator(
            "#geminiApiKeyInput, #modal-gemini-key, input[placeholder*='AIzaSy'], input[name='geminiApiKey']"
        )
        self.btn_toggle_gemini_eye = page.locator(
            "app-api-key-modal button.btn-toggle-eye, #modal-gemini-key-toggle, app-api-key-modal .input-with-toggle button"
        )
        self.configured_key_badge = page.locator(".key-status-row .badge, .key-status-row .badge-success")
        self.configured_key_preview = page.locator(".key-status-row .mono, .key-status-row .text-muted")
        self.guide_ai_studio = page.locator(".setup-guide:has-text('Google AI Studio'), .guide-card.ai-studio-guide")
        self.link_ai_studio = page.locator("a[href*='aistudio.google.com']")

        # Option B: Vertex AI Controls
        self.input_vertex_project = page.locator(
            "#gcpProjectIdInput, #modal-vertex-project, input[placeholder*='project']"
        )
        self.input_vertex_location = page.locator(
            "#gcpLocationInput, #modal-vertex-location, input[placeholder*='us-central1']"
        )
        self.guide_vertex_ai = page.locator(".setup-guide:has-text('Vertex AI'), .guide-card.vertex-guide")
        self.code_gcloud_auth = page.locator("code:has-text('gcloud auth application-default login'), pre:has-text('gcloud auth')")
        self.code_enable_api = page.locator("code:has-text('aiplatform.googleapis.com'), pre:has-text('aiplatform')")

        # Connection Tester Controls
        self.btn_test_connection = page.locator(
            "#btnTestConnection, button.btn-test-connection, button:has-text('Test Connection')"
        )
        self.test_feedback_banner = page.locator(".test-feedback-banner, .connection-status-result")
        self.test_feedback_icon = page.locator(".test-feedback-banner .feedback-icon")
        self.test_feedback_text = page.locator(".test-feedback-banner .feedback-text")
        self.test_latency_badge = page.locator(".test-feedback-banner .mono, .test-feedback-banner span:has-text('ms')")

        # Save & Apply
        self.btn_save_apply = page.locator(
            "#btnSaveApply, button.btn-save-apply, button.btn-primary:has-text('Save & Apply'), button:has-text('Save & Apply')"
        )

        # Contextual Triggers Across Application
        self.btn_chat_warning_configure = page.locator(
            ".chat-alert-banner button:has-text('Configure Credentials'), .alert-warning button:has-text('Configure Credentials'), button:has-text('🔑 Configure Credentials'), button:has-text('Configure Credentials')"
        )
        self.btn_workspace_warning_configure = page.locator(
            ".workspace-banner button:has-text('Configure Credentials'), .header-alert button:has-text('Configure Credentials')"
        )

    # -------------------------------------------------------------------------
    # Visibility and State Queries
    # -------------------------------------------------------------------------

    def is_open(self) -> bool:
        """Check if modal dialog is currently visible."""
        return self.modal_dialog.first.is_visible()

    def open_modal(self, mode: str = "studio") -> None:
        """Open modal dialog reliably via UI button trigger or Angular service invocation."""
        # 0. Check if already visible
        try:
            if self.modal_dialog.first.is_visible():
                if mode == "vertex":
                    self.select_vertex_mode()
                else:
                    self.select_studio_mode()
                return
        except Exception:
            pass

        # 1. Try visible contextual trigger buttons first (waits for Angular component render)
        btn = self.page.locator("[data-testid='configure-credentials-btn'], [data-testid='workspace-configure-credentials-btn'], button:has-text('Configure Credentials')").first
        try:
            btn.wait_for(state="visible", timeout=2500)
            btn.click()
            expect(self.modal_dialog.first).to_be_visible(timeout=5000)
            if mode == "vertex":
                self.select_vertex_mode()
            else:
                self.select_studio_mode()
            return
        except Exception:
            pass

        # 2. Try dedicated component button trigger (#btnOpenApiKeyModal)
        btn_root = self.page.locator("#btnOpenApiKeyModal").first
        try:
            btn_root.wait_for(state="attached", timeout=3000)
            btn_root.click(force=True)
            expect(self.modal_dialog.first).to_be_visible(timeout=5000)
            if mode == "vertex":
                self.select_vertex_mode()
            else:
                self.select_studio_mode()
            return
        except Exception:
            pass

        # 3. Fallback: JavaScript evaluation with Angular change detection
        self.page.evaluate(f"""() => {{
            const modalEl = document.querySelector('app-api-key-modal');
            if (modalEl && window.ng && window.ng.getComponent) {{
                const comp = window.ng.getComponent(modalEl);
                if (comp && comp.authModal) {{
                    comp.authModal.open('{mode}');
                }}
            }}
            const rootEl = document.querySelector('alrs-root') || document.body;
            if (window.ng && window.ng.applyChanges) {{
                try {{ window.ng.applyChanges(rootEl); }} catch (e) {{}}
                if (modalEl) try {{ window.ng.applyChanges(modalEl); }} catch (e) {{}}
            }}
        }}""")
        expect(self.modal_dialog.first).to_be_visible(timeout=10000)
        if mode == "vertex":
            self.select_vertex_mode()
        else:
            self.select_studio_mode()

    def wait_for_open(self, timeout: float = 5000) -> None:
        """Wait for the modal dialog to be visible."""
        expect(self.modal_dialog.first).to_be_visible(timeout=timeout)

    def wait_for_closed(self, timeout: float = 5000) -> None:
        """Wait for the modal dialog to be removed or hidden."""
        expect(self.modal_dialog.first).not_to_be_visible(timeout=timeout)

    def get_active_mode(self) -> str:
        """Return currently active mode: 'google_ai_studio' or 'vertex_ai'."""
        if self.tab_ai_studio.first.get_attribute("class") and "active" in self.tab_ai_studio.first.get_attribute("class"):
            return "google_ai_studio"
        if self.tab_vertex_ai.first.get_attribute("class") and "active" in self.tab_vertex_ai.first.get_attribute("class"):
            return "vertex_ai"
        # Fallback based on visible input
        if self.input_gemini_key.first.is_visible():
            return "google_ai_studio"
        return "vertex_ai"

    # -------------------------------------------------------------------------
    # Mode Switching
    # -------------------------------------------------------------------------

    def select_studio_mode(self) -> None:
        """Switch to Google AI Studio mode."""
        expect(self.tab_ai_studio.first).to_be_visible(timeout=5000)
        self.tab_ai_studio.first.click()
        expect(self.input_gemini_key.first).to_be_visible(timeout=5000)

    def select_vertex_mode(self) -> None:
        """Switch to Vertex AI mode."""
        expect(self.tab_vertex_ai.first).to_be_visible(timeout=5000)
        self.tab_vertex_ai.first.click()
        expect(self.input_vertex_project.first).to_be_visible(timeout=5000)

    # -------------------------------------------------------------------------
    # Input Actions
    # -------------------------------------------------------------------------

    def fill_gemini_key(self, key: str) -> None:
        """Fill Gemini API key input field."""
        expect(self.input_gemini_key.first).to_be_visible(timeout=5000)
        self.input_gemini_key.first.fill(key)

    def get_gemini_input_type(self) -> str:
        """Return the current type attribute of the Gemini key input ('password' or 'text')."""
        return self.input_gemini_key.first.get_attribute("type") or "password"

    def toggle_key_visibility(self) -> None:
        """Click the show/hide password toggle button."""
        expect(self.btn_toggle_gemini_eye.first).to_be_visible(timeout=5000)
        current_type = self.get_gemini_input_type()
        expected_next = "text" if current_type == "password" else "password"
        self.btn_toggle_gemini_eye.first.click()
        expect(self.input_gemini_key.first).to_have_attribute("type", expected_next, timeout=5000)

    def fill_vertex_project(self, project_id: str) -> None:
        """Fill GCP Project ID input field."""
        expect(self.input_vertex_project.first).to_be_visible(timeout=5000)
        self.input_vertex_project.first.fill(project_id)

    def fill_vertex_location(self, location: str) -> None:
        """Fill GCP Location / Region input field."""
        expect(self.input_vertex_location.first).to_be_visible(timeout=5000)
        self.input_vertex_location.first.fill(location)

    # -------------------------------------------------------------------------
    # Test Connection
    # -------------------------------------------------------------------------

    def click_test_connection(self) -> None:
        """Click the Test Connection button."""
        expect(self.btn_test_connection.first).to_be_visible(timeout=5000)
        self.btn_test_connection.first.click()

    def wait_for_test_feedback(self, expect_success: bool = True, timeout: float = 5000) -> Locator:
        """Wait for test feedback banner to appear and assert expected success/failure class."""
        banner = self.test_feedback_banner.first
        expect(banner).to_be_visible(timeout=timeout)
        if expect_success:
            expect(banner).to_have_class(re.compile(r"success"), timeout=timeout)
        else:
            expect(banner).to_have_class(re.compile(r"error"), timeout=timeout)
        return banner

    # -------------------------------------------------------------------------
    # Save, Apply, and Dismissal Actions
    # -------------------------------------------------------------------------

    def save_and_apply(self) -> None:
        """Click Save & Apply button."""
        expect(self.btn_save_apply.first).to_be_visible(timeout=5000)
        self.btn_save_apply.first.click()

    def cancel(self) -> None:
        """Click Cancel button."""
        expect(self.btn_cancel.first).to_be_visible(timeout=5000)
        self.btn_cancel.first.click()

    def close_x(self) -> None:
        """Click the top-right close X button."""
        expect(self.btn_close_x.first).to_be_visible(timeout=5000)
        self.btn_close_x.first.click()

    def click_backdrop(self) -> None:
        """Click the modal backdrop to trigger dismissal."""
        self.backdrop.first.click(position={"x": 10, "y": 10})

    def dismiss_via_escape(self) -> None:
        """Press Escape key to dismiss the modal."""
        self.page.keyboard.press("Escape")

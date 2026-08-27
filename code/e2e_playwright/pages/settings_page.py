from typing import Optional, Dict
from playwright.sync_api import Page, Locator, expect
from e2e_playwright.pages.base_page import BasePage


class SettingsPage(BasePage):
    """Page Object for the Settings View (/settings)."""

    def __init__(self, page: Page, base_url: Optional[str] = None):
        super().__init__(page, base_url)
        
        # Header
        self.page_title = page.locator("h1.page-title")
        
        # Backend Connection Section
        self.api_base_url_input = page.locator("#api-base-url")
        
        # API Keys Section
        self.gemini_key_input = page.locator("#gemini-key")
        self.gemini_toggle_btn = page.locator(".setting-row:has(#gemini-key) button.toggle-btn")
        self.gemini_status_badge = page.locator(".setting-row:has(#gemini-key) .setting-status .badge")
        
        self.openalex_key_input = page.locator("#openalex-key")
        self.openalex_toggle_btn = page.locator(".setting-row:has(#openalex-key) button.toggle-btn")
        self.openalex_status_badge = page.locator(".setting-row:has(#openalex-key) .setting-status .badge")
        
        # Contact Info Section
        self.openalex_email_input = page.locator("#openalex-email")
        
        # System Info Readout
        self.embedding_model_value = page.locator(".info-item:has(.info-label:has-text('Embedding Model')) .info-value")
        self.embedding_dims_value = page.locator(".info-item:has(.info-label:has-text('Dimensions')) .info-value")
        
        # Save Controls
        self.save_btn = page.locator("button.btn-save:has-text('Save Settings')")

    def navigate(self) -> None:
        """Navigate to the settings page."""
        self.goto("/settings")
        self.wait_for_url_match("**/settings")

    def set_gemini_key(self, key: str) -> None:
        """Enter Gemini API key."""
        expect(self.gemini_key_input).to_be_visible(timeout=5000)
        self.gemini_key_input.fill(key)

    def set_openalex_key(self, key: str) -> None:
        """Enter OpenAlex API key."""
        expect(self.openalex_key_input).to_be_visible(timeout=5000)
        self.openalex_key_input.fill(key)

    def set_contact_email(self, email: str) -> None:
        """Enter OpenAlex contact email."""
        expect(self.openalex_email_input).to_be_visible(timeout=5000)
        self.openalex_email_input.fill(email)

    def toggle_gemini_visibility(self) -> None:
        """Toggle Gemini API key password/text masking."""
        self.gemini_toggle_btn.click()

    def toggle_openalex_visibility(self) -> None:
        """Toggle OpenAlex API key password/text masking."""
        self.openalex_toggle_btn.click()

    def save_settings(self) -> None:
        """Click Save Settings button."""
        expect(self.save_btn).to_be_visible(timeout=5000)
        self.save_btn.click()

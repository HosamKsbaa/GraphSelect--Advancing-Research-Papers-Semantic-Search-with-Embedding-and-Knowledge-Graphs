import os
from typing import List, Optional, Dict, Any
from playwright.sync_api import Page, Locator, expect


class BasePage:
    """Base class for all Playwright Page Objects with common interaction methods."""

    def __init__(self, page: Page, base_url: Optional[str] = None):
        self.page = page
        self.base_url = base_url or os.environ.get("ALRS_BASE_URL", "http://localhost:4200")
        
        # Global Navigation Locators
        self.app_shell = page.locator(".app-shell")
        self.sidebar = page.locator("aside.sidebar")
        self.logo_title = page.locator(".logo-title")
        self.logo_version = page.locator(".logo-version")
        self.health_indicator = page.locator(".sidebar-footer .health-indicator")
        
        # Sidebar Links
        self.nav_projects = page.locator("a[routerLink='/projects'], a[href='/projects']")
        self.nav_search = page.locator("a[routerLink='/search'], a[href='/search']")
        self.nav_system_status = page.locator("a[routerLink='/system-status'], a[href='/system-status']")
        self.nav_logs = page.locator("a[routerLink='/logs'], a[href='/logs']")
        self.nav_debug = page.locator("a[routerLink='/debug'], a[href='/debug']")
        self.nav_settings = page.locator("a[routerLink='/settings'], a[href='/settings']")
        
        # Global Toast Container
        self.toast_container = page.locator("alrs-toast-container")
        self.toasts = page.locator("alrs-toast-container .toast")
        self.toast_messages = page.locator("alrs-toast-container .toast-message")
        self.toast_titles = page.locator("alrs-toast-container .toast-title")
        self.toast_close_buttons = page.locator("alrs-toast-container .toast-close")

    def goto(self, path: str = "") -> None:
        """Navigate to a relative path from the base URL."""
        target_url = f"{self.base_url.rstrip('/')}/{path.lstrip('/')}"
        self.page.goto(target_url, wait_until="commit")

    def wait_for_url_match(self, pattern: str, timeout: float = 15000) -> None:
        """Wait for page URL to match the expected glob or regex pattern."""
        self.page.wait_for_url(pattern, timeout=timeout, wait_until="commit")

    def get_page_title(self) -> str:
        """Get the text content of the primary h1 heading."""
        heading = self.page.locator("h1").first
        expect(heading).to_be_visible(timeout=5000)
        return heading.inner_text().strip()

    # Sidebar Navigation Helpers
    def navigate_to_projects(self) -> None:
        """Click sidebar link for Projects."""
        self.nav_projects.click()
        self.wait_for_url_match("**/projects")

    def navigate_to_search(self) -> None:
        """Click sidebar link for New Search."""
        self.nav_search.click()
        self.wait_for_url_match("**/search")

    def navigate_to_system_status(self) -> None:
        """Click sidebar link for System Status."""
        self.nav_system_status.click()
        self.wait_for_url_match("**/system-status")

    def navigate_to_logs(self) -> None:
        """Click sidebar link for API Logs."""
        self.nav_logs.click()
        self.wait_for_url_match("**/logs")

    def navigate_to_debug(self) -> None:
        """Click sidebar link for Debug."""
        self.nav_debug.click()
        self.wait_for_url_match("**/debug")

    def navigate_to_settings(self) -> None:
        """Click sidebar link for Settings."""
        self.nav_settings.click()
        self.wait_for_url_match("**/settings")

    # Toast Notifications
    def wait_for_toast(
        self,
        expected_title_substring: str = "",
        expected_text_substring: str = "",
        timeout: float = 5000
    ) -> Locator:
        """Wait for a toast to appear, asserting zero [object Object] anomalies."""
        toast = self.toasts.first
        expect(toast).to_be_visible(timeout=timeout)
        
        title_text = ""
        msg_text = ""
        
        if self.toast_titles.count() > 0:
            title_text = self.toast_titles.first.inner_text()
            assert "[object Object]" not in title_text, f"Toast title contains [object Object]: '{title_text}'"
            if expected_title_substring:
                assert expected_title_substring.lower() in title_text.lower(), (
                    f"Expected '{expected_title_substring}' in toast title '{title_text}'"
                )
                
        if self.toast_messages.count() > 0:
            msg_text = self.toast_messages.first.inner_text()
            assert "[object Object]" not in msg_text, f"Toast message contains [object Object]: '{msg_text}'"
            if expected_text_substring:
                assert expected_text_substring.lower() in msg_text.lower(), (
                    f"Expected '{expected_text_substring}' in toast message '{msg_text}'"
                )
                
        return toast

    def get_all_toast_texts(self) -> List[str]:
        """Return text contents of all currently rendered toast notifications."""
        texts = []
        count = self.toasts.count()
        for i in range(count):
            toast_text = self.toasts.nth(i).inner_text().strip()
            assert "[object Object]" not in toast_text, f"Detected [object Object] in toast: {toast_text}"
            texts.append(toast_text)
        return texts

    # Modal Dismissal & Keyboard Helpers
    def dismiss_modal_via_escape(self, modal_selector: str = ".modal-backdrop, .modal-container, .dialog-backdrop") -> None:
        """Dismiss an open modal or dialog using the Escape key."""
        modal = self.page.locator(modal_selector).first
        expect(modal).to_be_visible(timeout=5000)
        self.page.keyboard.press("Escape")
        expect(modal).not_to_be_visible(timeout=5000)

    # Screenshot Helper
    def capture_screenshot(self, name: str) -> str:
        """Capture screenshot to the screenshots directory."""
        screenshot_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "screenshots")
        os.makedirs(screenshot_dir, exist_ok=True)
        screenshot_path = os.path.join(screenshot_dir, f"{name}.png")
        self.page.screenshot(path=screenshot_path, full_page=True)
        return screenshot_path

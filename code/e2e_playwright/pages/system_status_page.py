from typing import List, Optional, Dict, Any
from playwright.sync_api import Page, Locator, expect
from e2e_playwright.pages.base_page import BasePage


class SystemStatusPage(BasePage):
    """Page Object for the System Status View (/system-status)."""

    def __init__(self, page: Page, base_url: Optional[str] = None):
        super().__init__(page, base_url)
        
        # Header
        self.page_title = page.locator("h1.page-title")
        self.new_search_btn = page.locator(".page-header a:has-text('New Search')")
        
        # Health & Metric Cards
        self.status_cards = page.locator(".status-card")
        self.system_status_badge = page.locator(".status-card:has(span:has-text('System Status')) .status-value .badge")
        self.neo4j_status_badge = page.locator(".detail-row:has(span:has-text('Neo4j')) .badge")
        self.mysql_status_badge = page.locator(".detail-row:has(span:has-text('MySQL')) .badge")
        self.version_display = page.locator(".version-display")
        self.sessions_count_display = page.locator(".status-card:has(span:has-text('Sessions')) .stat-number")
        
        # Error & Recent Sessions
        self.error_banner = page.locator(".error-banner")
        self.recent_sessions_grid = page.locator(".sessions-grid")
        self.session_cards = page.locator(".sessions-grid .session-card")
        self.session_seed_dois = page.locator(".session-card .session-header .mono")
        self.session_status_badges = page.locator(".session-card .session-header .badge")
        self.empty_sessions_state = page.locator(".system-status .empty-state")

    def navigate(self) -> None:
        """Navigate to the system status page."""
        self.goto("/system-status")
        self.wait_for_url_match("**/system-status")

    def get_system_health(self) -> str:
        """Return system health status badge text ('healthy', 'degraded', etc.)."""
        expect(self.system_status_badge).to_be_visible(timeout=10000)
        return self.system_status_badge.inner_text().strip()

    def get_neo4j_status(self) -> str:
        """Return Neo4j connection status text."""
        expect(self.neo4j_status_badge).to_be_visible(timeout=10000)
        return self.neo4j_status_badge.inner_text().strip()

    def get_mysql_status(self) -> str:
        """Return MySQL connection status text."""
        expect(self.mysql_status_badge).to_be_visible(timeout=10000)
        return self.mysql_status_badge.inner_text().strip()

    def get_version(self) -> str:
        """Return application version string."""
        expect(self.version_display).to_be_visible(timeout=5000)
        return self.version_display.inner_text().strip()

    def get_sessions_count(self) -> int:
        """Return total recent sessions count from metric card."""
        expect(self.sessions_count_display).to_be_visible(timeout=5000)
        return int(self.sessions_count_display.inner_text().strip())

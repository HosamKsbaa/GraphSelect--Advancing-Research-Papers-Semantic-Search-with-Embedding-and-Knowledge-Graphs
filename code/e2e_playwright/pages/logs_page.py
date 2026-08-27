from typing import List, Optional, Dict, Any
from playwright.sync_api import Page, Locator, expect
from e2e_playwright.pages.base_page import BasePage


class LogsPage(BasePage):
    """Page Object for the Logs & Monitoring View (/logs)."""

    def __init__(self, page: Page, base_url: Optional[str] = None):
        super().__init__(page, base_url)
        
        # Header
        self.page_title = page.locator("h1.page-title")
        
        # Tabs
        self.tab_app_logs = page.locator(".tabs-header button:has-text('Application Logs')")
        self.tab_api_logs = page.locator(".tabs-header button:has-text('Scholarly API Requests')")
        self.tab_agent_traces = page.locator(".tabs-header button:has-text('Agent Traces')")
        
        # Filter Controls
        self.level_select = page.locator("#level-select")
        self.service_select = page.locator("#service-select")
        self.project_select = page.locator("#project-select")
        self.agent_name_input = page.locator("#agent-name")
        self.since_date_input = page.locator("#since-date")
        self.end_date_input = page.locator("#end-date")
        self.limit_select = page.locator("#limit-select")
        self.refresh_btn = page.locator("button:has-text('Refresh Console')")
        
        # Logs Console & Tables
        self.terminal_console = page.locator(".terminal-console")
        self.logs_table = page.locator("table.logs-table")
        self.log_rows = page.locator("table.logs-table tbody tr.log-row")
        self.empty_logs_msg = page.locator(".empty-logs")
        self.trace_cards = page.locator(".trace-card")

    def navigate(self) -> None:
        """Navigate to the logs & monitoring page."""
        self.goto("/logs")
        self.wait_for_url_match("**/logs")
        expect(self.page_title).to_be_visible(timeout=15000)

    def switch_tab(self, tab_name: str) -> None:
        """Switch logs tab ('app', 'api', 'agent')."""
        tab_lower = tab_name.lower()
        if "app" in tab_lower:
            self.tab_app_logs.click()
        elif "api" in tab_lower:
            self.tab_api_logs.click()
        elif "agent" in tab_lower or "trace" in tab_lower:
            self.tab_agent_traces.click()
        else:
            raise ValueError(f"Unknown logs tab: {tab_name}")

    def filter_by_level(self, level: str = "INFO") -> None:
        """Filter Application Logs by severity level ('DEBUG', 'INFO', 'WARNING', 'ERROR')."""
        self.level_select.select_option(level)

    def filter_by_service(self, service: str = "OpenAlex") -> None:
        """Filter Scholarly API logs by service ('OpenAlex', 'OpenCitations', 'Gemini')."""
        self.service_select.select_option(service)

    def click_refresh(self) -> None:
        """Click the Refresh Console button."""
        expect(self.refresh_btn).to_be_visible(timeout=5000)
        self.refresh_btn.click()

    def get_log_row_count(self) -> int:
        """Return the number of log rows displayed."""
        return self.log_rows.count()

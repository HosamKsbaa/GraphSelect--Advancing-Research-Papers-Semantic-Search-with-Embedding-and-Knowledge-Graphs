from typing import Optional
from playwright.sync_api import Page, Locator, expect
from e2e_playwright.pages.base_page import BasePage


class ProjectWorkspacePage(BasePage):
    """Page Object for the Project Workspace container and sub-navigation (/projects/:id)."""

    def __init__(self, page: Page, base_url: Optional[str] = None):
        super().__init__(page, base_url)
        
        # Workspace Navigation
        self.workspace_layout = page.locator(".workspace-layout")
        self.workspace_nav = page.locator(".workspace-nav")
        self.api_key_warning = page.locator(".alert-banner.warning")
        
        # Tabs
        self.tab_research = page.locator("a.tab-link:has-text('Research')")
        self.tab_analysis = page.locator("a.tab-link:has-text('Analysis')")
        self.tab_planning = page.locator("a.tab-link:has-text('Planning')")
        self.tab_writing = page.locator("a.tab-link:has-text('Writing')")
        self.tab_export = page.locator("a.tab-link:has-text('Export')")
        self.all_tabs = page.locator(".workspace-nav a.tab-link")
        
        # Folder Path Popover
        self.open_folder_btn = page.locator("button:has-text('Open Folder')")
        self.folder_popover = page.locator(".folder-popover")
        self.path_input = page.locator(".folder-popover input.path-input")
        self.copy_path_btn = page.locator(".folder-popover button.btn-copy")
        self.close_popover_btn = page.locator(".folder-popover button.btn-close")

    def navigate(self, project_id: str, tab: str = "research") -> None:
        """Navigate directly to a project's workspace tab."""
        self.goto(f"/projects/{project_id}/{tab}")
        self.wait_for_url_match(f"**/projects/{project_id}/**")

    def switch_tab(self, tab_name: str) -> None:
        """Switch to a specific workspace tab ('Research', 'Analysis', 'Planning', 'Writing', 'Export')."""
        tab_lower = tab_name.lower().strip()
        tab_locator = self.page.locator(f"a.tab-link:has-text('{tab_name.title()}')")
        expect(tab_locator).to_be_visible(timeout=5000)
        tab_locator.click()
        self.wait_for_url_match(f"**/{tab_lower}")

    def is_api_key_warning_visible(self) -> bool:
        """Check if Gemini API key warning banner is visible."""
        return self.api_key_warning.is_visible()

    def open_folder_popover(self) -> None:
        """Open the project folder path popover."""
        self.open_folder_btn.click()
        expect(self.folder_popover).to_be_visible(timeout=5000)

    def close_folder_popover(self) -> None:
        """Close the project folder path popover."""
        self.close_popover_btn.click()
        expect(self.folder_popover).not_to_be_visible(timeout=5000)

    def get_project_path(self) -> str:
        """Retrieve the project directory path shown in the popover."""
        if not self.folder_popover.is_visible():
            self.open_folder_popover()
        expect(self.path_input).to_be_visible(timeout=5000)
        return self.path_input.input_value()

    def copy_project_path(self) -> None:
        """Click copy project path button."""
        if not self.folder_popover.is_visible():
            self.open_folder_popover()
        self.copy_path_btn.click()

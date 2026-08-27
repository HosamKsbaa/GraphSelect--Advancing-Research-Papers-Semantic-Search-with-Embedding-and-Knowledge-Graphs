from typing import List, Optional
from playwright.sync_api import Page, Locator, expect
from e2e_playwright.pages.base_page import BasePage


class ProjectListPage(BasePage):
    """Page Object for the Projects Management View (/projects)."""

    def __init__(self, page: Page, base_url: Optional[str] = None):
        super().__init__(page, base_url)
        
        # Header Controls
        self.page_header = page.locator(".page-header")
        self.show_archived_toggle = page.locator("label.toggle-switch")
        self.show_archived_checkbox = page.locator("label.toggle-switch input[type='checkbox']")
        self.new_project_btn = page.locator("button.btn.btn-primary:has-text('New Project'), button:has-text('Create Your First Project')").first
        self.search_input = page.locator(".search-bar input[type='text']")
        
        # Empty State
        self.empty_state = page.locator("app-empty-state")
        self.empty_state_cta = page.locator("app-empty-state button, app-empty-state a").first
        self.no_results_message = page.locator(".no-results")
        
        # Project Groups & Cards
        self.project_groups = page.locator(".project-group")
        self.master_group = page.locator(".project-group:has(h2:has-text('Master Level'))")
        self.phd_group = page.locator(".project-group:has(h2:has-text('PhD Level'))")
        self.archived_group = page.locator(".project-group.archived")
        self.project_cards = page.locator(".project-card")
        
        # Create Project Modal
        self.modal_backdrop = page.locator(".modal-backdrop")
        self.modal_container = page.locator(".modal-container")
        self.project_name_input = page.locator("#projectName")
        self.project_topic_input = page.locator("#projectTopic")
        self.target_level_select = page.locator("#targetLevel")
        self.project_desc_input = page.locator("#projectDesc")
        self.submit_create_btn = page.locator("button[type='submit']:has-text('Create Project')")
        self.cancel_create_btn = page.locator(".modal-footer button:has-text('Cancel'), .modal-header button.btn-ghost")

    def navigate(self) -> None:
        """Navigate to the /projects route."""
        self.goto("/projects")
        self.wait_for_url_match("**/projects")

    def is_empty_state_visible(self) -> bool:
        """Check if empty state is visible."""
        return self.empty_state.is_visible()

    def open_create_dialog(self) -> None:
        """Open the new project modal dialog."""
        self.new_project_btn.click()
        expect(self.modal_container).to_be_visible(timeout=5000)

    def close_create_dialog(self) -> None:
        """Close the project creation dialog by clicking cancel."""
        self.cancel_create_btn.first.click()
        expect(self.modal_container).not_to_be_visible(timeout=5000)

    def fill_create_project_form(
        self,
        name: str,
        topic: str = "",
        target_level: str = "master",
        description: str = ""
    ) -> None:
        """Fill all fields in the create project dialog."""
        self.project_name_input.fill(name)
        if topic:
            self.project_topic_input.fill(topic)
        if target_level:
            self.target_level_select.select_option(target_level)
        if description:
            self.project_desc_input.fill(description)

    def submit_create_project(self) -> None:
        """Click create project submit button."""
        self.submit_create_btn.click()

    def create_project(
        self,
        name: str,
        topic: str = "",
        target_level: str = "master",
        description: str = ""
    ) -> None:
        """Perform full project creation flow."""
        self.open_create_dialog()
        self.fill_create_project_form(name, topic, target_level, description)
        self.submit_create_project()

    def search_projects(self, query: str) -> None:
        """Filter projects using the search bar."""
        self.search_input.fill(query)

    def toggle_show_archived(self) -> None:
        """Toggle the Show Archived checkbox."""
        self.show_archived_toggle.click()

    def get_project_card(self, name_or_pattern: str) -> Locator:
        """Get a specific project card by title/name."""
        return self.project_cards.filter(has_text=name_or_pattern).first

    def click_project(self, name_or_pattern: str) -> None:
        """Click a project card to open its workspace."""
        card = self.get_project_card(name_or_pattern)
        expect(card).to_be_visible(timeout=5000)
        card.click()
        self.wait_for_url_match("**/projects/**")

    def archive_project(self, name_or_pattern: str) -> None:
        """Archive a project via its card archive icon button."""
        card = self.get_project_card(name_or_pattern)
        expect(card).to_be_visible(timeout=5000)
        archive_btn = card.locator("button[title='Archive Project']")
        archive_btn.click()

from typing import List, Optional, Dict, Any
from playwright.sync_api import Page, Locator, expect
from e2e_playwright.pages.base_page import BasePage


class PlanningTabPage(BasePage):
    """Page Object for the Planning Tab (/projects/:id/planning)."""

    def __init__(self, page: Page, base_url: Optional[str] = None):
        super().__init__(page, base_url)
        
        # Container & States
        self.container = page.locator(".planning-container")
        self.empty_state = page.locator(".planning-container app-empty-state")
        self.loading_indicator = page.locator(".planning-container app-loading-indicator")
        
        # Readiness Summary Card
        self.readiness_card = page.locator(".readiness-summary")
        self.papers_stat_value = page.locator(".stat-item:has(.label:has-text('Papers')) .value")
        self.questions_stat_value = page.locator(".stat-item:has(.label:has-text('Questions')) .value")
        self.gaps_stat_value = page.locator(".stat-item:has(.label:has-text('Gaps')) .value")
        self.outline_stat_icon = page.locator(".stat-item:has(.label:has-text('Outline')) .status .icon")
        self.drafts_stat_icon = page.locator(".stat-item:has(.label:has-text('Drafts')) .status .icon")
        self.open_config_btn = page.locator(".readiness-summary button:has-text('Generate Outline')")
        
        # Outline Configuration Dialog
        self.config_dialog = page.locator(".dialog-backdrop")
        self.style_select = page.locator("#style")
        self.num_sections_input = page.locator("#numSections")
        self.confirm_generate_btn = page.locator(".dialog-actions button.primary:has-text('Generate')")
        self.cancel_config_btn = page.locator(".dialog-actions button.secondary:has-text('Cancel')")
        
        # Generated Outline List
        self.outline_list = page.locator(".outline-list")
        self.section_cards = page.locator(".outline-list .section-card")
        self.section_orders = page.locator(".outline-list .section-order")
        self.section_titles = page.locator(".outline-list h4")
        self.section_descriptions = page.locator(".outline-list .description")
        self.assigned_papers = page.locator(".outline-list .assigned-papers")
        self.regenerate_section_btns = page.locator(".section-actions button:has-text('Regenerate')")
        self.approve_section_btns = page.locator(".section-actions button:has-text('Approve')")

    def navigate(self, project_id: str) -> None:
        """Navigate to the planning tab for a project."""
        self.goto(f"/projects/{project_id}/planning")
        self.wait_for_url_match(f"**/projects/{project_id}/planning")
        expect(self.container).to_be_visible(timeout=15000)
        expect(self.readiness_card).to_be_visible(timeout=15000)

    def open_outline_dialog(self) -> None:
        """Open outline configuration dialog."""
        expect(self.open_config_btn).to_be_visible(timeout=5000)
        self.open_config_btn.click()
        expect(self.config_dialog).to_be_visible(timeout=5000)

    def close_outline_dialog(self) -> None:
        """Close outline configuration dialog."""
        self.cancel_config_btn.click()
        expect(self.config_dialog).not_to_be_visible(timeout=5000)

    def configure_and_generate_outline(
        self,
        style: str = "academic",
        num_sections: int = 5
    ) -> None:
        """Set style, section count and generate outline."""
        self.open_outline_dialog()
        self.style_select.select_option(style)
        self.num_sections_input.fill(str(num_sections))
        self.confirm_generate_btn.click()

    def get_section_count(self) -> int:
        """Return number of generated outline sections."""
        return self.section_cards.count()

    def approve_section(self, index: int = 0) -> None:
        """Click approve on outline section card."""
        btn = self.approve_section_btns.nth(index)
        btn.click()

    def regenerate_section(self, index: int = 0) -> None:
        """Click regenerate on outline section card."""
        btn = self.regenerate_section_btns.nth(index)
        btn.click()

from typing import List, Optional, Dict, Any
from playwright.sync_api import Page, Locator, expect
from e2e_playwright.pages.base_page import BasePage


class ResearchTabPage(BasePage):
    """Page Object for the Research Tab (/projects/:id/research)."""

    def __init__(self, page: Page, base_url: Optional[str] = None):
        super().__init__(page, base_url)
        
        # Container
        self.container = page.locator(".research-workspace")
        
        # Left Sidebar (Questions)
        self.question_input = page.locator("#inputQuestion")
        self.add_question_btn = page.locator("#btnAddQuestion")
        self.question_list = page.locator(".question-list")
        self.question_items = page.locator(".question-list .question-item")
        self.question_texts = page.locator(".question-list .question-text")
        self.question_status_icons = page.locator(".question-list .status-icon")
        self.question_coverage_badges = page.locator(".question-list .coverage-badge")
        self.delete_question_btns = page.locator(".question-list .delete-btn")
        self.questions_empty_state = page.locator(".left-sidebar app-empty-state")
        
        # Delete Confirmation Modal
        self.confirm_delete_modal = page.locator(".modal-overlay")
        self.confirm_delete_btn = page.locator(".modal-overlay button.btn-danger")
        self.cancel_delete_btn = page.locator(".modal-overlay button.btn-cancel")
        
        # Center (Paper Library)
        self.toggle_mode_btn = page.locator(".toggle-mode-btn")
        self.search_input = page.locator(".search-section input")
        self.search_web_btn = page.locator(".search-section .search-btn")
        self.library_filter_input = page.locator(".filter-input")
        self.paper_table = page.locator("table.paper-table")
        self.paper_rows = page.locator("table.paper-table tbody tr.paper-row")
        self.detail_rows = page.locator("table.paper-table tbody tr.detail-row")
        self.library_empty_state = page.locator(".library-section app-empty-state")
        self.pagination_prev_btn = page.locator(".pagination button:has-text('Previous')")
        self.pagination_next_btn = page.locator(".pagination button:has-text('Next')")
        self.pagination_label = page.locator(".pagination span")
        
        # Right Sidebar (Top Authors & Venues)
        self.top_authors_widget = page.locator(".right-sidebar .widget:has(h3:has-text('Top Authors'))")
        self.top_authors_items = page.locator(".right-sidebar .widget:has(h3:has-text('Top Authors')) ul.ranked-list li")
        self.top_venues_widget = page.locator(".right-sidebar .widget:has(h3:has-text('Top Venues'))")
        self.top_venues_items = page.locator(".right-sidebar .widget:has(h3:has-text('Top Venues')) ul.ranked-list li")

    def navigate(self, project_id: str) -> None:
        """Navigate to the research tab for a specific project."""
        self.goto(f"/projects/{project_id}/research")
        self.wait_for_url_match(f"**/projects/{project_id}/research")
        expect(self.container).to_be_visible(timeout=10000)

    # Research Questions Methods
    def add_research_question(self, question_text: str) -> None:
        """Add a new research question via left sidebar input."""
        expect(self.question_input).to_be_visible(timeout=5000)
        self.question_input.fill(question_text)
        self.add_question_btn.click()

    def get_question_texts(self) -> List[str]:
        """Return a list of all research question texts."""
        texts = []
        count = self.question_texts.count()
        for i in range(count):
            texts.append(self.question_texts.nth(i).inner_text().strip())
        return texts

    def delete_question(self, index: int = 0) -> None:
        """Click delete button for question at index and confirm."""
        self.delete_question_btns.nth(index).click()
        if self.confirm_delete_modal.is_visible():
            self.confirm_delete_btn.click()

    def toggle_search_mode(self) -> str:
        """Toggle between searching by Author and searching by Venue."""
        current = self.toggle_mode_btn.inner_text().strip()
        expected = "Venue" if "Author" in current else "Author"
        self.toggle_mode_btn.click()
        expect(self.toggle_mode_btn).to_contain_text(expected)
        return self.toggle_mode_btn.inner_text().strip()

    def search_web_papers(self, query: str) -> None:
        """Perform author or venue search from research tab."""
        self.search_input.fill(query)
        self.search_web_btn.click()

    def filter_library(self, text: str) -> None:
        """Filter current paper library table."""
        self.library_filter_input.fill(text)

    def get_paper_row_count(self) -> int:
        """Return the number of visible paper rows in the table."""
        return self.paper_rows.count()

    def toggle_paper_detail(self, index: int = 0) -> Locator:
        """Click a paper row to expand/collapse its details."""
        row = self.paper_rows.nth(index)
        row.click()
        return self.detail_rows.nth(index)

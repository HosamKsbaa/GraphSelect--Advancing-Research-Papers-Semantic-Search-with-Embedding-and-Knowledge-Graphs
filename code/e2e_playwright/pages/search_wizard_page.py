from typing import List, Optional, Dict, Any
from playwright.sync_api import Page, Locator, expect
from e2e_playwright.pages.base_page import BasePage


class SearchWizardPage(BasePage):
    """Page Object for the 4-step Literature Search Wizard (/search)."""

    def __init__(self, page: Page, base_url: Optional[str] = None):
        super().__init__(page, base_url)
        
        # Header & Step Indicators
        self.page_title = page.locator("h1.page-title")
        self.step_indicators = page.locator(".steps .step")
        self.step_find_paper = page.locator(".step:has-text('Find Paper')")
        self.step_questions = page.locator(".step:has-text('Questions')")
        self.step_crawl = page.locator(".step:has-text('Crawl')")
        self.step_results = page.locator(".step:has-text('Results')")
        self.error_banner = page.locator(".error-banner")
        
        # Step 1: Find Seed Paper
        self.seed_title_input = page.locator("input[placeholder*='Enter paper title']")
        self.seed_search_btn = page.locator(".search-input-row button.btn-primary")
        self.candidate_cards = page.locator(".candidates-list .candidate-card")
        self.candidate_titles = page.locator(".candidates-list .candidate-title")
        self.candidate_dois = page.locator(".candidates-list .candidate-meta .mono")
        
        # Step 2: Research Questions & Settings
        self.selected_paper_badge = page.locator(".selected-paper-badge")
        self.question_rows = page.locator(".questions-list .question-row")
        self.question_inputs = page.locator(".questions-list .question-row input")
        self.remove_question_btns = page.locator(".questions-list .question-row button.btn-ghost")
        self.add_question_btn = page.locator("button:has-text('+ Add Question')")
        self.similarity_slider = page.locator(".settings-grid input[type='range']")
        self.max_depth_select = page.locator(".setting-item:has(label:has-text('Max Depth')) select")
        self.mode_select = page.locator(".setting-item:has(label:has-text('Mode')) select")
        self.step2_back_btn = page.locator(".step-actions button:has-text('← Back')")
        self.step2_start_btn = page.locator(".step-actions button:has-text('Start Search →')")
        
        # Step 3: BFS Crawl Progress Monitor
        self.crawl_status_icon = page.locator(".crawl-status-icon")
        self.progress_bar_fill = page.locator(".progress-container .progress-fill")
        self.progress_text = page.locator(".progress-container .progress-text")
        self.session_info_details = page.locator(".result-details")
        self.event_log_items = page.locator(".event-log .event-item")
        self.view_results_btn = page.locator("button:has-text('View Results')")
        self.view_sessions_link = page.locator("a:has-text('View Sessions')")
        self.step3_new_search_btn = page.locator("button:has-text('+ New Search')")
        
        # Step 4: Search Results (alrs-results component)
        self.results_view = page.locator("alrs-results")
        self.results_session_id = page.locator(".control-panel .session-meta .meta-value")
        self.threshold_slider = page.locator("#threshold-slider")
        self.weight_slider = page.locator("#weight-slider")
        self.total_relevant_stat = page.locator(".quick-stats .stat-row .mono")
        self.project_selector = page.locator("#project-selector")
        self.import_selected_btn = page.locator("button.import-btn:has-text('Import Selected')")
        self.step4_reset_btn = page.locator("button.reset-btn:has-text('New Search')")
        self.question_tabs = page.locator(".question-tabs button.tab-btn")
        self.results_paper_cards = page.locator(".papers-list .paper-card")
        self.paper_checkboxes = page.locator(".papers-list input.paper-checkbox")
        self.score_rings = page.locator(".papers-list .score-ring .score-val")

    def navigate(self) -> None:
        """Navigate to the literature search page."""
        self.goto("/search")
        self.wait_for_url_match("**/search")

    # Step 1 Methods
    def search_seed_title(self, title: str) -> None:
        """Enter paper title and initiate resolution."""
        expect(self.seed_title_input).to_be_visible(timeout=5000)
        self.seed_title_input.fill(title)
        self.seed_search_btn.click()

    def select_candidate(self, index: int = 0) -> None:
        """Click candidate card to select paper DOI and proceed to Step 2."""
        card = self.candidate_cards.nth(index)
        expect(card).to_be_visible(timeout=10000)
        card.click()

    # Step 2 Methods
    def fill_research_questions(self, questions: List[str]) -> None:
        """Fill research questions inputs in Step 2."""
        for i, q in enumerate(questions):
            if i >= self.question_inputs.count() and self.question_inputs.count() < 6:
                self.add_question_btn.click()
            self.question_inputs.nth(i).fill(q)

    def start_search(self) -> None:
        """Click Start Search button in Step 2."""
        expect(self.step2_start_btn).to_be_visible(timeout=5000)
        self.step2_start_btn.click()

    # Step 3 Methods
    def wait_for_crawl_complete(self, timeout: float = 30000) -> None:
        """Wait for BFS crawl to complete."""
        expect(self.view_results_btn).to_be_visible(timeout=timeout)

    def click_view_results(self) -> None:
        """Click View Results button to proceed to Step 4."""
        self.view_results_btn.click()

    # Step 4 Methods
    def select_question_tab(self, index: int = 0) -> None:
        """Select a question tab in Step 4 results view."""
        tab = self.question_tabs.nth(index)
        tab.click()

    def toggle_paper_selection(self, index: int = 0) -> None:
        """Toggle checkbox for a paper card."""
        checkbox = self.paper_checkboxes.nth(index)
        checkbox.click()

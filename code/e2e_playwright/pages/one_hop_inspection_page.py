from typing import List, Optional
from playwright.sync_api import Page, Locator, expect
from e2e_playwright.pages.base_page import BasePage


class OneHopInspectionPage(BasePage):
    """Page Object Model for the 1-Hop HITL Inspection & Steering Interface."""

    def __init__(self, page: Page, base_url: Optional[str] = None):
        super().__init__(page, base_url)

        # Pre-flight summary locators
        self.preflight_container = page.locator(".preflight-summary-card, .preflight-container")
        self.preflight_seed_title = page.locator(".preflight-seed-title")
        self.preflight_seed_doi = page.locator(".preflight-seed-doi")
        self.preflight_active_rqs = page.locator(".preflight-active-rqs, .preflight-questions-section")
        self.btn_start_1hop = page.locator("button.btn-start-1hop, button:has-text('Start 1-Hop Traversal'), button:has-text('Start Search →')")

        # 1-Hop Results Inspection locators
        self.inspection_container = page.locator(".one-hop-inspection-container, .cycle-results-view")
        self.level_badge = page.locator(".level-badge")
        self.stat_discovered = page.locator(".stat-discovered .stat-num")
        self.stat_new = page.locator(".stat-new .stat-num")
        self.stat_avg_similarity = page.locator(".stat-avg-similarity .stat-num")

        # Strategic Appraisal & Recommendations
        self.strategic_section = page.locator(".strategic-appraisal-section")
        self.strategic_recommendation_text = page.locator(".strategic-recommendation-text")
        self.steering_option_chips = page.locator(".btn-steering-option")

        # Toolbar controls
        self.direction_select = page.locator(".filter-group:has(label:has-text('Direction')) select")
        self.status_select = page.locator(".filter-group:has(label:has-text('Library Status')) select")
        self.archetype_select = page.locator(".filter-group:has(label:has-text('Archetype')) select")
        self.sort_select = page.locator(".filter-group:has(label:has-text('Sort By')) select")
        self.filter_search_input = page.locator(".search-filter-group input")
        self.threshold_slider = page.locator(".threshold-slider-group input[type='range']")
        self.btn_select_all_visible = page.locator("button:has-text('Select All Visible')")
        self.btn_clear_selection = page.locator("button:has-text('Clear Selection')")

        # Candidate Paper Cards
        self.candidate_cards = page.locator(".candidate-paper-card, .paper-card-1hop")
        self.card_titles = page.locator(".candidate-paper-card .card-title, .paper-title")
        self.card_dois = page.locator(".candidate-paper-card .card-doi, .paper-doi")
        self.direction_badges = page.locator(".direction-badge")
        self.similarity_badges = page.locator(".similarity-badge")
        self.pagerank_badges = page.locator(".pagerank-badge")
        self.degree_badges = page.locator(".degree-badge")
        self.in_library_badges = page.locator(".badge-in-library")
        self.cached_badges = page.locator(".badge-cached")
        self.rq_score_bars = page.locator(".rq-score-bar")
        self.abstract_previews = page.locator(".abstract-preview")
        self.btn_toggle_abstracts = page.locator(".btn-toggle-abstract")
        self.candidate_checkboxes = page.locator(".candidate-checkbox")

        # Steering Action Buttons
        self.btn_add_to_project = page.locator("button.btn-add-project, button:has-text('Add to Project')")
        self.btn_expand_1hop = page.locator("button.btn-expand-hop, button:has-text('Expand 1 Hop Deeper')")
        self.btn_branch_seed = page.locator("button.btn-branch-seed, button:has-text('Branch to New Seed')")
        self.btn_conclude_synthesize = page.locator("button.btn-conclude, button:has-text('Conclude & Synthesize')")
        self.btn_batch_expand = page.locator("button.btn-batch-expand, button:has-text('Batch Expand Selected')")
        self.btn_reset_search = page.locator("button.btn-reset-search, button:has-text('Start Over')")

    def navigate_search(self) -> None:
        """Navigate to /search."""
        self.goto("/search")
        self.wait_for_url_match("**/search")

    def get_candidate_count(self) -> int:
        return self.candidate_cards.count()

    def get_card(self, index: int = 0) -> Locator:
        return self.candidate_cards.nth(index)

    def add_candidate_to_project(self, index: int = 0) -> None:
        card = self.get_card(index)
        btn = card.locator("button:has-text('Add to Project'), button.btn-add-project")
        btn.click()

    def expand_deeper_on_paper(self, index: int = 0) -> None:
        card = self.get_card(index)
        btn = card.locator("button:has-text('Expand 1 Hop Deeper'), button.btn-expand-hop")
        btn.click()

    def branch_as_new_seed(self, index: int = 0) -> None:
        card = self.get_card(index)
        btn = card.locator("button:has-text('Branch to New Seed'), button.btn-branch-seed")
        btn.click()

    def toggle_abstract(self, index: int = 0) -> None:
        card = self.get_card(index)
        btn = card.locator("button.btn-toggle-abstract")
        btn.click()

    def conclude_and_synthesize(self) -> None:
        self.btn_conclude_synthesize.click()

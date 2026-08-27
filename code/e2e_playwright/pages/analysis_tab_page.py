from typing import List, Optional, Dict, Any
from playwright.sync_api import Page, Locator, expect
from e2e_playwright.pages.base_page import BasePage


class AnalysisTabPage(BasePage):
    """Page Object for the Analysis Tab (/projects/:id/analysis)."""

    def __init__(self, page: Page, base_url: Optional[str] = None):
        super().__init__(page, base_url)
        
        # Container
        self.container = page.locator(".analysis-container")
        self.analysis_layout = page.locator(".analysis-layout")
        self.empty_state = page.locator(".analysis-container app-empty-state")
        self.loading_indicator = page.locator(".analysis-container app-loading-indicator")
        
        # Left Column: Research Question Coverage
        self.coverage_column = page.locator(".coverage-column")
        self.coverage_cards = page.locator(".coverage-card")
        self.coverage_question_texts = page.locator(".coverage-card .question-text")
        self.coverage_status_badges = page.locator(".coverage-card .status-badge")
        self.coverage_progress_bars = page.locator(".coverage-card .progress-bar")
        self.suggest_queries_btns = page.locator(".coverage-card button:has-text('Suggest Queries')")
        self.suggested_queries_container = page.locator(".suggested-queries")
        self.suggested_query_items = page.locator(".query-list .query-item")
        self.suggested_query_texts = page.locator(".query-list .query-text")
        self.copy_query_btns = page.locator(".query-list button[title='Copy to clipboard']")
        
        # Right Column: Insights & Stats
        self.insights_column = page.locator(".insights-column")
        self.stats_panel = page.locator(".stats-panel")
        self.total_papers_stat = page.locator(".stat-item:has(.stat-label:has-text('Total Papers')) .stat-value")
        self.avg_similarity_stat = page.locator(".stat-item:has(.stat-label:has-text('Avg Similarity')) .stat-value")
        self.network_density_stat = page.locator(".stat-item:has(.stat-label:has-text('Network Density')) .stat-value")
        
        # Ranked Literature Panel
        self.ranked_papers_panel = page.locator(".ranked-papers-panel")
        self.ranked_paper_rows = page.locator(".ranked-papers-panel .paper-row")
        self.ranked_paper_titles = page.locator(".ranked-papers-panel .paper-title")
        self.ranked_paper_scores = page.locator(".ranked-papers-panel .paper-scores")
        
        # Neo4j Polarity Subgraph (Consensus & Disputes)
        self.polarity_panel = page.locator(".polarity-panel")
        self.polarity_cards = page.locator(".polarity-card")
        self.polarity_supports_badge = page.locator(".polarity-card span:has-text('[SUPPORTS]')")
        self.polarity_contradicts_badge = page.locator(".polarity-card span:has-text('[CONTRADICTS]')")
        self.verified_edge_badge = page.locator(".badge:has-text('Verified Edge')")
        self.controversy_edge_badge = page.locator(".badge:has-text('Controversy Edge')")

    def navigate(self, project_id: str) -> None:
        """Navigate to the analysis tab for a project."""
        self.goto(f"/projects/{project_id}/analysis")
        self.wait_for_url_match(f"**/projects/{project_id}/analysis")

    def get_coverage_cards_count(self) -> int:
        """Return number of coverage cards."""
        return self.coverage_cards.count()

    def click_suggest_queries(self, card_index: int = 0) -> None:
        """Trigger LLM gap query suggestion for a specific question coverage card."""
        btn = self.suggest_queries_btns.nth(card_index)
        expect(btn).to_be_visible(timeout=5000)
        btn.click()

    def get_suggested_queries(self) -> List[str]:
        """Return list of suggested gap-filling query strings."""
        expect(self.suggested_queries_container.first).to_be_visible(timeout=10000)
        queries = []
        count = self.suggested_query_texts.count()
        for i in range(count):
            queries.append(self.suggested_query_texts.nth(i).inner_text().strip())
        return queries

    def get_ranked_paper_titles(self) -> List[str]:
        """Return titles of ranked literature."""
        titles = []
        count = self.ranked_paper_titles.count()
        for i in range(count):
            titles.append(self.ranked_paper_titles.nth(i).inner_text().strip())
        return titles

    def is_polarity_subgraph_visible(self) -> bool:
        """Check if Neo4j polarity subgraph consensus & disputes panel is visible."""
        return self.polarity_panel.is_visible()

from typing import Optional
from playwright.sync_api import Page, Locator, expect
from e2e_playwright.pages.base_page import BasePage


class DebugPage(BasePage):
    """Page Object for the Debug Diagnostics Console (/debug)."""

    def __init__(self, page: Page, base_url: Optional[str] = None):
        super().__init__(page, base_url)
        
        # Header
        self.page_title = page.locator("h1.page-title")
        
        # Panel 1: Paper Retrieval
        self.retrieve_panel = page.locator(".debug-panel:has(h2:has-text('Paper Retrieval'))")
        self.retrieve_doi_input = page.locator("#debug-doi")
        self.retrieve_run_btn = page.locator(".debug-panel:has(h2:has-text('Paper Retrieval')) button.btn-run")
        self.retrieve_result_card = page.locator(".debug-panel:has(h2:has-text('Paper Retrieval')) .result-card")
        self.retrieve_badge = page.locator(".debug-panel:has(h2:has-text('Paper Retrieval')) .result-badge")
        self.retrieve_title_value = page.locator(".debug-panel:has(h2:has-text('Paper Retrieval')) .result-field:has(.field-label:has-text('Title')) .field-value")
        
        # Panel 2: Text Embedding
        self.embed_panel = page.locator(".debug-panel:has(h2:has-text('Text Embedding'))")
        self.embed_textarea = page.locator("#debug-embed-text")
        self.embed_run_btn = page.locator(".debug-panel:has(h2:has-text('Text Embedding')) button.btn-run")
        self.embed_result_card = page.locator(".debug-panel:has(h2:has-text('Text Embedding')) .result-card")
        self.embed_badge = page.locator(".debug-panel:has(h2:has-text('Text Embedding')) .result-badge")
        self.embed_dims_value = page.locator(".debug-panel:has(h2:has-text('Text Embedding')) .result-field:has(.field-label:has-text('Dimensions')) .field-value")
        
        # Panel 3: Cosine Similarity
        self.sim_panel = page.locator(".debug-panel:has(h2:has-text('Cosine Similarity'))")
        self.sim_text_a = page.locator("#debug-sim-a")
        self.sim_text_b = page.locator("#debug-sim-b")
        self.sim_run_btn = page.locator(".debug-panel:has(h2:has-text('Cosine Similarity')) button.btn-run")
        self.sim_result_card = page.locator(".debug-panel:has(h2:has-text('Cosine Similarity')) .result-card")
        self.sim_badge = page.locator(".debug-panel:has(h2:has-text('Cosine Similarity')) .result-badge")
        self.sim_gauge_value = page.locator(".gauge-value")
        self.sim_gauge_fill = page.locator(".gauge-bar .gauge-fill")

    def navigate(self) -> None:
        """Navigate to the debug diagnostics page."""
        self.goto("/debug")
        self.wait_for_url_match("**/debug")
        expect(self.page_title).to_be_visible(timeout=15000)

    def test_paper_retrieval(self, doi: str) -> None:
        """Execute OpenAlex paper retrieval test."""
        expect(self.retrieve_doi_input).to_be_visible(timeout=5000)
        self.retrieve_doi_input.fill(doi)
        self.retrieve_run_btn.click()

    def test_text_embedding(self, text: str) -> None:
        """Execute Gemini text embedding test."""
        expect(self.embed_textarea).to_be_visible(timeout=5000)
        self.embed_textarea.fill(text)
        self.embed_run_btn.click()

    def test_cosine_similarity(self, text_a: str, text_b: str) -> None:
        """Execute semantic cosine similarity comparison test."""
        expect(self.sim_text_a).to_be_visible(timeout=5000)
        self.sim_text_a.fill(text_a)
        self.sim_text_b.fill(text_b)
        self.sim_run_btn.click()

from typing import List, Optional, Dict, Any
from playwright.sync_api import Page, Locator, expect
from e2e_playwright.pages.base_page import BasePage


class WritingTabPage(BasePage):
    """Page Object for the Writing Tab (/projects/:id/writing)."""

    def __init__(self, page: Page, base_url: Optional[str] = None):
        super().__init__(page, base_url)
        
        # Container & Banners
        self.container = page.locator(".writing-tab-container")
        self.export_banner = page.locator(".export-banner")
        self.go_to_export_link = page.locator(".export-banner a:has-text('Go to Export')")
        
        # Left Panel (Outline Sections)
        self.section_list = page.locator(".section-list")
        self.section_cards = page.locator(".section-list .section-card")
        self.section_titles = page.locator(".section-list .section-card h4")
        self.section_status_badges = page.locator(".section-list .section-card .badge")
        self.empty_sections_state = page.locator(".section-list app-empty-state")
        
        # Right Panel (Draft Workspace)
        self.draft_workspace = page.locator(".draft-workspace")
        self.workspace_title = page.locator(".workspace-header h3")
        self.workspace_desc = page.locator(".workspace-header .section-desc")
        self.hallucination_gate_badge = page.locator(".badge:has-text('0.0% Citation Hallucination Gate')")
        self.gcdl_loop_badge = page.locator(".badge:has-text('GCDL Inner Drafting Loop')")
        
        # Action Buttons
        self.draft_section_btn = page.locator(".workspace-header button:has-text('Draft Section')")
        self.review_section_btn = page.locator(".workspace-header button.btn-secondary")
        self.toggle_edit_btn = page.locator(".workspace-header button.btn-outline")
        
        # Editor & Preview
        self.markdown_editor = page.locator("textarea.markdown-editor")
        self.markdown_preview = page.locator("app-markdown-preview")
        self.loading_indicator = page.locator(".editor-area app-loading-indicator")
        
        # Review Feedback Panel
        self.feedback_panel = page.locator(".feedback-panel")
        self.feedback_status_badge = page.locator(".feedback-header .badge")
        self.issues_list = page.locator(".issue-list li")
        self.missing_citations_list = page.locator(".citation-list li")
        self.revision_count_text = page.locator(".revision-count")
        self.revise_btn = page.locator("button.revise-btn:has-text('Revise & Redraft')")

    def navigate(self, project_id: str) -> None:
        """Navigate to the writing tab for a project."""
        self.goto(f"/projects/{project_id}/writing")
        self.wait_for_url_match(f"**/projects/{project_id}/writing")
        expect(self.container).to_be_visible(timeout=15000)

    def select_section(self, index: int = 0) -> None:
        """Select a section from the left panel list."""
        card = self.section_cards.nth(index)
        expect(card).to_be_visible(timeout=5000)
        card.click()

    def click_draft_section(self) -> None:
        """Click Draft Section button to trigger generation."""
        expect(self.draft_section_btn).to_be_visible(timeout=5000)
        self.draft_section_btn.click()

    def click_review_section(self) -> None:
        """Click Review button to run citation verification and rubric checks."""
        expect(self.review_section_btn).to_be_visible(timeout=5000)
        self.review_section_btn.click()

    def toggle_edit_preview(self) -> None:
        """Toggle between Markdown editor and Markdown preview."""
        expect(self.toggle_edit_btn).to_be_visible(timeout=5000)
        self.toggle_edit_btn.click()

    def fill_markdown_editor(self, content: str) -> None:
        """Fill markdown editor content."""
        if not self.markdown_editor.is_visible():
            self.toggle_edit_preview()
        expect(self.markdown_editor).to_be_visible(timeout=5000)
        self.markdown_editor.fill(content)

    def click_revise_redraft(self) -> None:
        """Click Revise & Redraft button in feedback panel."""
        expect(self.revise_btn).to_be_visible(timeout=5000)
        self.revise_btn.click()

    def is_export_banner_visible(self) -> bool:
        """Check if all-approved export banner is visible."""
        return self.export_banner.is_visible()

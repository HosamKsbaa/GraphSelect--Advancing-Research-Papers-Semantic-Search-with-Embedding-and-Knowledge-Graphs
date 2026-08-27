from typing import Optional
from playwright.sync_api import Page, Locator, expect
from e2e_playwright.pages.base_page import BasePage


class ExportTabPage(BasePage):
    """Page Object for the Export Tab (/projects/:id/export)."""

    def __init__(self, page: Page, base_url: Optional[str] = None):
        super().__init__(page, base_url)
        
        # Container
        self.container = page.locator(".export-tab-container")
        self.loading_indicator = page.locator(".export-tab-container app-loading-indicator")
        
        # Export Cards Grid
        self.export_cards_grid = page.locator(".export-cards-grid")
        self.latex_card = page.locator(".export-card:has(h3:has-text('LaTeX Document'))")
        self.bibtex_card = page.locator(".export-card:has(h3:has-text('BibTeX References'))")
        self.graph_card = page.locator(".export-card:has(h3:has-text('Citation Graph'))")
        
        # Action Buttons on Cards
        self.export_latex_btn = page.locator("button:has-text('Export LaTeX')")
        self.export_bibtex_btn = page.locator("button:has-text('Export BibTeX')")
        self.export_graph_btn = page.locator("button:has-text('Export Graph')")
        
        # Disabled Prerequisites Messages
        self.latex_disabled_msg = page.locator(".export-card:has(h3:has-text('LaTeX Document')) .disabled-message")
        self.bibtex_disabled_msg = page.locator(".export-card:has(h3:has-text('BibTeX References')) .disabled-message")
        self.graph_disabled_msg = page.locator(".export-card:has(h3:has-text('Citation Graph')) .disabled-message")
        
        # LaTeX Template Selection Modal
        self.latex_modal = page.locator(".modal-backdrop:has(.modal-dialog)")
        self.latex_modal_dialog = page.locator(".modal-dialog")
        self.radio_ieee = page.locator("input[type='radio'][value='ieee']")
        self.radio_acm = page.locator("input[type='radio'][value='acm']")
        self.radio_plain = page.locator("input[type='radio'][value='plain']")
        self.confirm_export_btn = page.locator(".modal-footer button.btn-primary:has-text('Confirm Export')")
        self.cancel_modal_btn = page.locator(".modal-footer button.btn-secondary:has-text('Cancel')")
        self.close_modal_btn = page.locator(".modal-header button.btn-close")

    def navigate(self, project_id: str) -> None:
        """Navigate to the export tab for a project."""
        self.goto(f"/projects/{project_id}/export")
        self.wait_for_url_match(f"**/projects/{project_id}/export")

    def open_latex_dialog(self) -> None:
        """Open the LaTeX template selection dialog."""
        expect(self.export_latex_btn).to_be_visible(timeout=5000)
        self.export_latex_btn.click()
        expect(self.latex_modal_dialog).to_be_visible(timeout=5000)

    def close_latex_dialog(self) -> None:
        """Close the LaTeX template selection dialog."""
        self.cancel_modal_btn.click()
        expect(self.latex_modal_dialog).not_to_be_visible(timeout=5000)

    def select_latex_template(self, template: str = "ieee") -> None:
        """Select a LaTeX template format ('ieee', 'acm', 'plain')."""
        if template.lower() == "ieee":
            self.radio_ieee.check()
        elif template.lower() == "acm":
            self.radio_acm.check()
        elif template.lower() == "plain":
            self.radio_plain.check()
        else:
            raise ValueError(f"Unknown LaTeX template: {template}")

    def confirm_latex_export(self) -> None:
        """Click Confirm Export inside the LaTeX dialog."""
        self.confirm_export_btn.click()

    def export_latex(self, template: str = "ieee") -> None:
        """Full flow: open dialog, select template, confirm export."""
        self.open_latex_dialog()
        self.select_latex_template(template)
        self.confirm_latex_export()

    def export_bibtex(self) -> None:
        """Trigger BibTeX references export."""
        expect(self.export_bibtex_btn).to_be_visible(timeout=5000)
        self.export_bibtex_btn.click()

    def export_citation_graph(self) -> None:
        """Trigger Citation Graph export."""
        expect(self.export_graph_btn).to_be_visible(timeout=5000)
        self.export_graph_btn.click()

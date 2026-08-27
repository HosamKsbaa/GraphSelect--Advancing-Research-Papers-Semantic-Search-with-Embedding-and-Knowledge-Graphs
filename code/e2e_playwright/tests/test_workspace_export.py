"""Comprehensive Playwright E2E tests for Workspace Export Tab (Requirement R1.7).

Covers:
- Export cards disabled state messages and tooltips when prerequisite papers or drafts are missing.
- LaTeX Document export modal opening, template radio options (IEEE, ACM, Plain Article), and dismiss actions.
- Full LaTeX export trigger with selected template.
- BibTeX References export trigger.
- Citation Graph export trigger.
"""
import sys
import os
import pytest
from playwright.sync_api import Page, expect

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from e2e_playwright.conftest import mock_api_route
from e2e_playwright.pages.export_tab_page import ExportTabPage


def _mock_project_base(page: Page, project_id: str):
    """Helper to mock baseline project metadata and touch endpoint."""
    mock_api_route(page, f"**/api/projects/{project_id}*", status_code=200, json_data={
        "id": project_id,
        "name": f"Export Test Project {project_id}",
        "description": "Automated Playwright Export Tab Test",
        "topic": "Graph Neural Networks",
        "target_level": "master"
    })
    mock_api_route(page, f"**/api/projects/{project_id}/touch*", status_code=200, json_data={"message": "ok"})


def test_export_tab_disabled_states_when_unready(page: Page, base_url: str):
    """Test all export cards disabled state messages when 0 papers and no drafts exist."""
    project_id = "test-export-proj-unready"
    _mock_project_base(page, project_id)

    mock_summary = {
        "paper_count": 0,
        "question_count": 0,
        "gap_count": 0,
        "has_outline": False,
        "has_drafts": False,
        "research_questions": []
    }

    mock_api_route(page, f"**/api/planning/{project_id}/summary*", status_code=200, json_data=mock_summary)

    export_tab = ExportTabPage(page, base_url)
    export_tab.navigate(project_id)

    # Verify Export cards grid
    expect(export_tab.export_cards_grid).to_be_visible()

    # LaTeX Document Card assertions
    expect(export_tab.latex_card).to_have_class("card export-card disabled")
    expect(export_tab.latex_disabled_msg).to_be_visible()
    expect(export_tab.latex_disabled_msg).to_have_text("Requires completed section drafts")
    expect(export_tab.export_latex_btn).to_be_disabled()

    # BibTeX References Card assertions
    expect(export_tab.bibtex_card).to_have_class("card export-card disabled")
    expect(export_tab.bibtex_disabled_msg).to_be_visible()
    expect(export_tab.bibtex_disabled_msg).to_have_text("Requires papers in library")
    expect(export_tab.export_bibtex_btn).to_be_disabled()

    # Citation Graph Card assertions
    expect(export_tab.graph_card).to_have_class("card export-card disabled")
    expect(export_tab.graph_disabled_msg).to_be_visible()
    expect(export_tab.graph_disabled_msg).to_have_text("Requires papers in library")
    expect(export_tab.export_graph_btn).to_be_disabled()


def test_latex_template_selection_modal_controls_and_dismissal(page: Page, base_url: str):
    """Test LaTeX template modal opening, radio button options (IEEE, ACM, Plain), and cancel/close actions."""
    project_id = "test-export-proj-modal"
    _mock_project_base(page, project_id)

    mock_summary = {
        "paper_count": 12,
        "question_count": 3,
        "gap_count": 0,
        "has_outline": True,
        "has_drafts": True,
        "research_questions": ["Q1"]
    }

    mock_api_route(page, f"**/api/planning/{project_id}/summary*", status_code=200, json_data=mock_summary)

    export_tab = ExportTabPage(page, base_url)
    export_tab.navigate(project_id)

    # Verify Export LaTeX button enabled
    expect(export_tab.export_latex_btn).to_be_enabled()

    # Open LaTeX dialog
    export_tab.open_latex_dialog()
    expect(export_tab.latex_modal_dialog).to_be_visible()
    expect(export_tab.latex_modal_dialog.locator("h2")).to_have_text("Export LaTeX")

    # Radio button selection tests
    expect(export_tab.radio_ieee).to_be_checked()

    export_tab.select_latex_template("acm")
    expect(export_tab.radio_acm).to_be_checked()
    expect(export_tab.radio_ieee).not_to_be_checked()

    export_tab.select_latex_template("plain")
    expect(export_tab.radio_plain).to_be_checked()
    expect(export_tab.radio_acm).not_to_be_checked()

    # Close via Cancel button
    export_tab.close_latex_dialog()
    expect(export_tab.latex_modal_dialog).not_to_be_visible()

    # Re-open and close via header 'x' button
    export_tab.open_latex_dialog()
    expect(export_tab.latex_modal_dialog).to_be_visible()
    export_tab.close_modal_btn.click()
    expect(export_tab.latex_modal_dialog).not_to_be_visible()


def test_latex_export_trigger(page: Page, base_url: str):
    """Test full LaTeX export flow with template selection and backend dispatch."""
    project_id = "test-export-proj-latex"
    _mock_project_base(page, project_id)

    mock_summary = {
        "paper_count": 10,
        "question_count": 2,
        "gap_count": 0,
        "has_outline": True,
        "has_drafts": True,
        "research_questions": ["Q1"]
    }

    mock_api_route(page, f"**/api/planning/{project_id}/summary*", status_code=200, json_data=mock_summary)
    
    # Mock LaTeX zip export endpoint
    mock_api_route(
        page,
        f"**/api/export/{project_id}/latex*",
        status_code=200,
        json_data={"latex": "% LaTeX Document Content\n\\documentclass{article}\n", "template": "ieee"},
        headers={"Content-Disposition": f"attachment; filename=project_{project_id}_latex.zip"}
    )

    export_tab = ExportTabPage(page, base_url)
    export_tab.navigate(project_id)

    # Trigger export
    export_tab.export_latex(template="ieee")

    # Verify dialog closed after confirmation
    expect(export_tab.latex_modal_dialog).not_to_be_visible()


def test_bibtex_export_trigger(page: Page, base_url: str):
    """Test BibTeX references export enabled when papers exist and disabled for LaTeX without drafts."""
    project_id = "test-export-proj-bibtex"
    _mock_project_base(page, project_id)

    # 8 papers exist, but drafts do NOT exist
    mock_summary = {
        "paper_count": 8,
        "question_count": 2,
        "gap_count": 0,
        "has_outline": True,
        "has_drafts": False,
        "research_questions": ["Q1"]
    }

    mock_api_route(page, f"**/api/planning/{project_id}/summary*", status_code=200, json_data=mock_summary)
    mock_api_route(
        page,
        f"**/api/export/{project_id}/bibtex*",
        status_code=200,
        json_data={"bibtex": "@article{smith2022,\n  title={GraphSelect}\n}"},
        headers={"Content-Disposition": f"attachment; filename=project_{project_id}_bibtex.bib"}
    )

    export_tab = ExportTabPage(page, base_url)
    export_tab.navigate(project_id)

    # LaTeX should remain disabled
    expect(export_tab.export_latex_btn).to_be_disabled()

    # BibTeX should be enabled
    expect(export_tab.export_bibtex_btn).to_be_enabled()
    expect(export_tab.bibtex_card).not_to_have_class("card export-card disabled")

    # Trigger BibTeX export
    export_tab.export_bibtex()


def test_citation_graph_export_trigger(page: Page, base_url: str):
    """Test Citation Graph export button enabled and dispatching export request."""
    project_id = "test-export-proj-graph"
    _mock_project_base(page, project_id)

    mock_summary = {
        "paper_count": 5,
        "question_count": 2,
        "gap_count": 0,
        "has_outline": False,
        "has_drafts": False,
        "research_questions": []
    }

    mock_api_route(page, f"**/api/planning/{project_id}/summary*", status_code=200, json_data=mock_summary)
    mock_api_route(
        page,
        f"**/api/export/{project_id}/citation-graph*",
        status_code=200,
        json_data={"nodes": [{"id": "10.1145/1"}], "edges": []},
        headers={"Content-Disposition": f"attachment; filename=project_{project_id}_citation_graph.json"}
    )

    export_tab = ExportTabPage(page, base_url)
    export_tab.navigate(project_id)

    # Graph export button should be enabled
    expect(export_tab.export_graph_btn).to_be_enabled()
    expect(export_tab.graph_card).not_to_have_class("card export-card disabled")

    # Trigger Citation Graph export
    export_tab.export_citation_graph()

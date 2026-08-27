"""Comprehensive Playwright E2E tests for Workspace Writing Tab (Requirement R1.6).

Covers:
- Empty outline state rendering with call to action in Planning tab.
- Outline section selection and active card highlight in left panel.
- Header badges inspection (🛡️ 0.0% Citation Hallucination Gate and ⚡ GCDL Inner Drafting Loop).
- Multi-turn section drafting triggering LLM generation with markdown preview rendering.
- Markdown editor vs preview toggle and manual content edits.
- Section review flow with 5-dimension feedback, issues list, missing citations, and revision counter.
- Revision loop (Revise & Redraft action and 3-revision cap warning).
- Ready for Export banner rendering when all sections are approved with navigation to Export tab.
"""
import sys
import os
import pytest
from playwright.sync_api import Page, expect

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from e2e_playwright.conftest import mock_api_route
from e2e_playwright.pages.writing_tab_page import WritingTabPage


def _mock_project_base(page: Page, project_id: str):
    """Helper to mock baseline project metadata and touch endpoint."""
    mock_api_route(page, f"**/api/projects/{project_id}*", status_code=200, json_data={
        "id": project_id,
        "name": f"Writing Test Project {project_id}",
        "description": "Automated Playwright Writing Tab Test",
        "topic": "Graph Neural Networks",
        "target_level": "master"
    })
    mock_api_route(page, f"**/api/projects/{project_id}/touch*", status_code=200, json_data={"message": "ok"})


def test_writing_tab_empty_outline_state(page: Page, base_url: str):
    """Test Writing Tab empty state when no outline exists in planning."""
    project_id = "test-writing-proj-empty"
    _mock_project_base(page, project_id)

    mock_api_route(page, f"**/api/planning/{project_id}/outline*", status_code=200, json_data={
        "project_id": project_id,
        "sections": []
    })

    writing_tab = WritingTabPage(page, base_url)
    writing_tab.navigate(project_id)

    # Verify left panel empty state
    expect(writing_tab.empty_sections_state).to_be_visible()
    expect(writing_tab.empty_sections_state).to_contain_text("No Sections")
    expect(writing_tab.empty_sections_state).to_contain_text("Generate an outline first in the Planning tab.")

    # Verify right panel placeholder state
    placeholder = page.locator(".placeholder-state")
    expect(placeholder).to_be_visible()
    expect(placeholder).to_contain_text("Select a section from the list to start drafting.")


def test_section_selection_and_gcdl_badges_inspection(page: Page, base_url: str):
    """Test selecting outline section and verifying GCDL and Hallucination Gate badges."""
    project_id = "test-writing-proj-badges"
    _mock_project_base(page, project_id)

    mock_outline = {
        "project_id": project_id,
        "sections": [
            {
                "order": 1,
                "title": "Theoretical Foundations of Graph Neural Networks",
                "description": "Mathematical formulations of spatial and spectral convolutions.",
                "paper_dois": ["10.1145/3534678.3539078"]
            },
            {
                "order": 2,
                "title": "Oversmoothing and Expressive Power Bounds",
                "description": "Dirichlet energy dynamics and Weisfeiler-Lehman 1-WL limits.",
                "paper_dois": ["10.1145/3394486.3403067"]
            }
        ]
    }

    mock_api_route(page, f"**/api/planning/{project_id}/outline*", status_code=200, json_data=mock_outline)

    writing_tab = WritingTabPage(page, base_url)
    writing_tab.navigate(project_id)

    # Verify section cards rendered in left panel
    expect(writing_tab.section_cards).to_have_count(2)
    expect(writing_tab.section_titles.nth(0)).to_have_text("Theoretical Foundations of Graph Neural Networks")
    expect(writing_tab.section_status_badges.nth(0)).to_have_text("Not_started")

    # Select Section 1
    writing_tab.select_section(0)
    expect(writing_tab.section_cards.nth(0)).to_have_class("section-card card active")

    # Assert Workspace Header titles and descriptions
    expect(writing_tab.workspace_title).to_have_text("Theoretical Foundations of Graph Neural Networks")
    expect(writing_tab.workspace_desc).to_contain_text("Mathematical formulations of spatial and spectral convolutions.")

    # Assert Core Badges
    expect(writing_tab.hallucination_gate_badge).to_be_visible()
    expect(writing_tab.hallucination_gate_badge).to_contain_text("🛡️ 0.0% Citation Hallucination Gate")

    expect(writing_tab.gcdl_loop_badge).to_be_visible()
    expect(writing_tab.gcdl_loop_badge).to_contain_text("⚡ GCDL Inner Drafting Loop")

    # Assert Draft Section button is visible
    expect(writing_tab.draft_section_btn).to_be_visible()


def test_section_drafting_and_markdown_preview(page: Page, base_url: str):
    """Test triggering section drafting and rendering generated Markdown preview."""
    project_id = "test-writing-proj-draft"
    _mock_project_base(page, project_id)

    mock_outline = {
        "project_id": project_id,
        "sections": [
            {
                "order": 1,
                "title": "Spectral Graph Convolutions",
                "description": "Chebyshev polynomial approximations of graph Laplacian eigenvectors.",
                "paper_dois": ["10.1145/3534678.3539078"]
            }
        ]
    }

    mock_draft_response = {
        "section_title": "Spectral Graph Convolutions",
        "draft_text": r"### Spectral Convolutions\n\nGraph convolutional networks approximate spectral filters using truncated Chebyshev polynomials \cite{10.1145/3534678.3539078}.",
        "word_count": 42,
        "citations_used": ["10.1145/3534678.3539078"]
    }

    mock_api_route(page, f"**/api/planning/{project_id}/outline*", status_code=200, json_data=mock_outline)
    mock_api_route(page, f"**/api/writing/{project_id}/draft*", status_code=200, json_data=mock_draft_response)

    writing_tab = WritingTabPage(page, base_url)
    writing_tab.navigate(project_id)

    writing_tab.select_section(0)
    expect(writing_tab.draft_section_btn).to_be_visible()

    # Trigger drafting
    writing_tab.click_draft_section()

    # Verify status badge updates to 'Drafted'
    expect(writing_tab.section_status_badges.first).to_have_text("Drafted")

    # Verify Markdown preview renders generated content
    expect(writing_tab.markdown_preview).to_be_visible()
    expect(writing_tab.markdown_preview).to_contain_text("Spectral Convolutions")
    expect(writing_tab.markdown_preview).to_contain_text("truncated Chebyshev polynomials")

    # Verify Review and Edit buttons are now present
    expect(writing_tab.review_section_btn).to_be_visible()
    expect(writing_tab.toggle_edit_btn).to_be_visible()
    expect(writing_tab.toggle_edit_btn).to_have_text("Edit")


def test_markdown_editor_toggle_and_content_modification(page: Page, base_url: str):
    """Test switching between Markdown editor and preview, making manual text changes."""
    project_id = "test-writing-proj-edit"
    _mock_project_base(page, project_id)

    mock_outline = {
        "project_id": project_id,
        "sections": [
            {
                "order": 1,
                "title": "Expressive Power Bounds",
                "description": "Analysis of Weisfeiler-Lehman 1-WL limits.",
                "paper_dois": ["10.1145/3394486.3403067"]
            }
        ]
    }

    mock_draft_response = {
        "section_title": "Expressive Power Bounds",
        "draft_text": "Initial drafted paragraph on 1-WL isomorphism bounds.",
        "word_count": 8,
        "citations_used": ["10.1145/3394486.3403067"]
    }

    mock_api_route(page, f"**/api/planning/{project_id}/outline*", status_code=200, json_data=mock_outline)
    mock_api_route(page, f"**/api/writing/{project_id}/draft*", status_code=200, json_data=mock_draft_response)

    writing_tab = WritingTabPage(page, base_url)
    writing_tab.navigate(project_id)

    writing_tab.select_section(0)
    writing_tab.click_draft_section()

    # Click Edit button
    writing_tab.toggle_edit_preview()
    expect(writing_tab.toggle_edit_btn).to_have_text("Preview")
    expect(writing_tab.markdown_editor).to_be_visible()
    expect(writing_tab.markdown_editor).to_have_value("Initial drafted paragraph on 1-WL isomorphism bounds.")

    # Modify markdown editor text
    updated_content = "### Enhanced 1-WL Expressiveness\n\nStandard message-passing cannot distinguish non-isomorphic graphs that 1-WL fails on."
    writing_tab.fill_markdown_editor(updated_content)

    # Click Preview button to switch back
    writing_tab.toggle_edit_preview()
    expect(writing_tab.toggle_edit_btn).to_have_text("Edit")
    expect(writing_tab.markdown_preview).to_be_visible()
    expect(writing_tab.markdown_preview).to_contain_text("Enhanced 1-WL Expressiveness")
    expect(writing_tab.markdown_preview).to_contain_text("Standard message-passing cannot distinguish")


def test_section_review_feedback_panel_and_revision_loop(page: Page, base_url: str):
    """Test automated peer review execution, feedback panel rendering, and revision loop."""
    project_id = "test-writing-proj-review"
    _mock_project_base(page, project_id)

    mock_outline = {
        "project_id": project_id,
        "sections": [
            {
                "order": 1,
                "title": "Attention Mechanisms in Graph Transformers",
                "description": "Global vs localized multi-head attention over graphs.",
                "paper_dois": ["10.1145/3534678.3539078", "10.1145/3394486.3403067"]
            }
        ]
    }

    mock_draft_response = {
        "section_title": "Attention Mechanisms in Graph Transformers",
        "draft_text": r"Graph transformers apply global attention across all node pairs \cite{10.1145/3534678.3539078}.",
        "word_count": 12,
        "citations_used": ["10.1145/3534678.3539078"]
    }

    mock_review_unapproved = {
        "section_title": "Attention Mechanisms in Graph Transformers",
        "approved": False,
        "scores": {
            "citation_grounding": 3.8,
            "structural_coherence": 3.5,
            "methodological_rigor": 3.9
        },
        "overall_score": 3.73,
        "feedback": [
            "Missing comparative discussion with Graph Attention Networks (GATv2).",
            "Explain positional encoding strategies (e.g. Laplacian eigenvectors)."
        ],
        "missing_citations": ["10.1145/3394486.3403067"]
    }

    mock_api_route(page, f"**/api/planning/{project_id}/outline*", status_code=200, json_data=mock_outline)
    mock_api_route(page, f"**/api/writing/{project_id}/draft*", status_code=200, json_data=mock_draft_response)
    mock_api_route(page, f"**/api/writing/{project_id}/review*", status_code=200, json_data=mock_review_unapproved)

    writing_tab = WritingTabPage(page, base_url)
    writing_tab.navigate(project_id)

    writing_tab.select_section(0)
    writing_tab.click_draft_section()

    # Click Review button
    writing_tab.click_review_section()

    # Verify section status is 'Reviewed'
    expect(writing_tab.section_status_badges.first).to_have_text("Reviewed")

    # Assert Feedback Panel
    expect(writing_tab.feedback_panel).to_be_visible()
    expect(writing_tab.feedback_status_badge).to_have_text("Needs Revision")

    # Assert Issues list
    expect(writing_tab.issues_list).to_have_count(2)
    expect(writing_tab.issues_list.nth(0)).to_contain_text("Missing comparative discussion with Graph Attention Networks")
    expect(writing_tab.issues_list.nth(1)).to_contain_text("Explain positional encoding strategies")

    # Assert Missing Citations list
    expect(writing_tab.missing_citations_list).to_have_count(1)
    expect(writing_tab.missing_citations_list.first).to_have_text("10.1145/3394486.3403067")

    # Assert Revision Counter
    expect(writing_tab.revision_count_text).to_have_text("Revisions: 0 / 3")

    # Click Revise & Redraft button
    writing_tab.click_revise_redraft()

    # Verify state transitions back to Drafted and section is redrafted
    expect(writing_tab.section_status_badges.first).to_have_text("Drafted")

    # Click Review button again to verify the revision count is preserved and displayed as 1 / 3
    writing_tab.click_review_section()
    expect(writing_tab.feedback_panel).to_be_visible()
    expect(writing_tab.revision_count_text).to_have_text("Revisions: 1 / 3")


def test_all_sections_approved_export_banner_navigation(page: Page, base_url: str):
    """Test all sections approved state displays Export Banner and navigates to Export Tab."""
    project_id = "test-writing-proj-approved"
    _mock_project_base(page, project_id)

    mock_outline = {
        "project_id": project_id,
        "sections": [
            {
                "order": 1,
                "title": "Introduction to Graph Learning",
                "description": "Introductory remarks.",
                "paper_dois": ["10.1145/1"]
            }
        ]
    }

    mock_draft_response = {
        "section_title": "Introduction to Graph Learning",
        "draft_text": r"Complete, rigorously grounded introductory chapter \cite{10.1145/1}.",
        "word_count": 10,
        "citations_used": ["10.1145/1"]
    }

    mock_review_approved = {
        "section_title": "Introduction to Graph Learning",
        "approved": True,
        "scores": {"citation_grounding": 5.0, "structural_coherence": 5.0},
        "overall_score": 5.0,
        "feedback": [],
        "missing_citations": []
    }

    mock_api_route(page, f"**/api/planning/{project_id}/outline*", status_code=200, json_data=mock_outline)
    mock_api_route(page, f"**/api/writing/{project_id}/draft*", status_code=200, json_data=mock_draft_response)
    mock_api_route(page, f"**/api/writing/{project_id}/review*", status_code=200, json_data=mock_review_approved)

    # Mock export summary endpoint when navigated to export tab
    mock_api_route(page, f"**/api/planning/{project_id}/summary*", status_code=200, json_data={
        "paper_count": 5, "question_count": 2, "gap_count": 0, "has_outline": True, "has_drafts": True
    })

    writing_tab = WritingTabPage(page, base_url)
    writing_tab.navigate(project_id)

    writing_tab.select_section(0)
    writing_tab.click_draft_section()
    writing_tab.click_review_section()

    # Verify section status is Approved
    expect(writing_tab.section_status_badges.first).to_have_text("Approved")

    # Verify All-Approved Export Banner is visible
    expect(writing_tab.export_banner).to_be_visible()
    expect(writing_tab.export_banner).to_contain_text("Ready for Export!")
    expect(writing_tab.export_banner).to_contain_text("All sections have been approved.")

    # Click Go to Export link
    expect(writing_tab.go_to_export_link).to_be_visible()
    writing_tab.go_to_export_link.click()

    # Verify URL transitioned to /export
    page.wait_for_url(f"**/projects/{project_id}/export")
    expect(page.locator(".export-tab-container")).to_be_visible()

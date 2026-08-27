"""Comprehensive Playwright E2E tests for Workspace Planning Tab (Requirement R1.5).

Covers:
- Project readiness summary cards (Papers, Questions, Gaps, Outline, Drafts status with check/cross indicators).
- Disabled 'Generate Outline' button state when paper_count or question_count is 0.
- Outline configuration dialog (writing style select: academic, narrative, concise; section count input; cancel vs generate).
- Generated outline section cards with order badges (Section 1..N), titles, descriptions, assigned paper DOI links, and empty paper badges.
- Section card action buttons (Regenerate and Approve).
"""
import sys
import os
import pytest
from playwright.sync_api import Page, expect

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from e2e_playwright.conftest import mock_api_route
from e2e_playwright.pages.planning_tab_page import PlanningTabPage


def _mock_project_base(page: Page, project_id: str):
    """Helper to mock baseline project metadata and touch endpoint."""
    mock_api_route(page, f"**/api/projects/{project_id}*", status_code=200, json_data={
        "id": project_id,
        "name": f"Planning Test Project {project_id}",
        "description": "Automated Playwright Planning Tab Test",
        "topic": "Graph Neural Networks",
        "target_level": "master"
    })
    mock_api_route(page, f"**/api/projects/{project_id}/touch*", status_code=200, json_data={"message": "ok"})


def test_planning_tab_readiness_summary_unready_state(page: Page, base_url: str):
    """Test readiness summary when 0 papers and 0 questions exist: disabled button and ✗ indicators."""
    project_id = "test-planning-proj-unready"
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
    mock_api_route(page, f"**/api/planning/{project_id}/outline*", status_code=200, json_data={"project_id": project_id, "sections": []})

    planning_tab = PlanningTabPage(page, base_url)
    planning_tab.navigate(project_id)

    # Verify Readiness Summary card
    expect(planning_tab.readiness_card).to_be_visible()
    expect(planning_tab.papers_stat_value).to_have_text("0")
    expect(planning_tab.questions_stat_value).to_have_text("0")
    expect(planning_tab.gaps_stat_value).to_have_text("0")

    # Assert ✗ indicators
    expect(planning_tab.outline_stat_icon).to_have_text("✗")
    expect(planning_tab.drafts_stat_icon).to_have_text("✗")

    # Assert Generate Outline button is disabled with descriptive tooltip
    expect(planning_tab.open_config_btn).to_be_disabled()
    expect(planning_tab.open_config_btn).to_have_attribute(
        "title", "Requires at least 1 paper and 1 question to generate outline"
    )

    # Assert Empty State
    expect(planning_tab.empty_state).to_be_visible()
    expect(planning_tab.empty_state).to_contain_text("No Outline Yet")


def test_planning_tab_readiness_summary_ready_state(page: Page, base_url: str):
    """Test readiness summary when papers and questions exist: enabled button and ✓ indicators."""
    project_id = "test-planning-proj-ready"
    _mock_project_base(page, project_id)

    mock_summary = {
        "paper_count": 15,
        "question_count": 4,
        "gap_count": 1,
        "has_outline": False,
        "has_drafts": False,
        "research_questions": ["Q1", "Q2", "Q3", "Q4"]
    }

    mock_api_route(page, f"**/api/planning/{project_id}/summary*", status_code=200, json_data=mock_summary)
    mock_api_route(page, f"**/api/planning/{project_id}/outline*", status_code=200, json_data={"project_id": project_id, "sections": []})

    planning_tab = PlanningTabPage(page, base_url)
    planning_tab.navigate(project_id)

    # Verify Stat values
    expect(planning_tab.papers_stat_value).to_have_text("15")
    expect(planning_tab.questions_stat_value).to_have_text("4")
    expect(planning_tab.gaps_stat_value).to_have_text("1")

    # Verify check indicators for papers and questions
    papers_icon = page.locator(".stat-item:has(.label:has-text('Papers')) .status .icon")
    questions_icon = page.locator(".stat-item:has(.label:has-text('Questions')) .status .icon")
    expect(papers_icon).to_have_text("✓")
    expect(papers_icon).to_have_class("icon success")
    expect(questions_icon).to_have_text("✓")
    expect(questions_icon).to_have_class("icon success")

    # Verify Generate Outline button is enabled
    expect(planning_tab.open_config_btn).to_be_enabled()


def test_outline_configuration_dialog_controls_and_cancel(page: Page, base_url: str):
    """Test outline configuration dialog controls (style select, numSections, cancel action)."""
    project_id = "test-planning-proj-dialog"
    _mock_project_base(page, project_id)

    mock_summary = {
        "paper_count": 10,
        "question_count": 3,
        "gap_count": 0,
        "has_outline": False,
        "has_drafts": False,
        "research_questions": ["Q1", "Q2", "Q3"]
    }

    mock_api_route(page, f"**/api/planning/{project_id}/summary*", status_code=200, json_data=mock_summary)
    mock_api_route(page, f"**/api/planning/{project_id}/outline*", status_code=200, json_data={"project_id": project_id, "sections": []})

    planning_tab = PlanningTabPage(page, base_url)
    planning_tab.navigate(project_id)

    # Open dialog
    planning_tab.open_outline_dialog()
    expect(planning_tab.config_dialog).to_be_visible()

    # Verify style dropdown options
    expect(planning_tab.style_select).to_have_value("academic")
    planning_tab.style_select.select_option("narrative")
    expect(planning_tab.style_select).to_have_value("narrative")
    planning_tab.style_select.select_option("concise")
    expect(planning_tab.style_select).to_have_value("concise")
    planning_tab.style_select.select_option("academic")
    expect(planning_tab.style_select).to_have_value("academic")

    # Verify number of sections input
    expect(planning_tab.num_sections_input).to_have_value("5")
    planning_tab.num_sections_input.fill("7")
    expect(planning_tab.num_sections_input).to_have_value("7")

    # Click Cancel button to close dialog
    planning_tab.close_outline_dialog()
    expect(planning_tab.config_dialog).not_to_be_visible()


def test_outline_generation_and_section_cards_rendering(page: Page, base_url: str):
    """Test outline generation flow and rendering of section cards with metadata and assigned papers."""
    project_id = "test-planning-proj-generate"
    _mock_project_base(page, project_id)

    mock_summary_initial = {
        "paper_count": 12,
        "question_count": 3,
        "gap_count": 0,
        "has_outline": False,
        "has_drafts": False,
        "research_questions": ["Q1", "Q2", "Q3"]
    }

    mock_generated_sections = [
        {
            "order": 1,
            "title": "Introduction & Theoretical Foundations of Graph Neural Networks",
            "description": "Foundational overview of spatial vs spectral message-passing paradigms.",
            "paper_dois": ["10.1145/3534678.3539078", "10.1145/3394486.3403067"]
        },
        {
            "order": 2,
            "title": "Oversmoothing and Expressive Power Bounds",
            "description": "Theoretical analysis of Dirichlet energy dissipation in deep cascades.",
            "paper_dois": ["10.1145/2222222"]
        },
        {
            "order": 3,
            "title": "Attention Mechanisms and Graph Transformers",
            "description": "Survey of linear graph attention models and global receptive fields.",
            "paper_dois": ["10.1145/3333333"]
        },
        {
            "order": 4,
            "title": "Empirical Benchmark Synthesis & Open Challenges",
            "description": "Comparative literature matrix across Open Graph Benchmark datasets.",
            "paper_dois": []
        }
    ]

    mock_summary_after = {
        "paper_count": 12,
        "question_count": 3,
        "gap_count": 0,
        "has_outline": True,
        "has_drafts": False,
        "research_questions": ["Q1", "Q2", "Q3"]
    }

    mock_api_route(page, f"**/api/planning/{project_id}/summary*", status_code=200, json_data=mock_summary_initial)
    mock_api_route(page, f"**/api/planning/{project_id}/outline*", status_code=200, json_data={
        "project_id": project_id,
        "style": "academic",
        "sections": mock_generated_sections
    })

    planning_tab = PlanningTabPage(page, base_url)
    planning_tab.navigate(project_id)

    # Configure and trigger outline generation
    planning_tab.configure_and_generate_outline(style="academic", num_sections=4)

    # Verify 4 section cards rendered
    expect(planning_tab.section_cards).to_have_count(4)

    # Section 1 verification
    s1 = planning_tab.section_cards.nth(0)
    expect(s1.locator(".section-order")).to_have_text("Section 1")
    expect(s1.locator("h4")).to_have_text("Introduction & Theoretical Foundations of Graph Neural Networks")
    expect(s1.locator(".description")).to_contain_text("Foundational overview of spatial vs spectral")
    expect(s1.locator(".assigned-papers li")).to_have_count(2)
    expect(s1.locator(".assigned-papers a").first).to_have_text("10.1145/3534678.3539078")
    expect(s1.locator(".assigned-papers a").first).to_have_attribute("href", "https://doi.org/10.1145/3534678.3539078")

    # Section 4 verification (Empty papers)
    s4 = planning_tab.section_cards.nth(3)
    expect(s4.locator(".section-order")).to_have_text("Section 4")
    expect(s4.locator("h4")).to_have_text("Empirical Benchmark Synthesis & Open Challenges")
    expect(s4.locator(".empty-papers")).to_be_visible()
    expect(s4.locator(".empty-papers")).to_have_text("None")

    # Action buttons verification on Section 1
    expect(s1.locator("button:has-text('Regenerate')")).to_be_visible()
    expect(s1.locator("button:has-text('Approve')")).to_be_visible()

    # Trigger regenerate and approve
    planning_tab.regenerate_section(0)
    planning_tab.approve_section(0)

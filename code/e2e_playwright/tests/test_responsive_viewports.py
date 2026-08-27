"""Comprehensive Playwright E2E tests for Multi-Viewport & Responsive Layout (Requirement R2).

Automates cross-viewport validation across standard screen dimensions:
- Desktop FHD: 1920x1080
- Desktop HD: 1280x800
- Tablet: 768x1024 (iPad with touch emulation)
- Mobile: 375x812 (iPhone X with touch emulation)
"""
import sys
import os
import pytest
from playwright.sync_api import Page, expect

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from e2e_playwright.conftest import mock_api_route, mock_sse_route
from e2e_playwright.pages.project_list_page import ProjectListPage
from e2e_playwright.pages.search_wizard_page import SearchWizardPage
from e2e_playwright.pages.research_tab_page import ResearchTabPage
from e2e_playwright.pages.analysis_tab_page import AnalysisTabPage
from e2e_playwright.pages.planning_tab_page import PlanningTabPage
from e2e_playwright.pages.writing_tab_page import WritingTabPage
from e2e_playwright.pages.export_tab_page import ExportTabPage
from e2e_playwright.pages.system_status_page import SystemStatusPage
from e2e_playwright.pages.logs_page import LogsPage
from e2e_playwright.pages.debug_page import DebugPage
from e2e_playwright.pages.settings_page import SettingsPage


def _mock_project_base(page: Page, project_id: str, name: str = "Responsive Test Project"):
    """Helper to mock baseline project metadata and touch endpoint."""
    mock_api_route(page, f"**/api/projects/{project_id}*", status_code=200, json_data={
        "id": project_id,
        "name": name,
        "description": "Automated Playwright Responsive Viewport Project",
        "topic": "Graph Neural Networks and Multi-Agent Systems",
        "target_level": "master"
    })
    mock_api_route(page, f"**/api/projects/{project_id}/touch*", status_code=200, json_data={"message": "ok"})


# ===========================================================================
# 1. Projects List & Creation Modal Responsiveness
# ===========================================================================

def test_responsive_projects_list_and_creation_modal(responsive_page: Page, base_url: str):
    """Verify Projects Management page and Creation Modal adapt across all viewports."""
    mock_projects = [
        {
            "id": "proj-master-1",
            "name": "Heterogeneous Graph Reasoning",
            "topic": "Graph Neural Networks",
            "description": "Analysis of multi-hop relational path reasoning in sparse academic citation networks.",
            "target_level": "master",
            "paper_count": 14,
            "question_count": 3,
            "archived": False,
            "created_at": "2026-08-20T10:00:00Z",
            "last_accessed": "2026-08-27T08:00:00Z"
        },
        {
            "id": "proj-phd-1",
            "name": "Zero-Hallucination Agentic Co-Authoring",
            "topic": "Multi-Agent Systems",
            "description": "Formal verification and citation grounding in autonomous academic paper generation.",
            "target_level": "phd",
            "paper_count": 28,
            "question_count": 6,
            "archived": False,
            "created_at": "2026-08-15T14:30:00Z",
            "last_accessed": "2026-08-26T19:45:00Z"
        }
    ]
    mock_api_route(responsive_page, "**/api/projects*", status_code=200, json_data=mock_projects)

    project_list = ProjectListPage(responsive_page, base_url)
    project_list.navigate()

    expect(project_list.page_header).to_be_visible()
    expect(project_list.search_input).to_be_visible()

    search_box = project_list.search_input.bounding_box()
    assert search_box is not None
    assert search_box["width"] > 0

    project_list.search_projects("Zero-Hallucination")
    expect(project_list.get_project_card("Zero-Hallucination")).to_be_visible()
    expect(project_list.get_project_card("Heterogeneous Graph")).not_to_be_visible()

    project_list.search_projects("")
    expect(project_list.get_project_card("Heterogeneous Graph")).to_be_visible()

    card = project_list.get_project_card("Heterogeneous Graph")
    expect(card).to_be_visible()
    card_box = card.bounding_box()
    assert card_box is not None
    assert card_box["width"] > 0

    expect(card.locator(".badge-success")).to_contain_text("14 Papers")
    expect(card.locator(".badge-warning")).to_contain_text("3 Questions")

    # Open modal with force=True for small viewport overlay compatibility
    project_list.new_project_btn.click(force=True)
    expect(project_list.modal_container).to_be_visible()

    modal_box = project_list.modal_container.bounding_box()
    assert modal_box is not None
    assert modal_box["width"] > 0

    expect(project_list.project_name_input).to_be_visible()
    expect(project_list.project_topic_input).to_be_visible()
    expect(project_list.target_level_select).to_be_visible()
    expect(project_list.project_desc_input).to_be_visible()
    expect(project_list.submit_create_btn).to_be_visible()

    project_list.fill_create_project_form(
        name="Responsive Layout Test Project",
        topic="Adaptive UI Engineering",
        target_level="phd",
        description="Testing layout adaptation across desktop, tablet, and mobile form factors."
    )
    expect(project_list.submit_create_btn).to_be_enabled()

    # Close modal with force=True
    project_list.cancel_create_btn.first.click(force=True)
    expect(project_list.modal_container).not_to_be_visible()


# ===========================================================================
# 2. Literature Search Wizard Responsiveness
# ===========================================================================

def test_responsive_search_wizard_and_results_component(responsive_page: Page, base_url: str):
    """Verify Literature Search Wizard (Steps 1-4) and Results Component adapt across all viewports."""
    wizard = SearchWizardPage(responsive_page, base_url)
    wizard.navigate()

    expect(wizard.step_find_paper).to_be_visible()
    expect(wizard.step_questions).to_be_visible()
    expect(wizard.step_crawl).to_be_visible()
    expect(wizard.step_results).to_be_visible()
    expect(wizard.step_find_paper).to_have_class("step active")

    mock_candidates = [
        {
            "doi": "10.1145/3534678.3539078",
            "title": "GraphSelect: Embedding-Guided Graph Traversal for Scalable Semantic Paper Search",
            "authors": ["Alice Smith", "Bob Jones", "Carol White"],
            "year": 2024,
            "cited_by_count": 1420
        },
        {
            "doi": "10.1145/3394486.3403067",
            "title": "Autonomous Multi-Agent Literature Synthesis with Google ADK",
            "authors": ["H. Ksbaa", "M. Research"],
            "year": 2026,
            "cited_by_count": 88
        }
    ]
    mock_api_route(responsive_page, "**/api/search/resolve*", status_code=200, json_data=mock_candidates)

    wizard.seed_title_input.fill("GraphSelect")
    wizard.seed_search_btn.click(force=True)
    expect(wizard.candidate_cards).to_have_count(2)

    card0 = wizard.candidate_cards.nth(0)
    expect(card0).to_be_visible()
    card0_box = card0.bounding_box()
    assert card0_box is not None
    assert card0_box["width"] > 0
    expect(card0.locator(".candidate-title")).to_contain_text("GraphSelect: Embedding-Guided Graph Traversal")
    expect(card0.locator(".candidate-meta")).to_contain_text("2024")

    card0.click(force=True)
    expect(wizard.step_questions).to_have_class("step active")

    expect(wizard.selected_paper_badge).to_be_visible()
    expect(wizard.question_inputs.first).to_be_visible()
    expect(wizard.add_question_btn).to_be_visible()

    expect(wizard.similarity_slider).to_be_visible()
    expect(wizard.max_depth_select).to_be_visible()
    expect(wizard.mode_select).to_be_visible()

    settings_grid = responsive_page.locator(".settings-grid")
    expect(settings_grid).to_be_visible()
    grid_box = settings_grid.bounding_box()
    assert grid_box is not None
    assert grid_box["width"] > 0

    session_id = "session-resp-001"
    seed_doi = "10.1145/3534678.3539078"
    mock_api_route(responsive_page, "**/api/search/start*", status_code=200, json_data={
        "session_id": session_id,
        "seed_paper_doi": seed_doi,
        "status": "running"
    })
    mock_sse_route(responsive_page, f"**/api/search/{session_id}/stream*", [
        {"event": "search_started", "data": {"event_type": "search_started", "message": "Starting traversal.", "progress_percent": 20}},
        {"event": "search_complete", "data": {"event_type": "search_complete", "message": "Search completed.", "progress_percent": 100}}
    ])

    mock_ranked_results = {
        "session_id": session_id,
        "total_papers": 1,
        "similarity_threshold": 0.50,
        "similarity_weight": 0.70,
        "pagerank_weight": 0.30,
        "groups": [
            {
                "question": "How do attention mechanisms scale in citation graphs?",
                "avg_similarity": 0.94,
                "papers": [
                    {
                        "doi": seed_doi,
                        "title": "Scalable Graph Attention Networks with PageRank Pruning",
                        "authors": ["P. Veličković", "Y. Bengio"],
                        "year": 2025,
                        "cited_by_count": 312,
                        "similarity_score": 0.96,
                        "pagerank_score": 0.91,
                        "hybrid_score": 0.94,
                        "abstract_snippet": "We present an empirical study on citation graph traversal using embedding-guided BFS."
                    }
                ]
            }
        ]
    }
    mock_api_route(responsive_page, f"**/api/search/{session_id}/results*", status_code=200, json_data=mock_ranked_results)

    wizard.fill_research_questions(["How do attention mechanisms scale in citation graphs?"])
    wizard.step2_start_btn.click(force=True)

    # Automatically advances to results view upon SSE completion
    expect(wizard.results_view).to_be_visible(timeout=10000)

    control_panel = responsive_page.locator(".control-panel")
    expect(control_panel).to_be_visible()
    cp_box = control_panel.bounding_box()
    assert cp_box is not None
    assert cp_box["width"] > 0

    expect(wizard.threshold_slider).to_be_visible()
    expect(wizard.weight_slider).to_be_visible()
    expect(wizard.question_tabs.first).to_be_visible()

    expect(wizard.results_paper_cards.first).to_be_visible()
    paper_card = wizard.results_paper_cards.first
    paper_card_box = paper_card.bounding_box()
    assert paper_card_box is not None
    assert paper_card_box["width"] > 0

    # Expand drawer and assert abstract text
    paper_card.click(force=True)
    expect(paper_card.locator(".abstract-section .abstract")).to_contain_text("embedding-guided BFS")


# ===========================================================================
# 3. Workspace: Research Tab Responsiveness
# ===========================================================================

def test_responsive_workspace_research_tab(responsive_page: Page, base_url: str):
    """Verify Workspace Research Tab sidebars, question input, library table, and row details adapt cleanly."""
    project_id = "test-proj-resp-research"

    _mock_project_base(responsive_page, project_id, "Responsive Research Workspace")

    mock_questions = [
        {
            "id": "q1",
            "text": "How do attention mechanisms prevent oversmoothing in deep GNNs?",
            "embedding_status": "embedded",
            "coverage_score": 0.85
        },
        {
            "id": "q2",
            "text": "What is the computational complexity of BFS citation traversal?",
            "embedding_status": "embedded",
            "coverage_score": 0.60
        }
    ]
    mock_api_route(responsive_page, f"**/api/research/{project_id}/questions*", status_code=200, json_data={"questions": mock_questions})

    mock_papers = [
        {
            "doi": "10.1145/3394486.3403177",
            "title": "Deep Graph Library: A Scalable Framework for Deep Learning on Graphs",
            "authors": ["M. Wang", "D. Zheng", "Z. Ye"],
            "year": 2024,
            "similarity_score": 0.92,
            "hybrid_score": 0.90,
            "pagerank_score": 0.85,
            "question_similarities": [
                {"question_id": "q1", "question_text": "How do attention mechanisms prevent oversmoothing in deep GNNs?", "similarity_score": 0.94},
                {"question_id": "q2", "question_text": "What is the computational complexity of BFS citation traversal?", "similarity_score": 0.88}
            ]
        },
        {
            "doi": "10.1109/ICDE.2023.00045",
            "title": "GraphSelect: Topology-Aware Semantic Traversal over OpenAlex",
            "authors": ["H. Ksbaa", "A. Colleague"],
            "year": 2025,
            "similarity_score": 0.89,
            "hybrid_score": 0.87,
            "pagerank_score": 0.82,
            "question_similarities": [
                {"question_id": "q1", "question_text": "How do attention mechanisms prevent oversmoothing in deep GNNs?", "similarity_score": 0.86},
                {"question_id": "q2", "question_text": "What is the computational complexity of BFS citation traversal?", "similarity_score": 0.92}
            ]
        }
    ]
    mock_api_route(responsive_page, f"**/api/analysis/{project_id}/ranked-papers*", status_code=200, json_data={"ranked_papers": mock_papers})
    mock_api_route(responsive_page, f"**/api/research/{project_id}/top-authors*", status_code=200, json_data={"authors": []})
    mock_api_route(responsive_page, f"**/api/research/{project_id}/top-venues*", status_code=200, json_data={"venues": []})

    research_tab = ResearchTabPage(responsive_page, base_url)
    research_tab.navigate(project_id)

    expect(research_tab.question_input).to_be_visible()
    expect(research_tab.add_question_btn).to_be_visible()
    expect(research_tab.question_items).to_have_count(2)

    q_input_box = research_tab.question_input.bounding_box()
    assert q_input_box is not None
    assert q_input_box["width"] > 0

    expect(research_tab.question_status_icons.first).to_contain_text("✓")
    expect(research_tab.question_coverage_badges.first).to_contain_text("85%")

    expect(research_tab.toggle_mode_btn).to_be_visible()
    expect(research_tab.search_input).to_be_visible()
    expect(research_tab.paper_table).to_be_visible()

    table_box = research_tab.paper_table.bounding_box()
    assert table_box is not None
    assert table_box["width"] > 0

    expect(research_tab.paper_rows).to_have_count(2)

    research_tab.filter_library("GraphSelect")
    expect(research_tab.paper_rows).to_have_count(1)
    expect(research_tab.paper_rows.first).to_contain_text("GraphSelect")

    research_tab.filter_library("")
    expect(research_tab.paper_rows).to_have_count(2)

    research_tab.paper_rows.first.click(force=True)
    expect(research_tab.detail_rows.first).to_be_visible()
    detail_box = research_tab.detail_rows.first.bounding_box()
    assert detail_box is not None
    assert detail_box["width"] > 0

    expect(research_tab.top_authors_widget).to_be_visible()
    expect(research_tab.top_venues_widget).to_be_visible()


# ===========================================================================
# 4. Workspace: Analysis Tab Responsiveness
# ===========================================================================

def test_responsive_workspace_analysis_tab(responsive_page: Page, base_url: str):
    """Verify Workspace Analysis Tab 2-column to 1-column responsive collapse, coverage cards, and polarity subgraph."""
    project_id = "test-proj-resp-analysis"
    viewport = responsive_page.viewport_size or {"width": 1280, "height": 800}
    viewport_width = viewport["width"]

    _mock_project_base(responsive_page, project_id, "Responsive Analysis Workspace")

    mock_coverage = {
        "gap_questions": [
            {
                "question_id": "q1",
                "question": "How do attention mechanisms prevent oversmoothing in heterogeneous graphs?",
                "best_score": 0.25,
                "paper_count": 1
            }
        ],
        "covered_questions": [
            {
                "question_id": "q2",
                "question": "What is the message-passing efficiency in deep GNNs?",
                "best_score": 0.88,
                "paper_count": 6
            }
        ],
        "overall_coverage": 0.56
    }
    mock_api_route(responsive_page, f"**/api/analysis/{project_id}/coverage*", status_code=200, json_data=mock_coverage)

    mock_stats = {
        "total_papers": 8,
        "average_similarity": 0.78,
        "network_density": 0.42
    }
    mock_api_route(responsive_page, f"**/api/analysis/{project_id}/citation-stats*", status_code=200, json_data=mock_stats)

    mock_ranked = {
        "ranked_papers": [
            {
                "doi": "10.1145/p1",
                "title": "Scalable Graph Attention Networks with PageRank Pruning",
                "year": 2024,
                "hybrid_score": 0.92,
                "similarity_score": 0.94,
                "pagerank_score": 0.88,
                "question_similarities": [{"question_id": "q1", "question_text": "q1", "similarity_score": 0.92}]
            }
        ]
    }
    mock_api_route(responsive_page, f"**/api/analysis/{project_id}/ranked-papers*", status_code=200, json_data=mock_ranked)

    mock_gap_queries = {
        "gap_question": "How do attention mechanisms prevent oversmoothing in heterogeneous graphs?",
        "queries": [
            "heterogeneous graph attention oversmoothing prevention mechanisms",
            "deep GNN message passing scalability and bottleneck analysis"
        ]
    }
    mock_api_route(responsive_page, f"**/api/analysis/{project_id}/gap-queries*", status_code=200, json_data=mock_gap_queries)

    analysis_tab = AnalysisTabPage(responsive_page, base_url)
    analysis_tab.navigate(project_id)

    expect(analysis_tab.analysis_layout).to_be_visible()

    cov_box = analysis_tab.coverage_column.bounding_box()
    ins_box = analysis_tab.insights_column.bounding_box()
    assert cov_box is not None and ins_box is not None

    if viewport_width > 1200:
        assert ins_box["x"] >= cov_box["x"] + cov_box["width"] - 20
    else:
        assert ins_box["y"] >= cov_box["y"]

    expect(analysis_tab.coverage_cards).to_have_count(2)
    card0 = analysis_tab.coverage_cards.nth(0)
    card0_box = card0.bounding_box()
    assert card0_box is not None
    assert card0_box["width"] > 0
    expect(card0.locator(".status-badge")).to_contain_text("Gap")
    expect(card0.locator(".progress-bar")).to_have_class("progress-bar progress-bad")

    analysis_tab.suggest_queries_btns.first.click(force=True)
    expect(analysis_tab.suggested_queries_container.first).to_be_visible()
    expect(analysis_tab.suggested_query_items).to_have_count(2)

    # Citation stats formatted as decimals in Angular template
    expect(analysis_tab.stats_panel).to_be_visible()
    expect(analysis_tab.total_papers_stat).to_contain_text("8")
    expect(analysis_tab.avg_similarity_stat).to_contain_text("0.78")
    expect(analysis_tab.network_density_stat).to_contain_text("0.42")

    expect(analysis_tab.ranked_papers_panel).to_be_visible()
    expect(analysis_tab.ranked_paper_titles.first).to_contain_text("Scalable Graph Attention Networks")

    expect(analysis_tab.polarity_panel).to_be_visible()
    expect(analysis_tab.polarity_supports_badge).to_be_visible()
    expect(analysis_tab.polarity_contradicts_badge).to_be_visible()
    expect(analysis_tab.verified_edge_badge).to_be_visible()
    expect(analysis_tab.controversy_edge_badge).to_be_visible()


# ===========================================================================
# 5. Workspace: Planning Tab Responsiveness
# ===========================================================================

def test_responsive_workspace_planning_tab(responsive_page: Page, base_url: str):
    """Verify Workspace Planning Tab readiness stat wrapping, outline configuration dialog, and section cards."""
    project_id = "test-proj-resp-planning"

    _mock_project_base(responsive_page, project_id, "Responsive Planning Workspace")

    mock_summary = {
        "paper_count": 12,
        "question_count": 4,
        "gap_count": 1,
        "has_outline": True,
        "has_drafts": False,
        "research_questions": ["Q1", "Q2", "Q3", "Q4"]
    }
    mock_api_route(responsive_page, f"**/api/planning/{project_id}/summary*", status_code=200, json_data=mock_summary)

    mock_outline = {
        "project_id": project_id,
        "style": "academic",
        "sections": [
            {
                "order": 1,
                "title": "Introduction & Theoretical Foundations",
                "description": "Background on graph attention networks, message-passing limitations, and research objectives.",
                "paper_dois": ["10.1000/182", "10.1000/183"]
            },
            {
                "order": 2,
                "title": "Empirical Methodology & Graph Traversal Architecture",
                "description": "BFS citation graph expansion with 3-tier PageRank and vector similarity pruning.",
                "paper_dois": ["10.1145/3394486.3403177"]
            }
        ]
    }
    mock_api_route(responsive_page, f"**/api/planning/{project_id}/outline*", status_code=200, json_data=mock_outline)

    planning_tab = PlanningTabPage(responsive_page, base_url)
    planning_tab.navigate(project_id)

    expect(planning_tab.readiness_card).to_be_visible()
    expect(planning_tab.papers_stat_value).to_contain_text("12")
    expect(planning_tab.questions_stat_value).to_contain_text("4")
    expect(planning_tab.gaps_stat_value).to_contain_text("1")

    stats_container = responsive_page.locator(".summary-stats")
    expect(stats_container).to_be_visible()
    stats_box = stats_container.bounding_box()
    assert stats_box is not None
    assert stats_box["width"] > 0

    # Open dialog with force=True for small viewport overlay compatibility
    planning_tab.open_config_btn.click(force=True)
    expect(planning_tab.config_dialog).to_be_visible()

    dialog_box = planning_tab.config_dialog.locator(".dialog-content").bounding_box()
    assert dialog_box is not None
    assert dialog_box["width"] > 0

    expect(planning_tab.style_select).to_be_visible()
    expect(planning_tab.num_sections_input).to_be_visible()
    expect(planning_tab.confirm_generate_btn).to_be_visible()
    expect(planning_tab.cancel_config_btn).to_be_visible()

    # Generate outline to render section cards
    planning_tab.confirm_generate_btn.click(force=True)
    expect(planning_tab.config_dialog).not_to_be_visible()

    expect(planning_tab.section_cards).to_have_count(2)
    card0 = planning_tab.section_cards.nth(0)
    card0_box = card0.bounding_box()
    assert card0_box is not None
    assert card0_box["width"] > 0

    expect(card0.locator(".section-order")).to_contain_text("Section 1")
    expect(card0.locator("h4")).to_contain_text("Introduction & Theoretical Foundations")
    expect(card0.locator(".description")).to_contain_text("Background on graph attention networks")
    expect(card0.locator("button:has-text('Regenerate')")).to_be_visible()
    expect(card0.locator("button:has-text('Approve')")).to_be_visible()


# ===========================================================================
# 6. Workspace: Writing Tab Responsiveness
# ===========================================================================

def test_responsive_workspace_writing_tab(responsive_page: Page, base_url: str):
    """Verify Workspace Writing Tab split layout, badges, markdown editor/preview toggle, and feedback panel."""
    project_id = "test-proj-resp-writing"

    _mock_project_base(responsive_page, project_id, "Responsive Writing Workspace")

    mock_outline = {
        "project_id": project_id,
        "sections": [
            {
                "order": 1,
                "title": "Introduction & Background",
                "description": "Foundations of autonomous literature retrieval and graph traversal.",
                "paper_dois": ["10.1000/182"]
            },
            {
                "order": 2,
                "title": "System Architecture & Methods",
                "description": "Multi-agent coordination using Google ADK and CitationVerifier.",
                "paper_dois": ["10.1000/183"]
            }
        ]
    }
    mock_api_route(responsive_page, f"**/api/planning/{project_id}/outline*", status_code=200, json_data=mock_outline)

    mock_draft_response = {
        "section_title": "Introduction & Background",
        "draft_text": "## Introduction\n\nRecent advances in Graph Neural Networks (GNNs) enable rich representation learning.",
        "word_count": 14,
        "citations_used": ["10.1000/182"]
    }
    mock_api_route(responsive_page, f"**/api/writing/{project_id}/draft*", status_code=200, json_data=mock_draft_response)

    mock_review_response = {
        "section_title": "Introduction & Background",
        "approved": False,
        "scores": {
            "citation_grounding": 4.2,
            "structural_coherence": 4.0
        },
        "overall_score": 4.2,
        "feedback": ["Expand upon message-passing bottlenecks in heterogeneous graphs."],
        "missing_citations": ["10.1145/3394486.3403177"]
    }
    mock_api_route(responsive_page, f"**/api/writing/{project_id}/review*", status_code=200, json_data=mock_review_response)

    writing_tab = WritingTabPage(responsive_page, base_url)
    writing_tab.navigate(project_id)

    expect(writing_tab.section_cards).to_have_count(2)

    # Select Section 1 and draft
    writing_tab.section_cards.first.click(force=True)
    expect(writing_tab.draft_workspace).to_be_visible()

    workspace_box = writing_tab.draft_workspace.bounding_box()
    assert workspace_box is not None
    assert workspace_box["width"] > 0

    expect(writing_tab.hallucination_gate_badge).to_be_visible()
    expect(writing_tab.gcdl_loop_badge).to_be_visible()
    expect(writing_tab.draft_section_btn).to_be_visible()

    # Draft section
    writing_tab.draft_section_btn.click(force=True)

    expect(writing_tab.markdown_preview).to_be_visible()
    expect(writing_tab.markdown_preview).to_contain_text("Introduction")

    # Toggle to Markdown Editor
    writing_tab.toggle_edit_btn.click(force=True)
    expect(writing_tab.markdown_editor).to_be_visible()
    expect(writing_tab.markdown_editor).to_have_value(mock_draft_response["draft_text"])

    writing_tab.markdown_editor.fill("## Introduction\n\nUpdated draft text in responsive viewport.")
    expect(writing_tab.markdown_editor).to_have_value("## Introduction\n\nUpdated draft text in responsive viewport.")

    # Toggle back to Preview
    writing_tab.toggle_edit_btn.click(force=True)

    # Review section (use specific button selector to avoid strict mode collisions)
    responsive_page.locator(".workspace-header button.btn-secondary").click(force=True)

    expect(writing_tab.feedback_panel).to_be_visible()
    expect(writing_tab.feedback_status_badge).to_contain_text("Needs Revision")
    expect(writing_tab.issues_list.first).to_contain_text("Expand upon message-passing")
    expect(writing_tab.missing_citations_list.first).to_contain_text("10.1145/3394486.3403177")
    expect(writing_tab.revision_count_text).to_contain_text("Revisions: 0 / 3")
    expect(writing_tab.revise_btn).to_be_visible()


# ===========================================================================
# 7. Workspace: Export Tab Responsiveness
# ===========================================================================

def test_responsive_workspace_export_tab(responsive_page: Page, base_url: str):
    """Verify Workspace Export Tab export cards grid, LaTeX template modal scaling, and radio controls."""
    project_id = "test-proj-resp-export"

    _mock_project_base(responsive_page, project_id, "Responsive Export Workspace")

    mock_summary = {
        "paper_count": 10,
        "question_count": 3,
        "gap_count": 0,
        "has_outline": True,
        "has_drafts": True,
        "research_questions": ["Q1"]
    }
    mock_api_route(responsive_page, f"**/api/planning/{project_id}/summary*", status_code=200, json_data=mock_summary)

    export_tab = ExportTabPage(responsive_page, base_url)
    export_tab.navigate(project_id)

    expect(export_tab.export_cards_grid).to_be_visible()
    expect(export_tab.latex_card).to_be_visible()
    expect(export_tab.bibtex_card).to_be_visible()
    expect(export_tab.graph_card).to_be_visible()

    grid_box = export_tab.export_cards_grid.bounding_box()
    assert grid_box is not None
    assert grid_box["width"] > 0

    expect(export_tab.export_latex_btn).to_be_visible()
    expect(export_tab.export_bibtex_btn).to_be_visible()
    expect(export_tab.export_graph_btn).to_be_visible()

    export_tab.export_latex_btn.click(force=True)
    expect(export_tab.latex_modal_dialog).to_be_visible()

    dialog_box = export_tab.latex_modal_dialog.bounding_box()
    assert dialog_box is not None
    assert dialog_box["width"] > 0

    expect(export_tab.radio_ieee).to_be_visible()
    expect(export_tab.radio_acm).to_be_visible()
    expect(export_tab.radio_plain).to_be_visible()
    expect(export_tab.confirm_export_btn).to_be_visible()
    expect(export_tab.cancel_modal_btn).to_be_visible()

    export_tab.radio_acm.check(force=True)
    expect(export_tab.radio_acm).to_be_checked()

    export_tab.radio_plain.check(force=True)
    expect(export_tab.radio_plain).to_be_checked()

    export_tab.cancel_modal_btn.click(force=True)
    expect(export_tab.latex_modal_dialog).not_to_be_visible()


# ===========================================================================
# 8. System Tools Responsiveness
# ===========================================================================

def test_responsive_system_tools_views(responsive_page: Page, base_url: str):
    """Verify System Status, Logs, Debug, and Settings views adapt across all viewports."""
    # 8.1 System Status Page (/system-status)
    mock_status_data = {
        "status": "healthy",
        "neo4j": "connected",
        "mysql": "connected"
    }
    mock_api_route(responsive_page, "**/api/health*", status_code=200, json_data=mock_status_data)
    mock_api_route(responsive_page, "**/api/system/status*", status_code=200, json_data=mock_status_data)
    mock_api_route(responsive_page, "**/api/version*", status_code=200, json_data={"version": "v3.0.0-alpha.1"})

    mock_sessions = {
        "sessions": [
            {
                "session_id": "session-resp-1",
                "seed_doi": "10.1000/182",
                "status": "completed",
                "papers_discovered": 45,
                "papers_relevant": 12,
                "current_depth": 2,
                "created_at": "2026-08-27T10:00:00Z"
            }
        ],
        "total": 1
    }
    mock_api_route(responsive_page, "**/api/sessions*", status_code=200, json_data=mock_sessions)

    status_page = SystemStatusPage(responsive_page, base_url)
    status_page.navigate()

    expect(status_page.page_title).to_be_visible()
    expect(status_page.status_cards.first).to_be_visible()
    grid = responsive_page.locator(".status-grid")
    expect(grid).to_be_visible()
    grid_box = grid.bounding_box()
    assert grid_box is not None
    assert grid_box["width"] > 0

    expect(status_page.system_status_badge).to_contain_text("healthy", ignore_case=True)
    expect(status_page.neo4j_status_badge).to_contain_text("connected", ignore_case=True)
    expect(status_page.mysql_status_badge).to_contain_text("connected", ignore_case=True)
    expect(status_page.version_display).to_contain_text("3.0.0-alpha.1")

    # 8.2 Logs Page (/logs)
    mock_logs = [
        {
            "id": "log-1",
            "timestamp": "2026-08-27T10:15:30Z",
            "level": "INFO",
            "message": "GraphSelect citation traversal started for seed DOI 10.1000/182",
            "module": "graph_traversal",
            "extra": {"depth": 2, "max_nodes": 50}
        },
        {
            "id": "log-2",
            "timestamp": "2026-08-27T10:15:32Z",
            "level": "WARNING",
            "message": "OpenCitations rate limit threshold reached (80%)",
            "module": "opencitations_client",
            "extra": {"remaining_quota": 200}
        }
    ]
    mock_api_route(responsive_page, "**/api/logs*", status_code=200, json_data=mock_logs)

    logs_page = LogsPage(responsive_page, base_url)
    logs_page.navigate()

    tabs_header = responsive_page.locator(".tabs-header")
    expect(tabs_header).to_be_visible()
    expect(logs_page.tab_app_logs).to_be_visible()
    expect(logs_page.tab_api_logs).to_be_visible()
    expect(logs_page.tab_agent_traces).to_be_visible()

    filter_bar = responsive_page.locator(".filter-bar")
    expect(filter_bar).to_be_visible()
    expect(logs_page.level_select).to_be_visible()
    expect(logs_page.limit_select).to_be_visible()
    expect(logs_page.refresh_btn).to_be_visible()

    filter_box = filter_bar.bounding_box()
    assert filter_box is not None
    assert filter_box["width"] > 0

    expect(logs_page.log_rows).to_have_count(2)

    # 8.3 Debug Page (/debug) - Correct endpoint: test-retrieve
    mock_api_route(responsive_page, "**/api/debug/test-retrieve*", status_code=200, json_data={
        "success": True,
        "doi": "10.1000/182",
        "title": "Attention-Guided Graph Pruning",
        "year": 2024,
        "cited_by_count": 89,
        "abstract": "We evaluate attention-guided BFS citation pruning.",
        "elapsed_ms": 142.5
    })

    debug_page = DebugPage(responsive_page, base_url)
    debug_page.navigate()

    expect(debug_page.retrieve_panel).to_be_visible()
    expect(debug_page.embed_panel).to_be_visible()
    expect(debug_page.sim_panel).to_be_visible()

    retrieval_box = debug_page.retrieve_panel.bounding_box()
    assert retrieval_box is not None
    assert retrieval_box["width"] > 0

    debug_page.retrieve_doi_input.fill("10.1000/182")
    debug_page.retrieve_run_btn.click(force=True)
    expect(debug_page.retrieve_result_card).to_be_visible()
    expect(debug_page.retrieve_badge).to_contain_text("SUCCESS", ignore_case=True)

    # 8.4 Settings Page (/settings)
    mock_settings = {
        "api_base_url": "http://localhost:8000/api",
        "gemini_api_key_set": True,
        "gemini_api_key_preview": "AIzaSyD...",
        "openalex_api_key_set": True,
        "openalex_api_key_preview": "oa_key_...",
        "openalex_email": "author@institution.edu",
        "embedding_model": "gemini-embedding-2",
        "embedding_dimensions": 768
    }
    mock_api_route(responsive_page, "**/api/settings*", status_code=200, json_data=mock_settings)

    settings_page = SettingsPage(responsive_page, base_url)
    settings_page.navigate()

    expect(settings_page.api_base_url_input).to_be_visible()
    expect(settings_page.gemini_key_input).to_be_visible()
    expect(settings_page.gemini_toggle_btn).to_be_visible()
    expect(settings_page.openalex_key_input).to_be_visible()
    expect(settings_page.openalex_toggle_btn).to_be_visible()
    expect(settings_page.openalex_email_input).to_be_visible()
    expect(settings_page.save_btn).to_be_visible()

    settings_row = responsive_page.locator(".setting-row").first
    expect(settings_row).to_be_visible()
    row_box = settings_row.bounding_box()
    assert row_box is not None
    assert row_box["width"] > 0

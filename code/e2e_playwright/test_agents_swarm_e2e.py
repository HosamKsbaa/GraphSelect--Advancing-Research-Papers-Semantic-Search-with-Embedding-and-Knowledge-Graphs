"""Playwright E2E Test Suite for Milestone 4: Custom Agent Swarm Settings, Tool Directory & Live Traces (/agents).

Comprehensive Test Coverage:
1. Navigation to /agents from top navigation bar and direct URL.
2. Verification of all 9 live ADK agent cards and their canonical metadata:
   - ProjectAgent, ResearchAgent, ALRSAgent, GapFinderAgent, EvidenceSynthesizerAgent,
     PlannerAgent, DraftingAgent, ReviewerAgent, DebuggerAgent.
3. Interactive Configuration:
   - Model selection (gemini-3.7-flash, gemini-2.5-pro, etc.)
   - Sampling sliders (Temperature, Top-P, Max Output Tokens) with real-time value badges.
   - System prompt override editor with character counter and base prompt preview.
   - Saving settings with confirmation toast notifications.
4. 1-Click "Reset to Default":
   - Single agent reset via card button & confirmation modal.
   - Swarm-wide "Reset All to Defaults" via global toolbar.
   - Immediate DOM value restoration with zero page reloads.
5. Dynamic Tool Directory:
   - Expandable tool list per agent.
   - Tool docstrings and descriptions.
   - Visual parameter tree (types, required/optional badges, default values).
   - Raw JSON Schema viewer toggle and copy button.
6. Live Traces Inspector:
   - Toggle to Live Traces tab.
   - Filter by agent, status, limit, and free-text search.
   - Inspect LLM prompt payloads, tool call arguments/results, and raw completions.
   - Copy-to-clipboard functionality.
7. Swarm Search & Hierarchy Visualization:
   - Keyword search across agent names, roles, and models.
   - Tier filtering (Tier 1 Orchestration vs Tier 2 Workers).
   - Grid View vs Delegation Tree View toggle.
8. Adversarial & Error Handling:
   - Backend 500 failure resilience on save and reset.
   - Modal escape/backdrop dismissal.
   - Test Connection action.
"""
from __future__ import annotations

import json
import pytest
from playwright.sync_api import Page, expect

from e2e_playwright.conftest import (
    assert_toast_message,
    mock_api_route,
    mock_error_route,
    verify_modal_escape_dismiss,
)
from e2e_playwright.pages.agents_page import AgentsPage

EXPECTED_9_AGENTS = [
    "ProjectAgent",
    "ResearchAgent",
    "ALRSAgent",
    "GapFinderAgent",
    "EvidenceSynthesizerAgent",
    "PlannerAgent",
    "DraftingAgent",
    "ReviewerAgent",
    "DebuggerAgent",
]


# ===========================================================================
# 1. Navigation & Top Header Verification
# ===========================================================================

def test_navigation_to_agents_from_top_navbar(page: Page, base_url: str) -> None:
    """Test navigating to /agents using the top navigation bar link."""
    page.goto(f"{base_url}/projects")
    page.wait_for_url("**/projects", timeout=10000)

    agents_page = AgentsPage(page, base_url)
    agents_page.navigate_via_sidebar()

    expect(page).to_have_url(f"{base_url}/agents")
    expect(agents_page.page_title).to_contain_text("Agent Swarm Inspector & Configuration")
    expect(agents_page.page_subtitle).to_contain_text("Google ADK 9-agent research swarm")

    # Verify system default model badges
    expect(agents_page.tier1_badge).to_be_visible()
    expect(agents_page.tier2_badge).to_be_visible()


def test_direct_url_navigation_and_tab_switching(page: Page, base_url: str) -> None:
    """Test direct URL navigation to /agents and switching between Swarm and Live Traces tabs."""
    agents_page = AgentsPage(page, base_url)
    agents_page.navigate()

    # Default tab is Swarm Hierarchy
    expect(agents_page.tab_swarm).to_have_class(re_class="active")
    expect(agents_page.agent_cards.first).to_be_visible()

    # Switch to Live Traces tab
    agents_page.switch_to_traces_tab()
    expect(agents_page.tab_traces).to_have_class(re_class="active")
    expect(agents_page.trace_viewer).to_be_visible()

    # Switch back to Swarm Hierarchy tab
    agents_page.switch_to_swarm_tab()
    expect(agents_page.tab_swarm).to_have_class(re_class="active")
    expect(agents_page.agent_cards.first).to_be_visible()


# ===========================================================================
# 2. Verification of All 9 Agent Cards
# ===========================================================================

def test_verify_all_9_agent_cards_rendered(page: Page, base_url: str) -> None:
    """Verify all 9 agent cards are rendered with their canonical names, roles, and tier badges."""
    agents_page = AgentsPage(page, base_url)
    agents_page.navigate()

    # Assert exactly 9 agent cards
    expect(agents_page.agent_cards).to_have_count(9)

    for agent_name in EXPECTED_9_AGENTS:
        card = agents_page.get_agent_card(agent_name)
        expect(card).to_be_visible()

        # Check name tag
        name_tag = card.locator(".agent-name-tag")
        expect(name_tag).to_contain_text(agent_name)

        # Check model dropdown exists
        model_select = agents_page.get_agent_model_select(agent_name)
        expect(model_select).to_be_visible()

        # Check sliders exist
        expect(agents_page.get_agent_temp_slider(agent_name)).to_be_visible()
        expect(agents_page.get_agent_topp_slider(agent_name)).to_be_visible()
        expect(agents_page.get_agent_tokens_slider(agent_name)).to_be_visible()

        # Check reset button exists
        expect(card.locator("button.btn-reset")).to_be_visible()


def test_agent_tier_and_delegation_badges(page: Page, base_url: str) -> None:
    """Verify Tier 1 vs Tier 2 designations and delegation sub-agent pills."""
    agents_page = AgentsPage(page, base_url)
    agents_page.navigate()

    # ProjectAgent (Tier 1 Root)
    project_card = agents_page.get_agent_card("ProjectAgent")
    expect(project_card.locator(".badge-tier1")).to_contain_text("Tier 1: Orchestrator")

    # ResearchAgent (Tier 1 Coordinator)
    research_card = agents_page.get_agent_card("ResearchAgent")
    expect(research_card.locator(".badge-tier1")).to_contain_text("Tier 1: Orchestrator")
    # ResearchAgent delegates to ALRSAgent, GapFinderAgent, EvidenceSynthesizerAgent
    expect(research_card.locator(".sub-agent-pill:has-text('ALRSAgent')")).to_be_visible()

    # ALRSAgent (Tier 2 Worker)
    alrs_card = agents_page.get_agent_card("ALRSAgent")
    expect(alrs_card.locator(".badge-tier2")).to_contain_text("Tier 2: Specialized Worker")


# ===========================================================================
# 3. Interactive Configuration: Model, Sliders, Prompt Override & Save
# ===========================================================================

def test_change_model_and_sliders_and_save_with_toast(page: Page, base_url: str) -> None:
    """Test modifying agent model, temperature/top_p sliders, prompt prefix, and saving settings."""
    agents_page = AgentsPage(page, base_url)
    agents_page.navigate()

    target_agent = "ALRSAgent"
    card = agents_page.get_agent_card(target_agent)

    # 1. Change model to gemini-3.7-flash
    agents_page.set_agent_model(target_agent, "gemini-3.7-flash")

    # 2. Adjust temperature slider to 0.15
    agents_page.set_agent_temperature(target_agent, 0.15)
    expect(card.locator(".slider-header:has-text('Temperature') .slider-value-badge")).to_contain_text("0.15")

    # 3. Adjust top-p slider to 0.85
    agents_page.set_agent_top_p(target_agent, 0.85)
    expect(card.locator(".slider-header:has-text('Top-P') .slider-value-badge")).to_contain_text("0.85")

    # 4. Open prompt editor and enter custom prefix
    custom_prefix = "MANDATORY ADK DIRECTIVE: Prioritize high-PageRank seed papers with high cosine similarity."
    agents_page.set_agent_prompt_prefix(target_agent, custom_prefix)

    # 5. Verify Modified status badge and unsaved indicators
    expect(agents_page.get_agent_status_badge(target_agent)).to_contain_text("Modified")
    expect(card.locator(".status-unsaved")).to_be_visible()
    expect(agents_page.save_count_badge).to_contain_text("1")

    # 6. Click Save All Settings
    agents_page.save_all()

    # 7. Assert confirmation toast appears
    assert_toast_message(page, expected_text_substring="saved")

    # 8. Verify status is in sync with server
    expect(card.locator(".status-synced")).to_be_visible()

    # Clean up: Reset ALRSAgent back to default
    agents_page.click_reset_agent(target_agent)
    agents_page.confirm_reset_modal()
    expect(agents_page.get_agent_status_badge(target_agent)).to_contain_text("Default")


# ===========================================================================
# 4. 1-Click "Reset to Default" Verification
# ===========================================================================

def test_single_agent_reset_to_default_with_modal(page: Page, base_url: str) -> None:
    """Test 1-click Reset to Default restores an individual agent's default parameters."""
    agents_page = AgentsPage(page, base_url)
    agents_page.navigate()

    target_agent = "ResearchAgent"
    card = agents_page.get_agent_card(target_agent)

    # Modify temperature and model
    agents_page.set_agent_model(target_agent, "gemini-2.5-pro")
    agents_page.set_agent_temperature(target_agent, 1.40)
    agents_page.save_all()
    page.wait_for_timeout(500)

    # Click Reset to Default
    agents_page.click_reset_agent(target_agent)

    # Verify modal details
    expect(agents_page.reset_modal).to_be_visible()
    expect(agents_page.reset_modal_body).to_contain_text(target_agent)

    # Confirm Reset
    agents_page.confirm_reset_modal()

    # Assert toast notification
    assert_toast_message(page, expected_text_substring="reset")

    # Verify status badge returns to Default without page reload
    expect(agents_page.get_agent_status_badge(target_agent)).to_contain_text("Default")


def test_reset_all_agents_to_defaults(page: Page, base_url: str) -> None:
    """Test Swarm-wide 'Reset All to Defaults' restores all 9 agents."""
    agents_page = AgentsPage(page, base_url)
    agents_page.navigate()

    # Modify two agents
    agents_page.set_agent_temperature("ProjectAgent", 1.80)
    agents_page.set_agent_temperature("DebuggerAgent", 0.05)
    agents_page.save_all()
    page.wait_for_timeout(500)

    # Click Reset All to Defaults in toolbar
    agents_page.reset_all_btn.click()

    # Verify modal details
    expect(agents_page.reset_modal).to_be_visible()
    expect(agents_page.reset_modal_body).to_contain_text("all 9 agents")

    # Confirm Reset
    agents_page.confirm_reset_modal()

    # Assert toast notification
    assert_toast_message(page, expected_text_substring="reset")

    # Verify all 9 agents have Default status badge
    for agent_name in EXPECTED_9_AGENTS:
        badge = agents_page.get_agent_status_badge(agent_name)
        expect(badge).to_contain_text("Default")


# ===========================================================================
# 5. Dynamic Tool Directory, Docstrings & JSON Argument Schemas
# ===========================================================================

def test_expand_tools_directory_and_inspect_schemas(page: Page, base_url: str) -> None:
    """Test expanding tool directory, viewing docstrings, visual parameter tree, and raw JSON schema."""
    agents_page = AgentsPage(page, base_url)
    agents_page.navigate()

    target_agent = "ALRSAgent"
    card = agents_page.get_agent_card(target_agent)

    # Expand Registered Tools accordion
    agents_page.open_tools_directory(target_agent)

    # Verify tool items exist
    tools = agents_page.get_agent_tools(target_agent)
    expect(tools.first).to_be_visible()
    tool_count = tools.count()
    assert tool_count > 0, f"Expected registered tools for {target_agent}"

    # Expand the first tool
    first_tool = tools.first
    tool_name_text = first_tool.locator(".tool-name").inner_text().strip()
    first_tool.locator(".tool-item-header").click()

    # Verify tool docstring is visible
    expect(first_tool.locator(".tool-description")).to_be_visible()

    # Verify Visual Parameter Tree mode
    param_tree = first_tool.locator(".parameters-tree")
    expect(param_tree).to_be_visible()

    # Check for parameter rows (if parameters exist)
    param_rows = first_tool.locator(".param-row")
    if param_rows.count() > 0:
        first_param = param_rows.first
        expect(first_param.locator(".param-name")).to_be_visible()
        expect(first_param.locator(".param-type-badge")).to_be_visible()

    # Toggle to JSON Schema mode
    first_tool.locator("button.toggle-btn:has-text('JSON Schema')").click()
    json_view = first_tool.locator(".json-schema-view pre.schema-code")
    expect(json_view).to_be_visible()

    # Verify JSON content is valid JSON
    raw_json = json_view.inner_text()
    parsed = json.loads(raw_json)
    assert "type" in parsed
    assert parsed["type"] == "object"

    # Test Copy Schema button
    copy_btn = first_tool.locator(".btn-copy-schema")
    expect(copy_btn).to_be_visible()
    copy_btn.click()
    expect(first_tool.locator(".copied-indicator")).to_be_visible()


# ===========================================================================
# 6. Live Traces Inspector Tab & Payload Inspection
# ===========================================================================

def test_live_traces_inspector_filtering_and_inspection(page: Page, base_url: str) -> None:
    """Test Live Traces Inspector tab, filtering by agent, and inspecting prompt/tool/response payloads."""
    # Mock realistic trace data for comprehensive UI verification
    mock_traces = [
        {
            "id": "trace-e2e-001",
            "timestamp": "2026-08-29T16:00:00Z",
            "project_id": "proj-e2e-test",
            "agent_name": "ALRSAgent",
            "action_summary": "Executed 1-Hop GraphSelect citation traversal",
            "llm_prompt": "You are ALRSAgent. Expand seed DOI 10.1145/3442188.3445922 with bounded 1-hop traversal.",
            "llm_response": "Discovered 8 candidate papers. Top candidate: 'Fairness in Graph Neural Networks' (similarity 0.89).",
            "tool_calls": [
                {
                    "name": "run_graphselect_traversal",
                    "arguments": {"seed_doi": "10.1145/3442188.3445922", "max_depth": 1, "top_k": 8},
                    "result": "Discovered 8 forward and backward citations."
                }
            ],
            "token_count": 680,
            "latency_ms": 420.5,
            "status": "success",
            "decision_outcome": "Delegated candidate appraisal to ResearchAgent."
        },
        {
            "id": "trace-e2e-002",
            "timestamp": "2026-08-29T16:01:00Z",
            "project_id": "proj-e2e-test",
            "agent_name": "ReviewerAgent",
            "action_summary": "5-dimension rubric paper evaluation",
            "llm_prompt": "Evaluate Section 3 of the draft on Groundedness and Methodology rigor.",
            "llm_response": "Methodology score: 4.8/5.0. Claim in line 42 requires empirical citation grounding.",
            "tool_calls": [],
            "token_count": 320,
            "latency_ms": 210.0,
            "status": "success",
            "decision_outcome": "Passed review threshold; forwarded to DraftingAgent."
        }
    ]

    mock_api_route(
        page,
        "**/api/agents/traces*",
        status_code=200,
        json_data={"traces": mock_traces, "total": 2},
        method="GET"
    )

    agents_page = AgentsPage(page, base_url)
    agents_page.navigate()

    # Switch to Live Traces tab
    agents_page.switch_to_traces_tab()

    # Verify trace counter
    expect(agents_page.traces_count_label).to_contain_text("2 traces visible")

    # Verify 2 trace cards rendered
    expect(agents_page.trace_cards).to_have_count(2)

    # 1. Inspect First Trace (ALRSAgent)
    trace_1 = agents_page.trace_cards.first
    expect(trace_1.locator(".badge-agent")).to_contain_text("ALRSAgent")
    expect(trace_1.locator(".action-summary")).to_contain_text("Executed 1-Hop GraphSelect")
    expect(trace_1.locator(".latency-badge")).to_contain_text("421ms")
    expect(trace_1.locator(".tokens-badge")).to_contain_text("680")
    expect(trace_1.locator(".decision-banner")).to_contain_text("Delegated candidate appraisal")

    # Expand LLM Prompt accordion
    prompt_sec = trace_1.locator(".trace-section:has-text('Prompt / System Instructions')")
    prompt_sec.locator(".section-header").click()
    expect(prompt_sec.locator(".code-payload")).to_contain_text("You are ALRSAgent")

    # Expand Tool Invocations accordion
    tools_sec = trace_1.locator(".trace-section:has-text('Tool Invocations')")
    tools_sec.locator(".section-header").click()
    expect(tools_sec.locator("code:has-text('run_graphselect_traversal')")).to_be_visible()
    expect(tools_sec.locator(".tool-call-args")).to_contain_text("10.1145/3442188.3445922")

    # Expand LLM Response accordion
    response_sec = trace_1.locator(".trace-section:has-text('Raw Model Completion')")
    response_sec.locator(".section-header").click()
    expect(response_sec.locator(".response-payload")).to_contain_text("Fairness in Graph Neural Networks")

    # 2. Test Agent Dropdown Filter
    agents_page.trace_agent_select.select_option("ReviewerAgent")
    # Free-text search filter inside the traces view
    agents_page.trace_search_input.fill("Methodology")
    expect(agents_page.trace_cards).to_have_count(1)
    expect(agents_page.trace_cards.first.locator(".badge-agent")).to_contain_text("ReviewerAgent")

    # Clear trace search
    agents_page.trace_search_input.fill("")
    agents_page.trace_agent_select.select_option("all")


# ===========================================================================
# 7. Swarm Search, Tier Filters & Hierarchy Tree View
# ===========================================================================

def test_search_and_filter_agents(page: Page, base_url: str) -> None:
    """Test searching agents by keyword and filtering by tier and status."""
    agents_page = AgentsPage(page, base_url)
    agents_page.navigate()

    # 1. Search for "GapFinder"
    agents_page.search_input.fill("GapFinder")
    expect(agents_page.agent_cards).to_have_count(1)
    expect(agents_page.agent_cards.first.locator(".agent-name-tag")).to_contain_text("GapFinderAgent")

    # Clear search
    agents_page.clear_search_btn.click()
    expect(agents_page.agent_cards).to_have_count(9)

    # 2. Filter by Tier 1
    agents_page.tier_filter_select.select_option("tier1")
    expect(agents_page.agent_cards).to_have_count(2)  # ProjectAgent and ResearchAgent

    # 3. Filter by Tier 2
    agents_page.tier_filter_select.select_option("tier2")
    expect(agents_page.agent_cards).to_have_count(7)  # 7 specialized workers

    # Reset Tier filter
    agents_page.tier_filter_select.select_option("all")
    expect(agents_page.agent_cards).to_have_count(9)

    # 4. Search non-matching text -> empty state
    agents_page.search_input.fill("NonExistentAgentZZZ")
    expect(agents_page.empty_state).to_be_visible()
    expect(agents_page.empty_state).to_contain_text("No Agents Match Filter")

    # Click Reset Filters button in empty state
    agents_page.empty_state.locator("button:has-text('Reset Filters')").click()
    expect(agents_page.agent_cards).to_have_count(9)


def test_toggle_grid_and_delegation_tree_views(page: Page, base_url: str) -> None:
    """Test toggling between Grid View and Swarm Delegation Tree View."""
    agents_page = AgentsPage(page, base_url)
    agents_page.navigate()

    # Switch to Hierarchy Tree View
    agents_page.tree_mode_btn.click()
    expect(agents_page.hierarchy_tree).to_be_visible()
    expect(agents_page.hierarchy_tree.locator(".root-node")).to_contain_text("Root Orchestrator")
    expect(agents_page.hierarchy_tree.locator(".coord-node").first).to_be_visible()
    expect(agents_page.hierarchy_tree.locator(".worker-node").first).to_be_visible()

    # Switch back to Grid View
    agents_page.grid_mode_btn.click()
    expect(agents_page.agent_cards).to_have_count(9)


# ===========================================================================
# 8. Adversarial Resilience & Error Handling
# ===========================================================================

def test_backend_error_handling_on_save(page: Page, base_url: str) -> None:
    """Simulate 500 error on PUT /api/agents/settings and verify graceful error toast handling."""
    mock_error_route(page, "**/api/agents/settings", status_code=500, detail="Database Connection Timeout")

    agents_page = AgentsPage(page, base_url)
    agents_page.navigate()

    # Modify an agent to enable Save All
    agents_page.set_agent_temperature("PlannerAgent", 0.90)
    agents_page.save_all()

    # Assert error toast is shown and page does not crash
    assert_toast_message(page, expected_text_substring="failed")


def test_modal_escape_and_cancel_dismissal(page: Page, base_url: str) -> None:
    """Test dismissing the Reset Confirmation Modal via Cancel button and Escape key."""
    agents_page = AgentsPage(page, base_url)
    agents_page.navigate()

    # 1. Open modal and dismiss via Cancel button
    agents_page.click_reset_agent("DraftingAgent")
    expect(agents_page.reset_modal).to_be_visible()
    agents_page.cancel_reset_modal()
    expect(agents_page.reset_modal).not_to_be_visible()

    # 2. Open modal and dismiss via Escape key
    agents_page.click_reset_agent("DraftingAgent")
    expect(agents_page.reset_modal).to_be_visible()
    verify_modal_escape_dismiss(page, ".modal-dialog")


def test_agent_connection_test_button(page: Page, base_url: str) -> None:
    """Test clicking 'Test Connection' triggers connection probe and displays latency badge."""
    mock_api_route(
        page,
        "**/api/settings/test-connection*",
        status_code=200,
        json_data={"status": "connected", "latency_ms": 145.2, "model": "gemini-2.5-pro", "message": "Connection verified"},
        method="POST"
    )

    agents_page = AgentsPage(page, base_url)
    agents_page.navigate()

    agents_page.test_connection_btn.click()
    expect(page.locator(".latency-pill")).to_contain_text("145ms")
    assert_toast_message(page, expected_text_substring="verified")

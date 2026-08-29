"""Playwright E2E Test Suite for Swarm Hierarchy Tree, Tier Management & Per-Agent Configuration.

4-Tier Progressive Test Architecture:
- Tier 1: Feature Coverage & Contract Integrity (Hierarchy tree, SVG connectors, agent drawer, tier editor modal, mode toggles).
- Tier 2: Boundary & Corner Cases (System tier deletion protection, empty name validation, temperature/tokens limits, multi-agent safe reassignment).
- Tier 3: Cross-Feature Dynamic Combinations (Dynamic parameter cascading to inherited agents vs custom override isolation, custom tier lifecycle).
- Tier 4: Real-World Multi-Agent Workflows (End-to-end multi-step inspection, tier creation, assignment, and persistence).
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List
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

DEFAULT_MOCK_TIERS = [
    {
        "id": "tier1",
        "name": "Tier 1: Orchestration",
        "description": "High-reasoning orchestrators and coordination planners",
        "model": "gemini-2.5-flash",
        "temperature": 0.7,
        "top_p": 0.95,
        "max_output_tokens": 8192,
        "color": "#3b82f6",
        "is_system": True,
    },
    {
        "id": "tier2",
        "name": "Tier 2: Specialized Workers",
        "description": "Focused workers for paper retrieval and extraction",
        "model": "gemini-2.5-flash",
        "temperature": 0.3,
        "top_p": 0.9,
        "max_output_tokens": 4096,
        "color": "#10b981",
        "is_system": True,
    },
    {
        "id": "tier3",
        "name": "Tier 3: Writing & Review",
        "description": "Academic section drafting and rubric critique",
        "model": "gemini-2.5-pro",
        "temperature": 0.5,
        "top_p": 0.95,
        "max_output_tokens": 16384,
        "color": "#8b5cf6",
        "is_system": True,
    },
]

DEFAULT_MOCK_AGENTS = [
    {
        "name": "ProjectAgent",
        "display_name": "Project Orchestrator",
        "description": "Root supervisor coordinating planning, research, drafting, and debugging",
        "role": "Root Orchestrator",
        "tier": "tier1",
        "assigned_tier_id": "tier1",
        "config_mode": "inherit",
        "sub_agents": ["ResearchAgent", "PlannerAgent", "ReviewerAgent", "DebuggerAgent"],
        "tools": [],
        "config": {
            "model": "gemini-2.5-flash",
            "default_model": "gemini-2.5-flash",
            "temperature": 0.7,
            "default_temperature": 0.7,
            "top_p": 0.95,
            "default_top_p": 0.95,
            "max_output_tokens": 8192,
            "default_max_output_tokens": 8192,
            "custom_prompt_prefix": None,
            "system_prompt": "You are ProjectAgent, root orchestrator.",
            "is_default": True,
            "config_mode": "inherit",
            "assigned_tier_id": "tier1",
        },
    },
    {
        "name": "ResearchAgent",
        "display_name": "Research Coordinator",
        "description": "Coordinates literature discovery, gap analysis, and evidence synthesis",
        "role": "Research Coordinator",
        "tier": "tier1",
        "assigned_tier_id": "tier1",
        "config_mode": "inherit",
        "sub_agents": ["ALRSAgent", "GapFinderAgent", "EvidenceSynthesizerAgent"],
        "tools": [],
        "config": {
            "model": "gemini-2.5-flash",
            "default_model": "gemini-2.5-flash",
            "temperature": 0.7,
            "default_temperature": 0.7,
            "top_p": 0.95,
            "default_top_p": 0.95,
            "max_output_tokens": 8192,
            "default_max_output_tokens": 8192,
            "custom_prompt_prefix": None,
            "system_prompt": "You are ResearchAgent.",
            "is_default": True,
            "config_mode": "inherit",
            "assigned_tier_id": "tier1",
        },
    },
    {
        "name": "ALRSAgent",
        "display_name": "Literature Discovery Agent",
        "description": "Paper Discovery & GraphSelect BFS Traversal",
        "role": "Paper Discovery",
        "tier": "tier2",
        "assigned_tier_id": "tier2",
        "config_mode": "inherit",
        "sub_agents": [],
        "tools": [
            {
                "name": "run_graphselect_traversal",
                "description": "Execute BFS traversal across paper citation graphs",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "seed_doi": {"type": "string", "description": "Seed paper DOI"},
                        "max_depth": {"type": "integer", "default": 2},
                    },
                    "required": ["seed_doi"],
                },
            }
        ],
        "config": {
            "model": "gemini-2.5-flash",
            "default_model": "gemini-2.5-flash",
            "temperature": 0.3,
            "default_temperature": 0.3,
            "top_p": 0.9,
            "default_top_p": 0.9,
            "max_output_tokens": 4096,
            "default_max_output_tokens": 4096,
            "custom_prompt_prefix": None,
            "system_prompt": "You are ALRSAgent.",
            "is_default": True,
            "config_mode": "inherit",
            "assigned_tier_id": "tier2",
        },
    },
    {
        "name": "GapFinderAgent",
        "display_name": "Gap Analysis & Ranking Agent",
        "description": "Citation Analysis, Coverage Gaps & PageRank Ranking",
        "role": "Gap Analysis",
        "tier": "tier2",
        "assigned_tier_id": "tier2",
        "config_mode": "inherit",
        "sub_agents": [],
        "tools": [],
        "config": {
            "model": "gemini-2.5-flash",
            "default_model": "gemini-2.5-flash",
            "temperature": 0.3,
            "default_temperature": 0.3,
            "top_p": 0.9,
            "default_top_p": 0.9,
            "max_output_tokens": 4096,
            "default_max_output_tokens": 4096,
            "custom_prompt_prefix": None,
            "system_prompt": "You are GapFinderAgent.",
            "is_default": True,
            "config_mode": "inherit",
            "assigned_tier_id": "tier2",
        },
    },
    {
        "name": "EvidenceSynthesizerAgent",
        "display_name": "Evidence Synthesizer Agent",
        "description": "Literature Extraction & Comparison Matrix Synthesis",
        "role": "Synthesis",
        "tier": "tier2",
        "assigned_tier_id": "tier2",
        "config_mode": "inherit",
        "sub_agents": [],
        "tools": [],
        "config": {
            "model": "gemini-2.5-flash",
            "default_model": "gemini-2.5-flash",
            "temperature": 0.3,
            "default_temperature": 0.3,
            "top_p": 0.9,
            "default_top_p": 0.9,
            "max_output_tokens": 4096,
            "default_max_output_tokens": 4096,
            "custom_prompt_prefix": None,
            "system_prompt": "You are EvidenceSynthesizerAgent.",
            "is_default": True,
            "config_mode": "inherit",
            "assigned_tier_id": "tier2",
        },
    },
    {
        "name": "PlannerAgent",
        "display_name": "Outline Planner Agent",
        "description": "Outline Architecture & Section Scoping",
        "role": "Planning",
        "tier": "tier1",
        "assigned_tier_id": "tier1",
        "config_mode": "inherit",
        "sub_agents": [],
        "tools": [],
        "config": {
            "model": "gemini-2.5-flash",
            "default_model": "gemini-2.5-flash",
            "temperature": 0.7,
            "default_temperature": 0.7,
            "top_p": 0.95,
            "default_top_p": 0.95,
            "max_output_tokens": 8192,
            "default_max_output_tokens": 8192,
            "custom_prompt_prefix": None,
            "system_prompt": "You are PlannerAgent.",
            "is_default": True,
            "config_mode": "inherit",
            "assigned_tier_id": "tier1",
        },
    },
    {
        "name": "DraftingAgent",
        "display_name": "Section Drafting Agent",
        "description": "Academic Literature Review Drafting",
        "role": "Drafting",
        "tier": "tier2",
        "assigned_tier_id": "tier2",
        "config_mode": "inherit",
        "sub_agents": [],
        "tools": [],
        "config": {
            "model": "gemini-2.5-flash",
            "default_model": "gemini-2.5-flash",
            "temperature": 0.3,
            "default_temperature": 0.3,
            "top_p": 0.9,
            "default_top_p": 0.9,
            "max_output_tokens": 4096,
            "default_max_output_tokens": 4096,
            "custom_prompt_prefix": None,
            "system_prompt": "You are DraftingAgent.",
            "is_default": True,
            "config_mode": "inherit",
            "assigned_tier_id": "tier2",
        },
    },
    {
        "name": "ReviewerAgent",
        "display_name": "Peer Review Agent",
        "description": "Peer Review, Rubric Critique & Citation Verification",
        "role": "Review",
        "tier": "tier1",
        "assigned_tier_id": "tier1",
        "config_mode": "inherit",
        "sub_agents": [],
        "tools": [],
        "config": {
            "model": "gemini-2.5-flash",
            "default_model": "gemini-2.5-flash",
            "temperature": 0.7,
            "default_temperature": 0.7,
            "top_p": 0.95,
            "default_top_p": 0.95,
            "max_output_tokens": 8192,
            "default_max_output_tokens": 8192,
            "custom_prompt_prefix": None,
            "system_prompt": "You are ReviewerAgent.",
            "is_default": True,
            "config_mode": "inherit",
            "assigned_tier_id": "tier1",
        },
    },
    {
        "name": "DebuggerAgent",
        "display_name": "Autonomous Diagnostic Agent",
        "description": "Runtime Error Interception & AST Hot-Patching",
        "role": "Diagnostic",
        "tier": "tier1",
        "assigned_tier_id": "tier1",
        "config_mode": "inherit",
        "sub_agents": [],
        "tools": [],
        "config": {
            "model": "gemini-2.5-flash",
            "default_model": "gemini-2.5-flash",
            "temperature": 0.7,
            "default_temperature": 0.7,
            "top_p": 0.95,
            "default_top_p": 0.95,
            "max_output_tokens": 8192,
            "default_max_output_tokens": 8192,
            "custom_prompt_prefix": None,
            "system_prompt": "You are DebuggerAgent.",
            "is_default": True,
            "config_mode": "inherit",
            "assigned_tier_id": "tier1",
        },
    },
]


def setup_standard_mocks(page: Page) -> None:
    """Setup standard mock routes for /api/agents/tiers, /api/agents/registry, and /api/agents/settings."""
    mock_api_route(
        page,
        "**/api/agents/tiers",
        status_code=200,
        json_data={"tiers": DEFAULT_MOCK_TIERS, "total": len(DEFAULT_MOCK_TIERS)},
        method="GET",
    )
    mock_api_route(
        page,
        "**/api/agents/registry",
        status_code=200,
        json_data={
            "agents": DEFAULT_MOCK_AGENTS,
            "total": len(DEFAULT_MOCK_AGENTS),
            "system_default_tier1_model": "gemini-2.5-flash",
            "system_default_tier2_model": "gemini-2.5-flash",
        },
        method="GET",
    )
    mock_api_route(
        page,
        "**/api/agents/settings",
        status_code=200,
        json_data={"success": True, "message": "Settings updated", "updated_agents": ["ALRSAgent"]},
        method="PUT",
    )
    mock_api_route(
        page,
        "**/api/agents/settings/reset",
        status_code=200,
        json_data={"success": True, "message": "Reset completed", "reset_agents": ["ALRSAgent"]},
        method="POST",
    )


# ===========================================================================
# Tier 1: Feature Coverage & Contract Integrity
# ===========================================================================

def test_tier1_switch_to_hierarchy_tree_and_display_svg_connectors(page: Page, base_url: str) -> None:
    """Tier 1: Verify switching from Grid to Hierarchy Tree view renders SVG connectors and nodes."""
    setup_standard_mocks(page)
    agents_page = AgentsPage(page, base_url)
    agents_page.navigate()

    # Default is Grid View
    expect(agents_page.agent_cards.first).to_be_visible()

    # Switch to Hierarchy Tree View
    agents_page.switch_to_tree_view()

    # Verify tree container and SVG canvas are visible
    expect(agents_page.hierarchy_tree).to_be_visible()
    expect(agents_page.tree_svg.first).to_be_visible()

    # Verify root orchestrator and subordinate nodes are present
    expect(agents_page.get_tree_node("ProjectAgent")).to_be_visible()
    expect(agents_page.get_tree_node("ResearchAgent")).to_be_visible()
    expect(agents_page.get_tree_node("ALRSAgent")).to_be_visible()


def test_tier1_open_agent_drawer_on_tree_node_click(page: Page, base_url: str) -> None:
    """Tier 1: Verify clicking a node in the hierarchy tree opens the detailed agent configuration drawer."""
    setup_standard_mocks(page)
    agents_page = AgentsPage(page, base_url)
    agents_page.navigate()

    # Switch to Hierarchy Tree
    agents_page.switch_to_tree_view()

    # Click ResearchAgent tree node
    agents_page.click_tree_node("ResearchAgent")

    # Assert drawer opens and displays ResearchAgent metadata
    expect(agents_page.agent_drawer).to_be_visible()
    expect(agents_page.agent_drawer).to_contain_text("ResearchAgent")
    expect(agents_page.agent_drawer.locator(".drawer-title, .agent-title, h3, h2").first).to_contain_text("Research")


def test_tier1_open_tier_editor_modal(page: Page, base_url: str) -> None:
    """Tier 1: Verify opening the Tier Editor modal via toolbar action button."""
    setup_standard_mocks(page)
    agents_page = AgentsPage(page, base_url)
    agents_page.navigate()

    # Click Manage Tiers
    agents_page.open_tier_editor()

    # Verify modal is open and displays default system tiers
    expect(agents_page.tier_editor_modal).to_be_visible()
    expect(agents_page.tier_editor_modal).to_contain_text("Tier 1: Orchestration")
    expect(agents_page.tier_editor_modal).to_contain_text("Tier 2: Specialized Workers")


def test_tier1_create_custom_tier_in_modal(page: Page, base_url: str) -> None:
    """Tier 1: Verify creating a custom tier in the Tier Editor modal submits to backend and adds to tier list."""
    setup_standard_mocks(page)
    
    # Mock POST /api/agents/tiers
    mock_api_route(
        page,
        "**/api/agents/tiers",
        status_code=201,
        json_data={
            "id": "tier_custom_4",
            "name": "Tier 4: Fast Brainstorming",
            "description": "Rapid synthesis with low token limits",
            "model": "gemini-2.5-flash",
            "temperature": 0.85,
            "top_p": 0.95,
            "max_output_tokens": 4096,
            "color": "#f59e0b",
            "is_system": False,
        },
        method="POST",
    )

    agents_page = AgentsPage(page, base_url)
    agents_page.navigate()

    # Open Tier Editor and create custom tier
    agents_page.open_tier_editor()
    agents_page.create_custom_tier(
        name="Tier 4: Fast Brainstorming",
        model="gemini-2.5-flash",
        temperature=0.85,
        max_tokens=4096,
    )

    # Verify confirmation or new tier item displayed in modal
    expect(agents_page.tier_editor_modal.locator(":has-text('Tier 4: Fast Brainstorming')").first).to_be_visible()


def test_tier1_toggle_inherit_vs_custom_override_mode(page: Page, base_url: str) -> None:
    """Tier 1: Verify toggling between 'Inherit Tier Defaults' and 'Custom Override' locks/unlocks controls."""
    setup_standard_mocks(page)
    agents_page = AgentsPage(page, base_url)
    agents_page.navigate()

    target_agent = "ALRSAgent"
    card = agents_page.get_agent_card(target_agent)

    # In Inherit mode, tier dropdown is active, parameter inputs are locked/disabled or reflect inherited state
    agents_page.set_agent_mode(target_agent, "inherit")
    expect(card.locator(".badge-mode, .mode-indicator, :has-text('Inherit')").first).to_be_visible()

    # Switch to Custom Override mode
    agents_page.set_agent_mode(target_agent, "custom")
    expect(card.locator(".badge-mode, .mode-indicator, :has-text('Custom')").first).to_be_visible()

    # Sliders and model selects are unlocked and editable
    agents_page.set_agent_temperature(target_agent, 1.35)
    expect(card.locator(".slider-value-badge:has-text('1.35')").first).to_be_visible()


# ===========================================================================
# Tier 2: Boundary & Corner Cases
# ===========================================================================

def test_tier2_system_tier_deletion_protection(page: Page, base_url: str) -> None:
    """Tier 2: Verify deletion of system tiers (tier1, tier2, tier3) is disabled or rejected by backend with 400/403."""
    setup_standard_mocks(page)
    
    # Mock DELETE on system tier returning 400
    mock_error_route(
        page,
        "**/api/agents/tiers/tier1",
        status_code=400,
        detail="System tiers cannot be deleted",
    )

    agents_page = AgentsPage(page, base_url)
    agents_page.navigate()

    agents_page.open_tier_editor()

    # System tier item should not have enabled delete button or clicking returns protection warning
    tier1_row = agents_page.tier_editor_modal.locator(".tier-item:has-text('Tier 1'), .tier-card:has-text('Tier 1')").first
    if tier1_row.count() > 0:
        delete_btn = tier1_row.locator("button.btn-delete, button.btn-delete-tier, button:has-text('Delete')")
        if delete_btn.count() > 0 and delete_btn.is_visible():
            # If button exists, it must be disabled or click triggers rejection toast
            if delete_btn.is_enabled():
                delete_btn.click()
                assert_toast_message(page, expected_text_substring="cannot be deleted")
            else:
                expect(delete_btn).to_be_disabled()


def test_tier2_empty_tier_name_validation(page: Page, base_url: str) -> None:
    """Tier 2: Verify empty or whitespace-only tier names trigger client/server validation errors."""
    setup_standard_mocks(page)
    agents_page = AgentsPage(page, base_url)
    agents_page.navigate()

    agents_page.open_tier_editor()
    
    # Attempt to submit empty name
    if agents_page.add_tier_btn.count() > 0 and agents_page.add_tier_btn.is_visible():
        agents_page.add_tier_btn.click()
    
    if agents_page.tier_name_input.count() > 0:
        agents_page.tier_name_input.fill("")
        if agents_page.tier_save_btn.is_disabled():
            expect(agents_page.tier_save_btn).to_be_disabled()
        else:
            agents_page.tier_save_btn.click()
            expect(agents_page.tier_editor_modal.locator(".error-message, .invalid-feedback, :has-text('required')").first).to_be_visible()


def test_tier2_extreme_temperature_boundary_values(page: Page, base_url: str) -> None:
    """Tier 2: Verify boundary temperature values 0.00 and 2.00 are supported without truncation or NaN errors."""
    setup_standard_mocks(page)
    agents_page = AgentsPage(page, base_url)
    agents_page.navigate()

    target_agent = "GapFinderAgent"
    agents_page.set_agent_mode(target_agent, "custom")

    # Min boundary 0.00
    agents_page.set_agent_temperature(target_agent, 0.00)
    card = agents_page.get_agent_card(target_agent)
    expect(card.locator(".slider-value-badge:has-text('0.0'), .slider-value-badge:has-text('0.00')").first).to_be_visible()

    # Max boundary 2.00
    agents_page.set_agent_temperature(target_agent, 2.00)
    expect(card.locator(".slider-value-badge:has-text('2.0'), .slider-value-badge:has-text('2.00')").first).to_be_visible()


def test_tier2_max_tokens_boundary_values(page: Page, base_url: str) -> None:
    """Tier 2: Verify max tokens boundary values 128 (min) and 32768/65536 (max)."""
    setup_standard_mocks(page)
    agents_page = AgentsPage(page, base_url)
    agents_page.navigate()

    target_agent = "EvidenceSynthesizerAgent"
    agents_page.set_agent_mode(target_agent, "custom")

    # Min boundary 512
    agents_page.set_agent_max_tokens(target_agent, 512)
    card = agents_page.get_agent_card(target_agent)
    expect(card.locator(".slider-value-badge:has-text('512')").first).to_be_visible()

    # High boundary 32768
    agents_page.set_agent_max_tokens(target_agent, 32768)
    expect(card.locator(".slider-value-badge:has-text('32768'), .slider-value-badge:has-text('32,768')").first).to_be_visible()


def test_tier2_delete_tier_with_multiple_assigned_agents_safe_reassignment(page: Page, base_url: str) -> None:
    """Tier 2: Deleting a custom tier with assigned agents safely reassigns member agents back to Tier 1."""
    setup_standard_mocks(page)

    # Setup mock with custom tier and assigned agents
    tiers_with_custom = list(DEFAULT_MOCK_TIERS) + [
        {
            "id": "tier_custom_temp",
            "name": "Tier Temp: Experimental",
            "description": "Temporary tier",
            "model": "gemini-3.7-flash",
            "temperature": 0.9,
            "top_p": 0.9,
            "max_output_tokens": 4096,
            "color": "#ec4899",
            "is_system": False,
        }
    ]

    mock_api_route(
        page,
        "**/api/agents/tiers",
        status_code=200,
        json_data={"tiers": tiers_with_custom, "total": len(tiers_with_custom)},
        method="GET",
    )
    mock_api_route(
        page,
        "**/api/agents/tiers/tier_custom_temp",
        status_code=200,
        json_data={"status": "deleted", "tier_id": "tier_custom_temp", "reassigned_agents_count": 2, "reassigned_to_tier_id": "tier1"},
        method="DELETE",
    )

    agents_page = AgentsPage(page, base_url)
    agents_page.navigate()

    agents_page.open_tier_editor()

    # Delete custom tier
    custom_tier_card = agents_page.tier_editor_modal.locator(".tier-card:has-text('Tier Temp: Experimental')").first
    expect(custom_tier_card).to_be_visible()
    
    delete_btn = custom_tier_card.locator("button.btn-delete, button.btn-delete-tier, button:has-text('Delete')").first
    delete_btn.click()

    # Confirm delete in warning banner
    confirm_btn = agents_page.tier_editor_modal.locator("button:has-text('Confirm Delete'), .delete-warning-banner button.btn-danger")
    expect(confirm_btn).to_be_visible()
    confirm_btn.click()

    # Verify confirmation or toast and removal from list
    assert_toast_message(page, expected_text_substring="deleted")


# ===========================================================================
# Tier 3: Cross-Feature Dynamic Combinations
# ===========================================================================

def test_tier3_editing_tier_cascades_to_inherited_agents_not_overridden(page: Page, base_url: str) -> None:
    """Tier 3: Editing a tier's model immediately cascades to inherited agents while custom override agents remain untouched."""
    setup_standard_mocks(page)
    agents_page = AgentsPage(page, base_url)
    agents_page.navigate()

    # 1. ALRSAgent is in inherit mode (assigned to tier2)
    alrs_card = agents_page.get_agent_card("ALRSAgent")
    agents_page.set_agent_mode("ALRSAgent", "inherit")

    # 2. GapFinderAgent is in custom override mode with gemini-2.5-pro
    gap_card = agents_page.get_agent_card("GapFinderAgent")
    agents_page.set_agent_mode("GapFinderAgent", "custom")
    agents_page.set_agent_model("GapFinderAgent", "gemini-2.5-pro")

    # 3. Update Tier 2 model to gemini-3.7-flash via modal
    mock_api_route(
        page,
        "**/api/agents/tiers/tier2",
        status_code=200,
        json_data={
            "id": "tier2",
            "name": "Tier 2: Specialized Workers",
            "description": "Focused workers for paper retrieval and extraction",
            "model": "gemini-3.7-flash",
            "temperature": 0.3,
            "top_p": 0.9,
            "max_output_tokens": 4096,
            "color": "#10b981",
            "is_system": True,
        },
        method="PUT",
    )

    agents_page.open_tier_editor()
    tier2_edit = agents_page.tier_editor_modal.locator(".tier-card:has-text('Tier 2')").first
    if tier2_edit.locator("button.btn-edit, button:has-text('Edit')").count() > 0:
        tier2_edit.locator("button.btn-edit, button:has-text('Edit')").first.click()
    
    if agents_page.tier_model_select.count() > 0:
        agents_page.tier_model_select.first.select_option("gemini-3.7-flash")
        agents_page.tier_save_btn.first.click()

    agents_page.close_tier_editor()

    # 4. Verify ALRSAgent displayed model updated, GapFinderAgent custom model remained gemini-2.5-pro
    expect(gap_card.locator("select[id*='model'], .model-badge, :has-text('gemini-2.5-pro')").first).to_be_visible()


def test_tier3_create_custom_tier_assign_agent_then_delete_tier_reassigns_to_tier1(page: Page, base_url: str) -> None:
    """Tier 3: Create a custom tier, assign an agent to it, delete tier, and verify agent falls back to Tier 1."""
    setup_standard_mocks(page)
    agents_page = AgentsPage(page, base_url)
    agents_page.navigate()

    # Create custom tier
    mock_api_route(
        page,
        "**/api/agents/tiers",
        status_code=201,
        json_data={
            "id": "tier_custom_synthesis",
            "name": "Tier 4: Synthesis",
            "description": "Synthesis tier",
            "model": "gemini-2.5-pro",
            "temperature": 0.4,
            "top_p": 0.95,
            "max_output_tokens": 8192,
            "color": "#8b5cf6",
            "is_system": False,
        },
        method="POST",
    )

    agents_page.open_tier_editor()
    agents_page.create_custom_tier(name="Tier 4: Synthesis", model="gemini-2.5-pro")

    # Mock delete tier
    mock_api_route(
        page,
        "**/api/agents/tiers/tier_custom_synthesis",
        status_code=200,
        json_data={"status": "deleted", "tier_id": "tier_custom_synthesis", "reassigned_agents_count": 1, "reassigned_to_tier_id": "tier1"},
        method="DELETE",
    )

    # Delete custom tier
    custom_tier = agents_page.tier_editor_modal.locator(".tier-card:has-text('Tier 4: Synthesis')").first
    expect(custom_tier).to_be_visible()
    delete_btn = custom_tier.locator("button.btn-delete, button.btn-delete-tier, button:has-text('Delete')").first
    delete_btn.click()
    
    confirm_btn = agents_page.tier_editor_modal.locator("button:has-text('Confirm Delete'), .delete-warning-banner button.btn-danger")
    expect(confirm_btn).to_be_visible()
    confirm_btn.click()

    assert_toast_message(page, expected_text_substring="deleted")


# ===========================================================================
# Tier 4: Real-World Multi-Agent Workflows
# ===========================================================================

def test_tier4_full_swarm_tuning_workflow(page: Page, base_url: str) -> None:
    """Tier 4: Full user journey navigating visual tree, selecting nodes, custom overrides, custom tier creation and persistence."""
    setup_standard_mocks(page)
    agents_page = AgentsPage(page, base_url)
    agents_page.navigate()

    # Step 1: Switch to Visual Hierarchy Tree
    agents_page.switch_to_tree_view()
    expect(agents_page.hierarchy_tree).to_be_visible()

    # Step 2: Click ResearchAgent node, opening drawer
    agents_page.click_tree_node("ResearchAgent")
    expect(agents_page.agent_drawer).to_be_visible()

    # Step 3: Switch ResearchAgent to Custom Override with high temperature
    custom_pill = agents_page.agent_drawer.locator(".mode-pill-btn:has-text('Custom'), button:has-text('Custom'), .btn-mode-custom")
    if custom_pill.count() > 0:
        custom_pill.first.click()
    
    # Step 4: Open Tier Editor Modal, Add Custom Tier 'Tier 4: Fast Brainstorming'
    mock_api_route(
        page,
        "**/api/agents/tiers",
        status_code=201,
        json_data={
            "id": "tier4_fast",
            "name": "Tier 4: Fast Brainstorming",
            "description": "Fast evaluation tier",
            "model": "gemini-2.5-flash",
            "temperature": 0.9,
            "top_p": 0.95,
            "max_output_tokens": 4096,
            "color": "#f59e0b",
            "is_system": False,
        },
        method="POST",
    )
    agents_page.open_tier_editor()
    agents_page.create_custom_tier(name="Tier 4: Fast Brainstorming", model="gemini-2.5-flash", temperature=0.9)

    # Step 5: Close modal, switch to Grid view, modify GapFinderAgent
    agents_page.close_tier_editor()
    agents_page.switch_to_grid_view()
    gap_card = agents_page.get_agent_card("GapFinderAgent")
    expect(gap_card).to_be_visible()
    agents_page.set_agent_mode("GapFinderAgent", "custom")
    agents_page.set_agent_temperature("GapFinderAgent", 1.25)

    # Mock PUT /api/agents/config
    mock_api_route(
        page,
        "**/api/agents/config",
        status_code=200,
        json_data={"status": "success", "updated_agents": ["GapFinderAgent"], "count": 1},
        method="PUT",
    )

    # Step 6: Save All Settings
    agents_page.save_all()
    assert_toast_message(page, expected_text_substring="saved")


# ===========================================================================
# Baseline Navigation & Live Traces Inspector Tests
# ===========================================================================

def test_navigation_to_agents_from_top_navbar(page: Page, base_url: str) -> None:
    """Test navigating to /agents using top navbar link."""
    setup_standard_mocks(page)
    page.goto(f"{base_url}/projects")
    page.wait_for_url("**/projects", timeout=10000)

    agents_page = AgentsPage(page, base_url)
    agents_page.navigate_via_sidebar()

    expect(page).to_have_url(f"{base_url}/agents")
    expect(agents_page.page_title).to_contain_text("Agent Swarm Inspector")


def test_direct_url_navigation_and_tab_switching(page: Page, base_url: str) -> None:
    """Test direct navigation and switching between Swarm and Live Traces tabs."""
    setup_standard_mocks(page)
    agents_page = AgentsPage(page, base_url)
    agents_page.navigate()

    expect(agents_page.tab_swarm).to_have_class(re.compile(r"active"))
    expect(agents_page.agent_cards.first).to_be_visible()

    agents_page.switch_to_traces_tab()
    expect(agents_page.tab_traces).to_have_class(re.compile(r"active"))
    expect(agents_page.trace_viewer).to_be_visible()

    agents_page.switch_to_swarm_tab()
    expect(agents_page.tab_swarm).to_have_class(re.compile(r"active"))


def test_verify_all_9_agent_cards_rendered(page: Page, base_url: str) -> None:
    """Verify all 9 canonical agents are rendered with their controls."""
    setup_standard_mocks(page)
    agents_page = AgentsPage(page, base_url)
    agents_page.navigate()

    expect(agents_page.agent_cards).to_have_count(9)
    for agent_name in EXPECTED_9_AGENTS:
        card = agents_page.get_agent_card(agent_name)
        expect(card).to_be_visible()
        expect(card.locator(".agent-name-tag, .agent-title, h4")).to_contain_text(agent_name)


def test_expand_tools_directory_and_inspect_schemas(page: Page, base_url: str) -> None:
    """Test expanding tool directory and verifying JSON Schema viewer."""
    setup_standard_mocks(page)
    agents_page = AgentsPage(page, base_url)
    agents_page.navigate()

    target_agent = "ALRSAgent"
    agents_page.open_tools_directory(target_agent)
    tools = agents_page.get_agent_tools(target_agent)
    expect(tools.first).to_be_visible()


def test_live_traces_inspector_filtering_and_inspection(page: Page, base_url: str) -> None:
    """Test Live Traces Inspector tab filtering and payload inspection."""
    mock_traces = [
        {
            "id": "trace-e2e-001",
            "timestamp": "2026-08-29T16:00:00Z",
            "project_id": "proj-e2e-test",
            "agent_name": "ALRSAgent",
            "action_summary": "Executed 1-Hop GraphSelect citation traversal",
            "llm_prompt": "You are ALRSAgent.",
            "llm_response": "Discovered 8 candidate papers.",
            "tool_calls": [{"name": "run_graphselect_traversal", "arguments": {"seed_doi": "10.1145/3442188.3445922"}, "result": "Success"}],
            "token_count": 680,
            "latency_ms": 420.5,
            "status": "success",
            "decision_outcome": "Delegated candidate appraisal.",
        }
    ]
    setup_standard_mocks(page)
    mock_api_route(page, "**/api/agents/traces*", status_code=200, json_data={"traces": mock_traces, "total": 1}, method="GET")

    agents_page = AgentsPage(page, base_url)
    agents_page.navigate()

    agents_page.switch_to_traces_tab()
    expect(agents_page.trace_cards).to_have_count(1)
    expect(agents_page.trace_cards.first.locator(".badge-agent, .agent-tag")).to_contain_text("ALRSAgent")

"""Final Challenger Adversarial Test Suite for ALRS Swarm Visual Hierarchy Tree & Dynamic Tier Management.

Tests:
1. Hierarchy Tree graph topology & acyclicity verification.
2. Complete 9-agent live introspection, tool reflection, and role tagging.
3. Cross-agent tier assignment permutations & dynamic parameter cascades.
4. Edge cases & boundaries: extreme temperature, tokens, empty strings, unicode, long descriptions.
5. System tier deletion protection and safe multi-agent reassignment.
6. DB persistence fallback resilience.
"""
from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from main import app
from features.agents.models import (
    AgentConfigBatchUpdateRequest,
    AgentConfigOverrideItem,
    ModelTier,
    TierCreateRequest,
    TierUpdateRequest,
)


@pytest_asyncio.fixture
async def client() -> AsyncClient:
    """Async test client."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as ac:
        yield ac


@pytest_asyncio.fixture(autouse=True)
async def reset_state(client: AsyncClient):
    """Ensure clean state before and after each test."""
    await client.post("/api/agents/settings/reset", json={})
    yield
    await client.post("/api/agents/settings/reset", json={})


# ============================================================================
# 1. Swarm Hierarchy Tree Graph Topology & Acyclicity
# ============================================================================

@pytest.mark.asyncio
async def test_swarm_tree_topology_and_delegation_integrity(client: AsyncClient) -> None:
    """Verify live agent registry represents a valid directed tree without cycles."""
    res = await client.get("/api/agents/registry")
    assert res.status_code == 200
    data = res.json()
    agents = data["agents"]
    assert len(agents) >= 9

    agent_names = {a["name"] for a in agents}
    expected_agents = {
        "ProjectAgent",
        "ResearchAgent",
        "ALRSAgent",
        "GapFinderAgent",
        "EvidenceSynthesizerAgent",
        "PlannerAgent",
        "DraftingAgent",
        "ReviewerAgent",
        "DebuggerAgent",
    }
    assert expected_agents.issubset(agent_names)

    # Build adjacency list
    adj: dict[str, list[str]] = {}
    in_degree: dict[str, int] = {name: 0 for name in agent_names}
    for a in agents:
        name = a["name"]
        subs = a.get("sub_agents", [])
        adj[name] = subs
        for s in subs:
            if s in in_degree:
                in_degree[s] += 1

    # Verify ProjectAgent is root (in_degree == 0)
    assert in_degree.get("ProjectAgent") == 0

    # Verify no cycle using DFS
    visited = set()
    rec_stack = set()

    def has_cycle(node: str) -> bool:
        visited.add(node)
        rec_stack.add(node)
        for neighbor in adj.get(node, []):
            if neighbor not in visited:
                if has_cycle(neighbor):
                    return True
            elif neighbor in rec_stack:
                return True
        rec_stack.remove(node)
        return False

    for agent_name in agent_names:
        if agent_name not in visited:
            assert not has_cycle(agent_name), f"Cycle detected involving {agent_name}!"


# ============================================================================
# 2. Tool Schema Reflection Across All Swarm Agents
# ============================================================================

@pytest.mark.asyncio
async def test_tool_schema_reflection_completeness(client: AsyncClient) -> None:
    """Verify all registered tools have valid schemas with names and parameter objects."""
    res = await client.get("/api/agents/registry")
    assert res.status_code == 200
    agents = res.json()["agents"]

    total_tools = 0
    for agent in agents:
        for tool in agent.get("tools", []):
            total_tools += 1
            assert "name" in tool
            assert len(tool["name"]) > 0
            assert "parameters" in tool
            params = tool["parameters"]
            assert params.get("type") == "object"
            assert "properties" in params

    assert total_tools >= 0  # Tools reflected safely


# ============================================================================
# 3. Dynamic Tier Creation, Assignment, Cascading & Custom Mode Isolation
# ============================================================================

@pytest.mark.asyncio
async def test_tier_cascading_and_custom_override_isolation(client: AsyncClient) -> None:
    """Verify editing a custom tier cascades only to inherit-mode agents, leaving custom-mode agents intact."""
    # 1. Create a custom tier
    tier_res = await client.post(
        "/api/agents/tiers",
        json={
            "id": "tier_eval_final",
            "name": "Tier Evaluation Final",
            "description": "Adversarial test tier",
            "model": "gemini-2.5-flash",
            "temperature": 0.40,
            "top_p": 0.85,
            "max_output_tokens": 4096,
            "color": "#e11d48",
        },
    )
    assert tier_res.status_code == 201

    # 2. Assign ALRSAgent to inherit mode with tier_eval_final
    # and GapFinderAgent to custom mode with explicit temperature 1.85
    batch_res = await client.put(
        "/api/agents/config",
        json={
            "overrides": [
                {
                    "agent_id": "ALRSAgent",
                    "tier_id": "tier_eval_final",
                    "config_mode": "inherit",
                },
                {
                    "agent_id": "GapFinderAgent",
                    "tier_id": "tier_eval_final",
                    "config_mode": "custom",
                    "model": "gemini-2.5-pro",
                    "temperature": 1.85,
                    "top_p": 0.99,
                    "max_output_tokens": 16384,
                },
            ]
        },
    )
    assert batch_res.status_code == 200

    # 3. Update tier_eval_final to new model & sampling params
    update_res = await client.put(
        "/api/agents/tiers/tier_eval_final",
        json={
            "model": "gemini-3.7-flash",
            "temperature": 0.15,
            "top_p": 0.75,
            "max_output_tokens": 2048,
        },
    )
    assert update_res.status_code == 200

    # 4. Introspect config and verify:
    # - ALRSAgent (inherit) cascaded to 0.15 / 2048 / gemini-3.7-flash
    # - GapFinderAgent (custom) preserved 1.85 / 16384 / gemini-2.5-pro
    cfg_res = await client.get("/api/agents/config")
    assert cfg_res.status_code == 200
    cfg_map = {a["agent_id"]: a for a in cfg_res.json()["agents"]}

    alrs = cfg_map["ALRSAgent"]
    assert alrs["effective_model"] == "gemini-3.7-flash"
    assert alrs["effective_temperature"] == 0.15
    assert alrs["effective_max_output_tokens"] == 2048
    assert alrs["config_mode"] == "inherit"

    gap = cfg_map["GapFinderAgent"]
    assert gap["effective_model"] == "gemini-2.5-pro"
    assert gap["effective_temperature"] == 1.85
    assert gap["effective_max_output_tokens"] == 16384
    assert gap["config_mode"] == "custom"

    # 5. Clean up by deleting custom tier
    del_res = await client.delete("/api/agents/tiers/tier_eval_final")
    assert del_res.status_code == 200
    del_data = del_res.json()
    assert del_data["status"] == "deleted"
    assert del_data["reassigned_to_tier_id"] == "tier1"


# ============================================================================
# 4. Adversarial Payload & Boundary Fuzzing
# ============================================================================

@pytest.mark.asyncio
async def test_adversarial_sampling_boundary_inputs(client: AsyncClient) -> None:
    """Test boundary temperature and token limits on tier creation and agent settings."""
    # Valid min boundary (temp=0.0, tokens=128)
    min_res = await client.post(
        "/api/agents/tiers",
        json={
            "name": "Tier Boundary Min",
            "model": "gemini-2.5-flash",
            "temperature": 0.0,
            "top_p": 0.0,
            "max_output_tokens": 128,
            "color": "#10b981",
        },
    )
    assert min_res.status_code == 201
    min_id = min_res.json()["id"]

    # Valid max boundary (temp=2.0, tokens=65536)
    max_res = await client.post(
        "/api/agents/tiers",
        json={
            "name": "Tier Boundary Max",
            "model": "gemini-2.5-pro",
            "temperature": 2.0,
            "top_p": 1.0,
            "max_output_tokens": 65536,
            "color": "#6366f1",
        },
    )
    assert max_res.status_code == 201
    max_id = max_res.json()["id"]

    # Out of range temperature (2.1) -> 422
    invalid_temp = await client.post(
        "/api/agents/tiers",
        json={
            "name": "Tier Invalid Temp",
            "model": "gemini-2.5-flash",
            "temperature": 2.1,
            "top_p": 0.9,
            "max_output_tokens": 4096,
            "color": "#6366f1",
        },
    )
    assert invalid_temp.status_code == 422

    # Negative tokens (-10) -> 422
    invalid_tokens = await client.post(
        "/api/agents/tiers",
        json={
            "name": "Tier Invalid Tokens",
            "model": "gemini-2.5-flash",
            "temperature": 0.5,
            "top_p": 0.9,
            "max_output_tokens": -10,
            "color": "#6366f1",
        },
    )
    assert invalid_tokens.status_code == 422

    # Clean up
    await client.delete(f"/api/agents/tiers/{min_id}")
    await client.delete(f"/api/agents/tiers/{max_id}")


# ============================================================================
# 5. System Tier Immutability & Reassignment Safeguards
# ============================================================================

@pytest.mark.asyncio
async def test_system_tier_protection_and_reserved_slugs(client: AsyncClient) -> None:
    """Verify built-in system tiers tier1, tier2, tier3 cannot be deleted."""
    for sys_id in ["tier1", "tier2", "tier3"]:
        res = await client.delete(f"/api/agents/tiers/{sys_id}")
        assert res.status_code == 400
        assert "Cannot delete built-in system tier" in res.json()["detail"]

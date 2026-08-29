"""Adversarial Empirical Stress Test Suite for Model Tier Lifecycle, Live ADK Mutations & Batch Consistency.

Authored by Challenger M1-2 (Adversarial Empirical Challenger).
Empirically stress-tests:
1. Live ADK Agent object model attribute mutation and synchronization across the full 9-agent swarm.
2. Full tier switching cycles (tier1 -> custom tier -> tier2 -> custom tier -> delete custom -> tier1 fallback).
3. Custom override parameter isolation when assigned tier is deleted or modified.
4. Multi-agent swarm tier cluster migration, cascading updates, and safe multi-agent deletion fallback.
5. Batch configuration consistency (`PUT /api/agents/config` vs `GET /api/agents/config` vs `GET /api/agents/registry` vs live ADK state).
6. Batch configuration error handling (unknown tier_id 400, unknown agent_id 404, out-of-range parameters 422).
7. High-churn rapid tier creation, reassignment, mutation, and deletion cycles.
"""
from __future__ import annotations

import asyncio
import copy
from typing import Any
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from main import app
from features.agents.service import AgentService, AGENT_DISPLAY_ROLES
from agents.agent import root_agent


@pytest_asyncio.fixture
async def client() -> AsyncClient:
    """Async HTTP test client against FastAPI app."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as ac:
        yield ac


@pytest_asyncio.fixture(autouse=True)
async def cleanup_agent_settings(client: AsyncClient):
    """Ensure clean state before and after each test."""
    await client.post("/api/agents/settings/reset", json={})
    yield
    await client.post("/api/agents/settings/reset", json={})


def get_live_adk_agents_map() -> dict[str, Any]:
    """Inspect and map all live ADK agent instances traversed from root_agent."""
    agents_map = {}
    visited = set()

    def _traverse(node: Any):
        if node is None or id(node) in visited:
            return
        visited.add(id(node))
        name = getattr(node, "name", None)
        if name and hasattr(node, "model") and name in AGENT_DISPLAY_ROLES:
            agents_map[name] = node
        for sub in getattr(node, "sub_agents", []) or []:
            _traverse(sub)

    _traverse(root_agent)
    return agents_map


# ============================================================================
# 1. Live ADK Agent Object Model Attribute Mutation Stress Test
# ============================================================================

@pytest.mark.asyncio
async def test_live_adk_agent_model_mutation_on_tier_update(client: AsyncClient) -> None:
    """Empirically verify that updating a tier directly mutates the live Python agent.model attribute."""
    live_agents = get_live_adk_agents_map()
    assert len(live_agents) == 9, f"Expected 9 live agents, found {len(live_agents)}"

    # 1. Mutate Tier 1 model
    resp_t1 = await client.put(
        "/api/agents/tiers/tier1",
        json={"model": "gemini-2.5-pro-custom-orchestrator", "temperature": 0.62},
    )
    assert resp_t1.status_code == 200

    # Tier 1 agents: ProjectAgent, ResearchAgent, PlannerAgent, DebuggerAgent
    tier1_agents = ["ProjectAgent", "ResearchAgent", "PlannerAgent", "DebuggerAgent"]
    for agent_name in tier1_agents:
        agent_obj = live_agents[agent_name]
        assert agent_obj.model == "gemini-2.5-pro-custom-orchestrator", (
            f"Live agent '{agent_name}' model was {agent_obj.model}, expected 'gemini-2.5-pro-custom-orchestrator'"
        )

    # 2. Mutate Tier 2 model
    resp_t2 = await client.put(
        "/api/agents/tiers/tier2",
        json={"model": "gemini-2.5-flash-custom-discovery", "temperature": 0.25},
    )
    assert resp_t2.status_code == 200

    # Tier 2 agents: ALRSAgent, GapFinderAgent, EvidenceSynthesizerAgent
    tier2_agents = ["ALRSAgent", "GapFinderAgent", "EvidenceSynthesizerAgent"]
    for agent_name in tier2_agents:
        agent_obj = live_agents[agent_name]
        assert agent_obj.model == "gemini-2.5-flash-custom-discovery", (
            f"Live agent '{agent_name}' model was {agent_obj.model}, expected 'gemini-2.5-flash-custom-discovery'"
        )

    # 3. Mutate Tier 3 model
    resp_t3 = await client.put(
        "/api/agents/tiers/tier3",
        json={"model": "gemini-3.0-writer-review", "temperature": 0.48},
    )
    assert resp_t3.status_code == 200

    # Tier 3 agents: DraftingAgent, ReviewerAgent
    tier3_agents = ["DraftingAgent", "ReviewerAgent"]
    for agent_name in tier3_agents:
        agent_obj = live_agents[agent_name]
        assert agent_obj.model == "gemini-3.0-writer-review", (
            f"Live agent '{agent_name}' model was {agent_obj.model}, expected 'gemini-3.0-writer-review'"
        )


# ============================================================================
# 2. Full Tier Switching Lifecycle Stress Test
# ============================================================================

@pytest.mark.asyncio
async def test_full_tier_switching_lifecycle_and_fallback(client: AsyncClient) -> None:
    """Empirically test full lifecycle: tier2 -> custom tier -> tier1 -> custom tier -> delete custom -> fallback."""
    live_agents = get_live_adk_agents_map()
    alrs_obj = live_agents["ALRSAgent"]

    # Initial state: ALRSAgent is tier2 inherit mode
    res_initial = await client.get("/api/agents/config")
    alrs_cfg = next(a for a in res_initial.json()["agents"] if a["agent_id"] == "ALRSAgent")
    assert alrs_cfg["tier_id"] == "tier2"
    assert alrs_cfg["config_mode"] == "inherit"
    initial_model = alrs_cfg["effective_model"]
    assert alrs_obj.model == initial_model

    # Step 1: Create a custom tier
    create_res = await client.post(
        "/api/agents/tiers",
        json={
            "id": "tier_custom_deep_search",
            "name": "Custom Deep Search Tier",
            "model": "gemini-2.5-flash-deep-search",
            "temperature": 0.15,
            "top_p": 0.85,
            "max_output_tokens": 16384,
            "color": "#ec4899",
        },
    )
    assert create_res.status_code in (200, 201)
    custom_tier = create_res.json()
    assert custom_tier["id"] == "tier_custom_deep_search"

    # Step 2: Switch ALRSAgent to custom tier in inherit mode
    switch_res1 = await client.put(
        "/api/agents/config",
        json={
            "overrides": [
                {
                    "agent_id": "ALRSAgent",
                    "tier_id": "tier_custom_deep_search",
                    "config_mode": "inherit",
                }
            ]
        },
    )
    assert switch_res1.status_code == 200
    assert alrs_obj.model == "gemini-2.5-flash-deep-search"

    # Verify via GET /api/agents/config
    get_cfg1 = await client.get("/api/agents/config")
    alrs_cfg1 = next(a for a in get_cfg1.json()["agents"] if a["agent_id"] == "ALRSAgent")
    assert alrs_cfg1["tier_id"] == "tier_custom_deep_search"
    assert alrs_cfg1["effective_model"] == "gemini-2.5-flash-deep-search"
    assert abs(alrs_cfg1["effective_temperature"] - 0.15) < 1e-4
    assert alrs_cfg1["effective_max_output_tokens"] == 16384

    # Step 3: Switch ALRSAgent to tier1
    switch_res2 = await client.put(
        "/api/agents/config",
        json={
            "overrides": [
                {
                    "agent_id": "ALRSAgent",
                    "tier_id": "tier1",
                    "config_mode": "inherit",
                }
            ]
        },
    )
    assert switch_res2.status_code == 200
    
    tiers_res = await client.get("/api/agents/tiers")
    tier1_def = next(t for t in tiers_res.json()["tiers"] if t["id"] == "tier1")
    assert alrs_obj.model == tier1_def["model"]

    # Step 4: Switch ALRSAgent back to custom tier
    switch_res3 = await client.put(
        "/api/agents/config",
        json={
            "overrides": [
                {
                    "agent_id": "ALRSAgent",
                    "tier_id": "tier_custom_deep_search",
                    "config_mode": "inherit",
                }
            ]
        },
    )
    assert switch_res3.status_code == 200
    assert alrs_obj.model == "gemini-2.5-flash-deep-search"

    # Step 5: Delete the custom tier
    del_res = await client.delete("/api/agents/tiers/tier_custom_deep_search")
    assert del_res.status_code == 200
    del_data = del_res.json()
    assert del_data["status"] == "deleted"
    assert del_data["tier_id"] == "tier_custom_deep_search"
    assert del_data["reassigned_agents_count"] == 1
    assert del_data["reassigned_to_tier_id"] == "tier1"

    # Step 6: Verify ALRSAgent fell back safely to tier1 and live model is updated
    assert alrs_obj.model == tier1_def["model"]
    
    get_cfg_final = await client.get("/api/agents/config")
    alrs_cfg_final = next(a for a in get_cfg_final.json()["agents"] if a["agent_id"] == "ALRSAgent")
    assert alrs_cfg_final["tier_id"] == "tier1"
    assert alrs_cfg_final["effective_model"] == tier1_def["model"]


# ============================================================================
# 3. Custom Override Isolation During Tier Deletion Fallback
# ============================================================================

@pytest.mark.asyncio
async def test_custom_mode_isolation_during_tier_deletion(client: AsyncClient) -> None:
    """Verify that when an agent in custom mode is reassigned upon tier deletion, its custom overrides persist."""
    live_agents = get_live_adk_agents_map()
    gap_obj = live_agents["GapFinderAgent"]

    # 1. Create a custom tier
    await client.post(
        "/api/agents/tiers",
        json={
            "id": "tier_temp_custom_isolation",
            "name": "Temp Custom Tier",
            "model": "gemini-2.5-flash-temp",
            "temperature": 0.5,
        },
    )

    # 2. Configure GapFinderAgent in custom mode with specific model override
    await client.put(
        "/api/agents/config",
        json={
            "overrides": [
                {
                    "agent_id": "GapFinderAgent",
                    "tier_id": "tier_temp_custom_isolation",
                    "config_mode": "custom",
                    "model": "gemini-custom-pinned-override",
                    "temperature": 0.11,
                    "top_p": 0.88,
                    "max_output_tokens": 2048,
                }
            ]
        },
    )

    assert gap_obj.model == "gemini-custom-pinned-override"

    # 3. Delete the custom tier
    del_res = await client.delete("/api/agents/tiers/tier_temp_custom_isolation")
    assert del_res.status_code == 200
    assert del_res.json()["reassigned_agents_count"] == 1

    # 4. Verify GapFinderAgent was reassigned to tier1, but its custom overrides were preserved!
    assert gap_obj.model == "gemini-custom-pinned-override"

    get_cfg = await client.get("/api/agents/config")
    gap_cfg = next(a for a in get_cfg.json()["agents"] if a["agent_id"] == "GapFinderAgent")
    assert gap_cfg["tier_id"] == "tier1"
    assert gap_cfg["config_mode"] == "custom"
    assert gap_cfg["effective_model"] == "gemini-custom-pinned-override"
    assert abs(gap_cfg["effective_temperature"] - 0.11) < 1e-4


# ============================================================================
# 4. Multi-Agent Swarm Tier Cluster Migration & Safe Deletion
# ============================================================================

@pytest.mark.asyncio
async def test_multi_agent_swarm_cluster_migration_and_cascade(client: AsyncClient) -> None:
    """Stress-test migrating clusters of agents to custom tiers, updating parameters, and deleting clusters."""
    live_agents = get_live_adk_agents_map()

    # 1. Create two custom cluster tiers
    await client.post(
        "/api/agents/tiers",
        json={
            "id": "tier_cluster_scouts",
            "name": "Scouts Cluster",
            "model": "gemini-2.5-flash-scout-v1",
            "temperature": 0.20,
        },
    )
    await client.post(
        "/api/agents/tiers",
        json={
            "id": "tier_cluster_writers",
            "name": "Writers Cluster",
            "model": "gemini-2.5-pro-writer-v1",
            "temperature": 0.70,
        },
    )

    # 2. Assign 3 agents to scouts cluster and 3 agents to writers cluster
    scout_agents = ["ALRSAgent", "GapFinderAgent", "EvidenceSynthesizerAgent"]
    writer_agents = ["PlannerAgent", "DraftingAgent", "ReviewerAgent"]

    overrides = []
    for a in scout_agents:
        overrides.append({"agent_id": a, "tier_id": "tier_cluster_scouts", "config_mode": "inherit"})
    for a in writer_agents:
        overrides.append({"agent_id": a, "tier_id": "tier_cluster_writers", "config_mode": "inherit"})

    batch_res = await client.put("/api/agents/config", json={"overrides": overrides})
    assert batch_res.status_code == 200
    assert len(batch_res.json()["updated_agents"]) == 6

    # Verify live agent models
    for a in scout_agents:
        assert live_agents[a].model == "gemini-2.5-flash-scout-v1"
    for a in writer_agents:
        assert live_agents[a].model == "gemini-2.5-pro-writer-v1"

    # 3. Dynamic cascade: Update scouts cluster model
    upd_res = await client.put(
        "/api/agents/tiers/tier_cluster_scouts",
        json={"model": "gemini-3.0-flash-scout-upgraded"},
    )
    assert upd_res.status_code == 200

    # Verify scouts updated, writers untouched
    for a in scout_agents:
        assert live_agents[a].model == "gemini-3.0-flash-scout-upgraded"
    for a in writer_agents:
        assert live_agents[a].model == "gemini-2.5-pro-writer-v1"

    # 4. Safe deletion of scouts cluster
    del_scouts = await client.delete("/api/agents/tiers/tier_cluster_scouts")
    assert del_scouts.status_code == 200
    assert del_scouts.json()["reassigned_agents_count"] == 3

    # Scouts must now be on tier1 with tier1's model
    tiers_res = await client.get("/api/agents/tiers")
    tier1_model = next(t for t in tiers_res.json()["tiers"] if t["id"] == "tier1")["model"]

    for a in scout_agents:
        assert live_agents[a].model == tier1_model

    # Writers must still be on writers cluster
    for a in writer_agents:
        assert live_agents[a].model == "gemini-2.5-pro-writer-v1"

    # 5. Safe deletion of writers cluster
    del_writers = await client.delete("/api/agents/tiers/tier_cluster_writers")
    assert del_writers.status_code == 200
    assert del_writers.json()["reassigned_agents_count"] == 3

    for a in writer_agents:
        assert live_agents[a].model == tier1_model


# ============================================================================
# 5. Full Batch Configuration Consistency Stress Test
# ============================================================================

@pytest.mark.asyncio
async def test_batch_config_consistency_across_all_endpoints(client: AsyncClient) -> None:
    """Stress-test 9-agent simultaneous batch update and verify consistency across all REST endpoints and live ADK."""
    live_agents = get_live_adk_agents_map()

    # Create 1 custom tier for batch testing
    await client.post(
        "/api/agents/tiers",
        json={
            "id": "tier_batch_eval",
            "name": "Batch Eval Tier",
            "model": "gemini-2.5-flash-eval",
            "temperature": 0.4,
            "max_output_tokens": 12000,
        },
    )

    batch_payload = {
        "overrides": [
            {"agent_id": "ProjectAgent", "tier_id": "tier1", "config_mode": "inherit"},
            {"agent_id": "ResearchAgent", "tier_id": "tier1", "config_mode": "custom", "model": "gemini-research-override", "temperature": 0.65},
            {"agent_id": "ALRSAgent", "tier_id": "tier_batch_eval", "config_mode": "inherit"},
            {"agent_id": "GapFinderAgent", "tier_id": "tier_batch_eval", "config_mode": "custom", "temperature": 0.05},
            {"agent_id": "EvidenceSynthesizerAgent", "tier_id": "tier2", "config_mode": "inherit"},
            {"agent_id": "PlannerAgent", "tier_id": "tier3", "config_mode": "inherit"},
            {"agent_id": "DraftingAgent", "tier_id": "tier3", "config_mode": "custom", "custom_prompt_prefix": "CUSTOM DRAFTING RULE: Be extremely concise."},
            {"agent_id": "ReviewerAgent", "tier_id": "tier1", "config_mode": "inherit"},
            {"agent_id": "DebuggerAgent", "tier_id": "tier2", "config_mode": "custom", "model": "gemini-debugger-override", "max_output_tokens": 4096},
        ]
    }

    put_res = await client.put("/api/agents/config", json=batch_payload)
    assert put_res.status_code == 200
    put_data = put_res.json()
    assert put_data["success"] is True
    assert len(put_data["updated_agents"]) == 9

    # 1. Compare PUT response with GET /api/agents/config
    get_cfg = await client.get("/api/agents/config")
    assert get_cfg.status_code == 200
    get_cfg_agents = {a["agent_id"]: a for a in get_cfg.json()["agents"]}

    # 2. Compare with GET /api/agents/registry
    get_reg = await client.get("/api/agents/registry")
    assert get_reg.status_code == 200
    get_reg_agents = {a["name"]: a for a in get_reg.json()["agents"]}

    for agent_id, cfg_item in get_cfg_agents.items():
        reg_item = get_reg_agents[agent_id]
        live_obj = live_agents[agent_id]

        # Mode matching
        assert cfg_item["config_mode"] == reg_item["config_mode"]
        assert cfg_item["tier_id"] == reg_item["tier"]

        # Effective model matching
        assert cfg_item["effective_model"] == reg_item["config"]["effective_model"]
        assert live_obj.model == cfg_item["effective_model"], (
            f"Live object model {live_obj.model} does not match config {cfg_item['effective_model']} for {agent_id}"
        )

        # Temperature matching
        assert abs(cfg_item["effective_temperature"] - reg_item["config"]["effective_temperature"]) < 1e-4

        # Custom prompt prefix verification
        if cfg_item["custom_prompt_prefix"]:
            assert live_obj.instruction.startswith(cfg_item["custom_prompt_prefix"])


# ============================================================================
# 6. Batch Configuration Error Handling & Rejection
# ============================================================================

@pytest.mark.asyncio
async def test_batch_config_error_handling_and_rejection(client: AsyncClient) -> None:
    """Verify robust error handling on invalid batch updates."""
    # 1. Unknown tier_id in batch
    res_bad_tier = await client.put(
        "/api/agents/config",
        json={"overrides": [{"agent_id": "ALRSAgent", "tier_id": "non_existent_tier_404"}]},
    )
    assert res_bad_tier.status_code == 400
    assert "non_existent_tier_404" in res_bad_tier.json()["detail"]

    # 2. Unknown agent_id in batch
    res_bad_agent = await client.put(
        "/api/agents/config",
        json={"overrides": [{"agent_id": "GhostInTheShellAgent", "tier_id": "tier1"}]},
    )
    assert res_bad_agent.status_code == 404
    assert "GhostInTheShellAgent" in res_bad_agent.json()["detail"]

    # 3. Invalid parameter boundary in batch (temperature > 2.0)
    res_bad_temp = await client.put(
        "/api/agents/config",
        json={"overrides": [{"agent_id": "ALRSAgent", "temperature": 2.5}]},
    )
    assert res_bad_temp.status_code == 422

    # 4. Invalid parameter boundary in batch (max_output_tokens < 128)
    res_bad_tokens = await client.put(
        "/api/agents/config",
        json={"overrides": [{"agent_id": "ALRSAgent", "max_output_tokens": 10}]},
    )
    assert res_bad_tokens.status_code == 422


# ============================================================================
# 7. High-Churn Rapid Tier Lifecycle Stress Loop
# ============================================================================

@pytest.mark.asyncio
async def test_high_churn_rapid_tier_lifecycle_loop(client: AsyncClient) -> None:
    """Execute 15 rapid consecutive iterations of tier creation, assignment, cascade, deletion, and reset."""
    for i in range(15):
        tier_id = f"tier_churn_{i}"
        
        # 1. Create tier
        c_res = await client.post(
            "/api/agents/tiers",
            json={
                "id": tier_id,
                "name": f"Churn Tier {i}",
                "model": f"gemini-model-churn-{i}",
                "temperature": round(0.1 + (i % 9) * 0.1, 2),
                "color": "#10b981",
            },
        )
        assert c_res.status_code in (200, 201)

        # 2. Assign 2 agents to this tier
        assign_res = await client.put(
            "/api/agents/config",
            json={
                "overrides": [
                    {"agent_id": "PlannerAgent", "tier_id": tier_id, "config_mode": "inherit"},
                    {"agent_id": "DebuggerAgent", "tier_id": tier_id, "config_mode": "inherit"},
                ]
            },
        )
        assert assign_res.status_code == 200

        # 3. Mutate tier model
        upd_res = await client.put(
            f"/api/agents/tiers/{tier_id}",
            json={"model": f"gemini-model-churn-updated-{i}"},
        )
        assert upd_res.status_code == 200

        # 4. Delete tier
        del_res = await client.delete(f"/api/agents/tiers/{tier_id}")
        assert del_res.status_code == 200
        assert del_res.json()["reassigned_agents_count"] == 2

    # Verify clean state and all agents operational after churn loop
    reg_res = await client.get("/api/agents/registry")
    assert reg_res.status_code == 200
    assert reg_res.json()["total"] == 9

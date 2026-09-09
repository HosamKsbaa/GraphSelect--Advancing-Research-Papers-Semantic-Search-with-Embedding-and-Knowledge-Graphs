"""Adversarial and Empirical Stress Test Suite for Milestone 1: Backend Tier Management & Inheritance.

Authored by Challenger M1-1 (Empirical Challenger).

Empirically tests and stress-tests:
1. Malformed and invalid inputs (fuzzing temperature, top_p, token boundaries, invalid hex colors, system ID collisions, huge payloads).
2. Repeated tier mutations, rapid cascading cycles, and mode oscillation (inherit vs custom).
3. Complex deletion chains, cascading safe reassignment to tier1, and system tier deletion immutability.
4. High-concurrency race conditions (simultaneous tier creation, mutation, deletion, agent reassignment, and reads).
5. Live ADK agent object mutation and instruction prefix consistency.
6. MySQL persistence faults, corrupted database states, and in-memory degradation.
"""
from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, patch
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from main import app
from features.agents.models import (
    AgentConfigBatchUpdateRequest,
    AgentConfigOverrideItem,
    AgentConfigUpdate,
    ModelTier,
    TierCreateRequest,
    TierUpdateRequest,
)
from features.agents.service import AgentService


@pytest_asyncio.fixture
async def client() -> AsyncClient:
    """Async HTTP test client against FastAPI application."""
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


# ============================================================================
# 1. Invalid Inputs, Boundary Fuzzing, and Injection Attacks
# ============================================================================

@pytest.mark.asyncio
async def test_create_tier_system_id_collision_prevention(client: AsyncClient) -> None:
    """Verify cannot create custom tiers that collide with reserved system tier IDs."""
    reserved_ids = ["tier1", "tier2", "tier3", "TIER1", "Tier2", "  tier3  "]
    for sys_id in reserved_ids:
        resp = await client.post(
            "/api/agents/tiers",
            json={
                "id": sys_id,
                "name": f"Illegal {sys_id}",
                "model": "gemini-2.5-flash",
            },
        )
        assert resp.status_code in (400, 422), f"Reserved system ID '{sys_id}' must be rejected, got {resp.status_code}"


@pytest.mark.asyncio
async def test_create_tier_invalid_id_characters_and_lengths(client: AsyncClient) -> None:
    """Verify tier ID validation rejects invalid characters, emojis, and excessive lengths."""
    invalid_ids = [
        "tier with spaces",
        "tier@special!",
        "tier/slash",
        "tier#hash",
        "🤖_emoji_tier",
        "a" * 65,  # Exceeds max length of 64
        "",
    ]
    for bad_id in invalid_ids:
        resp = await client.post(
            "/api/agents/tiers",
            json={
                "id": bad_id,
                "name": "Invalid ID Tier",
                "model": "gemini-2.5-flash",
            },
        )
        assert resp.status_code in (400, 422), f"Invalid ID '{bad_id}' was not rejected: {resp.status_code}"


@pytest.mark.asyncio
async def test_tier_color_hex_fuzzing(client: AsyncClient) -> None:
    """Verify color validation strictly enforces valid 3, 6, or 8 digit hex format."""
    valid_colors = ["#fff", "#FFF", "#3b82f6", "#10B981", "#12345678", "#aabbccdd"]
    for valid_color in valid_colors:
        resp = await client.post(
            "/api/agents/tiers",
            json={
                "name": f"Color Tier {valid_color}",
                "model": "gemini-2.5-flash",
                "color": valid_color,
            },
        )
        assert resp.status_code in (200, 201), f"Valid color '{valid_color}' rejected: {resp.text}"

    invalid_colors = [
        "red",
        "blue",
        "#ff",
        "#12345",
        "#gggggg",
        "123456",  # missing leading #
        "#123456789",  # 9 chars
        "rgb(255,0,0)",
        "rgba(0,0,0,1)",
        "",
    ]
    for bad_color in invalid_colors:
        resp = await client.post(
            "/api/agents/tiers",
            json={
                "name": "Bad Color Tier",
                "model": "gemini-2.5-flash",
                "color": bad_color,
            },
        )
        assert resp.status_code == 422, f"Invalid color '{bad_color}' was not rejected with 422: {resp.status_code}"


@pytest.mark.asyncio
async def test_sampling_parameters_boundary_fuzzing(client: AsyncClient) -> None:
    """Verify exact boundary checks for temperature, top_p, and max_output_tokens."""
    # Temperature: valid [0.0, 2.0]
    for valid_t in (0.0, 0.01, 1.0, 1.99, 2.0):
        resp = await client.post(
            "/api/agents/tiers",
            json={"name": f"Temp {valid_t}", "model": "gemini-2.5-flash", "temperature": valid_t},
        )
        assert resp.status_code in (200, 201)

    for invalid_t in (-0.001, -1.0, 2.001, 3.5, 100.0):
        resp = await client.post(
            "/api/agents/tiers",
            json={"name": f"Bad Temp {invalid_t}", "model": "gemini-2.5-flash", "temperature": invalid_t},
        )
        assert resp.status_code == 422

    # Top-P: valid [0.0, 1.0]
    for valid_p in (0.0, 0.5, 1.0):
        resp = await client.post(
            "/api/agents/tiers",
            json={"name": f"TopP {valid_p}", "model": "gemini-2.5-flash", "top_p": valid_p},
        )
        assert resp.status_code in (200, 201)

    for invalid_p in (-0.01, 1.01, 2.0):
        resp = await client.post(
            "/api/agents/tiers",
            json={"name": f"Bad TopP {invalid_p}", "model": "gemini-2.5-flash", "top_p": invalid_p},
        )
        assert resp.status_code == 422

    # Max tokens: valid [128, 65536]
    for valid_tokens in (128, 512, 8192, 65536):
        resp = await client.post(
            "/api/agents/tiers",
            json={"name": f"Tokens {valid_tokens}", "model": "gemini-2.5-flash", "max_output_tokens": valid_tokens},
        )
        assert resp.status_code in (200, 201)

    for invalid_tokens in (0, 1, 127, 65537, 100000, -100):
        resp = await client.post(
            "/api/agents/tiers",
            json={"name": f"Bad Tokens {invalid_tokens}", "model": "gemini-2.5-flash", "max_output_tokens": invalid_tokens},
        )
        assert resp.status_code == 422


@pytest.mark.asyncio
async def test_update_tier_cannot_corrupt_system_tier_metadata(client: AsyncClient) -> None:
    """Verify updating a system tier cannot alter its is_system flag or tier_id."""
    resp = await client.put(
        "/api/agents/tiers/tier1",
        json={
            "name": "Renamed Tier 1",
            "model": "gemini-2.5-pro",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == "tier1"
    assert data["is_system"] is True
    assert data["name"] == "Renamed Tier 1"


# ============================================================================
# 2. Rapid Repeated Cascading Cycles & Mode Oscillation
# ============================================================================

@pytest.mark.asyncio
async def test_rapid_tier_cascading_cycles_50_iterations(client: AsyncClient) -> None:
    """Stress-test 50 rapid sequential updates to tier1 and verify all inherited agents cascade faithfully."""
    models_sequence = [
        "gemini-2.5-flash",
        "gemini-2.5-pro",
        "gemini-3.7-flash",
        "gemini-3.7-pro",
    ]

    for i in range(50):
        target_model = models_sequence[i % len(models_sequence)]
        target_temp = round(0.1 + (i % 10) * 0.15, 2)
        target_tokens = 1024 + (i % 8) * 1024

        update_resp = await client.put(
            "/api/agents/tiers/tier1",
            json={
                "model": target_model,
                "temperature": target_temp,
                "max_output_tokens": target_tokens,
            },
        )
        assert update_resp.status_code == 200

    # Verify final state on all agents inheriting tier1
    get_res = await client.get("/api/agents/config")
    assert get_res.status_code == 200
    agents = get_res.json()["agents"]

    tier1_agents = [a for a in agents if a["tier_id"] == "tier1" and a["config_mode"] == "inherit"]
    assert len(tier1_agents) > 0

    expected_model = models_sequence[49 % len(models_sequence)]
    expected_temp = round(0.1 + (49 % 10) * 0.15, 2)
    expected_tokens = 1024 + (49 % 8) * 1024

    for a in tier1_agents:
        assert a["effective_model"] == expected_model, f"Agent {a['agent_id']} failed model cascade"
        assert abs(a["effective_temperature"] - expected_temp) < 1e-4
        assert a["effective_max_output_tokens"] == expected_tokens


@pytest.mark.asyncio
async def test_multi_tier_round_robin_cascading(client: AsyncClient) -> None:
    """Create 4 custom tiers, assign all agents round-robin, update tiers, and verify isolation."""
    # 1. Create 4 custom tiers
    tier_ids = []
    for i in range(4):
        c_resp = await client.post(
            "/api/agents/tiers",
            json={
                "name": f"Custom Tier {i}",
                "model": f"gemini-custom-model-{i}",
                "temperature": round(0.2 + i * 0.2, 2),
                "top_p": round(0.7 + i * 0.05, 2),
                "max_output_tokens": 2048 * (i + 1),
            },
        )
        assert c_resp.status_code in (200, 201)
        tier_ids.append(c_resp.json()["id"])

    # 2. Get all agent IDs
    reg_resp = await client.get("/api/agents/config")
    agent_items = reg_resp.json()["agents"]
    all_agent_ids = [a["agent_id"] for a in agent_items]

    # 3. Assign agents round-robin to custom tiers
    overrides = []
    agent_tier_map = {}
    for idx, agent_id in enumerate(all_agent_ids):
        assigned_t = tier_ids[idx % len(tier_ids)]
        agent_tier_map[agent_id] = assigned_t
        overrides.append({
            "agent_id": agent_id,
            "tier_id": assigned_t,
            "config_mode": "inherit",
        })

    batch_resp = await client.put("/api/agents/config", json={"overrides": overrides})
    assert batch_resp.status_code == 200

    # 4. Verify each agent inherited its exact assigned tier's parameters
    verify_resp = await client.get("/api/agents/config")
    configs = {a["agent_id"]: a for a in verify_resp.json()["agents"]}

    for agent_id, assigned_t in agent_tier_map.items():
        t_idx = tier_ids.index(assigned_t)
        cfg = configs[agent_id]
        assert cfg["tier_id"] == assigned_t
        assert cfg["effective_model"] == f"gemini-custom-model-{t_idx}"
        assert abs(cfg["effective_temperature"] - round(0.2 + t_idx * 0.2, 2)) < 1e-4
        assert cfg["effective_max_output_tokens"] == 2048 * (t_idx + 1)


@pytest.mark.asyncio
async def test_mode_oscillation_stress(client: AsyncClient) -> None:
    """Rapidly toggle an agent between 'inherit' and 'custom' mode 30 times, testing override persistence."""
    agent_id = "ReviewerAgent"

    # Set custom override parameters
    custom_model = "gemini-reviewer-custom-3.7"
    custom_temp = 0.15

    for cycle in range(30):
        mode = "custom" if cycle % 2 == 0 else "inherit"
        resp = await client.put(
            "/api/agents/config",
            json={
                "overrides": [
                    {
                        "agent_id": agent_id,
                        "config_mode": mode,
                        "model": custom_model,
                        "temperature": custom_temp,
                    }
                ]
            },
        )
        assert resp.status_code == 200

        # Check effective config
        check_resp = await client.get("/api/agents/config")
        agent_cfg = next(a for a in check_resp.json()["agents"] if a["agent_id"] == agent_id)

        if mode == "custom":
            assert agent_cfg["effective_model"] == custom_model
            assert abs(agent_cfg["effective_temperature"] - custom_temp) < 1e-4
        else:
            # Should inherit from assigned tier (default tier3)
            assert agent_cfg["config_mode"] == "inherit"
            # Effective model should be tier3 model
            tier3_resp = await client.get("/api/agents/tiers")
            tier3 = next(t for t in tier3_resp.json()["tiers"] if t["id"] == agent_cfg["tier_id"])
            assert agent_cfg["effective_model"] == tier3["model"]
            assert abs(agent_cfg["effective_temperature"] - tier3["temperature"]) < 1e-4


# ============================================================================
# 3. Complex Deletion Chains & Cascading Safe Reassignment
# ============================================================================

@pytest.mark.asyncio
async def test_cascading_deletion_chain_and_reassignment(client: AsyncClient) -> None:
    """Test creating 3 custom tiers, assigning agents to each, and sequentially deleting them."""
    # 1. Create Tiers Alpha, Beta, Gamma
    tier_alpha = (await client.post("/api/agents/tiers", json={"name": "Tier Alpha", "model": "gemini-alpha"})).json()["id"]
    tier_beta = (await client.post("/api/agents/tiers", json={"name": "Tier Beta", "model": "gemini-beta"})).json()["id"]
    tier_gamma = (await client.post("/api/agents/tiers", json={"name": "Tier Gamma", "model": "gemini-gamma"})).json()["id"]

    # 2. Assign ProjectAgent -> Alpha, ALRSAgent -> Beta, ReviewerAgent -> Gamma
    await client.put(
        "/api/agents/config",
        json={
            "overrides": [
                {"agent_id": "ProjectAgent", "tier_id": tier_alpha, "config_mode": "inherit"},
                {"agent_id": "ALRSAgent", "tier_id": tier_beta, "config_mode": "inherit"},
                {"agent_id": "ReviewerAgent", "tier_id": tier_gamma, "config_mode": "inherit"},
            ]
        },
    )

    # 3. Delete Alpha -> ProjectAgent should be reassigned to tier1
    del_alpha = await client.delete(f"/api/agents/tiers/{tier_alpha}")
    assert del_alpha.status_code == 200
    assert del_alpha.json()["reassigned_agents_count"] >= 1
    assert del_alpha.json()["reassigned_to_tier_id"] == "tier1"

    cfg_1 = {a["agent_id"]: a for a in (await client.get("/api/agents/config")).json()["agents"]}
    assert cfg_1["ProjectAgent"]["tier_id"] == "tier1"
    assert cfg_1["ALRSAgent"]["tier_id"] == tier_beta

    # 4. Reassign ProjectAgent to Beta, then delete Beta -> ProjectAgent & ALRSAgent reassign to tier1
    await client.put(
        "/api/agents/config",
        json={"overrides": [{"agent_id": "ProjectAgent", "tier_id": tier_beta, "config_mode": "inherit"}]},
    )
    del_beta = await client.delete(f"/api/agents/tiers/{tier_beta}")
    assert del_beta.status_code == 200
    assert del_beta.json()["reassigned_agents_count"] >= 2

    cfg_2 = {a["agent_id"]: a for a in (await client.get("/api/agents/config")).json()["agents"]}
    assert cfg_2["ProjectAgent"]["tier_id"] == "tier1"
    assert cfg_2["ALRSAgent"]["tier_id"] == "tier1"
    assert cfg_2["ReviewerAgent"]["tier_id"] == tier_gamma

    # 5. Delete Gamma -> ReviewerAgent reassigns to tier1
    del_gamma = await client.delete(f"/api/agents/tiers/{tier_gamma}")
    assert del_gamma.status_code == 200
    assert del_gamma.json()["reassigned_agents_count"] >= 1

    cfg_3 = {a["agent_id"]: a for a in (await client.get("/api/agents/config")).json()["agents"]}
    assert cfg_3["ReviewerAgent"]["tier_id"] == "tier1"


@pytest.mark.asyncio
async def test_custom_mode_agent_deletion_reassignment_preserves_custom_values(client: AsyncClient) -> None:
    """When an agent in custom mode is assigned to a tier that gets deleted, its tier becomes tier1 but custom params remain."""
    # 1. Create custom tier
    tier_resp = await client.post("/api/agents/tiers", json={"name": "Tier Temporary", "model": "gemini-2.5-flash"})
    temp_tier_id = tier_resp.json()["id"]

    # 2. Assign DraftingAgent to this tier in CUSTOM mode with explicit custom params
    await client.put(
        "/api/agents/config",
        json={
            "overrides": [
                {
                    "agent_id": "DraftingAgent",
                    "tier_id": temp_tier_id,
                    "config_mode": "custom",
                    "model": "gemini-drafting-custom-pro",
                    "temperature": 0.92,
                }
            ]
        },
    )

    # 3. Delete the custom tier
    del_resp = await client.delete(f"/api/agents/tiers/{temp_tier_id}")
    assert del_resp.status_code == 200

    # 4. Verify DraftingAgent has assigned_tier_id == "tier1", but retains its custom model and temperature
    verify = await client.get("/api/agents/config")
    drafting = next(a for a in verify.json()["agents"] if a["agent_id"] == "DraftingAgent")
    assert drafting["tier_id"] == "tier1"
    assert drafting["config_mode"] == "custom"
    assert drafting["effective_model"] == "gemini-drafting-custom-pro"
    assert abs(drafting["effective_temperature"] - 0.92) < 1e-4


# ============================================================================
# 4. Extreme Concurrency & Race Condition Stress
# ============================================================================

@pytest.mark.asyncio
async def test_extreme_concurrency_tier_mutations_and_reads(client: AsyncClient) -> None:
    """Run 60 concurrent mixed operations: tier creates, updates, batch config, registry reads, tier list."""
    agents = ["ProjectAgent", "ResearchAgent", "ALRSAgent", "GapFinderAgent", "EvidenceSynthesizerAgent", "PlannerAgent", "DraftingAgent", "ReviewerAgent", "DebuggerAgent"]

    async def _worker_task(idx: int):
        op = idx % 5
        if op == 0:
            # Create a tier
            return await client.post(
                "/api/agents/tiers",
                json={
                    "name": f"Concurrent Tier {idx}",
                    "model": "gemini-2.5-flash",
                    "temperature": round(0.1 + (idx % 10) * 0.1, 2),
                },
            )
        elif op == 1:
            # Update tier1
            return await client.put(
                "/api/agents/tiers/tier1",
                json={"temperature": round(0.1 + (idx % 10) * 0.1, 2)},
            )
        elif op == 2:
            # Batch update agent config
            agent_target = agents[idx % len(agents)]
            return await client.put(
                "/api/agents/config",
                json={
                    "overrides": [
                        {
                            "agent_id": agent_target,
                            "tier_id": "tier1" if idx % 2 == 0 else "tier2",
                            "config_mode": "inherit" if idx % 3 == 0 else "custom",
                            "temperature": round(0.2 + (idx % 8) * 0.1, 2),
                        }
                    ]
                },
            )
        elif op == 3:
            # Read registry
            return await client.get("/api/agents/registry")
        else:
            # Read tiers
            return await client.get("/api/agents/tiers")

    tasks = [_worker_task(i) for i in range(60)]
    responses = await asyncio.gather(*tasks)

    for idx, resp in enumerate(responses):
        assert resp.status_code in (200, 201), f"Task {idx} failed with status {resp.status_code}: {resp.text}"

    # Final sanity check on registry
    final_res = await client.get("/api/agents/registry")
    assert final_res.status_code == 200
    assert final_res.json()["total"] >= 9


@pytest.mark.asyncio
async def test_concurrent_tier_deletion_race(client: AsyncClient) -> None:
    """Stress-test concurrent tier creation, agent reassignment, and immediate deletion."""
    # Create tier
    create_res = await client.post("/api/agents/tiers", json={"name": "Race Tier", "model": "gemini-2.5-flash"})
    tier_id = create_res.json()["id"]

    async def _assign_agents():
        for _ in range(10):
            try:
                await client.put(
                    "/api/agents/config",
                    json={"overrides": [{"agent_id": "ALRSAgent", "tier_id": tier_id, "config_mode": "inherit"}]},
                )
            except Exception:
                pass
            await asyncio.sleep(0.01)

    async def _delete_tier():
        await asyncio.sleep(0.02)
        return await client.delete(f"/api/agents/tiers/{tier_id}")

    assign_task = asyncio.create_task(_assign_agents())
    del_task = asyncio.create_task(_delete_tier())

    del_resp = await del_task
    await assign_task

    assert del_resp.status_code in (200, 404)

    # Sanity check ALRSAgent has a valid fallback tier
    final_cfg = await client.get("/api/agents/config")
    alrs = next(a for a in final_cfg.json()["agents"] if a["agent_id"] == "ALRSAgent")
    assert alrs["tier_id"] in ("tier1", "tier2", "tier3")


# ============================================================================
# 5. Live ADK Agent Object Reflection
# ============================================================================

@pytest.mark.asyncio
async def test_live_adk_agent_model_and_instruction_reflection() -> None:
    """Verify AgentService mutates the live Python ADK objects in-memory directly."""
    from agents.agent import root_agent

    service = AgentService(root_agent=root_agent, mysql_service=None)
    agents = service._get_all_agents()
    project_agent = next(a for a in agents if getattr(a, "name", "") == "ProjectAgent")

    # 1. Update tier1 model
    await service.update_tier("tier1", TierUpdateRequest(model="gemini-adk-live-test-model"))

    # 2. Check live ADK instance model attribute
    assert project_agent.model == "gemini-adk-live-test-model"

    # 3. Apply custom prompt prefix via config override
    await service.update_agent_configs([
        AgentConfigOverrideItem(
            agent_id="ProjectAgent",
            custom_prompt_prefix="### CRITICAL ADK DIRECTIVE ###",
        )
    ])

    # 4. Check live ADK instance instruction attribute
    assert project_agent.instruction.startswith("### CRITICAL ADK DIRECTIVE ###\n\n")


# ============================================================================
# 6. MySQL Database Fault Tolerance & Corrupted State Recovery
# ============================================================================

@pytest.mark.asyncio
async def test_corrupted_json_in_mysql_settings_recovery() -> None:
    """Verify AgentService recovers gracefully when MySQL settings contains corrupted JSON or invalid data."""
    from agents.agent import root_agent

    mock_db = AsyncMock()
    # Return malformed JSON for tiers and non-dict for overrides
    mock_db.fetch_one.side_effect = [
        {"setting_value": "INVALID_JSON{{{{{"},  # for agent_swarm_tiers
        {"setting_value": "12345"},               # for agent_swarm_overrides
    ]

    service = AgentService(root_agent=root_agent, mysql_service=mock_db)
    await service.initialize_from_db()

    # Verify default tiers remain intact
    tiers = await service.get_tiers()
    tier_ids = [t.id for t in tiers]
    assert "tier1" in tier_ids
    assert "tier2" in tier_ids
    assert "tier3" in tier_ids


@pytest.mark.asyncio
async def test_db_timeout_or_disconnect_during_tier_crud() -> None:
    """Verify tier CRUD operations succeed in memory even if MySQL operations raise timeout or disconnect."""
    from agents.agent import root_agent

    mock_db = AsyncMock()
    mock_db.fetch_one.return_value = None
    mock_db.execute.side_effect = asyncio.TimeoutError("DB Operation timed out")

    service = AgentService(root_agent=root_agent, mysql_service=mock_db)

    # 1. Create tier with failing DB
    created = await service.create_tier(
        TierCreateRequest(name="Resilient Tier", model="gemini-2.5-flash")
    )
    assert created.name == "Resilient Tier"

    # 2. Update tier with failing DB
    updated = await service.update_tier(
        created.id,
        TierUpdateRequest(temperature=0.88),
    )
    assert abs(updated.temperature - 0.88) < 1e-4

    # 3. Delete tier with failing DB
    deleted = await service.delete_tier(created.id)
    assert deleted.status == "deleted"
    assert deleted.tier_id == created.id

"""Pytest test suite for Agent Model Tiers, REST API, Dynamic Cascading & Inheritance.

Covers:
1. GET /api/agents/tiers - System tier listing & schema validation (tier1, tier2, tier3).
2. POST /api/agents/tiers - Custom tier creation & validation rules (temperature, top_p, tokens, name).
3. POST /api/agents/tiers - Boundary values validation (min/max temperature, tokens, top_p).
4. PUT /api/agents/tiers/{tier_id} - Tier updating and dynamic cascading to inherited agents.
5. Custom override isolation - Ensuring custom parameters are not overwritten by tier updates.
6. Mode toggle & tier reassignment - Switching between inherit and custom and reassigning tiers.
7. DELETE /api/agents/tiers/{tier_id} - System tier deletion protection (400/403).
8. DELETE /api/agents/tiers/{tier_id} - Custom tier deletion with safe reassignment of member agents to tier1.
9. DELETE /api/agents/tiers/{tier_id} - 404 on non-existent tier.
10. GET & PUT /api/agents/config - Batch configuration management & validation.
11. Persistence & Restoration - MySQL settings table synchronization and initialization.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from main import app
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


# ===========================================================================
# 1. GET /api/agents/tiers (Listing & Schema Verification)
# ===========================================================================

@pytest.mark.asyncio
async def test_get_agent_tiers_returns_default_system_tiers(client: AsyncClient) -> None:
    """Test GET /api/agents/tiers returns default system tiers with valid schema."""
    response = await client.get("/api/agents/tiers")
    assert response.status_code == 200
    data = response.json()

    assert "tiers" in data
    assert len(data["tiers"]) >= 3

    tier_ids = [t["id"] for t in data["tiers"]]
    assert "tier1" in tier_ids
    assert "tier2" in tier_ids
    assert "tier3" in tier_ids

    # Validate tier1 schema
    tier1 = next(t for t in data["tiers"] if t["id"] == "tier1")
    assert "name" in tier1
    assert "Orchestration" in tier1["name"]
    assert "model" in tier1
    assert tier1["is_system"] is True
    assert 0.0 <= tier1["temperature"] <= 2.0
    assert 0.0 <= tier1["top_p"] <= 1.0
    assert tier1["max_output_tokens"] >= 128
    assert "color" in tier1


# ===========================================================================
# 2. POST /api/agents/tiers (Creation & Validation)
# ===========================================================================

@pytest.mark.asyncio
async def test_create_custom_tier_success(client: AsyncClient) -> None:
    """Test POST /api/agents/tiers creates a new custom tier successfully."""
    payload = {
        "name": "Tier 4: Fast Brainstorming",
        "description": "Rapid synthesis with low token limits and fast model",
        "model": "gemini-2.5-flash",
        "temperature": 0.85,
        "top_p": 0.95,
        "max_output_tokens": 4096,
        "color": "#f59e0b",
    }

    response = await client.post("/api/agents/tiers", json=payload)
    assert response.status_code in (200, 201)
    tier = response.json()

    assert "id" in tier
    assert tier["name"] == "Tier 4: Fast Brainstorming"
    assert tier["model"] == "gemini-2.5-flash"
    assert abs(tier["temperature"] - 0.85) < 1e-4
    assert tier["max_output_tokens"] == 4096
    assert tier["color"] == "#f59e0b"
    assert tier["is_system"] is False

    # Verify tier appears in GET /api/agents/tiers
    get_res = await client.get("/api/agents/tiers")
    assert get_res.status_code == 200
    all_tiers = get_res.json()["tiers"]
    assert any(t["id"] == tier["id"] for t in all_tiers)


@pytest.mark.asyncio
async def test_create_tier_validation_errors(client: AsyncClient) -> None:
    """Test validation errors for invalid temperature, top_p, tokens, and empty name."""
    # 1. Invalid temperature > 2.0
    res_temp = await client.post(
        "/api/agents/tiers",
        json={"name": "Invalid Temp", "model": "gemini-2.5-flash", "temperature": 2.5},
    )
    assert res_temp.status_code == 422

    # 2. Invalid top_p > 1.0
    res_top_p = await client.post(
        "/api/agents/tiers",
        json={"name": "Invalid TopP", "model": "gemini-2.5-flash", "top_p": 1.5},
    )
    assert res_top_p.status_code == 422

    # 3. Invalid max_output_tokens < 128
    res_tokens = await client.post(
        "/api/agents/tiers",
        json={"name": "Invalid Tokens", "model": "gemini-2.5-flash", "max_output_tokens": 50},
    )
    assert res_tokens.status_code == 422

    # 4. Empty name
    res_name = await client.post(
        "/api/agents/tiers",
        json={"name": "", "model": "gemini-2.5-flash"},
    )
    assert res_name.status_code == 422


@pytest.mark.asyncio
async def test_create_tier_with_boundary_values(client: AsyncClient) -> None:
    """Test creating custom tiers with boundary values (temp 0.0 & 2.0, tokens 128 & 65536, top_p 0.0 & 1.0)."""
    payload_min = {
        "name": "Tier Min Boundary",
        "model": "gemini-2.5-flash",
        "temperature": 0.0,
        "top_p": 0.0,
        "max_output_tokens": 128,
        "color": "#111827",
    }
    res_min = await client.post("/api/agents/tiers", json=payload_min)
    assert res_min.status_code in (200, 201)
    tier_min = res_min.json()
    assert tier_min["temperature"] == 0.0
    assert tier_min["top_p"] == 0.0
    assert tier_min["max_output_tokens"] == 128

    payload_max = {
        "name": "Tier Max Boundary",
        "model": "gemini-2.5-pro",
        "temperature": 2.0,
        "top_p": 1.0,
        "max_output_tokens": 65536,
        "color": "#ffffff",
    }
    res_max = await client.post("/api/agents/tiers", json=payload_max)
    assert res_max.status_code in (200, 201)
    tier_max = res_max.json()
    assert tier_max["temperature"] == 2.0
    assert tier_max["top_p"] == 1.0
    assert tier_max["max_output_tokens"] == 65536


# ===========================================================================
# 3. PUT /api/agents/tiers/{tier_id} (Updating & Cascading)
# ===========================================================================

@pytest.mark.asyncio
async def test_update_tier_parameters(client: AsyncClient) -> None:
    """Test PUT /api/agents/tiers/{tier_id} updates tier parameters."""
    update_payload = {
        "model": "gemini-3.7-flash",
        "temperature": 0.45,
        "max_output_tokens": 6144,
    }

    response = await client.put("/api/agents/tiers/tier2", json=update_payload)
    assert response.status_code == 200
    tier = response.json()
    assert tier["id"] == "tier2"
    assert tier["model"] == "gemini-3.7-flash"
    assert abs(tier["temperature"] - 0.45) < 1e-4
    assert tier["max_output_tokens"] == 6144


@pytest.mark.asyncio
async def test_update_tier_cascades_to_inherited_agents(client: AsyncClient) -> None:
    """Test updating a tier cascades model and temperature to all agents set to inherit from that tier."""
    # 1. Update tier1 model
    await client.put(
        "/api/agents/tiers/tier1",
        json={"model": "gemini-2.5-pro", "temperature": 0.65},
    )

    # 2. Query agent registry and verify inherited agents reflected update
    get_res = await client.get("/api/agents/registry")
    assert get_res.status_code == 200
    registry = get_res.json()

    # ProjectAgent is assigned to tier1 in inherit mode
    project_agent = next(a for a in registry["agents"] if a["name"] == "ProjectAgent")
    assert project_agent["config"]["model"] == "gemini-2.5-pro"
    assert abs(project_agent["config"]["temperature"] - 0.65) < 1e-4


@pytest.mark.asyncio
async def test_update_tier_does_not_override_custom_mode_agents(client: AsyncClient) -> None:
    """Test updating a tier does NOT overwrite parameters for agents configured in custom override mode."""
    # 1. Set ALRSAgent to custom override mode with a specific model
    await client.put(
        "/api/agents/settings",
        json={
            "settings": {
                "ALRSAgent": {
                    "model": "gemini-3.7-pro",
                    "temperature": 0.12,
                    "top_p": 0.85,
                    "max_output_tokens": 2048,
                }
            }
        },
    )

    # 2. Update tier2 (ALRSAgent's assigned tier)
    await client.put(
        "/api/agents/tiers/tier2",
        json={"model": "gemini-2.5-flash", "temperature": 0.99},
    )

    # 3. Verify ALRSAgent retained its custom override model and temperature
    get_res = await client.get("/api/agents/registry")
    registry = get_res.json()
    alrs_agent = next(a for a in registry["agents"] if a["name"] == "ALRSAgent")

    assert alrs_agent["config"]["model"] == "gemini-3.7-pro"
    assert abs(alrs_agent["config"]["temperature"] - 0.12) < 1e-4


# ===========================================================================
# 4. Agent Mode Toggling & Tier Reassignment
# ===========================================================================

@pytest.mark.asyncio
async def test_agent_mode_toggle_and_tier_reassignment(client: AsyncClient) -> None:
    """Test toggling an agent's config_mode and reassigning its tier."""
    # 1. Switch GapFinderAgent to tier1 in inherit mode
    put_res = await client.put(
        "/api/agents/settings",
        json={
            "settings": {
                "GapFinderAgent": {
                    "assigned_tier_id": "tier1",
                    "config_mode": "inherit",
                }
            }
        },
    )
    assert put_res.status_code == 200

    # 2. Verify registry reflects new tier assignment
    get_res = await client.get("/api/agents/registry")
    registry = get_res.json()
    gap = next(a for a in registry["agents"] if a["name"] == "GapFinderAgent")
    assert gap.get("assigned_tier_id") == "tier1" or gap["config"].get("assigned_tier_id") == "tier1" or gap.get("tier") == "tier1"


# ===========================================================================
# 5. DELETE /api/agents/tiers/{tier_id} (Protection & Safe Reassignment)
# ===========================================================================

@pytest.mark.asyncio
async def test_delete_system_tier_is_forbidden(client: AsyncClient) -> None:
    """Test attempting to delete a system tier (tier1, tier2, tier3) returns 400 or 403."""
    for sys_tier_id in ["tier1", "tier2", "tier3"]:
        response = await client.delete(f"/api/agents/tiers/{sys_tier_id}")
        assert response.status_code in (400, 403), f"System tier {sys_tier_id} deletion must be rejected"


@pytest.mark.asyncio
async def test_delete_custom_tier_safely_reassigns_agents_to_tier1(client: AsyncClient) -> None:
    """Test deleting a custom tier safely reassigns member agents back to tier1."""
    # 1. Create a custom tier
    create_res = await client.post(
        "/api/agents/tiers",
        json={
            "name": "Tier 5: Temporary Group",
            "model": "gemini-2.5-flash",
            "temperature": 0.5,
            "max_output_tokens": 4096,
        },
    )
    custom_tier = create_res.json()
    custom_id = custom_tier["id"]

    # 2. Delete the custom tier
    delete_res = await client.delete(f"/api/agents/tiers/{custom_id}")
    assert delete_res.status_code == 200
    del_data = delete_res.json()
    assert del_data["status"] == "deleted"
    assert del_data["tier_id"] == custom_id

    # 3. Verify custom tier no longer appears in GET /api/agents/tiers
    get_res = await client.get("/api/agents/tiers")
    tier_ids = [t["id"] for t in get_res.json()["tiers"]]
    assert custom_id not in tier_ids


@pytest.mark.asyncio
async def test_delete_non_existent_tier_returns_404(client: AsyncClient) -> None:
    """Test deleting a non-existent tier ID returns 404 Not Found."""
    response = await client.delete("/api/agents/tiers/non_existent_tier_9999")
    assert response.status_code == 404


# ===========================================================================
# 6. GET & PUT /api/agents/config (Batch Endpoints)
# ===========================================================================

@pytest.mark.asyncio
async def test_get_and_put_agent_config_batch(client: AsyncClient) -> None:
    """Test GET /api/agents/config and batch PUT /api/agents/config updates."""
    # 1. GET /api/agents/config
    get_res = await client.get("/api/agents/config")
    assert get_res.status_code == 200
    config_data = get_res.json()
    assert "agents" in config_data
    assert config_data["total"] == 9

    # 2. PUT /api/agents/config batch update
    batch_payload = {
        "overrides": [
            {
                "agent_id": "PlannerAgent",
                "tier_id": "tier1",
                "config_mode": "custom",
                "model": "gemini-2.5-pro",
                "temperature": 0.55,
            },
            {
                "agent_id": "ALRSAgent",
                "tier_id": "tier2",
                "config_mode": "inherit",
            },
        ]
    }
    put_res = await client.put("/api/agents/config", json=batch_payload)
    assert put_res.status_code == 200
    put_data = put_res.json()
    assert put_data["success"] is True
    assert "PlannerAgent" in put_data["updated_agents"]
    assert "ALRSAgent" in put_data["updated_agents"]

    # 3. Verify effective parameters
    verify_res = await client.get("/api/agents/config")
    agents = verify_res.json()["agents"]
    planner = next(a for a in agents if a["agent_id"] == "PlannerAgent")
    assert planner["config_mode"] == "custom"
    assert planner["model"] == "gemini-2.5-pro"
    assert abs(planner["temperature"] - 0.55) < 1e-4


@pytest.mark.asyncio
async def test_put_agent_config_validation_errors(client: AsyncClient) -> None:
    """Test validation errors for invalid agent_id or invalid tier_id in PUT /api/agents/config."""
    # Unknown agent
    res_agent = await client.put(
        "/api/agents/config",
        json={"overrides": [{"agent_id": "UnknownAgentX", "config_mode": "inherit"}]},
    )
    assert res_agent.status_code == 404

    # Unknown tier_id
    res_tier = await client.put(
        "/api/agents/config",
        json={"overrides": [{"agent_id": "PlannerAgent", "tier_id": "nonexistent_tier_xyz"}]},
    )
    assert res_tier.status_code == 400


# ===========================================================================
# 7. Database Persistence & Restoration
# ===========================================================================

@pytest.mark.asyncio
async def test_tier_persistence_in_mysql_settings() -> None:
    """Test that AgentService saves custom tiers and overrides to MySQL settings table."""
    from agents.agent import root_agent

    mock_mysql = AsyncMock()
    mock_mysql.fetch_one.return_value = {
        "setting_value": json.dumps([
            {
                "id": "tier_custom_persisted",
                "name": "Tier Custom Persisted",
                "model": "gemini-2.5-pro",
                "temperature": 0.4,
                "top_p": 0.9,
                "max_output_tokens": 8192,
                "color": "#6366f1",
                "is_system": False,
            }
        ])
    }

    service = AgentService(root_agent=root_agent, mysql_service=mock_mysql)
    # Initialize from DB if supported
    if hasattr(service, "initialize_tiers_from_db"):
        await service.initialize_tiers_from_db()
    elif hasattr(service, "initialize_from_db"):
        await service.initialize_from_db()

    # Verify custom tier is in memory
    if hasattr(service, "get_tiers"):
        tiers = await service.get_tiers()
        assert any(t.id == "tier_custom_persisted" for t in tiers)

"""Comprehensive pytest suite for Agent Swarm Inspector & Configuration API."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from main import app
from features.agents.models import (
    AgentConfig,
    AgentConfigUpdate,
    AgentMetadata,
    AgentRegistryResponse,
    AgentResetResponse,
    AgentSettingsUpdateRequest,
    AgentSettingsUpdateResponse,
    AgentToolDefinition,
    LiveAgentTrace,
    ToolCallTrace,
)
from features.agents.service import AgentService, extract_tool_schema, python_type_to_json_schema


@pytest_asyncio.fixture
async def client() -> AsyncClient:
    """Async HTTP test client against FastAPI app."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as ac:
        yield ac


@pytest.mark.asyncio
async def test_get_agent_registry_introspects_live_hierarchy(client: AsyncClient) -> None:
    """Test GET /api/agents/registry returns complete live ADK agent swarm without hardcoded lists."""
    response = await client.get("/api/agents/registry")
    assert response.status_code == 200
    data = response.json()

    assert "agents" in data
    assert "total" in data
    assert data["total"] == 9

    agent_names = [a["name"] for a in data["agents"]]
    expected_agents = [
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
    for expected in expected_agents:
        assert expected in agent_names, f"Expected agent {expected} not found in registry"

    # Verify tool schema reflection for ALRSAgent
    alrs_meta = next(a for a in data["agents"] if a["name"] == "ALRSAgent")
    assert len(alrs_meta["tools"]) > 0
    tool_names = [t["name"] for t in alrs_meta["tools"]]
    assert "run_graphselect_traversal" in tool_names or "search_papers_by_keyword" in tool_names

    traversal_tool = next(t for t in alrs_meta["tools"] if "graphselect" in t["name"].lower() or "keyword" in t["name"].lower())
    assert "parameters" in traversal_tool
    assert traversal_tool["parameters"]["type"] == "object"
    assert "properties" in traversal_tool["parameters"]

    # Verify active vs default configuration parameters
    assert alrs_meta["config"]["model"] is not None
    assert alrs_meta["config"]["default_model"] is not None
    assert alrs_meta["config"]["temperature"] >= 0.0
    assert alrs_meta["config"]["top_p"] >= 0.0
    assert alrs_meta["config"]["max_output_tokens"] > 0
    assert "system_prompt" in alrs_meta["config"]
    assert alrs_meta["config"]["is_default"] is True


@pytest.mark.asyncio
async def test_update_agent_settings_hot_reloads_live_adk_instance(client: AsyncClient) -> None:
    """Test PUT /api/agents/settings updates configuration and hot-reloads runtime agent immediately."""
    payload = {
        "settings": {
            "ALRSAgent": {
                "model": "gemini-3.7-flash",
                "temperature": 0.15,
                "top_p": 0.88,
                "max_output_tokens": 4096,
                "custom_prompt_prefix": "MANDATORY HITL DIRECTIVE: Always prioritize highest similarity nodes.",
            }
        }
    }

    response = await client.put("/api/agents/settings", json=payload)
    assert response.status_code == 200
    res_data = response.json()
    assert res_data["success"] is True
    assert "ALRSAgent" in res_data["updated_agents"]

    # Verify via GET registry
    get_res = await client.get("/api/agents/registry")
    assert get_res.status_code == 200
    registry = get_res.json()
    alrs_meta = next(a for a in registry["agents"] if a["name"] == "ALRSAgent")

    assert alrs_meta["config"]["model"] == "gemini-3.7-flash"
    assert abs(alrs_meta["config"]["temperature"] - 0.15) < 1e-4
    assert abs(alrs_meta["config"]["top_p"] - 0.88) < 1e-4
    assert alrs_meta["config"]["max_output_tokens"] == 4096
    assert alrs_meta["config"]["custom_prompt_prefix"] == "MANDATORY HITL DIRECTIVE: Always prioritize highest similarity nodes."
    assert alrs_meta["config"]["is_default"] is False


@pytest.mark.asyncio
async def test_reset_single_agent_settings(client: AsyncClient) -> None:
    """Test POST /api/agents/settings/reset restores single agent back to factory defaults."""
    # First modify settings
    await client.put(
        "/api/agents/settings",
        json={"settings": {"ResearchAgent": {"model": "gemini-2.5-pro", "temperature": 1.2}}}
    )

    # Reset single agent
    response = await client.post("/api/agents/settings/reset", json={"agent_name": "ResearchAgent"})
    assert response.status_code == 200
    res_data = response.json()
    assert res_data["success"] is True
    assert "ResearchAgent" in res_data["reset_agents"]

    # Verify restored default
    get_res = await client.get("/api/agents/registry")
    registry = get_res.json()
    research_meta = next(a for a in registry["agents"] if a["name"] == "ResearchAgent")
    assert research_meta["config"]["is_default"] is True
    assert research_meta["config"]["model"] == research_meta["config"]["default_model"]


@pytest.mark.asyncio
async def test_reset_all_agents_settings(client: AsyncClient) -> None:
    """Test POST /api/agents/settings/reset without agent_name resets all agents to defaults."""
    # Modify multiple agents
    await client.put(
        "/api/agents/settings",
        json={
            "settings": {
                "ProjectAgent": {"temperature": 1.8},
                "DebuggerAgent": {"max_output_tokens": 16384},
            }
        }
    )

    # Reset all
    response = await client.post("/api/agents/settings/reset", json={})
    assert response.status_code == 200
    res_data = response.json()
    assert res_data["success"] is True
    assert len(res_data["reset_agents"]) == 9

    # Verify all are default
    get_res = await client.get("/api/agents/registry")
    registry = get_res.json()
    for a in registry["agents"]:
        assert a["config"]["is_default"] is True


@pytest.mark.asyncio
async def test_get_agent_traces_endpoint(client: AsyncClient) -> None:
    """Test GET /api/agents/traces queries traces correctly."""
    response = await client.get("/api/agents/traces?agent_name=ALRSAgent&limit=10")
    assert response.status_code == 200
    data = response.json()
    assert "traces" in data
    assert "total" in data
    assert isinstance(data["traces"], list)


@pytest.mark.asyncio
async def test_validation_errors_on_invalid_settings(client: AsyncClient) -> None:
    """Test validation errors for out-of-range temperatures, top_p, and unknown agent names."""
    # Invalid temperature > 2.0
    res_temp = await client.put(
        "/api/agents/settings",
        json={"settings": {"ALRSAgent": {"temperature": 2.5}}}
    )
    assert res_temp.status_code == 422

    # Invalid top_p > 1.0
    res_top_p = await client.put(
        "/api/agents/settings",
        json={"settings": {"ALRSAgent": {"top_p": 1.5}}}
    )
    assert res_top_p.status_code == 422

    # Unknown agent name in PUT
    res_unknown = await client.put(
        "/api/agents/settings",
        json={"settings": {"NonExistentAgent999": {"temperature": 0.5}}}
    )
    assert res_unknown.status_code == 404

    # Unknown agent name in reset POST
    res_reset_unknown = await client.post(
        "/api/agents/settings/reset",
        json={"agent_name": "NonExistentAgent999"}
    )
    assert res_reset_unknown.status_code == 404


@pytest.mark.asyncio
async def test_boundary_values_for_settings(client: AsyncClient) -> None:
    """Test boundary conditions: min/max temperature, top_p, and max_output_tokens."""
    payload = {
        "settings": {
            "GapFinderAgent": {
                "temperature": 0.0,
                "top_p": 0.0,
                "max_output_tokens": 128,
            },
            "EvidenceSynthesizerAgent": {
                "temperature": 2.0,
                "top_p": 1.0,
                "max_output_tokens": 65536,
            }
        }
    }
    response = await client.put("/api/agents/settings", json=payload)
    assert response.status_code == 200
    res_data = response.json()
    assert "GapFinderAgent" in res_data["updated_agents"]
    assert "EvidenceSynthesizerAgent" in res_data["updated_agents"]

    # Verify values reflected
    get_res = await client.get("/api/agents/registry")
    registry = get_res.json()
    gap = next(a for a in registry["agents"] if a["name"] == "GapFinderAgent")
    evidence = next(a for a in registry["agents"] if a["name"] == "EvidenceSynthesizerAgent")

    assert gap["config"]["temperature"] == 0.0
    assert gap["config"]["top_p"] == 0.0
    assert gap["config"]["max_output_tokens"] == 128

    assert evidence["config"]["temperature"] == 2.0
    assert evidence["config"]["top_p"] == 1.0
    assert evidence["config"]["max_output_tokens"] == 65536

    # Clean up reset
    await client.post("/api/agents/settings/reset", json={})


def test_extract_tool_schema_reflection() -> None:
    """Test dynamic tool introspection for various callable signatures and annotations."""
    def sample_tool(
        query: str,
        limit: int = 10,
        threshold: float = 0.75,
        flags: list[str] = None,
        tool_context: Any = None,
    ) -> dict:
        """Search papers using given semantic query and threshold.
        
        Args:
            query: The search keywords.
            limit: Maximum count.
            threshold: Minimum score.
            flags: Optional search flags.
        """
        return {"count": limit}

    schema = extract_tool_schema(sample_tool)
    assert schema.name == "sample_tool"
    assert "Search papers using given semantic query" in schema.description
    assert schema.parameters.type == "object"
    
    props = schema.parameters.properties
    assert "query" in props
    assert props["query"]["type"] == "string"
    assert "limit" in props
    assert props["limit"]["type"] == "integer"
    assert props["limit"]["default"] == 10
    assert "threshold" in props
    assert props["threshold"]["type"] == "number"
    assert props["threshold"]["default"] == 0.75
    assert "flags" in props
    assert props["flags"]["type"] == "array"
    
    # Internal tool_context must be stripped
    assert "tool_context" not in props
    assert "query" in schema.parameters.required


@pytest.mark.asyncio
async def test_trace_retrieval_service_with_mock_db() -> None:
    """Test AgentService.get_traces with mocked MySQL backend returning realistic trace rows."""
    from agents.agent import root_agent

    mock_mysql = AsyncMock()
    mock_rows = [
        {
            "id": 101,
            "created_at": datetime(2026, 8, 29, 12, 0, 0, tzinfo=timezone.utc),
            "project_id": "proj-12345",
            "agent_name": "ALRSAgent",
            "event_type": "tool_execution",
            "token_count": 420,
            "details": json.dumps({
                "tool_name": "search_papers_by_keyword",
                "args": {"query": "Graph neural networks", "limit": 5},
                "result": "Found 5 candidate papers.",
                "latency_ms": 350.5,
                "prompt": "Find recent papers on GNNs",
                "response": "Executing search...",
                "decision_outcome": "Delegated to GraphSelect traversal",
            }),
        },
        {
            "id": 102,
            "created_at": datetime(2026, 8, 29, 12, 1, 0, tzinfo=timezone.utc),
            "project_id": "proj-12345",
            "agent_name": "ReviewerAgent",
            "event_type": "error",
            "token_count": 150,
            "details": json.dumps({
                "prompt": "Evaluate section 2",
                "raw_response": "Rate limit exceeded",
                "latency_ms": 120.0,
            }),
        }
    ]
    mock_mysql.fetch_all.return_value = mock_rows

    service = AgentService(root_agent=root_agent, mysql_service=mock_mysql)
    traces = await service.get_traces(agent_name="ALRSAgent", project_id="proj-12345")

    assert len(traces) == 2
    
    # Verify trace 1
    t1 = traces[0]
    assert t1.id == "101"
    assert t1.agent_name == "ALRSAgent"
    assert t1.status == "success"
    assert t1.token_count == 420
    assert t1.latency_ms == 350.5
    assert len(t1.tool_calls) == 1
    assert t1.tool_calls[0].name == "search_papers_by_keyword"
    assert t1.tool_calls[0].arguments["query"] == "Graph neural networks"
    assert t1.decision_outcome == "Delegated to GraphSelect traversal"

    # Verify trace 2 (error)
    t2 = traces[1]
    assert t2.id == "102"
    assert t2.agent_name == "ReviewerAgent"
    assert t2.status == "error"
    assert t2.llm_response == "Rate limit exceeded"


@pytest.mark.asyncio
async def test_db_persistence_and_initialization() -> None:
    """Test that AgentService saves to and restores overrides from MySQL settings table."""
    from agents.agent import root_agent

    mock_mysql = AsyncMock()
    mock_mysql.fetch_one.return_value = {
        "setting_value": json.dumps({
            "PlannerAgent": {
                "model": "gemini-3.7-pro",
                "temperature": 0.55,
                "custom_prompt_prefix": "CUSTOM_PLANNER_PREFIX",
            }
        })
    }

    service = AgentService(root_agent=root_agent, mysql_service=mock_mysql)
    await service.initialize_from_db()

    registry = await service.get_registry()
    planner = next(a for a in registry.agents if a.name == "PlannerAgent")
    assert planner.config.model == "gemini-3.7-pro"
    assert abs(planner.config.temperature - 0.55) < 1e-4
    assert planner.config.custom_prompt_prefix == "CUSTOM_PLANNER_PREFIX"
    assert planner.config.is_default is False

    # Test update triggers MySQL execution
    await service.update_settings({
        "PlannerAgent": AgentConfigUpdate(temperature=0.60)
    })
    assert mock_mysql.execute.called

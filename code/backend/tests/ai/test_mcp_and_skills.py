from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from ai import (
    AgentToolRuntime,
    ResearchAgent,
    build_fastmcp_server,
    list_available_skills,
    load_skill,
)
from engines.alrs import AlrsEngine
from engines.collections import InMemoryCollectionStore
from main import app
from tests.ai.test_research_agent import FakeEmbeddingProvider, FakeOpenAlexProvider


def test_list_and_load_skills_by_name_and_alias() -> None:
    skills = list_available_skills()
    names = {s.name for s in skills}
    assert {
        "search-literature",
        "write-literature-review",
        "verify-citations",
        "collection-curator",
    }.issubset(names)

    s1 = load_skill("search-literature")
    s1_alias = load_skill("literature_search")
    assert s1.name == "search-literature"
    assert s1.instructions == s1_alias.instructions
    assert "discover_literature" in s1.instructions

    s2 = load_skill("evidence_review")
    assert s2.name == "write-literature-review"

    s3 = load_skill("citation_export")
    assert s3.name == "verify-citations"

    with pytest.raises(KeyError):
        load_skill("nonexistent-skill")


@pytest.mark.asyncio
async def test_research_agent_loads_skills_progressively_per_stage() -> None:
    openalex = FakeOpenAlexProvider()
    embeddings = FakeEmbeddingProvider()
    runtime = AgentToolRuntime(
        openalex=openalex,
        alrs_engine=AlrsEngine(openalex=openalex, embeddings=embeddings),
        collection_store=InMemoryCollectionStore(),
    )
    agent = ResearchAgent(runtime)

    paused = await agent.start_run(
        topic="How does GraphSelect rank academic literature?",
        require_approval=True,
    )
    assert paused.status == "awaiting_approval"
    assert paused.loaded_skills == ["search-literature"]

    completed = await agent.resume_run(paused.thread_id, approved=True)
    assert completed.status == "completed"
    assert completed.loaded_skills == [
        "search-literature",
        "write-literature-review",
        "verify-citations",
    ]


def test_fastapi_mcp_endpoint_and_fastmcp_server() -> None:
    openalex = FakeOpenAlexProvider()
    embeddings = FakeEmbeddingProvider()
    runtime = AgentToolRuntime(
        openalex=openalex,
        alrs_engine=AlrsEngine(openalex=openalex, embeddings=embeddings),
        collection_store=InMemoryCollectionStore(),
    )
    fastmcp = build_fastmcp_server(runtime)
    assert fastmcp.name == "alrs-research-agent"

    app.state.agent_runtime = runtime
    client = TestClient(app)

    tools_resp = client.get("/mcp/tools")
    assert tools_resp.status_code == 200
    body = tools_resp.json()
    tool_names = [t["name"] for t in body["tools"]]
    assert tool_names == [
        "search_papers",
        "discover_literature",
        "get_collection",
        "write_review",
        "verify_citations",
        "load_skill",
    ]

    init_resp = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
    )
    assert init_resp.status_code == 200
    assert init_resp.json()["result"]["serverInfo"]["name"] == "alrs-research-agent"

    search_rpc = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "search_papers",
                "arguments": {"query": "GraphSelect", "limit": 2},
            },
        },
    )
    assert search_rpc.status_code == 200
    structured = search_rpc.json()["result"]["structuredContent"]
    assert structured["candidates"][0]["doi"] == "10.1000/seed"

    skill_rpc = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "load_skill",
                "arguments": {"skill_name": "verify-citations"},
            },
        },
    )
    assert skill_rpc.status_code == 200
    assert (
        skill_rpc.json()["result"]["structuredContent"]["name"] == "verify-citations"
    )

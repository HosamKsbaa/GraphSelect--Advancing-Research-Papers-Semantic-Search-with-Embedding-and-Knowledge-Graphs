"""Empirical adversarial stress test suite for Agent Swarm Inspector & Configuration API.

Authored by Challenger M1-1 (Adversarial Empirical Verifier).
Empirically tests:
1. High-concurrency parallel mutations and race condition resilience.
2. Extreme values and boundary validation (temperature, top_p, token counts, trace limits).
3. Partial update payloads, empty payloads, and setting preservation.
4. Adversarial prompt prefixes (50KB payloads, emojis, Unicode, SQLi/XSS strings, escapes).
5. Non-existent agents, batch atomicity, case sensitivity, and reset idempotency.
6. Live agent instruction hot-reloading without stacking artifacts.
7. Database fault tolerance and graceful in-memory degradation.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from main import app
from features.agents.models import (
    AgentConfigUpdate,
    AgentRegistryResponse,
    AgentResetResponse,
    AgentSettingsUpdateRequest,
    AgentSettingsUpdateResponse,
)
from features.agents.service import AgentService, extract_tool_schema


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


# ============================================================================
# 1. High-Concurrency & Race Condition Stress Tests
# ============================================================================


@pytest.mark.asyncio
async def test_concurrent_multi_agent_updates(client: AsyncClient) -> None:
    """Stress-test 45 simultaneous concurrent PUT requests across all 9 agents."""
    agents = [
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

    async def _send_update(agent_name: str, index: int):
        temp = round(0.1 + (index % 10) * 0.15, 2)
        top_p = round(0.5 + (index % 5) * 0.1, 2)
        tokens = 1024 + (index % 8) * 1024
        payload = {
            "settings": {
                agent_name: {
                    "temperature": temp,
                    "top_p": top_p,
                    "max_output_tokens": tokens,
                    "custom_prompt_prefix": f"CONCURRENT_WORKER_{index} for {agent_name}",
                }
            }
        }
        return await client.put("/api/agents/settings", json=payload)

    tasks = [
        _send_update(agents[i % len(agents)], i)
        for i in range(45)
    ]
    responses = await asyncio.gather(*tasks)

    for resp in responses:
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data["success"] is True

    reg_resp = await client.get("/api/agents/registry")
    assert reg_resp.status_code == 200
    registry = reg_resp.json()
    assert registry["total"] == 9
    assert len(registry["agents"]) == 9


@pytest.mark.asyncio
async def test_concurrent_conflicting_updates_same_agent(client: AsyncClient) -> None:
    """Stress-test 30 concurrent competing updates targeting the single agent ALRSAgent."""
    async def _update_alrs(index: int):
        payload = {
            "settings": {
                "ALRSAgent": {
                    "model": "gemini-3.7-flash" if index % 2 == 0 else "gemini-2.5-pro",
                    "temperature": round(0.1 + (index % 10) * 0.1, 2),
                    "custom_prompt_prefix": f"PREFIX_VERSION_{index}",
                }
            }
        }
        return await client.put("/api/agents/settings", json=payload)

    tasks = [_update_alrs(i) for i in range(30)]
    responses = await asyncio.gather(*tasks)

    for resp in responses:
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    reg_resp = await client.get("/api/agents/registry")
    assert reg_resp.status_code == 200
    registry = reg_resp.json()
    alrs = next(a for a in registry["agents"] if a["name"] == "ALRSAgent")
    assert alrs["config"]["model"] in ("gemini-3.7-flash", "gemini-2.5-pro")
    assert alrs["config"]["custom_prompt_prefix"].startswith("PREFIX_VERSION_")


@pytest.mark.asyncio
async def test_concurrent_interleaved_updates_resets_and_reads(client: AsyncClient) -> None:
    """Stress-test a chaotic mix of concurrent updates, resets, and reads."""
    async def _worker(index: int):
        op = index % 3
        if op == 0:
            return await client.put(
                "/api/agents/settings",
                json={
                    "settings": {
                        "ReviewerAgent": {"temperature": 0.85, "custom_prompt_prefix": f"REVIEWER_TRY_{index}"}
                    }
                }
            )
        elif op == 1:
            return await client.post(
                "/api/agents/settings/reset",
                json={"agent_name": "ReviewerAgent" if index % 2 == 0 else None}
            )
        else:
            return await client.get("/api/agents/registry")

    tasks = [_worker(i) for i in range(60)]
    responses = await asyncio.gather(*tasks)

    for resp in responses:
        assert resp.status_code == 200, f"Interleaved op failed: {resp.status_code} - {resp.text}"


# ============================================================================
# 2. Extreme Values & Boundary Validation Fuzzing
# ============================================================================


@pytest.mark.asyncio
async def test_fuzz_temperature_boundaries(client: AsyncClient) -> None:
    """Verify temperature boundaries: [0.0, 2.0] valid, out-of-range returns 422."""
    for valid_temp in (0.0, 2.0, 0.0001, 1.9999, 1.0):
        resp = await client.put(
            "/api/agents/settings",
            json={"settings": {"GapFinderAgent": {"temperature": valid_temp}}}
        )
        assert resp.status_code == 200, f"Valid temp {valid_temp} rejected"

    for invalid_temp in (-0.0001, -1.0, -100.0, 2.0001, 2.5, 999.0):
        resp = await client.put(
            "/api/agents/settings",
            json={"settings": {"GapFinderAgent": {"temperature": invalid_temp}}}
        )
        assert resp.status_code == 422, f"Invalid temp {invalid_temp} was not rejected with 422"


@pytest.mark.asyncio
async def test_fuzz_top_p_boundaries(client: AsyncClient) -> None:
    """Verify top_p boundaries: [0.0, 1.0] valid, out-of-range returns 422."""
    for valid_top_p in (0.0, 1.0, 0.0001, 0.9999, 0.5):
        resp = await client.put(
            "/api/agents/settings",
            json={"settings": {"PlannerAgent": {"top_p": valid_top_p}}}
        )
        assert resp.status_code == 200, f"Valid top_p {valid_top_p} rejected"

    for invalid_top_p in (-0.0001, -0.5, 1.0001, 1.5, 10.0):
        resp = await client.put(
            "/api/agents/settings",
            json={"settings": {"PlannerAgent": {"top_p": invalid_top_p}}}
        )
        assert resp.status_code == 422, f"Invalid top_p {invalid_top_p} was not rejected with 422"


@pytest.mark.asyncio
async def test_fuzz_max_output_tokens_boundaries(client: AsyncClient) -> None:
    """Verify max_output_tokens boundaries: [128, 65536] valid, out-of-range returns 422."""
    for valid_tokens in (128, 65536, 129, 65535, 8192):
        resp = await client.put(
            "/api/agents/settings",
            json={"settings": {"DraftingAgent": {"max_output_tokens": valid_tokens}}}
        )
        assert resp.status_code == 200, f"Valid tokens {valid_tokens} rejected"

    for invalid_tokens in (127, 0, -1, -1000, 65537, 100000):
        resp = await client.put(
            "/api/agents/settings",
            json={"settings": {"DraftingAgent": {"max_output_tokens": invalid_tokens}}}
        )
        assert resp.status_code == 422, f"Invalid tokens {invalid_tokens} was not rejected with 422"


@pytest.mark.asyncio
async def test_fuzz_traces_query_params(client: AsyncClient) -> None:
    """Verify GET /api/agents/traces query parameter validation."""
    for limit in (1, 100, 500):
        resp = await client.get(f"/api/agents/traces?limit={limit}")
        assert resp.status_code == 200

    for bad_limit in (0, -1, -50, 501, 1000):
        resp = await client.get(f"/api/agents/traces?limit={bad_limit}")
        assert resp.status_code == 422

    resp = await client.get("/api/agents/traces?since=invalid-date-format")
    assert resp.status_code == 422


# ============================================================================
# 3. Partial Dictionaries, Nulls, and State Preservation
# ============================================================================


@pytest.mark.asyncio
async def test_partial_config_updates_preserve_existing_fields(client: AsyncClient) -> None:
    """Verify partial setting updates do not overwrite unmentioned fields."""
    await client.put(
        "/api/agents/settings",
        json={
            "settings": {
                "ProjectAgent": {
                    "model": "gemini-3.7-flash",
                    "custom_prompt_prefix": "CUSTOM_ORCHESTRATOR_PREFIX",
                }
            }
        }
    )

    resp = await client.put(
        "/api/agents/settings",
        json={"settings": {"ProjectAgent": {"temperature": 0.35}}}
    )
    assert resp.status_code == 200

    get_res = await client.get("/api/agents/registry")
    proj = next(a for a in get_res.json()["agents"] if a["name"] == "ProjectAgent")

    assert proj["config"]["model"] == "gemini-3.7-flash"
    assert proj["config"]["custom_prompt_prefix"] == "CUSTOM_ORCHESTRATOR_PREFIX"
    assert abs(proj["config"]["temperature"] - 0.35) < 1e-4
    assert proj["config"]["is_default"] is False


@pytest.mark.asyncio
async def test_empty_settings_dict_noop(client: AsyncClient) -> None:
    """Verify empty settings dictionary executes cleanly as a no-op."""
    resp = await client.put("/api/agents/settings", json={"settings": {}})
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["updated_agents"] == []


@pytest.mark.asyncio
async def test_whitespace_only_custom_prompt_prefix_strips_cleanly(client: AsyncClient) -> None:
    """Verify whitespace-only custom prompt prefix is stripped to empty string."""
    resp = await client.put(
        "/api/agents/settings",
        json={"settings": {"EvidenceSynthesizerAgent": {"custom_prompt_prefix": "   \n\t  \n  "}}}
    )
    assert resp.status_code == 200
    
    get_res = await client.get("/api/agents/registry")
    agent = next(a for a in get_res.json()["agents"] if a["name"] == "EvidenceSynthesizerAgent")
    assert agent["config"]["custom_prompt_prefix"] in ("", None)


# ============================================================================
# 4. Adversarial Prompt Prefixes (Payloads, Escaping, Unicode, SQLi)
# ============================================================================


@pytest.mark.asyncio
async def test_huge_custom_prompt_prefix_50kb(client: AsyncClient) -> None:
    """Verify 50KB custom prompt prefix is processed and hot-reloaded without memory leaks or crashes."""
    huge_prefix = "MANDATORY DIRECTIVE: " + ("Deeply analyze literature. " * 1500)
    huge_prefix = huge_prefix.strip()
    assert len(huge_prefix) > 30000

    resp = await client.put(
        "/api/agents/settings",
        json={"settings": {"ALRSAgent": {"custom_prompt_prefix": huge_prefix}}}
    )
    assert resp.status_code == 200

    get_res = await client.get("/api/agents/registry")
    assert get_res.status_code == 200
    alrs = next(a for a in get_res.json()["agents"] if a["name"] == "ALRSAgent")
    assert alrs["config"]["custom_prompt_prefix"] == huge_prefix


@pytest.mark.asyncio
async def test_unicode_and_emojis_prompt_prefix(client: AsyncClient) -> None:
    """Verify Unicode, Emojis, RTL scripts, and special symbols in prompt prefixes."""
    complex_text = (
        "🤖 ALRS Multi-Agent Swarm 🔬\n"
        "العربية: يرجى استخراج البيانات بدقة عالية.\n"
        "中文: 深度文献综述与图检索。\n"
        "Русский: Проверить цитирование и ссылки.\n"
        "Special: \u200b\u200c\u200d\uFEFF § ¶ † ‡ • « » —"
    )
    resp = await client.put(
        "/api/agents/settings",
        json={"settings": {"GapFinderAgent": {"custom_prompt_prefix": complex_text}}}
    )
    assert resp.status_code == 200

    get_res = await client.get("/api/agents/registry")
    gap = next(a for a in get_res.json()["agents"] if a["name"] == "GapFinderAgent")
    assert gap["config"]["custom_prompt_prefix"] == complex_text


@pytest.mark.asyncio
async def test_sqli_and_xss_in_prompt_prefix(client: AsyncClient) -> None:
    """Verify SQL injection, XSS, and markdown injection payloads are safely stored without executing."""
    malicious_inputs = [
        "'; DROP TABLE settings; DROP TABLE agent_traces; --",
        "' OR '1'='1' -- /* admin bypass */",
        "<script>alert('XSS_ATTACK'); window.location='http://evil.com';</script>",
        "```json\n{\"__proto__\": {\"admin\": true}}\n```",
        "{{ 7 * 7 }} ${7*7} <%= 7*7 %>",
    ]

    for payload in malicious_inputs:
        resp = await client.put(
            "/api/agents/settings",
            json={"settings": {"DebuggerAgent": {"custom_prompt_prefix": payload}}}
        )
        assert resp.status_code == 200
        get_res = await client.get("/api/agents/registry")
        debugger = next(a for a in get_res.json()["agents"] if a["name"] == "DebuggerAgent")
        assert debugger["config"]["custom_prompt_prefix"] == payload


# ============================================================================
# 5. Non-Existent Agents, Batch Atomicity & Reset Idempotency
# ============================================================================


@pytest.mark.asyncio
async def test_unknown_agent_in_batch_rejects_with_404(client: AsyncClient) -> None:
    """Verify batch request containing valid AND invalid agents returns 404."""
    resp = await client.put(
        "/api/agents/settings",
        json={
            "settings": {
                "ALRSAgent": {"temperature": 0.5},
                "GhostAgent999": {"temperature": 0.5},
            }
        }
    )
    assert resp.status_code == 404
    assert "GhostAgent999" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_case_sensitive_agent_names(client: AsyncClient) -> None:
    """Verify agent names are strictly matched case-sensitively."""
    resp = await client.put(
        "/api/agents/settings",
        json={"settings": {"alrsagent": {"temperature": 0.5}}}
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_reset_idempotency(client: AsyncClient) -> None:
    """Verify resetting already-default agents or resetting multiple times is strictly idempotent."""
    r1 = await client.post("/api/agents/settings/reset", json={})
    assert r1.status_code == 200
    assert len(r1.json()["reset_agents"]) == 9

    r2 = await client.post("/api/agents/settings/reset", json={})
    assert r2.status_code == 200
    assert len(r2.json()["reset_agents"]) == 9

    r3 = await client.post("/api/agents/settings/reset", json={"agent_name": "ALRSAgent"})
    assert r3.status_code == 200
    assert r3.json()["reset_agents"] == ["ALRSAgent"]

    r4 = await client.post("/api/agents/settings/reset", json={"agent_name": "ALRSAgent"})
    assert r4.status_code == 200


# ============================================================================
# 6. Live ADK Agent Hot-Reloading & System Instruction Stacking
# ============================================================================


@pytest.mark.asyncio
async def test_live_agent_instruction_prefix_and_revert() -> None:
    """Verify live agent instance has instruction modified and reverted without stacking artifacts."""
    from agents.agent import root_agent

    service = AgentService(root_agent=root_agent, mysql_service=None)
    agents = service._get_all_agents()
    alrs = next(a for a in agents if getattr(a, "name", "") == "ALRSAgent")
    original_instruction = alrs.instruction

    # Apply Prefix 1
    await service.update_settings({
        "ALRSAgent": AgentConfigUpdate(custom_prompt_prefix="PREFIX_ONE")
    })
    assert alrs.instruction.startswith("PREFIX_ONE\n\n")
    assert original_instruction in alrs.instruction

    # Apply Prefix 2 (must replace Prefix 1, not stack on top)
    await service.update_settings({
        "ALRSAgent": AgentConfigUpdate(custom_prompt_prefix="PREFIX_TWO")
    })
    assert alrs.instruction.startswith("PREFIX_TWO\n\n")
    assert "PREFIX_ONE" not in alrs.instruction

    # Reset settings (must revert to original instruction cleanly)
    await service.reset_settings("ALRSAgent")
    assert alrs.instruction == original_instruction


# ============================================================================
# 7. Database Failure Resilience & Graceful Degradation
# ============================================================================


@pytest.mark.asyncio
async def test_mysql_failure_resilience_during_update_and_reset() -> None:
    """Verify service handles MySQL exceptions during save/reset gracefully without crashing."""
    from agents.agent import root_agent

    mock_failing_mysql = AsyncMock()
    mock_failing_mysql.execute.side_effect = RuntimeError("Lost connection to MySQL server")
    mock_failing_mysql.fetch_all.side_effect = RuntimeError("Lost connection to MySQL server")
    mock_failing_mysql.fetch_one.side_effect = RuntimeError("Lost connection to MySQL server")

    service = AgentService(root_agent=root_agent, mysql_service=mock_failing_mysql)

    # 1. Update should not throw exception
    update_res = await service.update_settings({
        "ResearchAgent": AgentConfigUpdate(temperature=0.8)
    })
    assert update_res.success is True
    assert "ResearchAgent" in update_res.updated_agents

    # 2. Reset should not throw exception
    reset_res = await service.reset_settings("ResearchAgent")
    assert reset_res.success is True
    assert "ResearchAgent" in reset_res.reset_agents

    # 3. Traces should return empty list gracefully
    traces = await service.get_traces(agent_name="ResearchAgent")
    assert traces == []

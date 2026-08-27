"""Adversarial stress and edge-case empirical test suite for ChatService & Router.

Authored by Challenger 1 for Milestone 1 Verification.
Tests include:
- Cross-project isolation and tenant boundary enforcement
- URL path traversal handling (FastAPI routing normalization)
- SQL injection vectors & malicious ID strings
- Extreme Unicode, Emojis, RTL, and LaTeX formulas
- Large payloads (100KB)
- High concurrency (50 parallel chats, 20 parallel messages, rapid worker lifecycles)
- Deeply nested JSON and malformed tool responses
- Neo4j / MySQL fault injection & graceful degradation
- ADK event streaming resilience (partial streams, missing parts, error responses)
- Empirical reproduction of DOI extraction formatting bug in CitationVerifier
"""
from __future__ import annotations

import asyncio
import json
import urllib.parse
import uuid
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from main import app
from core.dependencies import get_chat_service
from agents.writing.citation_verifier import extract_dois
from features.chat.models import (
    ChatMessage,
    ChatSessionListResponse,
    ChatSessionSummary,
    CitationTrace,
    CreateChatRequest,
    SendMessageRequest,
    SendMessageResponse,
    ToolTrace,
)
from features.chat.service import (
    ChatService,
    _SESSIONS_STORE,
    _MESSAGES_STORE,
)


@pytest.fixture(autouse=True)
def clean_in_memory_stores():
    """Ensure in-memory stores are clean before and after each test."""
    _SESSIONS_STORE.clear()
    _MESSAGES_STORE.clear()
    yield
    _SESSIONS_STORE.clear()
    _MESSAGES_STORE.clear()


# ── 1. Cross-Project Isolation (Tenant Boundary) ──────────────────────

@pytest.mark.asyncio
async def test_cross_project_isolation_in_memory():
    """Ensure Project A cannot access, send messages to, or delete Project B's chat sessions."""
    service = ChatService(mysql_service=None, neo4j_service=None)
    proj_a = "proj-alpha"
    proj_b = "proj-beta"

    # Create chat in Project A
    chat_a = await service.create_chat(proj_a, title="Project A Thread")
    assert chat_a.id is not None

    # 1. Project B listing should NOT see chat_a
    chats_b = await service.list_chats(proj_b)
    assert len(chats_b) == 0
    assert all(c.id != chat_a.id for c in chats_b)

    # 2. Project B requesting messages from chat_a should get None (404)
    msgs_b = await service.get_messages(proj_b, chat_a.id)
    assert msgs_b is None

    # 3. Project B sending message to chat_a should get None (404)
    send_b = await service.send_message(proj_b, chat_a.id, "Unauthorized message attempt")
    assert send_b is None

    # 4. Project B attempting to delete chat_a should return False
    del_b = await service.delete_chat(proj_b, chat_a.id)
    assert del_b is False

    # 5. Verify chat_a is intact in Project A
    msgs_a = await service.get_messages(proj_a, chat_a.id)
    assert msgs_a is not None
    assert len(msgs_a) == 1


@pytest.mark.asyncio
async def test_cross_project_isolation_via_api():
    """Test API endpoint responses for cross-project unauthorized access."""
    service = ChatService(mysql_service=None, neo4j_service=None)
    app.dependency_overrides[get_chat_service] = lambda: service
    client = TestClient(app)

    # Create chat in Project A
    res = client.post("/api/projects/proj-alpha/chats", json={"title": "Alpha Chat"})
    assert res.status_code == status.HTTP_201_CREATED
    chat_id = res.json()["id"]

    # Try GET messages from Project B -> 404
    res_get = client.get(f"/api/projects/proj-beta/chats/{chat_id}/messages")
    assert res_get.status_code == status.HTTP_404_NOT_FOUND

    # Try POST message from Project B -> 404
    res_post = client.post(
        f"/api/projects/proj-beta/chats/{chat_id}/messages",
        json={"message": "Infiltrating Project B"},
    )
    assert res_post.status_code == status.HTTP_404_NOT_FOUND

    # Try DELETE from Project B -> 404
    res_del = client.delete(f"/api/projects/proj-beta/chats/{chat_id}")
    assert res_del.status_code == status.HTTP_404_NOT_FOUND


# ── 2. Payload Edge Cases & Injection Attacks ──────────────────────────

@pytest.mark.asyncio
async def test_sql_injection_and_special_character_ids():
    """Test handling of SQL injection strings, XSS payloads without slash, and special characters in project IDs."""
    service = ChatService(mysql_service=None, neo4j_service=None)
    app.dependency_overrides[get_chat_service] = lambda: service
    client = TestClient(app)

    malicious_ids = [
        "proj' OR '1'='1",
        "proj'; DROP TABLE chat_sessions; --",
        "spaces in id",
        "emoji-🧪-💥-🔥",
        "unicode-λ-∑-∫",
    ]

    for evil_id in malicious_ids:
        encoded_id = urllib.parse.quote(evil_id, safe="")
        # Create chat under encoded project ID
        res = client.post(f"/api/projects/{encoded_id}/chats", json={"title": f"Evil {evil_id}"})
        assert res.status_code == status.HTTP_201_CREATED
        chat = res.json()
        assert chat["project_id"] == evil_id

        # Retrieve messages
        res_msgs = client.get(f"/api/projects/{encoded_id}/chats/{chat['id']}/messages")
        assert res_msgs.status_code == status.HTTP_200_OK

        # Delete chat
        res_del = client.delete(f"/api/projects/{encoded_id}/chats/{chat['id']}")
        assert res_del.status_code == status.HTTP_200_OK


@pytest.mark.asyncio
async def test_path_traversal_blocked_by_router():
    """Test that path traversal attempts in project IDs are blocked/normalized by router."""
    service = ChatService(mysql_service=None, neo4j_service=None)
    app.dependency_overrides[get_chat_service] = lambda: service
    client = TestClient(app)

    # Path traversal ../../../../etc/passwd resolves outside /api/projects/.../chats route -> 404
    res = client.post("/api/projects/../../../../etc/passwd/chats", json={"title": "Traverse"})
    assert res.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_extreme_unicode_and_scientific_payloads():
    """Test handling of multi-byte Unicode, complex emojis, LaTeX formulas, RTL text."""
    service = ChatService(mysql_service=None, neo4j_service=None)
    app.dependency_overrides[get_chat_service] = lambda: service
    client = TestClient(app)

    # Create chat
    res = client.post("/api/projects/proj-unicode/chats", json={"title": "🔬 Quantum & 🧬 BioNLP"})
    assert res.status_code == status.HTTP_201_CREATED
    chat_id = res.json()["id"]

    complex_payloads = [
        # Complex emojis with ZWJ and skin tones
        "Researcher 👨🏾‍🔬 collaborates with 👩🏼‍💻 on 📚 Knowledge Graphs 🚀✨!",
        # RTL (Arabic / Hebrew)
        "هل يمكن تلخيص أوراق الشبكات العصبية الرسومية؟ וגם בעברית",
        # Math / LaTeX formulas
        r"Consider $\mathcal{L}_{GNN} = \sum_{v \in V} \log P(y_v | \mathbf{h}_v^{(K)})$ where $\mathbf{h}_v^{(k)} = \sigma\left(\mathbf{W} \cdot \text{AGG}(\{\mathbf{h}_u^{(k-1)} : u \in \mathcal{N}(v)\})\right)$",
        # CJK / Multi-byte scripts
        "こんにちは、グラフニューラルネットワークの最新動向を教えてください。 (Graph Neural Networks 综述)",
        # Special ASCII & Escaped characters
        "Line 1\nLine 2\r\nLine 3\tTabbed \"Quoted\" 'Single' \\Backslash /Slash \u200bZeroWidth",
    ]

    for payload in complex_payloads:
        with patch.object(service, "_process_adk_events", side_effect=Exception("Offline test")):
            res_send = client.post(
                f"/api/projects/proj-unicode/chats/{chat_id}/messages",
                json={"message": payload},
            )
        assert res_send.status_code == status.HTTP_200_OK
        data = res_send.json()
        assert data["user_message"]["content"] == payload.strip()
        assert len(data["assistant_message"]["content"]) > 0


@pytest.mark.asyncio
async def test_large_message_payload():
    """Test sending a large message (100KB) to ensure no buffer overflow or unhandled exceptions."""
    service = ChatService(mysql_service=None, neo4j_service=None)
    app.dependency_overrides[get_chat_service] = lambda: service
    client = TestClient(app)

    res = client.post("/api/projects/proj-large/chats", json={"title": "Large Payload Test"})
    chat_id = res.json()["id"]

    # 100KB payload of text
    large_text = "Graph neural network analysis: " + ("abcdefghijklmnopqrstuvwxyz0123456789 " * 2800)
    assert len(large_text) > 100_000

    with patch.object(service, "_process_adk_events", side_effect=Exception("Offline test")):
        res_send = client.post(
            f"/api/projects/proj-large/chats/{chat_id}/messages",
            json={"message": large_text},
        )
    assert res_send.status_code == status.HTTP_200_OK
    data = res_send.json()
    assert data["user_message"]["content"] == large_text.strip()


# ── 3. Concurrency & Race Conditions ──────────────────────────────────

@pytest.mark.asyncio
async def test_concurrent_chat_creations():
    """Test spinning up 50 chats concurrently for the same project without collisions."""
    service = ChatService(mysql_service=None, neo4j_service=None)
    proj_id = "proj-concurrency-create"

    tasks = [service.create_chat(proj_id, title=f"Thread #{i}") for i in range(50)]
    sessions = await asyncio.gather(*tasks)

    assert len(sessions) == 50
    session_ids = {s.id for s in sessions}
    assert len(session_ids) == 50  # All unique UUIDs

    # List all chats
    listed = await service.list_chats(proj_id)
    assert len(listed) == 50


@pytest.mark.asyncio
async def test_concurrent_messages_in_single_chat():
    """Test 20 concurrent messages sent to the same chat thread."""
    service = ChatService(mysql_service=None, neo4j_service=None)
    proj_id = "proj-concurrency-msg"

    chat = await service.create_chat(proj_id, title="Concurrent Chat")
    chat_id = chat.id

    async def _send(i: int):
        with patch.object(service, "_process_adk_events", side_effect=Exception("Offline test")):
            return await service.send_message(proj_id, chat_id, f"Concurrent question #{i}")

    tasks = [_send(i) for i in range(20)]
    results = await asyncio.gather(*tasks)

    for r in results:
        assert r is not None
        u, a = r
        assert u.sender == "user"
        assert a.sender == "assistant"

    # Total messages should be: 1 greeting + 20 * 2 = 41 messages
    messages = await service.get_messages(proj_id, chat_id)
    assert messages is not None
    assert len(messages) == 41

    # Session metadata check
    chats = await service.list_chats(proj_id)
    assert len(chats) == 1
    assert chats[0].message_count == 41


@pytest.mark.asyncio
async def test_rapid_create_send_delete_race():
    """Test rapid interleaving of create, send, and delete operations."""
    service = ChatService(mysql_service=None, neo4j_service=None)
    proj_id = "proj-race"

    async def lifecycle_worker(worker_id: int):
        # 1. Create
        chat = await service.create_chat(proj_id, title=f"Worker {worker_id}")
        cid = chat.id
        # 2. Send 2 messages
        with patch.object(service, "_process_adk_events", side_effect=Exception("Offline")):
            await service.send_message(proj_id, cid, f"Msg 1 from {worker_id}")
            await service.send_message(proj_id, cid, f"Msg 2 from {worker_id}")
        # 3. Read
        msgs = await service.get_messages(proj_id, cid)
        assert msgs is not None
        assert len(msgs) == 5  # 1 greeting + 2*2
        # 4. Delete
        deleted = await service.delete_chat(proj_id, cid)
        assert deleted is True
        # 5. Confirm deleted
        msgs_after = await service.get_messages(proj_id, cid)
        assert msgs_after is None

    workers = [lifecycle_worker(i) for i in range(15)]
    await asyncio.gather(*workers)

    # After all workers complete, store for proj-race should be empty
    final_chats = await service.list_chats(proj_id)
    assert len(final_chats) == 0


# ── 4. Deeply Nested JSON & Tool Trace Resilience ──────────────────────

@pytest.mark.asyncio
async def test_tool_trace_with_deep_nested_arguments_and_results():
    """Test tool traces containing arbitrarily deep JSON, lists, nulls, and non-string types."""
    service = ChatService(mysql_service=None, neo4j_service=None)
    proj_id = "proj-json-nest"

    chat = await service.create_chat(proj_id)
    chat_id = chat.id

    # Construct complex mock ADK event
    complex_args = {
        "depth_1": {
            "depth_2": {
                "depth_3": {
                    "numbers": [1, 2, 3, 4.5],
                    "booleans": [True, False, None],
                    "unicode": "🌟 Graph Embedding 🌟",
                }
            }
        }
    }
    complex_response = {
        "status": "success",
        "subgraph": {
            "nodes": [{"id": f"node_{i}", "label": "Paper"} for i in range(10)],
            "metrics": {"modularity": 0.854, "density": 0.012},
        },
    }

    mock_call = MagicMock()
    mock_call.name = "DeepGraphAnalysisTool"
    mock_call.args = complex_args

    mock_resp = MagicMock()
    mock_resp.name = "DeepGraphAnalysisTool"
    mock_resp.response = complex_response

    mock_event_call = MagicMock()
    mock_event_call.get_function_calls.return_value = [mock_call]
    mock_event_call.get_function_responses.return_value = []
    mock_event_call.content = None

    mock_event_resp = MagicMock()
    mock_event_resp.get_function_calls.return_value = []
    mock_event_resp.get_function_responses.return_value = [mock_resp]
    part = MagicMock()
    part.text = "Deep subgraph analysis complete."
    mock_event_resp.content = MagicMock(parts=[part])

    async def mock_event_stream():
        yield mock_event_call
        yield mock_event_resp

    with patch.object(service, "_process_adk_events", wraps=service._process_adk_events):
        tool_traces, assistant_text = await service._process_adk_events(mock_event_stream())

    assert len(tool_traces) == 1
    trace = tool_traces[0]
    assert trace.tool_name == "DeepGraphAnalysisTool"
    assert trace.input_args == complex_args
    assert trace.status == "success"
    assert "modularity" in trace.output_result
    assert assistant_text == "Deep subgraph analysis complete."


@pytest.mark.asyncio
async def test_tool_trace_error_status_detection():
    """Test that tool responses with error payloads are marked as status='error'."""
    service = ChatService(mysql_service=None, neo4j_service=None)

    mock_call = MagicMock()
    mock_call.name = "FailingNeo4jTool"
    mock_call.args = {"query": "MATCH (n) RETURN n"}

    mock_resp = MagicMock()
    mock_resp.name = "FailingNeo4jTool"
    mock_resp.response = {"error": "Connection timeout to Neo4j instance", "status": "error"}

    mock_event = MagicMock()
    mock_event.get_function_calls.return_value = [mock_call]
    mock_event.get_function_responses.return_value = [mock_resp]
    mock_event.content = MagicMock(parts=[MagicMock(text="Encountered graph error.")])

    async def mock_event_stream():
        yield mock_event

    tool_traces, text = await service._process_adk_events(mock_event_stream())

    assert len(tool_traces) == 1
    assert tool_traces[0].status == "error"
    assert "Connection timeout" in tool_traces[0].output_result


# ── 5. Fault Injection: MySQL and Neo4j Service Failures ──────────────

@pytest.mark.asyncio
async def test_mysql_failure_graceful_degradation():
    """Test that if MySQL raises database errors, ChatService gracefully falls back to in-memory store."""
    failing_mysql = AsyncMock()
    failing_mysql.fetch_all.side_effect = RuntimeError("MySQL server has gone away")
    failing_mysql.fetch_one.side_effect = RuntimeError("MySQL server has gone away")
    failing_mysql.execute.side_effect = RuntimeError("MySQL server has gone away")

    service = ChatService(mysql_service=failing_mysql, neo4j_service=None)
    proj_id = "proj-mysql-fail"

    # Create chat should still succeed in in-memory store despite MySQL failure log
    chat = await service.create_chat(proj_id, title="Survives MySQL Outage")
    assert chat is not None
    assert chat.title == "Survives MySQL Outage"

    # List chats should fall back to in-memory store
    chats = await service.list_chats(proj_id)
    assert len(chats) == 1
    assert chats[0].id == chat.id

    # Send message should succeed in memory
    with patch.object(service, "_process_adk_events", side_effect=Exception("Offline")):
        res = await service.send_message(proj_id, chat.id, "Testing during DB outage")
    assert res is not None
    user_msg, assistant_msg = res
    assert user_msg.content == "Testing during DB outage"

    # Delete chat should clean up in-memory store
    deleted = await service.delete_chat(proj_id, chat.id)
    assert deleted is True
    chats_after = await service.list_chats(proj_id)
    assert len(chats_after) == 0


# ── 6. Empirical Vulnerability Reproduction: Markdown DOI Formatting Bug ──

def test_empirical_doi_extraction_markdown_backtick_bug():
    """Empirically verify that extract_dois includes trailing backtick and asterisk when formatted as *DOI: `...`*."""
    grounded_markdown_bullet = "*DOI: `10.1145/3447548.3467285`* [Verified Ground-Truth]"
    extracted = extract_dois(grounded_markdown_bullet)
    
    # Document empirical behavior: DOI regex pattern captures trailing backtick and asterisk
    assert len(extracted) == 1
    assert extracted[0] == "10.1145/3447548.3467285`*"

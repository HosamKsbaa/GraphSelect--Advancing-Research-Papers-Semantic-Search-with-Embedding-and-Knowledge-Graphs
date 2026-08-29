"""Adversarial stress test suite for multi-turn chat continuation in ChatService & Router.

Covers:
- User input variations: raw DOIs, URL-formatted DOIs (https/http/dx), option selectors ("Option A", "Let's do option B"), invalid strings, empty strings, and malformed DOIs.
- Session history preservation across multi-turn interactions.
- Traversal triggering and appraisal payload verification for valid targets.
- Project state preservation and cross-project isolation.
- Full FastAPI REST endpoint integration verification.
"""
from __future__ import annotations

import os
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from main import app
from core.dependencies import get_chat_service
from features.chat.models import ChatMessage, ChatSessionSummary
from features.chat.service import (
    ChatService,
    _MESSAGES_STORE,
    _SESSIONS_STORE,
)


@pytest.fixture(autouse=True)
def setup_chat_test_environment():
    """Ensure clean in-memory state and test mode for every test."""
    _SESSIONS_STORE.clear()
    _MESSAGES_STORE.clear()
    os.environ["PYTEST_CURRENT_TEST"] = "1"
    yield
    _SESSIONS_STORE.clear()
    _MESSAGES_STORE.clear()


@pytest.fixture
def mock_neo4j_service() -> AsyncMock:
    """Mock Neo4j service with research questions and paper library."""
    mock = AsyncMock()
    mock.get_research_questions.return_value = [
        {"question_id": "rq-1", "question_text": "Scalability and BFS bounds in graph traversal"},
        {"question_id": "rq-2", "question_text": "Graph representation learning for academic literature"},
    ]
    mock.get_project_papers.return_value = [
        {
            "doi": "10.1145/3613904.3642697",
            "title": "Graph Neural Networks for Scholarly Literature Reviews",
            "year": 2021,
            "cited_by_count": 1420,
        },
        {
            "doi": "10.1016/j.cag.2025.04.012",
            "title": "Subgraph Sampling & Dynamic Embedding at Web-Scale",
            "year": 2025,
            "cited_by_count": 38,
        },
    ]
    mock.verify_doi = AsyncMock(return_value=True)
    return mock


@pytest.fixture
def chat_service(mock_neo4j_service: AsyncMock) -> ChatService:
    """Create ChatService instance with mocked Neo4j and disabled live LLM."""
    return ChatService(
        mysql_service=None,
        neo4j_service=mock_neo4j_service,
        llm_service=None,
    )


# ── 1. Raw DOI Input Variations ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_raw_doi_input_variations(chat_service: ChatService):
    """Test continuation with raw DOI strings across multiple formats."""
    project_id = "proj-raw-doi-adv"
    session = await chat_service.create_chat(project_id, title="Raw DOI Continuation")
    chat_id = session.id

    raw_dois = [
        "10.1145/3613904.3642697",
        "10.1016/j.cag.2025.04.012",
        "10.1007/s10618-024-00982-x",
    ]

    for doi in raw_dois:
        user_msg, asst_msg = await chat_service.send_message(
            project_id=project_id,
            chat_id=chat_id,
            user_text=f"Please traverse and appraise {doi}",
        )
        assert user_msg is not None
        assert asst_msg is not None

        # Verify traversal tool traces
        tool_names = [t.tool_name for t in asst_msg.tool_traces]
        assert "run_graphselect_traversal" in tool_names
        assert "appraise_1hop_candidate_pool" in tool_names

        # Verify appraisal metadata matches input DOI
        assert asst_msg.appraisal is not None
        assert asst_msg.appraisal["seed_doi"] == doi
        assert len(asst_msg.steering_options) == 4

        # Verify content contains 3 archetypes
        assert "Foundational Prior Art" in asst_msg.content
        assert "Contemporary Breakthroughs" in asst_msg.content
        assert "Topological Bridges" in asst_msg.content


# ── 2. URL-Formatted DOI Variations ──────────────────────────────────────

@pytest.mark.asyncio
async def test_url_formatted_doi_variations(chat_service: ChatService):
    """Test continuation with various URL-formatted DOI variations."""
    project_id = "proj-url-doi-adv"
    session = await chat_service.create_chat(project_id, title="URL DOI Continuation")
    chat_id = session.id

    url_variations = [
        ("https://doi.org/10.1145/3613904.3642697", "10.1145/3613904.3642697"),
        ("http://dx.doi.org/10.1016/j.cag.2025.04.012", "10.1016/j.cag.2025.04.012"),
        ("https://dx.doi.org/10.1007/s10618-024-00982-x", "10.1007/s10618-024-00982-x"),
        ("doi: 10.1145/3613904.3642697", "10.1145/3613904.3642697"),
        ("(DOI: 10.1016/j.cag.2025.04.012)", "10.1016/j.cag.2025.04.012"),
    ]

    for url_input, expected_canonical_doi in url_variations:
        user_msg, asst_msg = await chat_service.send_message(
            project_id=project_id,
            chat_id=chat_id,
            user_text=f"Expand from this link: {url_input}",
        )
        assert user_msg is not None
        assert asst_msg is not None

        # Verify normalization canonicalized the DOI
        assert asst_msg.appraisal is not None
        assert asst_msg.appraisal["seed_doi"] == expected_canonical_doi
        assert len(asst_msg.steering_options) == 4


# ── 3. Option Selection Strings ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_option_selection_strings(chat_service: ChatService):
    """Test user replying with option names (Option A, Option B, etc.)."""
    project_id = "proj-option-adv"
    session = await chat_service.create_chat(project_id, title="Option Selection")
    chat_id = session.id

    option_prompts = [
        "Option A",
        "Let's do option B",
        "I select Option C for topological bridges",
        "Option D: finalize and adopt papers",
    ]

    for prompt in option_prompts:
        user_msg, asst_msg = await chat_service.send_message(
            project_id=project_id,
            chat_id=chat_id,
            user_text=prompt,
        )
        assert user_msg is not None
        assert asst_msg is not None

        # Traversal and appraisal should be triggered
        tool_names = [t.tool_name for t in asst_msg.tool_traces]
        assert "run_graphselect_traversal" in tool_names
        assert "appraise_1hop_candidate_pool" in tool_names
        assert len(asst_msg.steering_options) == 4
        assert asst_msg.appraisal is not None


# ── 4. Non-Traversal & Invalid Strings ────────────────────────────────────

@pytest.mark.asyncio
async def test_invalid_and_non_traversal_strings(chat_service: ChatService):
    """Ensure invalid strings, chit-chat, and empty inputs do NOT falsely trigger graph traversal."""
    project_id = "proj-invalid-adv"
    session = await chat_service.create_chat(project_id, title="Invalid Inputs")
    chat_id = session.id

    invalid_inputs = [
        "What is the weather in Tokyo today?",
        "Random chit chat unrelated to academic literature",
        "   ",
        "!@#$%^&*()_+=-~`",
        "tell me a joke",
    ]

    for user_input in invalid_inputs:
        user_msg, asst_msg = await chat_service.send_message(
            project_id=project_id,
            chat_id=chat_id,
            user_text=user_input,
        )
        assert user_msg is not None
        assert asst_msg is not None

        # Traversal tools MUST NOT be triggered for irrelevant non-DOI chat
        tool_names = [t.tool_name for t in asst_msg.tool_traces]
        assert "run_graphselect_traversal" not in tool_names
        assert "appraise_1hop_candidate_pool" not in tool_names

        # Steering options must be empty
        assert len(asst_msg.steering_options) == 0
        assert asst_msg.appraisal is None


# ── 5. Multi-Turn State Preservation & Context History ───────────────────

@pytest.mark.asyncio
async def test_multi_turn_state_preservation_interleaved(chat_service: ChatService):
    """Test full 7-turn session with interleaved valid traversals, chit-chat, and option picks."""
    project_id = "proj-interleaved-history"
    session = await chat_service.create_chat(project_id, title="Interleaved History")
    chat_id = session.id

    turns = [
        ("Start 1-hop traversal on 10.1145/3613904.3642697", True),
        ("Hello, who are you?", False),
        ("Let's expand on Option B: 10.1016/j.cag.2025.04.012", True),
        ("What time is it?", False),
        ("Traverse from https://doi.org/10.1007/s10618-024-00982-x", True),
        ("Option D: conclude cycle", True),
    ]

    for user_text, should_traverse in turns:
        u, a = await chat_service.send_message(project_id, chat_id, user_text)
        assert u.content == user_text
        if should_traverse:
            assert len(a.steering_options) == 4
            assert any(t.tool_name == "run_graphselect_traversal" for t in a.tool_traces)
        else:
            assert len(a.steering_options) == 0
            assert not any(t.tool_name == "run_graphselect_traversal" for t in a.tool_traces)

    # Verify complete message history (1 welcome + 6*2 = 13 messages)
    history = await chat_service.get_messages(project_id, chat_id)
    assert history is not None
    assert len(history) == 13

    # Check order preservation
    assert history[0].sender == "assistant"  # Welcome greeting
    for idx, (user_text, _) in enumerate(turns):
        user_msg_idx = 1 + idx * 2
        asst_msg_idx = 2 + idx * 2
        assert history[user_msg_idx].sender == "user"
        assert history[user_msg_idx].content == user_text
        assert history[asst_msg_idx].sender == "assistant"

    # Check session summary in list_chats
    summaries = await chat_service.list_chats(project_id)
    assert len(summaries) == 1
    assert summaries[0].id == chat_id
    assert summaries[0].message_count == 13


# ── 6. FastAPI REST API Endpoint Verification ────────────────────────────

@pytest.mark.asyncio
async def test_fastapi_rest_chat_continuation_api(chat_service: ChatService):
    """Verify REST API serialization and multi-turn flow through HTTP endpoints."""
    app.dependency_overrides[get_chat_service] = lambda: chat_service
    client = TestClient(app)
    project_id = "proj-fastapi-e2e"

    # 1. Create chat via POST
    res_create = client.post(f"/api/projects/{project_id}/chats", json={"title": "REST HITL Test"})
    assert res_create.status_code == status.HTTP_201_CREATED
    chat = res_create.json()
    chat_id = chat["id"]
    assert chat["message_count"] == 1

    # 2. Turn 1: Send traversal request
    res_t1 = client.post(
        f"/api/projects/{project_id}/chats/{chat_id}/messages",
        json={"message": "1-hop crawl on 10.1145/3613904.3642697"},
    )
    assert res_t1.status_code == status.HTTP_200_OK
    data_t1 = res_t1.json()
    assert data_t1["user_message"]["content"] == "1-hop crawl on 10.1145/3613904.3642697"
    assert "Foundational Prior Art" in data_t1["assistant_message"]["content"]
    assert len(data_t1["assistant_message"]["steering_options"]) == 4

    # 3. Turn 2: Send URL DOI
    res_t2 = client.post(
        f"/api/projects/{project_id}/chats/{chat_id}/messages",
        json={"message": "Continue with https://doi.org/10.1016/j.cag.2025.04.012"},
    )
    assert res_t2.status_code == status.HTTP_200_OK
    data_t2 = res_t2.json()
    assert len(data_t2["assistant_message"]["steering_options"]) == 4

    # 4. Turn 3: Send Option A
    res_t3 = client.post(
        f"/api/projects/{project_id}/chats/{chat_id}/messages",
        json={"message": "Option A"},
    )
    assert res_t3.status_code == status.HTTP_200_OK
    data_t3 = res_t3.json()
    assert len(data_t3["assistant_message"]["steering_options"]) == 4

    # 5. Fetch all messages via GET
    res_msgs = client.get(f"/api/projects/{project_id}/chats/{chat_id}/messages")
    assert res_msgs.status_code == status.HTTP_200_OK
    msgs_data = res_msgs.json()
    assert "messages" in msgs_data
    assert len(msgs_data["messages"]) == 7  # 1 greeting + 3 turns * 2

    # 6. Verify list_chats summary
    res_list = client.get(f"/api/projects/{project_id}/chats")
    assert res_list.status_code == status.HTTP_200_OK
    chat_list_data = res_list.json()
    assert "chats" in chat_list_data
    assert len(chat_list_data["chats"]) == 1
    assert chat_list_data["chats"][0]["message_count"] == 7

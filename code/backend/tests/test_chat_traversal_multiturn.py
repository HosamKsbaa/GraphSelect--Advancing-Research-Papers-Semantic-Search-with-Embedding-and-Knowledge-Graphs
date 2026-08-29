"""Integration tests for multi-turn 1-hop GraphSelect traversal & DOI continuation in ChatService."""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from features.chat.service import ChatService


@pytest.fixture
def mock_chat_env() -> tuple[ChatService, AsyncMock]:
    """Create ChatService instance with mocked Neo4j service."""
    mock_neo4j = AsyncMock()
    mock_neo4j.get_research_questions.return_value = [
        {"question_id": "rq-1", "question_text": "Scalability in GNNs", "embedding": [0.1] * 768},
        {"question_id": "rq-2", "question_text": "Over-smoothing mitigation", "embedding": [0.2] * 768},
    ]
    mock_neo4j.get_project_papers.return_value = [
        {
            "doi": "10.1145/3613904.3642697",
            "title": "Graph Neural Networks for Scholarly Literature Reviews",
            "year": 2021,
            "cited_by_count": 1420,
        }
    ]
    mock_neo4j.verify_doi = AsyncMock(return_value=True)

    chat_service = ChatService(
        mysql_service=None,
        neo4j_service=mock_neo4j,
        llm_service=None,
    )
    return chat_service, mock_neo4j


@pytest.mark.asyncio
async def test_multiturn_traversal_and_doi_continuation_flow(
    mock_chat_env: tuple[ChatService, AsyncMock],
) -> None:
    """Test full multi-turn chat cycle: start traversal -> appraisal -> reply with DOI -> continue next cycle."""
    chat_service, mock_neo4j = mock_chat_env
    project_id = "proj-multiturn-hitl"

    # Step 1: Create new chat session
    session = await chat_service.create_chat(project_id=project_id, title="1-Hop Traversal HITL Session")
    chat_id = session.id
    assert session.message_count == 1  # Initial welcome message

    # Step 2: Turn 1 - User requests 1-hop traversal on seed paper
    user_msg_1, asst_msg_1 = await chat_service.send_message(
        project_id=project_id,
        chat_id=chat_id,
        user_text="Start 1-hop GraphSelect traversal on seed DOI 10.1145/3613904.3642697",
    )

    assert user_msg_1 is not None
    assert asst_msg_1 is not None
    assert "Foundational Prior Art" in asst_msg_1.content
    assert "Contemporary Breakthroughs" in asst_msg_1.content
    assert "Topological Bridges" in asst_msg_1.content
    assert "Strategic Steering Options" in asst_msg_1.content

    # Verify tool traces
    tool_names = [t.tool_name for t in asst_msg_1.tool_traces]
    assert "run_graphselect_traversal" in tool_names
    assert "appraise_1hop_candidate_pool" in tool_names

    # Verify steering options attached to message
    assert len(asst_msg_1.steering_options) == 4
    option_ids = [opt["option_id"] for opt in asst_msg_1.steering_options]
    assert "option_a_foundational" in option_ids
    assert "option_b_contemporary" in option_ids
    assert "option_c_bridge" in option_ids
    assert "option_d_adopt_finalize" in option_ids

    # Step 3: Turn 2 - User replies with chosen DOI (Option B - contemporary breakthrough)
    user_msg_2, asst_msg_2 = await chat_service.send_message(
        project_id=project_id,
        chat_id=chat_id,
        user_text="Let's expand on Option B: 10.1016/j.cag.2025.04.012",
    )

    assert user_msg_2 is not None
    assert asst_msg_2 is not None
    assert "10.1016/j.cag.2025.04.012" in asst_msg_2.content
    assert "Stepwise 1-Hop GraphSelect Traversal" in asst_msg_2.content
    assert len(asst_msg_2.steering_options) == 4

    # Step 4: Turn 3 - User chooses to adopt and finalize (Option D)
    user_msg_3, asst_msg_3 = await chat_service.send_message(
        project_id=project_id,
        chat_id=chat_id,
        user_text="Let's proceed with Option D: adopt and finalize traversal cycle",
    )

    assert user_msg_3 is not None
    assert asst_msg_3 is not None
    assert len(asst_msg_3.steering_options) == 4

    # Step 5: Verify full message history persistence
    messages = await chat_service.get_messages(project_id=project_id, chat_id=chat_id)
    assert messages is not None
    assert len(messages) == 7  # 1 welcome + 3 user + 3 assistant
    assert messages[1].content == "Start 1-hop GraphSelect traversal on seed DOI 10.1145/3613904.3642697"
    assert messages[3].content == "Let's expand on Option B: 10.1016/j.cag.2025.04.012"
    assert messages[5].content == "Let's proceed with Option D: adopt and finalize traversal cycle"


@pytest.mark.asyncio
async def test_multiturn_generic_seed_lookup_from_project_library(
    mock_chat_env: tuple[ChatService, AsyncMock],
) -> None:
    """When user asks for traversal without explicit DOI, ChatService resolves library seed."""
    chat_service, mock_neo4j = mock_chat_env
    project_id = "proj-auto-seed"

    session = await chat_service.create_chat(project_id=project_id)
    user_msg, asst_msg = await chat_service.send_message(
        project_id=project_id,
        chat_id=session.id,
        user_text="Please expand and traverse the citation network from our project seed",
    )

    assert user_msg is not None
    assert asst_msg is not None
    assert "10.1145/3613904.3642697" in asst_msg.content
    assert len(asst_msg.steering_options) == 4

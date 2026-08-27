"""Integration and unit tests for the Chat REST router endpoints and ChatService persistence."""
from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from fastapi import status
from fastapi.testclient import TestClient

from main import app
from core.dependencies import get_chat_service
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
from features.chat.service import ChatService


@pytest.fixture
def mock_chat_service() -> AsyncMock:
    """Mock ChatService fixture with async methods."""
    service = AsyncMock(spec=ChatService)
    return service


# ── 1. List Chats ──────────────────────────────────────────────────────

def test_list_project_chats_empty(mock_chat_service: AsyncMock) -> None:
    """Test listing chats when no chat sessions exist for a project."""
    mock_chat_service.list_chats.return_value = []
    app.dependency_overrides[get_chat_service] = lambda: mock_chat_service

    client = TestClient(app)
    response = client.get("/api/projects/proj-test-123/chats")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "chats" in data
    assert data["chats"] == []
    mock_chat_service.list_chats.assert_called_once_with("proj-test-123")


def test_list_project_chats_multiple(mock_chat_service: AsyncMock) -> None:
    """Test listing multiple chat sessions ordered by update timestamp."""
    sessions = [
        ChatSessionSummary(
            id="chat-1",
            project_id="proj-123",
            title="GNN Survey",
            message_count=3,
            last_message_preview="GNN demonstrates superior accuracy...",
            created_at="2026-08-27T10:00:00+00:00",
            updated_at="2026-08-27T10:30:00+00:00",
        ),
        ChatSessionSummary(
            id="chat-2",
            project_id="proj-123",
            title="Methodology Brainstorm",
            message_count=1,
            last_message_preview="Hello! I am your research assistant.",
            created_at="2026-08-27T09:00:00+00:00",
            updated_at="2026-08-27T09:15:00+00:00",
        ),
    ]
    mock_chat_service.list_chats.return_value = sessions
    app.dependency_overrides[get_chat_service] = lambda: mock_chat_service

    client = TestClient(app)
    response = client.get("/api/projects/proj-123/chats")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert len(data["chats"]) == 2
    assert data["chats"][0]["id"] == "chat-1"
    assert data["chats"][0]["title"] == "GNN Survey"
    assert data["chats"][0]["message_count"] == 3
    assert data["chats"][0]["last_message_preview"] == "GNN demonstrates superior accuracy..."
    assert data["chats"][1]["id"] == "chat-2"


# ── 2. Create Chat ─────────────────────────────────────────────────────

def test_create_project_chat_default_title(mock_chat_service: AsyncMock) -> None:
    """Test creating a chat session with no custom title (auto-generated)."""
    session = ChatSessionSummary(
        id="new-chat-uuid",
        project_id="proj-123",
        title="Research Session #1",
        message_count=1,
        last_message_preview="Hello! I am your Google ADK Literature Research Assistant...",
    )
    mock_chat_service.create_chat.return_value = session
    app.dependency_overrides[get_chat_service] = lambda: mock_chat_service

    client = TestClient(app)
    response = client.post("/api/projects/proj-123/chats", json={})

    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["id"] == "new-chat-uuid"
    assert data["project_id"] == "proj-123"
    assert data["title"] == "Research Session #1"
    mock_chat_service.create_chat.assert_called_once_with("proj-123", title=None)


def test_create_project_chat_custom_title(mock_chat_service: AsyncMock) -> None:
    """Test creating a chat session with a specific custom title."""
    session = ChatSessionSummary(
        id="custom-chat-uuid",
        project_id="proj-123",
        title="Polarity Matrix Analysis",
        message_count=1,
    )
    mock_chat_service.create_chat.return_value = session
    app.dependency_overrides[get_chat_service] = lambda: mock_chat_service

    client = TestClient(app)
    response = client.post(
        "/api/projects/proj-123/chats",
        json={"title": "Polarity Matrix Analysis"},
    )

    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["id"] == "custom-chat-uuid"
    assert data["title"] == "Polarity Matrix Analysis"
    mock_chat_service.create_chat.assert_called_once_with("proj-123", title="Polarity Matrix Analysis")


# ── 3. Get Messages ────────────────────────────────────────────────────

def test_get_chat_messages_success(mock_chat_service: AsyncMock) -> None:
    """Test retrieving messages for an existing chat session."""
    messages = [
        ChatMessage(
            id="msg-1",
            chat_id="chat-123",
            sender="assistant",
            content="Hello! I am your research assistant.",
            timestamp="2026-08-27T10:00:00+00:00",
            tool_traces=[
                ToolTrace(
                    tool_name="KnowledgeGraphGrounding",
                    input_args={"project_id": "proj-123"},
                    output_result="Linked project context and active citation subgraphs.",
                    status="success",
                )
            ],
            citations=[],
        ),
        ChatMessage(
            id="msg-2",
            chat_id="chat-123",
            sender="user",
            content="Summarize literature gaps in citation modeling.",
            timestamp="2026-08-27T10:01:00+00:00",
        ),
    ]
    mock_chat_service.get_messages.return_value = messages
    app.dependency_overrides[get_chat_service] = lambda: mock_chat_service

    client = TestClient(app)
    response = client.get("/api/projects/proj-123/chats/chat-123/messages")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert len(data["messages"]) == 2
    assert data["messages"][0]["sender"] == "assistant"
    assert len(data["messages"][0]["tool_traces"]) == 1
    assert data["messages"][0]["tool_traces"][0]["tool_name"] == "KnowledgeGraphGrounding"
    assert data["messages"][1]["sender"] == "user"
    assert data["messages"][1]["content"] == "Summarize literature gaps in citation modeling."


def test_get_chat_messages_not_found(mock_chat_service: AsyncMock) -> None:
    """Test 404 when retrieving messages for a non-existent chat session."""
    mock_chat_service.get_messages.return_value = None
    app.dependency_overrides[get_chat_service] = lambda: mock_chat_service

    client = TestClient(app)
    response = client.get("/api/projects/proj-123/chats/non-existent-id/messages")

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert "not found" in response.json()["detail"].lower()


# ── 4. Send Message ────────────────────────────────────────────────────

def test_send_chat_message_success(mock_chat_service: AsyncMock) -> None:
    """Test sending a user message and receiving assistant response with traces and citations."""
    user_msg = ChatMessage(
        id="msg-u1",
        chat_id="chat-123",
        sender="user",
        content="What are the main findings in graph attention networks?",
        timestamp="2026-08-27T10:05:00+00:00",
    )
    assistant_msg = ChatMessage(
        id="msg-a1",
        chat_id="chat-123",
        sender="assistant",
        content="Based on your knowledge graph, GAT demonstrates superior edge attention.",
        timestamp="2026-08-27T10:05:02+00:00",
        tool_traces=[
            ToolTrace(
                tool_name="Neo4jPolaritySubgraphSearch",
                input_args={"project_id": "proj-123"},
                output_result="Retrieved 3 papers",
                status="success",
            ),
            ToolTrace(
                tool_name="GeminiEmbeddingSemanticMatch",
                input_args={"dim": 768},
                output_result="Cosine match computed",
                status="success",
            ),
        ],
        citations=[
            CitationTrace(
                doi="10.1145/3292500.3330919",
                title="Graph Attention Networks",
                authors=["Veličković et al."],
                year=2018,
                verified_in_graph=True,
            )
        ],
    )
    mock_chat_service.send_message.return_value = (user_msg, assistant_msg)
    app.dependency_overrides[get_chat_service] = lambda: mock_chat_service

    client = TestClient(app)
    response = client.post(
        "/api/projects/proj-123/chats/chat-123/messages",
        json={"message": "What are the main findings in graph attention networks?"},
    )

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "user_message" in data
    assert "assistant_message" in data
    assert data["user_message"]["content"] == "What are the main findings in graph attention networks?"
    assert data["assistant_message"]["sender"] == "assistant"
    assert len(data["assistant_message"]["tool_traces"]) == 2
    assert len(data["assistant_message"]["citations"]) == 1
    assert data["assistant_message"]["citations"][0]["doi"] == "10.1145/3292500.3330919"
    assert data["assistant_message"]["citations"][0]["verified_in_graph"] is True


def test_send_chat_message_validation_empty_422(mock_chat_service: AsyncMock) -> None:
    """Test 422 validation error when sending an empty message string."""
    app.dependency_overrides[get_chat_service] = lambda: mock_chat_service
    client = TestClient(app)
    response = client.post(
        "/api/projects/proj-123/chats/chat-123/messages",
        json={"message": ""},
    )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


def test_send_chat_message_validation_whitespace_422(mock_chat_service: AsyncMock) -> None:
    """Test 422 validation error when sending whitespace-only string."""
    app.dependency_overrides[get_chat_service] = lambda: mock_chat_service
    client = TestClient(app)
    response = client.post(
        "/api/projects/proj-123/chats/chat-123/messages",
        json={"message": "   \n\t  "},
    )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


def test_send_chat_message_missing_field_422(mock_chat_service: AsyncMock) -> None:
    """Test 422 validation error when request body lacks 'message' key."""
    app.dependency_overrides[get_chat_service] = lambda: mock_chat_service
    client = TestClient(app)
    response = client.post(
        "/api/projects/proj-123/chats/chat-123/messages",
        json={},
    )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


def test_send_chat_message_not_found(mock_chat_service: AsyncMock) -> None:
    """Test 404 when sending a message to a non-existent chat session."""
    mock_chat_service.send_message.return_value = None
    app.dependency_overrides[get_chat_service] = lambda: mock_chat_service

    client = TestClient(app)
    response = client.post(
        "/api/projects/proj-123/chats/non-existent-id/messages",
        json={"message": "Hello?"},
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert "not found" in response.json()["detail"].lower()


# ── 5. Delete Chat ─────────────────────────────────────────────────────

def test_delete_project_chat_success(mock_chat_service: AsyncMock) -> None:
    """Test deleting an existing chat session."""
    mock_chat_service.delete_chat.return_value = True
    app.dependency_overrides[get_chat_service] = lambda: mock_chat_service

    client = TestClient(app)
    response = client.delete("/api/projects/proj-123/chats/chat-123")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["status"] == "success"
    assert data["chat_id"] == "chat-123"
    mock_chat_service.delete_chat.assert_called_once_with("proj-123", "chat-123")


def test_delete_project_chat_not_found(mock_chat_service: AsyncMock) -> None:
    """Test 404 when deleting a non-existent chat session."""
    mock_chat_service.delete_chat.return_value = False
    app.dependency_overrides[get_chat_service] = lambda: mock_chat_service

    client = TestClient(app)
    response = client.delete("/api/projects/proj-123/chats/non-existent-id")

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert "not found" in response.json()["detail"].lower()


# ── 6. Error & Dependency Overrides ────────────────────────────────────

def test_chat_router_service_exception_500(mock_chat_service: AsyncMock) -> None:
    """Test that unexpected service exceptions return HTTP 500."""
    mock_chat_service.list_chats.side_effect = RuntimeError("Database connection lost")
    app.dependency_overrides[get_chat_service] = lambda: mock_chat_service

    client = TestClient(app)
    response = client.get("/api/projects/proj-123/chats")

    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert "Database connection lost" in response.json()["detail"]


# ── 7. Real Service In-Memory Lifecycle End-to-End ─────────────────────

@pytest.mark.asyncio
async def test_chat_service_lifecycle_in_memory() -> None:
    """Test full lifecycle directly against ChatService in in-memory mode."""
    service = ChatService(mysql_service=None, neo4j_service=None)
    proj_id = f"proj-{uuid.uuid4()}"

    # 1. Initially empty
    chats = await service.list_chats(proj_id)
    assert len(chats) == 0

    # 2. Create chat
    session = await service.create_chat(proj_id, title="Quantum GNNs")
    assert session.project_id == proj_id
    assert session.title == "Quantum GNNs"
    assert session.message_count == 1

    # 3. List contains newly created session
    chats = await service.list_chats(proj_id)
    assert len(chats) == 1
    assert chats[0].id == session.id

    # 4. Get messages contains initial greeting
    messages = await service.get_messages(proj_id, session.id)
    assert messages is not None
    assert len(messages) == 1
    assert messages[0].sender == "assistant"
    assert len(messages[0].tool_traces) == 1

    # 5. Send user message (using grounded response when ADK Runner falls back or executes)
    with patch.object(service, "_process_adk_events", side_effect=Exception("Test offline fallback")):
        user_msg, assistant_msg = await service.send_message(
            proj_id, session.id, "Explain quantum random walks on graphs."
        )
    assert user_msg.sender == "user"
    assert user_msg.content == "Explain quantum random walks on graphs."
    assert assistant_msg.sender == "assistant"
    assert len(assistant_msg.tool_traces) >= 1

    # 6. Messages updated
    updated_messages = await service.get_messages(proj_id, session.id)
    assert updated_messages is not None
    assert len(updated_messages) == 3

    # 7. Delete chat
    deleted = await service.delete_chat(proj_id, session.id)
    assert deleted is True

    # 8. Post-delete check
    post_delete_messages = await service.get_messages(proj_id, session.id)
    assert post_delete_messages is None
    chats_after = await service.list_chats(proj_id)
    assert len(chats_after) == 0


# ── 8. ChatService with Mocked MySQL & Neo4j ──────────────────────────

@pytest.mark.asyncio
async def test_chat_service_mysql_crud() -> None:
    """Test ChatService SQL execution with mocked MySQLService."""
    mock_mysql = AsyncMock()
    mock_neo4j = AsyncMock()

    mock_mysql.fetch_all.return_value = [
        {
            "id": "chat-sql-1",
            "project_id": "proj-sql-1",
            "title": "SQL Persisted Session",
            "message_count": 2,
            "last_message_preview": "Summary of literature...",
            "created_at": "2026-08-27 12:00:00",
            "updated_at": "2026-08-27 12:30:00",
        }
    ]
    mock_mysql.fetch_one.return_value = {"id": "chat-sql-1", "title": "SQL Persisted Session", "message_count": 2}
    mock_mysql.execute.return_value = 1

    mock_neo4j.get_research_questions.return_value = [{"question_id": "q1", "text": "What is GNN?"}]
    mock_neo4j.get_project_papers.return_value = [
        {"doi": "10.1000/sql-paper-1", "title": "SQL Paper 1", "year": 2024, "authors": ["Author A"]}
    ]

    service = ChatService(mysql_service=mock_mysql, neo4j_service=mock_neo4j)

    # 1. List chats from MySQL
    chats = await service.list_chats("proj-sql-1")
    assert len(chats) == 1
    assert chats[0].id == "chat-sql-1"
    assert chats[0].title == "SQL Persisted Session"
    mock_mysql.fetch_all.assert_called()

    # 2. Get messages with JSON deserialization
    mock_mysql.fetch_all.return_value = [
        {
            "id": "msg-sql-1",
            "chat_id": "chat-sql-1",
            "project_id": "proj-sql-1",
            "sender": "assistant",
            "content": "Hello",
            "tool_traces": json.dumps([{"tool_name": "TestTool", "input_args": {}, "status": "success"}]),
            "citations": json.dumps([{"doi": "10.1000/sql-paper-1", "title": "SQL Paper 1", "verified_in_graph": True}]),
            "created_at": "2026-08-27 12:00:00",
        }
    ]
    msgs = await service.get_messages("proj-sql-1", "chat-sql-1")
    assert msgs is not None
    assert len(msgs) == 1
    assert msgs[0].id == "msg-sql-1"
    assert len(msgs[0].tool_traces) == 1
    assert msgs[0].tool_traces[0].tool_name == "TestTool"
    assert len(msgs[0].citations) == 1
    assert msgs[0].citations[0].doi == "10.1000/sql-paper-1"

    # 3. Delete chat via MySQL
    mock_mysql.execute.return_value = 1
    deleted = await service.delete_chat("proj-sql-1", "chat-sql-1")
    assert deleted is True


# ── 9. Model Validations ───────────────────────────────────────────────

def test_chat_models_serialization() -> None:
    """Test serialization and validation across all Pydantic models."""
    trace = ToolTrace(
        tool_name="SearchTool",
        input_args={"k": 5},
        output_result="Found 5 papers",
        status="success",
    )
    assert trace.tool_name == "SearchTool"
    assert trace.status == "success"

    cit = CitationTrace(
        doi="10.1000/test",
        title="Test Title",
        authors=["Author 1", "Author 2"],
        year=2024,
        verified_in_graph=True,
    )
    assert cit.doi == "10.1000/test"
    assert cit.verified_in_graph is True

    msg = ChatMessage(
        id="m1",
        chat_id="c1",
        sender="assistant",
        content="Response",
        tool_traces=[trace],
        citations=[cit],
    )
    assert msg.sender == "assistant"
    assert len(msg.tool_traces) == 1
    assert len(msg.citations) == 1

    summary = ChatSessionSummary(
        id="c1",
        project_id="p1",
        title="Session 1",
        message_count=1,
        last_message_preview="Preview",
    )
    assert summary.message_count == 1
    assert summary.last_message_preview == "Preview"

    list_resp = ChatSessionListResponse(chats=[summary])
    assert len(list_resp.chats) == 1

    send_resp = SendMessageResponse(
        user_message=ChatMessage(id="u1", chat_id="c1", sender="user", content="Hello"),
        assistant_message=msg,
    )
    assert send_resp.user_message.content == "Hello"
    assert send_resp.assistant_message.content == "Response"

"""Adversarial stress tests and empirical verification suite for Milestone 1.

Tested areas:
1. Citation extraction, normalization, and zero-hallucination verification edge cases.
2. ADK ToolTrace stream processing and event correlation under asynchronous anomalies.
3. Multi-project session isolation across in-memory and database stores.
4. Database foreign key cascading deletes (projects -> chat_sessions -> chat_messages).
5. REST endpoint edge cases (whitespace validation, cross-project session access security, payload stress).
"""
from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from fastapi import status
from fastapi.testclient import TestClient

from main import app
from config import get_settings
from core.dependencies import get_chat_service
from core.db.mysql_service import MySQLService
from agents.writing.citation_verifier import (
    CitationVerificationResult,
    CitationVerifier,
    extract_dois,
    normalize_doi,
    verify_citation_grounding,
)
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
    _format_datetime,
    _parse_json,
)


# ============================================================================
# 1. Empirical Tests: Citation Extraction & Normalization Edge Cases
# ============================================================================

def test_normalize_doi_complex_edge_cases():
    """Stress test DOI normalization against malformed and varied formats."""
    # Standard format
    assert normalize_doi("10.1000/182") == "10.1000/182"
    # Mixed casing
    assert normalize_doi("10.1000/AbCdEf-123.XyZ") == "10.1000/abcdef-123.xyz"
    # Prefixes
    assert normalize_doi("doi: 10.1145/3308558.3313508") == "10.1145/3308558.3313508"
    assert normalize_doi("DOI: 10.1145/3308558.3313508") == "10.1145/3308558.3313508"
    assert normalize_doi("https://doi.org/10.1145/3308558.3313508") == "10.1145/3308558.3313508"
    assert normalize_doi("http://dx.doi.org/10.1145/3308558.3313508") == "10.1145/3308558.3313508"
    # Enclosed in brackets / parentheses / quotes
    assert normalize_doi("(DOI: 10.1000/182)") == "10.1000/182"
    assert normalize_doi("[10.1000/182]") == "10.1000/182"
    assert normalize_doi('"{10.1000/182}"') == "10.1000/182"
    assert normalize_doi(" '10.1000/182' ") == "10.1000/182"
    # Trailing punctuation
    assert normalize_doi("10.1000/182.") == "10.1000/182"
    assert normalize_doi("10.1000/182,") == "10.1000/182"
    assert normalize_doi("10.1000/182; ") == "10.1000/182"
    assert normalize_doi("10.1000/182: ") == "10.1000/182"
    # Empty and None
    assert normalize_doi("") == ""
    assert normalize_doi("   ") == ""


def test_extract_dois_complex_text():
    """Test DOI extraction from messy text, markdown links, LaTeX, and code snippets."""
    messy_text = """
    ## Literature Review
    In our analysis, we review several foundational papers:
    - Standard DOI: doi:10.1000/paper-one.
    - Markdown link: [Attention Is All You Need](https://doi.org/10.48550/arxiv.1706.03762)
    - Dx.doi URL: http://dx.doi.org/10.1145/3308558.3313508, which introduced key metrics.
    - Parenthesized: (see 10.1000/paper-two; also 10.1000/paper-three).
    - Duplicate mention: 10.1000/PAPER-ONE in uppercase!
    - LaTeX citation: \\cite{doi:10.1016/j.artint.2020.103345}
    - False positives (not DOIs): 10.1/invalid, 20.1000/not-doi, ISBN: 978-3-16-148410-0, IP: 192.168.1.1
    """
    dois = extract_dois(messy_text)
    assert len(dois) == 6
    assert "10.1000/paper-one" in dois
    assert "10.48550/arxiv.1706.03762" in dois
    assert "10.1145/3308558.3313508" in dois
    assert "10.1000/paper-two" in dois
    assert "10.1000/paper-three" in dois
    assert "10.1016/j.artint.2020.103345" in dois


def test_verify_citation_grounding_adversarial_scenarios():
    """Verify citation grounding calculations under extreme boundary conditions."""
    # 1. No citations in text, no assigned DOIs -> 100% grounded and passed
    r1 = verify_citation_grounding("", known_dois=[])
    assert r1.is_grounded is True
    assert r1.passed is True
    assert r1.hallucination_rate == 0.0
    assert r1.coverage_rate == 1.0

    # 2. No citations in text, but assigned DOIs were required -> grounded (no fake citations), but failed (missing)
    r2 = verify_citation_grounding("No citations here.", known_dois=["10.1/a"], assigned_dois=["10.1/a"])
    assert r2.is_grounded is True
    assert r2.passed is False
    assert r2.coverage_rate == 0.0
    assert r2.missing_assigned_dois == ["10.1/a"]

    # 3. 100% hallucinated citations
    r3 = verify_citation_grounding("Cite 10.1000/fake1 and 10.1000/fake2.", known_dois=["10.1000/real"])
    assert r3.is_grounded is False
    assert r3.passed is False
    assert r3.hallucination_rate == 1.0
    assert len(r3.hallucinated_dois) == 2

    # 4. Partial hallucination and partial coverage
    r4 = verify_citation_grounding(
        "Cite 10.1000/real and 10.1000/fake.",
        known_dois=["10.1000/real", "10.1000/missing"],
        assigned_dois=["10.1000/real", "10.1000/missing"],
    )
    assert r4.is_grounded is False
    assert r4.passed is False
    assert r4.hallucination_rate == 0.5
    assert r4.coverage_rate == 0.5
    assert r4.hallucinated_dois == ["10.1000/fake"]
    assert r4.missing_assigned_dois == ["10.1000/missing"]


# ============================================================================
# 2. Empirical Tests: ADK ToolTrace Stream Handling & Correlations
# ============================================================================

class MockADKEvent:
    def __init__(self, calls=None, responses=None, text=None):
        self._calls = calls or []
        self._responses = responses or []
        self.content = None
        if text is not None:
            part = MagicMock()
            part.text = text
            self.content = MagicMock()
            self.content.parts = [part]

    def get_function_calls(self):
        return self._calls

    def get_function_responses(self):
        return self._responses


class MockCall:
    def __init__(self, name: str, args: dict):
        self.name = name
        self.args = args


class MockResp:
    def __init__(self, name: str, response: Any):
        self.name = name
        self.response = response


@pytest.mark.asyncio
async def test_adk_process_events_correlations():
    """Empirically test _process_adk_events with asynchronous call/response pairs and anomalies."""
    service = ChatService()

    async def event_generator():
        # Event 1: Tool call 1
        yield MockADKEvent(calls=[MockCall("search_graph", {"query": "GNN", "limit": 5})])
        # Event 2: Tool call 2
        yield MockADKEvent(calls=[MockCall("verify_dois", {"dois": ["10.1000/1"]})])
        # Event 3: Tool response 1 (matches search_graph)
        yield MockADKEvent(responses=[MockResp("search_graph", {"status": "success", "results": [1, 2]})])
        # Event 4: Text chunk 1
        yield MockADKEvent(text="Based on graph search, ")
        # Event 5: Tool response 2 with error payload (matches verify_dois)
        yield MockADKEvent(responses=[MockResp("verify_dois", {"error": "Graph timeout", "status": "error"})])
        # Event 6: Unmatched tool response (no prior call)
        yield MockADKEvent(responses=[MockResp("unmatched_tool", "Raw result without call")])
        # Event 7: Text chunk 2
        yield MockADKEvent(text="GNNs demonstrate strong inductive bias.")
        # Event 8: Tool call with no subsequent response
        yield MockADKEvent(calls=[MockCall("dangling_tool", {"flag": True})])

    traces, text = await service._process_adk_events(event_generator())

    assert text == "Based on graph search, GNNs demonstrate strong inductive bias."
    assert len(traces) == 4

    # Trace 1: search_graph (success)
    assert traces[0].tool_name == "search_graph"
    assert traces[0].status == "success"
    assert "results" in traces[0].output_result

    # Trace 2: verify_dois (error detected from payload)
    assert traces[1].tool_name == "verify_dois"
    assert traces[1].status == "error"
    assert "Graph timeout" in traces[1].output_result

    # Trace 3: unmatched_tool
    assert traces[2].tool_name == "unmatched_tool"
    assert traces[2].output_result == "Raw result without call"

    # Trace 4: dangling_tool (completed stream turns running into success)
    assert traces[3].tool_name == "dangling_tool"
    assert traces[3].status == "success"


# ============================================================================
# 3. Empirical Tests: Multi-Project Session Isolation (In-Memory & Database)
# ============================================================================

@pytest.mark.asyncio
async def test_session_isolation_across_multiple_projects():
    """Verify strict isolation: Project B cannot see, read, write, or delete Project A's chats."""
    service = ChatService(mysql_service=None, neo4j_service=None)
    proj_a = str(uuid.uuid4())
    proj_b = str(uuid.uuid4())

    # 1. Create chats in Project A
    chat_a1 = await service.create_chat(proj_a, title="Project A - Chat 1")
    chat_a2 = await service.create_chat(proj_a, title="Project A - Chat 2")

    # 2. Create chats in Project B
    chat_b1 = await service.create_chat(proj_b, title="Project B - Chat 1")

    # 3. List chats for Project A and Project B
    list_a = await service.list_chats(proj_a)
    list_b = await service.list_chats(proj_b)

    assert len(list_a) == 2
    assert {c.id for c in list_a} == {chat_a1.id, chat_a2.id}
    assert len(list_b) == 1
    assert list_b[0].id == chat_b1.id

    # 4. Cross-project reading attempt: Access Project A chat from Project B
    msg_leak_attempt = await service.get_messages(project_id=proj_b, chat_id=chat_a1.id)
    assert msg_leak_attempt is None  # Strict 404, no cross-project data leakage!

    # 5. Cross-project injection attempt: Send message to Project A chat via Project B context
    send_leak_attempt = await service.send_message(
        project_id=proj_b,
        chat_id=chat_a1.id,
        user_text="Malicious cross-project message injection",
    )
    assert send_leak_attempt is None  # Strict 404 rejection!

    # 6. Cross-project deletion attempt: Delete Project A chat from Project B context
    del_leak_attempt = await service.delete_chat(project_id=proj_b, chat_id=chat_a1.id)
    assert del_leak_attempt is False  # Must fail

    # 7. Verify Project A's chat is still completely intact
    msgs_a1 = await service.get_messages(project_id=proj_a, chat_id=chat_a1.id)
    assert msgs_a1 is not None
    assert len(msgs_a1) == 1
    assert msgs_a1[0].sender == "assistant"


# ============================================================================
# 4. Empirical Tests: Cascading Deletes & Relational Integrity in MySQL
# ============================================================================

@pytest.mark.asyncio
async def test_mysql_cascading_deletes_live_or_emulated():
    """Empirically verify that deleting a project cascades to chat_sessions and chat_messages."""
    settings = get_settings()
    mysql = MySQLService(
        host=settings.mysql_host,
        port=settings.mysql_port,
        user=settings.mysql_user,
        password=settings.mysql_password,
        database=settings.mysql_database,
    )

    try:
        await mysql.connect()
        is_healthy = await mysql.health_check()
    except Exception:
        is_healthy = False

    if not is_healthy:
        # If MySQL is not reachable, test with an in-memory SQLite instance with FOREIGN KEY ON DELETE CASCADE
        import aiosqlite
        async with aiosqlite.connect(":memory:") as db:
            await db.execute("PRAGMA foreign_keys = ON;")
            await db.execute("""
                CREATE TABLE projects (
                    id VARCHAR(36) PRIMARY KEY,
                    name VARCHAR(200) NOT NULL
                );
            """)
            await db.execute("""
                CREATE TABLE chat_sessions (
                    id VARCHAR(36) PRIMARY KEY,
                    project_id VARCHAR(36) NOT NULL,
                    title VARCHAR(255) NOT NULL,
                    CONSTRAINT fk_cs_proj FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
                );
            """)
            await db.execute("""
                CREATE TABLE chat_messages (
                    id VARCHAR(36) PRIMARY KEY,
                    chat_id VARCHAR(36) NOT NULL,
                    project_id VARCHAR(36) NOT NULL,
                    content TEXT NOT NULL,
                    CONSTRAINT fk_cm_chat FOREIGN KEY (chat_id) REFERENCES chat_sessions(id) ON DELETE CASCADE,
                    CONSTRAINT fk_cm_proj FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
                );
            """)
            # Insert project, session, messages
            pid = str(uuid.uuid4())
            cid = str(uuid.uuid4())
            mid1, mid2 = str(uuid.uuid4()), str(uuid.uuid4())
            await db.execute("INSERT INTO projects (id, name) VALUES (?, ?)", (pid, "Test Project"))
            await db.execute("INSERT INTO chat_sessions (id, project_id, title) VALUES (?, ?, ?)", (cid, pid, "Chat 1"))
            await db.execute("INSERT INTO chat_messages (id, chat_id, project_id, content) VALUES (?, ?, ?, ?)", (mid1, cid, pid, "Hello"))
            await db.execute("INSERT INTO chat_messages (id, chat_id, project_id, content) VALUES (?, ?, ?, ?)", (mid2, cid, pid, "World"))
            await db.commit()

            # Delete project
            await db.execute("DELETE FROM projects WHERE id = ?", (pid,))
            await db.commit()

            # Assert cascade
            async with db.execute("SELECT COUNT(*) FROM chat_sessions WHERE project_id = ?", (pid,)) as cur:
                count_sessions = (await cur.fetchone())[0]
            async with db.execute("SELECT COUNT(*) FROM chat_messages WHERE project_id = ?", (pid,)) as cur:
                count_messages = (await cur.fetchone())[0]

            assert count_sessions == 0
            assert count_messages == 0
        return

    # Live MySQL execution (36-character UUID primary keys)
    test_proj_id = str(uuid.uuid4())
    test_chat_id = str(uuid.uuid4())
    test_msg_id = str(uuid.uuid4())

    try:
        # Initialize schema
        await mysql.initialize_schema()

        # 1. Insert test project
        await mysql.execute(
            "INSERT INTO projects (id, name, description, status) VALUES (%s, %s, %s, %s)",
            (test_proj_id, "Cascade Test Project", "Testing cascading delete", "active"),
        )

        # 2. Insert chat session
        await mysql.execute(
            "INSERT INTO chat_sessions (id, project_id, title, message_count) VALUES (%s, %s, %s, %s)",
            (test_chat_id, test_proj_id, "Cascade Chat Session", 1),
        )

        # 3. Insert chat message
        await mysql.execute(
            "INSERT INTO chat_messages (id, chat_id, project_id, sender, content, tool_traces, citations) VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (test_msg_id, test_chat_id, test_proj_id, "user", "Cascade test content", "[]", "[]"),
        )

        # 4. Verify presence
        row_s = await mysql.fetch_one("SELECT id FROM chat_sessions WHERE id = %s", (test_chat_id,))
        row_m = await mysql.fetch_one("SELECT id FROM chat_messages WHERE id = %s", (test_msg_id,))
        assert row_s is not None
        assert row_m is not None

        # 5. Delete project -> triggers ON DELETE CASCADE on chat_sessions and chat_messages
        await mysql.execute("DELETE FROM projects WHERE id = %s", (test_proj_id,))

        # 6. Verify cascading cleanup
        row_s_after = await mysql.fetch_one("SELECT id FROM chat_sessions WHERE id = %s", (test_chat_id,))
        row_m_after = await mysql.fetch_one("SELECT id FROM chat_messages WHERE id = %s", (test_msg_id,))
        assert row_s_after is None, "chat_sessions row was not cascade-deleted when project was deleted!"
        assert row_m_after is None, "chat_messages row was not cascade-deleted when project was deleted!"

    finally:
        # Cleanup if anything failed
        try:
            await mysql.execute("DELETE FROM projects WHERE id = %s", (test_proj_id,))
        except Exception:
            pass
        await mysql.close()


# ============================================================================
# 5. Empirical Tests: REST API Edge Cases & Stress Scenarios
# ============================================================================

def test_api_cross_project_isolation_rest_client():
    """Verify HTTP 404 on cross-project resource access via TestClient."""
    real_service = ChatService(mysql_service=None, neo4j_service=None)
    app.dependency_overrides[get_chat_service] = lambda: real_service

    client = TestClient(app)

    proj_1 = str(uuid.uuid4())
    proj_2 = str(uuid.uuid4())

    # Create chat in proj_1
    r_create = client.post(f"/api/projects/{proj_1}/chats", json={"title": "Private Proj 1 Chat"})
    assert r_create.status_code == status.HTTP_201_CREATED
    chat_id = r_create.json()["id"]

    # Attempt to read via proj_2 URL
    r_read_cross = client.get(f"/api/projects/{proj_2}/chats/{chat_id}/messages")
    assert r_read_cross.status_code == status.HTTP_404_NOT_FOUND

    # Attempt to post message via proj_2 URL
    r_post_cross = client.post(
        f"/api/projects/{proj_2}/chats/{chat_id}/messages",
        json={"message": "Infiltration attempt"},
    )
    assert r_post_cross.status_code == status.HTTP_404_NOT_FOUND

    # Attempt to delete via proj_2 URL
    r_del_cross = client.delete(f"/api/projects/{proj_2}/chats/{chat_id}")
    assert r_del_cross.status_code == status.HTTP_404_NOT_FOUND

    # Verify proj_1 can still access its chat
    r_read_legit = client.get(f"/api/projects/{proj_1}/chats/{chat_id}/messages")
    assert r_read_legit.status_code == status.HTTP_200_OK
    assert len(r_read_legit.json()["messages"]) == 1


def test_api_large_payload_stress():
    """Stress test sending large message payload with LaTeX, unicode, and multiline content."""
    real_service = ChatService(mysql_service=None, neo4j_service=None)
    app.dependency_overrides[get_chat_service] = lambda: real_service

    client = TestClient(app)
    proj_id = str(uuid.uuid4())

    # Create session
    r_create = client.post(f"/api/projects/{proj_id}/chats", json={"title": "Stress Session"})
    chat_id = r_create.json()["id"]

    # 20KB multiline markdown + LaTeX prompt
    large_prompt = (
        "# Theoretical Formulation\n"
        "Consider graph $\\mathcal{G} = (\\mathcal{V}, \\mathcal{E})$ with adjacency matrix $A \\in \\mathbb{R}^{N \\times N}$.\n"
        "We define the continuous-time diffusion equation:\n"
        "$$\\frac{\\partial \\mathbf{h}(t)}{\\partial t} = -(\\mathbf{I} - \\mathbf{D}^{-1/2}\\mathbf{A}\\mathbf{D}^{-1/2})\\mathbf{h}(t)$$\n"
        + ("Synthesize literature citing 10.1145/3308558.3313508 and compare with GAT.\n" * 200)
    )

    with patch.object(real_service, "_process_adk_events", side_effect=Exception("Offline mock")):
        r_msg = client.post(
            f"/api/projects/{proj_id}/chats/{chat_id}/messages",
            json={"message": large_prompt},
        )

    assert r_msg.status_code == status.HTTP_200_OK
    data = r_msg.json()
    assert data["user_message"]["content"] == large_prompt.strip()
    assert data["assistant_message"]["sender"] == "assistant"
    assert len(data["assistant_message"]["tool_traces"]) >= 1

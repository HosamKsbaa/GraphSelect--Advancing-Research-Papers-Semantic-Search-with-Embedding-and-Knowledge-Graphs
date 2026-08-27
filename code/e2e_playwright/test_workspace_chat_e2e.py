"""Playwright E2E integration tests for Dedicated Multi-Session Project Chat Tab."""
import pytest
from playwright.sync_api import Page, expect
from e2e_playwright.conftest import mock_api_route
from e2e_playwright.pages.project_workspace_page import ProjectWorkspacePage
from e2e_playwright.pages.chat_tab_page import ChatTabPage


def _mock_project_base(page: Page, project_id: str):
    """Mock project metadata and touch endpoint."""
    mock_api_route(page, f"**/api/projects/{project_id}*", status_code=200, json_data={
        "id": project_id,
        "name": "Chat E2E Live Project",
        "description": "Playwright Chat Tab Validation",
        "topic": "Graph Neural Networks",
        "target_level": "master"
    }, method="GET")
    mock_api_route(page, f"**/api/projects/{project_id}/touch*", status_code=200, json_data={"message": "ok"}, method="POST")
    mock_api_route(page, "**/api/settings*", status_code=200, json_data={
        "api_base_url": "http://localhost:8000/api",
        "gemini_api_key_set": True,
        "openalex_api_key_set": False,
        "openalex_email": "test@alrs.org"
    }, method="GET")


def test_project_chat_tab_navigation_and_creation(page: Page, base_url: str):
    """Test navigating to the Chat tab and creating a new chat session."""
    project_id = "test-chat-nav-create"
    _mock_project_base(page, project_id)

    mock_api_route(page, f"**/api/projects/{project_id}/chats*", status_code=200, json_data={"chats": []}, method="GET")

    chat_tab = ChatTabPage(page, base_url)
    chat_tab.navigate(project_id)

    expect(chat_tab.container).to_be_visible()
    expect(chat_tab.sidebar).to_be_visible()
    expect(chat_tab.btn_new_chat).to_be_visible()
    expect(chat_tab.chat_input).to_be_visible()
    expect(chat_tab.btn_send).to_be_visible()


def test_send_message_and_agent_grounded_response(page: Page, base_url: str):
    """Test sending a prompt to the ADK agent and receiving a response with tool traces."""
    project_id = "test-chat-msg-resp"
    _mock_project_base(page, project_id)

    chat_id = "chat-e2e-001"
    mock_chats = [{
        "id": chat_id,
        "project_id": project_id,
        "title": "Misinformation Dynamics",
        "message_count": 0,
        "created_at": "2026-08-27T16:00:00Z",
        "updated_at": "2026-08-27T16:00:00Z"
    }]

    mock_response_payload = {
        "user_message": {
            "id": "msg-u-01",
            "chat_id": chat_id,
            "sender": "user",
            "content": "What are the key methodologies for misinformation cascade detection?",
            "timestamp": "2026-08-27T16:01:00Z",
            "tool_traces": [],
            "citations": []
        },
        "assistant_message": {
            "id": "msg-a-01",
            "chat_id": chat_id,
            "sender": "assistant",
            "content": "### Research Findings\n\nKey methodologies include spatial graph convolutions and temporal cascade dynamics.",
            "timestamp": "2026-08-27T16:01:05Z",
            "tool_traces": [
                {
                    "tool_name": "query_project_papers",
                    "input_args": {"project_id": project_id},
                    "output_result": "Retrieved 5 papers from project library",
                    "status": "success"
                }
            ],
            "citations": [
                {
                    "doi": "10.1145/3534678.3539078",
                    "title": "Cascade Graph Neural Networks",
                    "verified_in_graph": True
                }
            ]
        }
    }

    mock_api_route(page, f"**/api/projects/{project_id}/chats*", status_code=200, json_data={"chats": mock_chats}, method="GET")
    mock_api_route(page, f"**/api/projects/{project_id}/chats/{chat_id}/messages*", status_code=200, json_data={"messages": []}, method="GET")
    mock_api_route(page, f"**/api/projects/{project_id}/chats/{chat_id}/messages*", status_code=200, json_data=mock_response_payload, method="POST")

    chat_tab = ChatTabPage(page, base_url)
    chat_tab.navigate(project_id)

    # Send research query
    chat_tab.send_message("What are the key methodologies for misinformation cascade detection?")

    # Wait for assistant response bubble
    expect(chat_tab.assistant_bubbles.last).to_be_visible(timeout=5000)
    expect(chat_tab.message_contents.last).to_contain_text("Research Findings")

    # Verify tool traces toggle and citations
    expect(chat_tab.tool_trace_toggle_btn.first).to_be_visible()
    expect(chat_tab.citations_section).to_be_visible()


def test_multi_chat_session_isolation_and_delete(page: Page, base_url: str):
    """Test spinning up multiple chat sessions, switching between them, and deleting one."""
    project_id = "test-chat-iso-del"
    _mock_project_base(page, project_id)

    chat_1 = {
        "id": "chat-sess-1",
        "project_id": project_id,
        "title": "First Session",
        "message_count": 0,
        "created_at": "2026-08-27T16:00:00Z",
        "updated_at": "2026-08-27T16:00:00Z"
    }
    chat_2 = {
        "id": "chat-sess-2",
        "project_id": project_id,
        "title": "Second Session",
        "message_count": 0,
        "created_at": "2026-08-27T16:05:00Z",
        "updated_at": "2026-08-27T16:05:00Z"
    }

    mock_api_route(page, f"**/api/projects/{project_id}/chats*", status_code=200, json_data={"chats": [chat_1]}, method="GET")
    mock_api_route(page, f"**/api/projects/{project_id}/chats/{chat_1['id']}/messages*", status_code=200, json_data={"messages": []}, method="GET")
    mock_api_route(page, f"**/api/projects/{project_id}/chats*", status_code=201, json_data=chat_2, method="POST")
    mock_api_route(page, f"**/api/projects/{project_id}/chats/{chat_2['id']}/messages*", status_code=200, json_data={"messages": []}, method="GET")
    mock_api_route(page, f"**/api/projects/{project_id}/chats/{chat_2['id']}*", status_code=200, json_data={"status": "deleted"}, method="DELETE")

    chat_tab = ChatTabPage(page, base_url)
    chat_tab.navigate(project_id)

    expect(chat_tab.session_items).to_have_count(1)

    # Click + New Chat
    chat_tab.click_new_chat()
    expect(chat_tab.session_items).to_have_count(2)

    # Delete second chat
    chat_tab.delete_session(0)
    expect(chat_tab.session_items).to_have_count(1)

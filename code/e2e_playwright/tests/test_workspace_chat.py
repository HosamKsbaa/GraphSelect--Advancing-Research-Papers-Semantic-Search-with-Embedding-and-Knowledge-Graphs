"""Comprehensive Playwright E2E tests for Workspace Chat Tab (Requirement R1, R2, R3, R4).

Covers all 10 required E2E scenarios from TEST_INFRA.md:
1. test_navigate_to_chat_tab
2. test_create_new_chat_session
3. test_send_user_message_and_receive_response
4. test_assistant_response_markdown_rendering
5. test_expandable_tool_traces
6. test_grounded_citations_display
7. test_session_switching_and_isolation
8. test_delete_chat_session
9. test_quick_prompt_chips
10. test_keyboard_actions_enter_and_shift_enter
"""
import sys
import os
import uuid
import pytest
from playwright.sync_api import Page, expect

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from e2e_playwright.conftest import mock_api_route
from e2e_playwright.pages.project_workspace_page import ProjectWorkspacePage
from e2e_playwright.pages.chat_tab_page import ChatTabPage


def _mock_project_base(page: Page, project_id: str, name: str = "Chat E2E Project"):
    """Helper to mock baseline project metadata, touch endpoint, and settings."""
    mock_api_route(page, f"**/api/projects/{project_id}*", status_code=200, json_data={
        "id": project_id,
        "name": name,
        "description": "Automated Playwright Chat Tab Test Project",
        "topic": "Graph Neural Networks & Misinformation Detection",
        "target_level": "master"
    }, method="GET")
    mock_api_route(page, f"**/api/projects/{project_id}/touch*", status_code=200, json_data={"message": "ok"}, method="POST")
    mock_api_route(page, "**/api/settings*", status_code=200, json_data={
        "api_base_url": "http://localhost:8000/api",
        "gemini_api_key_set": True,
        "openalex_api_key_set": False,
        "openalex_email": "test@alrs.org"
    }, method="GET")


# ===========================================================================
# 1. Navigation to Chat Tab & Deep Linking
# ===========================================================================

def test_navigate_to_chat_tab(page: Page, base_url: str):
    """Test navigating to the Chat tab via workspace navigation and direct URL deep link."""
    project_id = "test-chat-proj-nav"
    _mock_project_base(page, project_id)

    mock_api_route(page, f"**/api/projects/{project_id}/chats*", status_code=200, json_data={"chats": []}, method="GET")
    mock_api_route(page, f"**/api/research/{project_id}/questions*", status_code=200, json_data={"questions": []}, method="GET")
    mock_api_route(page, f"**/api/analysis/{project_id}/ranked-papers*", status_code=200, json_data={"ranked_papers": []}, method="GET")

    workspace = ProjectWorkspacePage(page, base_url)
    workspace.navigate(project_id, tab="research")

    # Verify Chat Tab link exists in workspace navigation
    expect(workspace.tab_chat).to_be_visible(timeout=5000)

    # Click Chat Tab via POM helper
    chat_tab = workspace.navigate_to_chat()
    page.wait_for_url(f"**/projects/{project_id}/chat", timeout=5000)

    # Verify Chat Tab Container elements
    expect(chat_tab.container).to_be_visible()
    expect(chat_tab.sidebar).to_be_visible()
    expect(chat_tab.main_pane).to_be_visible()
    expect(chat_tab.btn_new_chat).to_be_visible()
    expect(chat_tab.chat_input).to_be_visible()
    expect(chat_tab.btn_send).to_be_visible()

    # Direct Deep Link Navigation
    chat_tab.navigate(project_id)
    expect(chat_tab.container).to_be_visible()
    expect(page).to_have_url(f"{base_url}/projects/{project_id}/chat")


def test_chat_tab_switching_across_workspace_tabs(page: Page, base_url: str):
    """Test tab switching between Research, Writing, and Chat tabs without regressions."""
    project_id = "test-chat-proj-switch"
    _mock_project_base(page, project_id)

    mock_api_route(page, f"**/api/projects/{project_id}/chats*", status_code=200, json_data={"chats": []}, method="GET")
    mock_api_route(page, f"**/api/research/{project_id}/questions*", status_code=200, json_data={"questions": []}, method="GET")
    mock_api_route(page, f"**/api/analysis/{project_id}/ranked-papers*", status_code=200, json_data={"ranked_papers": []}, method="GET")
    mock_api_route(page, f"**/api/research/{project_id}/top-authors*", status_code=200, json_data={"authors": []}, method="GET")
    mock_api_route(page, f"**/api/research/{project_id}/top-venues*", status_code=200, json_data={"venues": []}, method="GET")
    mock_api_route(page, f"**/api/planning/{project_id}/outline*", status_code=200, json_data={"project_id": project_id, "sections": []}, method="GET")

    workspace = ProjectWorkspacePage(page, base_url)
    workspace.navigate(project_id, tab="research")

    # Navigate to Writing
    workspace.tab_writing.click()
    page.wait_for_url(f"**/projects/{project_id}/writing", timeout=5000)
    expect(page.locator(".writing-tab-container")).to_be_visible()

    # Switch to Chat
    workspace.tab_chat.click()
    page.wait_for_url(f"**/projects/{project_id}/chat", timeout=5000)
    chat_tab = ChatTabPage(page, base_url)
    expect(chat_tab.container).to_be_visible()

    # Switch back to Research
    workspace.tab_research.click()
    page.wait_for_url(f"**/projects/{project_id}/research", timeout=5000)
    expect(page.locator(".research-workspace")).to_be_visible()


# ===========================================================================
# 2. Create Chat Session
# ===========================================================================

def test_create_new_chat_session(page: Page, base_url: str):
    """Test empty state display and creating new chat threads from sidebar."""
    project_id = "test-chat-proj-create"
    _mock_project_base(page, project_id)

    # Initial empty chats list
    mock_api_route(page, f"**/api/projects/{project_id}/chats*", status_code=200, json_data={"chats": []}, method="GET")

    chat_tab = ChatTabPage(page, base_url)
    chat_tab.navigate(project_id)

    # Verify empty state
    expect(chat_tab.empty_chats_state).to_be_visible()
    expect(chat_tab.empty_chats_state).to_contain_text("No chat threads yet.")
    expect(chat_tab.btn_start_first_chat).to_be_visible()

    # Mock chat session creation response (POST)
    new_chat_1 = {
        "id": "chat-session-001",
        "project_id": project_id,
        "title": "Research Discussion #1",
        "message_count": 0,
        "created_at": "2026-08-27T16:00:00Z",
        "updated_at": "2026-08-27T16:00:00Z"
    }

    mock_api_route(page, f"**/api/projects/{project_id}/chats*", status_code=201, json_data=new_chat_1, method="POST")
    mock_api_route(page, f"**/api/projects/{project_id}/chats/{new_chat_1['id']}/messages*", status_code=200, json_data={"messages": []}, method="GET")

    # Click "+ Start First Chat"
    chat_tab.click_start_first_chat()

    # Verify session item in sidebar
    expect(chat_tab.session_items).to_have_count(1)
    expect(chat_tab.session_titles.first).to_have_text("Research Discussion #1")
    expect(chat_tab.session_items.first).to_have_class("chat-session-item active")
    expect(chat_tab.active_title).to_have_text("Research Discussion #1")

    # Create second session via "+ New Chat" button
    new_chat_2 = {
        "id": "chat-session-002",
        "project_id": project_id,
        "title": "Methodology Comparison",
        "message_count": 0,
        "created_at": "2026-08-27T16:05:00Z",
        "updated_at": "2026-08-27T16:05:00Z"
    }
    mock_api_route(page, f"**/api/projects/{project_id}/chats*", status_code=201, json_data=new_chat_2, method="POST")
    mock_api_route(page, f"**/api/projects/{project_id}/chats/{new_chat_2['id']}/messages*", status_code=200, json_data={"messages": []}, method="GET")

    chat_tab.create_new_chat()

    # Verify both sessions listed
    expect(chat_tab.session_items).to_have_count(2)
    expect(chat_tab.active_title).to_have_text("Methodology Comparison")


# ===========================================================================
# 3. Send User Message & Receive Response
# ===========================================================================

def test_send_user_message_and_receive_response(page: Page, base_url: str):
    """Test sending a message, immediate optimistic rendering, input clearing, and response."""
    project_id = "test-chat-proj-send"
    _mock_project_base(page, project_id)

    chat_id = "chat-send-01"
    mock_chats = [{
        "id": chat_id,
        "project_id": project_id,
        "title": "Misinformation Dynamics",
        "message_count": 0,
        "created_at": "2026-08-27T16:00:00Z",
        "updated_at": "2026-08-27T16:00:00Z"
    }]

    mock_api_route(page, f"**/api/projects/{project_id}/chats*", status_code=200, json_data={"chats": mock_chats}, method="GET")
    mock_api_route(page, f"**/api/projects/{project_id}/chats/{chat_id}/messages*", status_code=200, json_data={"messages": []}, method="GET")

    chat_tab = ChatTabPage(page, base_url)
    chat_tab.navigate(project_id)

    # Prepare user query & assistant response
    user_query = "What graph convolutional models are best suited for heterophilic cascade networks?"
    mock_response_payload = {
        "user_message": {
            "id": "msg-user-1",
            "chat_id": chat_id,
            "sender": "user",
            "content": user_query,
            "timestamp": "2026-08-27T16:01:00Z",
            "tool_traces": [],
            "citations": []
        },
        "assistant_message": {
            "id": "msg-asst-1",
            "chat_id": chat_id,
            "sender": "assistant",
            "content": "For heterophilic networks, **FAGCN** and **H2GCN** decouple feature transformation from graph propagation.",
            "timestamp": "2026-08-27T16:01:05Z",
            "tool_traces": [],
            "citations": []
        }
    }

    mock_api_route(page, f"**/api/projects/{project_id}/chats/{chat_id}/messages*", status_code=200, json_data=mock_response_payload, method="POST")

    # Send message using POM helper
    chat_tab.send_message(user_query)

    # Input should be cleared
    expect(chat_tab.chat_input).to_have_value("")

    # Verify User Message Bubble rendered
    expect(chat_tab.user_bubbles).to_have_count(1)
    expect(chat_tab.user_bubbles.first).to_contain_text("heterophilic cascade networks")

    # Verify Assistant Message Bubble rendered
    expect(chat_tab.assistant_bubbles).to_have_count(1)
    expect(chat_tab.assistant_bubbles.first).to_contain_text("FAGCN")


# ===========================================================================
# 4. Assistant Response Markdown Rendering
# ===========================================================================

def test_assistant_response_markdown_rendering(page: Page, base_url: str):
    """Test assistant response rendering with markdown headers, lists, code blocks, and LaTeX citations."""
    project_id = "test-chat-proj-md"
    _mock_project_base(page, project_id)

    chat_id = "chat-md-01"
    mock_chats = [{
        "id": chat_id,
        "project_id": project_id,
        "title": "Literature Synthesis",
        "message_count": 2,
        "created_at": "2026-08-27T16:00:00Z",
        "updated_at": "2026-08-27T16:00:00Z"
    }]

    markdown_content = """### Graph Neural Networks for Cascade Analysis

Key methodologies include:
- **Spatial Convolutions**: Local neighborhood aggregation $\\mathcal{N}(v)$.
- **Spectral Filters**: Truncated Chebyshev polynomials $\\mathbf{L} = \\mathbf{I} - \\mathbf{D}^{-1/2}\\mathbf{A}\\mathbf{D}^{-1/2}$.

```python
import torch
import torch_geometric.nn as pyg_nn
conv = pyg_nn.GCNConv(in_channels=128, out_channels=64)
```

Refer to baseline findings in \\cite{10.1145/3534678.3539078}.
"""

    mock_messages = [
        {
            "id": "msg-1",
            "chat_id": chat_id,
            "sender": "user",
            "content": "Summarize GNN convolutions for graphs.",
            "timestamp": "2026-08-27T16:00:10Z",
            "tool_traces": [],
            "citations": []
        },
        {
            "id": "msg-2",
            "chat_id": chat_id,
            "sender": "assistant",
            "content": markdown_content,
            "timestamp": "2026-08-27T16:00:15Z",
            "tool_traces": [],
            "citations": []
        }
    ]

    mock_api_route(page, f"**/api/projects/{project_id}/chats*", status_code=200, json_data={"chats": mock_chats}, method="GET")
    mock_api_route(page, f"**/api/projects/{project_id}/chats/{chat_id}/messages*", status_code=200, json_data={"messages": mock_messages}, method="GET")

    chat_tab = ChatTabPage(page, base_url)
    chat_tab.navigate(project_id)

    # Verify Markdown Preview is rendered in assistant bubble
    assistant_preview = chat_tab.assistant_bubbles.locator("app-markdown-preview")
    expect(assistant_preview).to_be_visible()
    expect(assistant_preview).to_contain_text("Graph Neural Networks for Cascade Analysis")
    expect(assistant_preview).to_contain_text("Spatial Convolutions")
    expect(assistant_preview).to_contain_text("import torch_geometric.nn as pyg_nn")


# ===========================================================================
# 5. Expandable Tool Traces
# ===========================================================================

def test_expandable_tool_traces(page: Page, base_url: str):
    """Test collapsible / expandable tool execution traces inside assistant messages."""
    project_id = "test-chat-proj-tools"
    _mock_project_base(page, project_id)

    chat_id = "chat-tool-01"
    mock_chats = [{
        "id": chat_id,
        "project_id": project_id,
        "title": "Neo4j Knowledge Graph Grounding",
        "message_count": 1,
        "created_at": "2026-08-27T16:00:00Z",
        "updated_at": "2026-08-27T16:00:00Z"
    }]

    mock_messages = [
        {
            "id": "msg-tool-1",
            "chat_id": chat_id,
            "sender": "assistant",
            "content": "I verified 3 relevant papers and conflicting polarity claims in your project graph.",
            "timestamp": "2026-08-27T16:00:15Z",
            "tool_traces": [
                {
                    "tool_name": "query_project_papers",
                    "input_args": {"project_id": project_id},
                    "output_result": "Retrieved 8 papers from project library (DOIs: 10.1145/1, 10.1145/2)",
                    "status": "success"
                },
                {
                    "tool_name": "extract_claim_polarities",
                    "input_args": {"topic": "Oversmoothing"},
                    "output_result": "Identified 2 conflicting claims on Dirichlet energy decay rates",
                    "status": "success"
                }
            ],
            "citations": []
        }
    ]

    mock_api_route(page, f"**/api/projects/{project_id}/chats*", status_code=200, json_data={"chats": mock_chats}, method="GET")
    mock_api_route(page, f"**/api/projects/{project_id}/chats/{chat_id}/messages*", status_code=200, json_data={"messages": mock_messages}, method="GET")

    chat_tab = ChatTabPage(page, base_url)
    chat_tab.navigate(project_id)

    # Verify tool traces toggle button is visible
    expect(chat_tab.tool_trace_toggle).to_be_visible()
    expect(chat_tab.tool_trace_toggle).to_contain_text("2 Tool Actions Executed")
    expect(chat_tab.tool_trace_toggle).to_contain_text("▼")

    # Details initially collapsed
    expect(chat_tab.tool_trace_details).not_to_be_visible()

    # Click toggle to expand
    chat_tab.toggle_tool_trace(0)
    expect(chat_tab.tool_trace_details).to_be_visible()
    expect(chat_tab.tool_trace_toggle).to_contain_text("▲")

    # Verify tool trace cards content
    expect(chat_tab.tool_trace_cards).to_have_count(2)
    expect(chat_tab.tool_trace_cards.nth(0)).to_contain_text("query_project_papers")
    expect(chat_tab.tool_trace_cards.nth(0)).to_contain_text("Retrieved 8 papers from project library")
    expect(chat_tab.tool_trace_cards.nth(1)).to_contain_text("extract_claim_polarities")
    expect(chat_tab.tool_trace_cards.nth(1)).to_contain_text("Dirichlet energy decay rates")

    # Click toggle again to collapse
    chat_tab.toggle_tool_trace(0)
    expect(chat_tab.tool_trace_details).not_to_be_visible()
    expect(chat_tab.tool_trace_toggle).to_contain_text("▼")


# ===========================================================================
# 6. Grounded Citations Display
# ===========================================================================

def test_grounded_citations_display(page: Page, base_url: str):
    """Test verified DOI citation badges rendered on assistant messages."""
    project_id = "test-chat-proj-citations"
    _mock_project_base(page, project_id)

    chat_id = "chat-cite-01"
    mock_chats = [{
        "id": chat_id,
        "project_id": project_id,
        "title": "Citation Grounding Check",
        "message_count": 1,
        "created_at": "2026-08-27T16:00:00Z",
        "updated_at": "2026-08-27T16:00:00Z"
    }]

    mock_messages = [
        {
            "id": "msg-cite-1",
            "chat_id": chat_id,
            "sender": "assistant",
            "content": "Graph Attention Networks (GAT) address dynamic edge weighting.",
            "timestamp": "2026-08-27T16:00:15Z",
            "tool_traces": [],
            "citations": [
                {
                    "doi": "10.1145/3534678.3539078",
                    "title": "Attention-Driven Misinformation Detection in Hypergraphs",
                    "authors": ["Author A", "Author B"],
                    "year": 2024,
                    "verified_in_graph": True
                },
                {
                    "doi": "10.1145/3394486.3403067",
                    "title": "Weisfeiler-Lehman Graph Isomorphism Limits",
                    "authors": ["Author C"],
                    "year": 2023,
                    "verified_in_graph": True
                }
            ]
        }
    ]

    mock_api_route(page, f"**/api/projects/{project_id}/chats*", status_code=200, json_data={"chats": mock_chats}, method="GET")
    mock_api_route(page, f"**/api/projects/{project_id}/chats/{chat_id}/messages*", status_code=200, json_data={"messages": mock_messages}, method="GET")

    chat_tab = ChatTabPage(page, base_url)
    chat_tab.navigate(project_id)

    # Verify Citations section
    expect(chat_tab.citations_section).to_be_visible()
    expect(chat_tab.citations_section).to_contain_text("Verified Graph Citations:")

    # Verify citation tags
    expect(chat_tab.citation_tags).to_have_count(2)
    expect(chat_tab.citation_tags.nth(0)).to_contain_text("10.1145/3534678.3539078")
    expect(chat_tab.citation_tags.nth(0)).to_have_attribute("title", "Attention-Driven Misinformation Detection in Hypergraphs")
    expect(chat_tab.citation_tags.nth(1)).to_contain_text("10.1145/3394486.3403067")

    # Verify citations helper
    citations = chat_tab.get_citations()
    assert len(citations) == 2
    assert any("10.1145/3534678.3539078" in c for c in citations)


# ===========================================================================
# 7. Session Switching & Isolation
# ===========================================================================

def test_session_switching_and_isolation(page: Page, base_url: str):
    """Test switching between multiple threads and confirming zero message cross-contamination."""
    project_id = "test-chat-proj-iso"
    _mock_project_base(page, project_id)

    chat_1_id = "chat-thread-alpha"
    chat_2_id = "chat-thread-beta"

    mock_chats = [
        {
            "id": chat_1_id,
            "project_id": project_id,
            "title": "Thread Alpha: Spectral GNNs",
            "message_count": 1,
            "created_at": "2026-08-27T16:00:00Z",
            "updated_at": "2026-08-27T16:00:00Z"
        },
        {
            "id": chat_2_id,
            "project_id": project_id,
            "title": "Thread Beta: Polarity Gap Analysis",
            "message_count": 1,
            "created_at": "2026-08-27T16:05:00Z",
            "updated_at": "2026-08-27T16:05:00Z"
        }
    ]

    messages_chat_1 = [
        {
            "id": "m1-alpha",
            "chat_id": chat_1_id,
            "sender": "assistant",
            "content": "ALPHA_EXCLUSIVE_CONTENT: Analyzing spectral Chebyshev polynomials.",
            "timestamp": "2026-08-27T16:00:10Z",
            "tool_traces": [],
            "citations": []
        }
    ]

    messages_chat_2 = [
        {
            "id": "m1-beta",
            "chat_id": chat_2_id,
            "sender": "assistant",
            "content": "BETA_EXCLUSIVE_CONTENT: Identifying open research gaps in cascade graphs.",
            "timestamp": "2026-08-27T16:05:10Z",
            "tool_traces": [],
            "citations": []
        }
    ]

    mock_api_route(page, f"**/api/projects/{project_id}/chats*", status_code=200, json_data={"chats": mock_chats}, method="GET")
    mock_api_route(page, f"**/api/projects/{project_id}/chats/{chat_1_id}/messages*", status_code=200, json_data={"messages": messages_chat_1}, method="GET")
    mock_api_route(page, f"**/api/projects/{project_id}/chats/{chat_2_id}/messages*", status_code=200, json_data={"messages": messages_chat_2}, method="GET")

    chat_tab = ChatTabPage(page, base_url)
    chat_tab.navigate(project_id)

    # First chat selected by default
    expect(chat_tab.session_items.nth(0)).to_have_class("chat-session-item active")
    expect(chat_tab.active_title).to_have_text("Thread Alpha: Spectral GNNs")
    expect(chat_tab.assistant_bubbles.first).to_contain_text("ALPHA_EXCLUSIVE_CONTENT")
    expect(chat_tab.assistant_bubbles).not_to_contain_text("BETA_EXCLUSIVE_CONTENT")

    # Switch to Thread Beta via POM select_chat helper
    chat_tab.select_chat("Thread Beta")

    # Assert Thread Beta active and messages swapped
    expect(chat_tab.session_items.nth(1)).to_have_class("chat-session-item active")
    expect(chat_tab.active_title).to_have_text("Thread Beta: Polarity Gap Analysis")
    expect(chat_tab.assistant_bubbles.first).to_contain_text("BETA_EXCLUSIVE_CONTENT")
    expect(chat_tab.assistant_bubbles).not_to_contain_text("ALPHA_EXCLUSIVE_CONTENT")

    # Switch back to Thread Alpha
    chat_tab.select_chat(0)
    expect(chat_tab.session_items.nth(0)).to_have_class("chat-session-item active")
    expect(chat_tab.assistant_bubbles.first).to_contain_text("ALPHA_EXCLUSIVE_CONTENT")


# ===========================================================================
# 8. Delete Chat Session
# ===========================================================================

def test_delete_chat_session(page: Page, base_url: str):
    """Test deleting a chat thread and transitioning to empty state when all threads are deleted."""
    project_id = "test-chat-proj-del"
    _mock_project_base(page, project_id)

    chat_1 = {
        "id": "chat-del-1",
        "project_id": project_id,
        "title": "Chat To Delete",
        "message_count": 0,
        "created_at": "2026-08-27T16:00:00Z",
        "updated_at": "2026-08-27T16:00:00Z"
    }

    mock_api_route(page, f"**/api/projects/{project_id}/chats*", status_code=200, json_data={"chats": [chat_1]}, method="GET")
    mock_api_route(page, f"**/api/projects/{project_id}/chats/{chat_1['id']}/messages*", status_code=200, json_data={"messages": []}, method="GET")
    mock_api_route(page, f"**/api/projects/{project_id}/chats/{chat_1['id']}*", status_code=200, json_data={"status": "deleted", "message": "deleted"}, method="DELETE")

    chat_tab = ChatTabPage(page, base_url)
    chat_tab.navigate(project_id)

    expect(chat_tab.session_items).to_have_count(1)

    # Click delete button on session
    chat_tab.delete_chat(0)

    # Confirm session removed and empty state shown
    expect(chat_tab.session_items).to_have_count(0)
    expect(chat_tab.empty_chats_state).to_be_visible()
    expect(chat_tab.btn_start_first_chat).to_be_visible()


# ===========================================================================
# 9. Quick Prompt Chips
# ===========================================================================

def test_quick_prompt_chips(page: Page, base_url: str):
    """Test clicking quick prompt chips to populate input and send message."""
    project_id = "test-chat-proj-chips"
    _mock_project_base(page, project_id)

    chat_id = "chat-chips-01"
    mock_chats = [{
        "id": chat_id,
        "project_id": project_id,
        "title": "Chips Testing Session",
        "message_count": 0,
        "created_at": "2026-08-27T16:00:00Z",
        "updated_at": "2026-08-27T16:00:00Z"
    }]

    mock_api_route(page, f"**/api/projects/{project_id}/chats*", status_code=200, json_data={"chats": mock_chats}, method="GET")
    mock_api_route(page, f"**/api/projects/{project_id}/chats/{chat_id}/messages*", status_code=200, json_data={"messages": []}, method="GET")

    chat_tab = ChatTabPage(page, base_url)
    chat_tab.navigate(project_id)

    # Verify quick prompt chips are visible
    expect(chat_tab.quick_prompts_bar).to_be_visible()
    expect(chat_tab.quick_prompt_chips).to_have_count(4)
    expect(chat_tab.quick_prompt_chips.nth(0)).to_have_text("Summarize key literature gaps")
    expect(chat_tab.quick_prompt_chips.nth(1)).to_have_text("Extract conflicting claims & disputes")

    # Mock response for quick prompt chip
    mock_chip_response = {
        "user_message": {
            "id": "msg-chip-u",
            "chat_id": chat_id,
            "sender": "user",
            "content": "Summarize key literature gaps",
            "timestamp": "2026-08-27T16:01:00Z",
            "tool_traces": [],
            "citations": []
        },
        "assistant_message": {
            "id": "msg-chip-a",
            "chat_id": chat_id,
            "sender": "assistant",
            "content": "Identified 3 primary gaps in heterophilic cascade evaluation.",
            "timestamp": "2026-08-27T16:01:05Z",
            "tool_traces": [],
            "citations": []
        }
    }
    mock_api_route(page, f"**/api/projects/{project_id}/chats/{chat_id}/messages*", status_code=200, json_data=mock_chip_response, method="POST")

    # Click first chip "Summarize key literature gaps" using POM helper
    chat_tab.click_prompt_chip("Summarize key literature gaps")

    # Verify user message and assistant reply
    expect(chat_tab.user_bubbles.first).to_contain_text("Summarize key literature gaps")
    expect(chat_tab.assistant_bubbles.first).to_contain_text("Identified 3 primary gaps")


# ===========================================================================
# 10. Keyboard Actions (Enter & Shift+Enter)
# ===========================================================================

def test_keyboard_actions_enter_and_shift_enter(page: Page, base_url: str):
    """Test Enter sends message and Shift+Enter inserts newline without sending."""
    project_id = "test-chat-proj-kb"
    _mock_project_base(page, project_id)

    chat_id = "chat-kb-01"
    mock_chats = [{
        "id": chat_id,
        "project_id": project_id,
        "title": "Keyboard Shortcuts Session",
        "message_count": 0,
        "created_at": "2026-08-27T16:00:00Z",
        "updated_at": "2026-08-27T16:00:00Z"
    }]

    mock_api_route(page, f"**/api/projects/{project_id}/chats*", status_code=200, json_data={"chats": mock_chats}, method="GET")
    mock_api_route(page, f"**/api/projects/{project_id}/chats/{chat_id}/messages*", status_code=200, json_data={"messages": []}, method="GET")

    chat_tab = ChatTabPage(page, base_url)
    chat_tab.navigate(project_id)

    # 1. Empty input -> Send button is disabled
    expect(chat_tab.btn_send).to_be_disabled()

    # 2. Shift+Enter inserts a newline without triggering send
    chat_tab.chat_input.focus()
    chat_tab.chat_input.fill("Line 1 of prompt")
    page.keyboard.press("Shift+Enter")
    chat_tab.chat_input.type("Line 2 of prompt")

    # Assert input contains newline and no messages were sent
    expect(chat_tab.chat_input).to_have_value("Line 1 of prompt\nLine 2 of prompt")
    expect(chat_tab.message_rows).to_have_count(0)

    # 3. Enter key triggers message send
    mock_kb_response = {
        "user_message": {
            "id": "msg-kb-u",
            "chat_id": chat_id,
            "sender": "user",
            "content": "Line 1 of prompt\nLine 2 of prompt",
            "timestamp": "2026-08-27T16:01:00Z",
            "tool_traces": [],
            "citations": []
        },
        "assistant_message": {
            "id": "msg-kb-a",
            "chat_id": chat_id,
            "sender": "assistant",
            "content": "Multiline prompt received and processed.",
            "timestamp": "2026-08-27T16:01:05Z",
            "tool_traces": [],
            "citations": []
        }
    }
    mock_api_route(page, f"**/api/projects/{project_id}/chats/{chat_id}/messages*", status_code=200, json_data=mock_kb_response, method="POST")

    page.keyboard.press("Enter")

    # Verify message sent and rendered
    expect(chat_tab.user_bubbles).to_have_count(1)
    expect(chat_tab.user_bubbles.first).to_contain_text("Line 1 of prompt")
    expect(chat_tab.assistant_bubbles).to_have_count(1)
    expect(chat_tab.assistant_bubbles.first).to_contain_text("Multiline prompt received and processed.")
    expect(chat_tab.chat_input).to_have_value("")

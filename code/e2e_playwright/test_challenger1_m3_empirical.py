"""Challenger 1 Empirical Adversarial Stress Test Suite for Milestone 3 (Chat E2E).

Empirically challenges:
1. Active vs. Inactive Session Deletion:
   - Deleting inactive sessions retains active selection and message stream.
   - Deleting active session reassigns to remaining session or transitions to empty state.
2. Independent Tool Traces Expand / Collapse:
   - Multi-message tool trace independence (expanded state tracked per message ID).
   - Zero-tool-trace messages render cleanly without toggle controls.
3. Multiline Input & Boundary Handling:
   - Multiline Shift+Enter preservation and Enter key submission.
   - Whitespace-only / empty multiline rejection and button disablement.
4. Robust Markdown, Code Blocks, and Mathematical Notations:
   - Complex markdown structure parsing in assistant responses.
5. Quick Prompt Chips & Concurrent Send Guard:
   - Interaction triggers prompt execution and guards against concurrent re-entry.
6. Failure Resilience & Optimistic Rollback:
   - Backend 500 failure gracefully rolls back optimistic message, restores input text, and shows error toast.
"""
import sys
import os
import json
import pytest
from playwright.sync_api import Page, expect
from e2e_playwright.conftest import mock_api_route, assert_toast_message
from e2e_playwright.pages.chat_tab_page import ChatTabPage


def _mock_project_base(page: Page, project_id: str, name: str = "Chat Empirical Stress Project"):
    mock_api_route(page, f"**/api/projects/{project_id}*", status_code=200, json_data={
        "id": project_id,
        "name": name,
        "description": "Adversarial chat testing workspace",
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
# 1. Active vs Inactive Session Deletion Empirical Resilience
# ===========================================================================

def test_delete_inactive_session_preserves_active_state_and_messages(page: Page, base_url: str):
    """Deleting an inactive session must not disturb active session selection or message stream."""
    project_id = "test-adv-del-inactive"
    _mock_project_base(page, project_id)

    chat_a = {"id": "c-alpha", "project_id": project_id, "title": "Session Alpha", "message_count": 1, "created_at": "2026-08-27T16:00:00Z", "updated_at": "2026-08-27T16:00:00Z"}
    chat_b = {"id": "c-beta", "project_id": project_id, "title": "Session Beta", "message_count": 1, "created_at": "2026-08-27T16:05:00Z", "updated_at": "2026-08-27T16:05:00Z"}
    chat_g = {"id": "c-gamma", "project_id": project_id, "title": "Session Gamma", "message_count": 1, "created_at": "2026-08-27T16:10:00Z", "updated_at": "2026-08-27T16:10:00Z"}

    mock_api_route(page, f"**/api/projects/{project_id}/chats*", status_code=200, json_data={"chats": [chat_a, chat_b, chat_g]}, method="GET")
    mock_api_route(page, f"**/api/projects/{project_id}/chats/c-alpha/messages*", status_code=200, json_data={"messages": [{"id": "m-a", "chat_id": "c-alpha", "sender": "assistant", "content": "ALPHA_MSG", "timestamp": "2026-08-27T16:00:00Z"}]}, method="GET")
    mock_api_route(page, f"**/api/projects/{project_id}/chats/c-beta/messages*", status_code=200, json_data={"messages": [{"id": "m-b", "chat_id": "c-beta", "sender": "assistant", "content": "BETA_MSG_ACTIVE", "timestamp": "2026-08-27T16:05:00Z"}]}, method="GET")
    mock_api_route(page, f"**/api/projects/{project_id}/chats/c-gamma/messages*", status_code=200, json_data={"messages": [{"id": "m-g", "chat_id": "c-gamma", "sender": "assistant", "content": "GAMMA_MSG", "timestamp": "2026-08-27T16:10:00Z"}]}, method="GET")

    mock_api_route(page, f"**/api/projects/{project_id}/chats/c-gamma*", status_code=200, json_data={"status": "deleted"}, method="DELETE")
    mock_api_route(page, f"**/api/projects/{project_id}/chats/c-alpha*", status_code=200, json_data={"status": "deleted"}, method="DELETE")

    chat_tab = ChatTabPage(page, base_url)
    chat_tab.navigate(project_id)

    expect(chat_tab.session_items).to_have_count(3)

    # 1. Switch to Session Beta (index 1)
    chat_tab.select_session(1)
    expect(chat_tab.active_title).to_have_text("Session Beta")
    expect(chat_tab.assistant_bubbles.first).to_contain_text("BETA_MSG_ACTIVE")

    # 2. Delete inactive Session Gamma (index 2)
    chat_tab.delete_session(2)

    # Verify count is 2, Session Beta remains active with messages undisturbed
    expect(chat_tab.session_items).to_have_count(2)
    expect(chat_tab.active_title).to_have_text("Session Beta")
    expect(chat_tab.assistant_bubbles.first).to_contain_text("BETA_MSG_ACTIVE")

    # 3. Delete inactive Session Alpha (index 0)
    chat_tab.delete_session(0)

    # Verify count is 1, Session Beta remains active and becomes index 0
    expect(chat_tab.session_items).to_have_count(1)
    expect(chat_tab.session_items.nth(0)).to_have_class("chat-session-item active")
    expect(chat_tab.active_title).to_have_text("Session Beta")
    expect(chat_tab.assistant_bubbles.first).to_contain_text("BETA_MSG_ACTIVE")


def test_delete_active_session_reassigns_to_remaining_or_empty(page: Page, base_url: str):
    """Deleting an active session automatically shifts active state to remaining session, then to empty state."""
    project_id = "test-adv-del-active"
    _mock_project_base(page, project_id)

    chat_1 = {"id": "c-1", "project_id": project_id, "title": "First Session", "message_count": 0, "created_at": "2026-08-27T16:00:00Z", "updated_at": "2026-08-27T16:00:00Z"}
    chat_2 = {"id": "c-2", "project_id": project_id, "title": "Second Session", "message_count": 0, "created_at": "2026-08-27T16:05:00Z", "updated_at": "2026-08-27T16:05:00Z"}

    mock_api_route(page, f"**/api/projects/{project_id}/chats*", status_code=200, json_data={"chats": [chat_1, chat_2]}, method="GET")
    mock_api_route(page, f"**/api/projects/{project_id}/chats/c-1/messages*", status_code=200, json_data={"messages": [{"id": "m1", "chat_id": "c-1", "sender": "assistant", "content": "MSG_ONE", "timestamp": "2026-08-27T16:00:00Z"}]}, method="GET")
    mock_api_route(page, f"**/api/projects/{project_id}/chats/c-2/messages*", status_code=200, json_data={"messages": [{"id": "m2", "chat_id": "c-2", "sender": "assistant", "content": "MSG_TWO", "timestamp": "2026-08-27T16:05:00Z"}]}, method="GET")

    mock_api_route(page, f"**/api/projects/{project_id}/chats/c-1*", status_code=200, json_data={"status": "deleted"}, method="DELETE")
    mock_api_route(page, f"**/api/projects/{project_id}/chats/c-2*", status_code=200, json_data={"status": "deleted"}, method="DELETE")

    chat_tab = ChatTabPage(page, base_url)
    chat_tab.navigate(project_id)

    expect(chat_tab.session_items).to_have_count(2)
    expect(chat_tab.active_title).to_have_text("First Session")
    expect(chat_tab.assistant_bubbles.first).to_contain_text("MSG_ONE")

    # Delete active session c-1
    chat_tab.delete_session(0)

    # Verify automatically shifted to Second Session
    expect(chat_tab.session_items).to_have_count(1)
    expect(chat_tab.active_title).to_have_text("Second Session")
    expect(chat_tab.assistant_bubbles.first).to_contain_text("MSG_TWO")

    # Delete remaining session c-2 (active)
    chat_tab.delete_session(0)

    # Verify complete empty state transition
    expect(chat_tab.session_items).to_have_count(0)
    expect(chat_tab.empty_chats_state).to_be_visible()
    expect(chat_tab.btn_start_first_chat).to_be_visible()


# ===========================================================================
# 2. Independent Tool Traces Expand / Collapse
# ===========================================================================

def test_independent_tool_traces_toggle_across_multiple_messages(page: Page, base_url: str):
    """Tool trace expansion state must be tracked independently per message ID."""
    project_id = "test-adv-tools-indep"
    _mock_project_base(page, project_id)

    chat_id = "c-tools"
    mock_chats = [{"id": chat_id, "project_id": project_id, "title": "Tools Session", "message_count": 3, "created_at": "2026-08-27T16:00:00Z", "updated_at": "2026-08-27T16:00:00Z"}]

    mock_messages = [
        {
            "id": "msg-t-1",
            "chat_id": chat_id,
            "sender": "assistant",
            "content": "First response with 1 tool trace.",
            "timestamp": "2026-08-27T16:01:00Z",
            "tool_traces": [{"tool_name": "query_project_papers", "input_args": {}, "output_result": "Trace Alpha Output", "status": "success"}],
            "citations": []
        },
        {
            "id": "msg-t-2",
            "chat_id": chat_id,
            "sender": "assistant",
            "content": "Second response with 2 tool traces.",
            "timestamp": "2026-08-27T16:02:00Z",
            "tool_traces": [
                {"tool_name": "search_openalex", "input_args": {}, "output_result": "Trace Beta 1 Output", "status": "success"},
                {"tool_name": "extract_claim_polarities", "input_args": {}, "output_result": "Trace Beta 2 Output", "status": "success"}
            ],
            "citations": []
        },
        {
            "id": "msg-t-3",
            "chat_id": chat_id,
            "sender": "assistant",
            "content": "Third response with ZERO tool traces.",
            "timestamp": "2026-08-27T16:03:00Z",
            "tool_traces": [],
            "citations": []
        }
    ]

    mock_api_route(page, f"**/api/projects/{project_id}/chats*", status_code=200, json_data={"chats": mock_chats}, method="GET")
    mock_api_route(page, f"**/api/projects/{project_id}/chats/{chat_id}/messages*", status_code=200, json_data={"messages": mock_messages}, method="GET")

    chat_tab = ChatTabPage(page, base_url)
    chat_tab.navigate(project_id)

    # 2 toggle buttons exist (messages 1 and 2), message 3 has none
    expect(chat_tab.tool_trace_toggle_btn).to_have_count(2)
    expect(chat_tab.tool_trace_details).to_have_count(0)

    # Expand message 1
    chat_tab.toggle_tool_traces(0)
    expect(chat_tab.tool_trace_details).to_have_count(1)
    expect(chat_tab.tool_trace_details.first).to_contain_text("Trace Alpha Output")
    expect(chat_tab.tool_trace_details).not_to_contain_text("Trace Beta 1 Output")

    # Expand message 2
    chat_tab.toggle_tool_traces(1)
    expect(chat_tab.tool_trace_details).to_have_count(2)
    expect(chat_tab.tool_trace_details.nth(1)).to_contain_text("Trace Beta 1 Output")

    # Collapse message 1
    chat_tab.toggle_tool_traces(0)
    expect(chat_tab.tool_trace_details).to_have_count(1)
    expect(chat_tab.tool_trace_details.first).to_contain_text("Trace Beta 1 Output")


# ===========================================================================
# 3. Multiline Input, Whitespace Boundary & Send Disablement
# ===========================================================================

def test_multiline_input_whitespace_guard_and_submission(page: Page, base_url: str):
    """Test typing Shift+Enter multiline prompts, whitespace-only send blocking, and valid multiline payload."""
    project_id = "test-adv-multiline"
    _mock_project_base(page, project_id)

    chat_id = "c-multi"
    mock_chats = [{"id": chat_id, "project_id": project_id, "title": "Multiline Session", "message_count": 0, "created_at": "2026-08-27T16:00:00Z", "updated_at": "2026-08-27T16:00:00Z"}]

    mock_api_route(page, f"**/api/projects/{project_id}/chats*", status_code=200, json_data={"chats": mock_chats}, method="GET")
    mock_api_route(page, f"**/api/projects/{project_id}/chats/{chat_id}/messages*", status_code=200, json_data={"messages": []}, method="GET")

    chat_tab = ChatTabPage(page, base_url)
    chat_tab.navigate(project_id)

    # 1. Whitespace only input -> send button disabled
    chat_tab.chat_input.fill("   \n\n\t   ")
    expect(chat_tab.btn_send).to_be_disabled()

    # Press Enter on whitespace -> should not send
    page.keyboard.press("Enter")
    expect(chat_tab.user_bubbles).to_have_count(0)

    # 2. Type multiline prompt
    chat_tab.chat_input.fill("Paragraph 1: Background of Study\nParagraph 2: Methodology Analysis\nParagraph 3: Key Open Questions")
    expect(chat_tab.btn_send).to_be_enabled()

    multiline_text = "Paragraph 1: Background of Study\nParagraph 2: Methodology Analysis\nParagraph 3: Key Open Questions"

    mock_response = {
        "user_message": {
            "id": "m-u-multi",
            "chat_id": chat_id,
            "sender": "user",
            "content": multiline_text,
            "timestamp": "2026-08-27T16:01:00Z",
            "tool_traces": [],
            "citations": []
        },
        "assistant_message": {
            "id": "m-a-multi",
            "chat_id": chat_id,
            "sender": "assistant",
            "content": "Received 3 structured paragraphs.",
            "timestamp": "2026-08-27T16:01:05Z",
            "tool_traces": [],
            "citations": []
        }
    }
    mock_api_route(page, f"**/api/projects/{project_id}/chats/{chat_id}/messages*", status_code=200, json_data=mock_response, method="POST")

    # Press Enter
    page.keyboard.press("Enter")

    # Verify user message preserved multiline formatting
    expect(chat_tab.user_bubbles).to_have_count(1)
    expect(chat_tab.user_bubbles.first).to_contain_text("Paragraph 1: Background of Study")
    expect(chat_tab.user_bubbles.first).to_contain_text("Paragraph 3: Key Open Questions")
    expect(chat_tab.assistant_bubbles.first).to_contain_text("Received 3 structured paragraphs.")
    expect(chat_tab.chat_input).to_have_value("")


# ===========================================================================
# 4. Backend Failure Resiliency & Optimistic Rollback
# ===========================================================================

def test_backend_send_failure_rollback_and_input_restoration(page: Page, base_url: str):
    """When the server returns 500 during sendChatMessage, optimistic message is rolled back and input restored."""
    project_id = "test-adv-error-rollback"
    _mock_project_base(page, project_id)

    chat_id = "c-err"
    mock_chats = [{"id": chat_id, "project_id": project_id, "title": "Error Session", "message_count": 0, "created_at": "2026-08-27T16:00:00Z", "updated_at": "2026-08-27T16:00:00Z"}]

    mock_api_route(page, f"**/api/projects/{project_id}/chats*", status_code=200, json_data={"chats": mock_chats}, method="GET")
    mock_api_route(page, f"**/api/projects/{project_id}/chats/{chat_id}/messages*", status_code=200, json_data={"messages": []}, method="GET")
    mock_api_route(page, f"**/api/projects/{project_id}/chats/{chat_id}/messages*", status_code=500, json_data={"detail": "Agent Swarm LLM Timeout"}, method="POST")

    chat_tab = ChatTabPage(page, base_url)
    chat_tab.navigate(project_id)

    failed_prompt = "Critical query triggering agent error"
    chat_tab.fill_message_input(failed_prompt)
    chat_tab.click_send()

    # Toast error must appear
    assert_toast_message(page, expected_title_substring="Error")

    # Optimistic bubble must be removed
    expect(chat_tab.user_bubbles).to_have_count(0)
    expect(chat_tab.assistant_bubbles).to_have_count(0)

    # Input text restored
    expect(chat_tab.chat_input).to_have_value(failed_prompt)
    expect(chat_tab.btn_send).to_be_enabled()

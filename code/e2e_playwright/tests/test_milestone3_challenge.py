"""Empirical Challenge Test Suite for Milestone 3 (Chat Tab Interceptor & Contextual Trigger).

Adversarially verifies:
1. Contextual banner trigger opens modal
2. Action interceptors (Send button, Enter key, Quick prompt chips) block network dispatch and preserve input
3. Save & Apply instant unlock: modal dismissal, warning banner removal, immediate chat transmission recovery
"""
import json
import re
from playwright.sync_api import Page, Route, expect
from e2e_playwright.conftest import mock_api_route
from e2e_playwright.pages.api_key_modal_page import ApiKeyModalPage
from e2e_playwright.pages.chat_tab_page import ChatTabPage


def _setup_stateful_workspace(page: Page, project_id: str = "challenge-m3-proj"):
    state = {
        "has_credentials": False,
        "mode": "google_ai_studio",
        "gemini_api_key_preview": None,
        "vertex_project": None,
        "vertex_location": "us-central1",
        "use_vertex_ai": False,
    }

    mock_api_route(
        page,
        f"**/api/projects/{project_id}*",
        status_code=200,
        json_data={
            "id": project_id,
            "name": "M3 Challenge Project",
            "description": "Adversarial test project",
            "topic": "Graph Neural Networks",
            "target_level": "master",
        },
        method="GET",
    )
    mock_api_route(
        page,
        f"**/api/projects/{project_id}/touch*",
        status_code=200,
        json_data={"message": "ok"},
        method="POST",
    )
    mock_api_route(
        page,
        re.compile(rf".*/api/projects/{project_id}/chats(\?.*)?$"),
        status_code=200,
        json_data={"chats": [{"id": "chat-001", "title": "Research Session 1", "created_at": "2026-08-28T00:00:00Z"}]},
        method="GET",
    )
    mock_api_route(
        page,
        re.compile(rf".*/api/projects/{project_id}/chats/chat-001/messages(\?.*)?$"),
        status_code=200,
        json_data={"messages": []},
        method="GET",
    )

    # Dynamic Auth Status handler
    def auth_status_handler(route: Route):
        if route.request.method.upper() == "GET":
            route.fulfill(
                status=200,
                headers={"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
                body=json.dumps(state),
            )
        else:
            route.fallback()

    page.route("**/api/settings/auth*", auth_status_handler)

    # Dynamic Settings update handler
    def settings_handler(route: Route):
        if route.request.method.upper() == "PUT":
            payload = json.loads(route.request.post_data or "{}")
            state["has_credentials"] = True
            if payload.get("gemini_api_key"):
                state["mode"] = "google_ai_studio"
                state["gemini_api_key_preview"] = "••••••••••••8888"
                state["use_vertex_ai"] = False
            elif payload.get("vertex_project"):
                state["mode"] = "vertex_ai"
                state["vertex_project"] = payload.get("vertex_project")
                state["vertex_location"] = payload.get("vertex_location", "us-central1")
                state["use_vertex_ai"] = True
            route.fulfill(
                status=200,
                headers={"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
                body=json.dumps({"success": True, "message": "Settings updated"}),
            )
        elif route.request.method.upper() == "GET":
            route.fulfill(
                status=200,
                headers={"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
                body=json.dumps({
                    "gemini_api_key_set": state["has_credentials"] and not state["use_vertex_ai"],
                    "gemini_api_key_preview": state["gemini_api_key_preview"] or "Not set",
                    "openalex_api_key_set": True,
                    "openalex_api_key_preview": "••••••••••••9999",
                    "openalex_email": "test@research.edu",
                    "embedding_model": "gemini-embedding-2",
                    "embedding_dimensions": 768,
                }),
            )
        else:
            route.fallback()

    page.route("**/api/settings*", settings_handler)

    return state


def test_challenge_banner_configure_credentials_trigger(page: Page, base_url: str):
    """Verify clicking '🔑 Configure Credentials' in chat banner opens modal."""
    project_id = "challenge-banner-trigger"
    _setup_stateful_workspace(page, project_id)

    chat_page = ChatTabPage(page, base_url)
    chat_page.navigate(project_id)

    # 1. Verify warning banner is visible
    warning_banner = page.locator(".api-key-warning-bar")
    expect(warning_banner).to_be_visible(timeout=5000)
    expect(warning_banner).to_contain_text("Credentials Missing")

    # 2. Click "🔑 Configure Credentials"
    modal_page = ApiKeyModalPage(page, base_url)
    expect(modal_page.btn_chat_warning_configure.first).to_be_visible(timeout=5000)
    modal_page.btn_chat_warning_configure.first.click()

    # 3. Assert modal opened
    expect(modal_page.modal_dialog.first).to_be_visible(timeout=5000)
    expect(modal_page.tab_ai_studio.first).to_be_visible()


def test_challenge_interceptor_click_send_no_network_preserves_text(page: Page, base_url: str):
    """Verify sending chat message via Send button when unconfigured opens modal, intercepts network call, preserves text."""
    project_id = "challenge-send-intercept"
    _setup_stateful_workspace(page, project_id)

    # Network spy to record any outgoing message dispatch
    dispatched_requests = []
    page.on("request", lambda req: dispatched_requests.append(req.url) if "/messages" in req.url and req.method == "POST" else None)

    chat_page = ChatTabPage(page, base_url)
    chat_page.navigate(project_id)

    test_prompt = "Adversarial prompt: Check if network dispatch is blocked."
    expect(chat_page.chat_input).to_be_visible(timeout=10000)
    chat_page.fill_message_input(test_prompt)

    # Click Send
    chat_page.click_send()

    # 1. Modal MUST open
    modal_page = ApiKeyModalPage(page, base_url)
    expect(modal_page.modal_dialog.first).to_be_visible(timeout=10000)

    # 2. Network request MUST NOT have been sent
    assert len(dispatched_requests) == 0, f"Expected 0 POST /messages requests, got {len(dispatched_requests)}: {dispatched_requests}"

    # 3. Text MUST be preserved in textarea
    expect(chat_page.chat_input).to_have_value(test_prompt)


def test_challenge_interceptor_enter_key_no_network_preserves_text(page: Page, base_url: str):
    """Verify pressing Enter in chat input when unconfigured opens modal, intercepts network call, preserves text."""
    project_id = "challenge-enter-intercept"
    _setup_stateful_workspace(page, project_id)

    dispatched_requests = []
    page.on("request", lambda req: dispatched_requests.append(req.url) if "/messages" in req.url and req.method == "POST" else None)

    chat_page = ChatTabPage(page, base_url)
    chat_page.navigate(project_id)

    test_prompt = "Adversarial prompt: Testing Enter key interception."
    expect(chat_page.chat_input).to_be_visible(timeout=10000)
    chat_page.fill_message_input(test_prompt)

    # Press Enter
    chat_page.chat_input.press("Enter")

    # 1. Modal MUST open
    modal_page = ApiKeyModalPage(page, base_url)
    expect(modal_page.modal_dialog.first).to_be_visible(timeout=10000)

    # 2. Network request MUST NOT have been sent
    assert len(dispatched_requests) == 0, f"Expected 0 POST /messages requests, got {len(dispatched_requests)}: {dispatched_requests}"

    # 3. Text MUST be preserved in textarea
    expect(chat_page.chat_input).to_have_value(test_prompt)


def test_challenge_interceptor_quick_prompt_chip_preserves_text(page: Page, base_url: str):
    """Verify clicking quick prompt chip when unconfigured opens modal, intercepts network, sets textarea."""
    project_id = "challenge-chip-intercept"
    _setup_stateful_workspace(page, project_id)

    dispatched_requests = []
    page.on("request", lambda req: dispatched_requests.append(req.url) if "/messages" in req.url and req.method == "POST" else None)

    chat_page = ChatTabPage(page, base_url)
    chat_page.navigate(project_id)

    expect(chat_page.quick_prompt_chips.first).to_be_visible(timeout=10000)
    chip_text = chat_page.quick_prompt_chips.first.inner_text().strip()

    # Click chip
    chat_page.quick_prompt_chips.first.click()

    # 1. Modal MUST open
    modal_page = ApiKeyModalPage(page, base_url)
    expect(modal_page.modal_dialog.first).to_be_visible(timeout=10000)

    # 2. Network request MUST NOT have been sent
    assert len(dispatched_requests) == 0, f"Expected 0 POST /messages requests, got {len(dispatched_requests)}: {dispatched_requests}"

    # 3. Text MUST match chip text in textarea
    expect(chat_page.chat_input).to_have_value(chip_text)


def test_challenge_save_key_instant_unlock_and_send_recovery(page: Page, base_url: str):
    """Verify saving key in modal dismisses modal, removes chat banner, and enables sending chat."""
    project_id = "challenge-save-unlock"
    _setup_stateful_workspace(page, project_id)

    # Setup mock for chat message send
    mock_api_route(
        page,
        f"**/api/projects/{project_id}/chats/chat-001/messages*",
        status_code=200,
        json_data={
            "user_message": {
                "id": "msg-u-1",
                "chat_id": "chat-001",
                "sender": "user",
                "content": "Synthesize literature on Graph Neural Networks.",
                "timestamp": "2026-08-28T00:01:00Z"
            },
            "assistant_message": {
                "id": "msg-a-1",
                "chat_id": "chat-001",
                "sender": "assistant",
                "content": "Graph Neural Networks (GNNs) operate on graph structures through message passing.",
                "timestamp": "2026-08-28T00:01:05Z",
                "citations": [{"doi": "10.1145/gnn2025", "title": "GNN Survey"}],
                "tool_traces": []
            }
        },
        method="POST",
    )

    chat_page = ChatTabPage(page, base_url)
    chat_page.navigate(project_id)

    # Step 1: Input text before configuring
    input_text = "Synthesize literature on Graph Neural Networks."
    chat_page.fill_message_input(input_text)
    chat_page.click_send()

    modal_page = ApiKeyModalPage(page, base_url)
    expect(modal_page.modal_dialog.first).to_be_visible(timeout=5000)

    # Step 2: Fill Gemini API Key and save
    modal_page.select_studio_mode()
    modal_page.fill_gemini_key("AIzaSyChallengeTestKey123")
    modal_page.save_and_apply()

    # Step 3: Verify modal is dismissed
    modal_page.wait_for_closed()

    # Step 4: Verify warning banner is removed
    warning_banner = page.locator(".api-key-warning-bar")
    expect(warning_banner).not_to_be_visible(timeout=5000)

    # Step 5: Verify input text is still in the textarea
    expect(chat_page.chat_input).to_have_value(input_text)

    # Step 6: Send message now that credentials are saved
    chat_page.click_send()

    # Step 7: Verify assistant response appears in conversation
    expect(chat_page.assistant_bubbles.first).to_be_visible(timeout=5000)
    expect(chat_page.assistant_bubbles.first).to_contain_text("Graph Neural Networks")

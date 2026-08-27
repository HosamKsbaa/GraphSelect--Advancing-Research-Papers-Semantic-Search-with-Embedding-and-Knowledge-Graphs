from typing import Optional, List, Dict, Any, Union
from playwright.sync_api import Page, Locator, expect
from e2e_playwright.pages.base_page import BasePage


class ChatTabPage(BasePage):
    """Page Object Model for the Project Workspace Chat Tab (/projects/:id/chat)."""

    def __init__(self, page: Page, base_url: Optional[str] = None):
        super().__init__(page, base_url)

        # Container & Structural Elements
        self.container = page.locator(".chat-tab-container")
        self.sidebar = page.locator(".chat-sidebar")
        self.main_pane = page.locator(".chat-main-pane")

        # Sidebar & Session List Locators
        self.btn_new_chat = page.locator("#btnNewChat, .btn-new-chat")
        self.btn_start_first_chat = page.locator(".empty-chats button, .empty-state button")
        self.empty_chats_state = page.locator(".empty-chats, .empty-state, .no-chats")
        self.empty_state = page.locator(".empty-chats, .empty-state, .no-chats")
        self.loading_chats = page.locator(".loading-chats")
        self.session_items = page.locator(".chat-session-item")
        self.chat_session_items = page.locator(".chat-session-item")
        self.session_titles = page.locator(".chat-session-item .session-title")
        self.session_metas = page.locator(".chat-session-item .session-meta")
        self.delete_chat_btns = page.locator(".chat-session-item .btn-delete-chat, .btn-delete-chat")
        self.btn_delete_chat = page.locator(".chat-session-item .btn-delete-chat, .btn-delete-chat")

        # Header Locators
        self.chat_header = page.locator(".chat-header")
        self.active_title = page.locator(".chat-header .active-title")
        self.badge_swarm = page.locator(".badge-info:has-text('Google ADK Agent Swarm')")
        self.badge_neo4j = page.locator(".badge-success:has-text('Grounded in Neo4j')")

        # Message Stream Locators
        self.messages_stream = page.locator(".messages-stream")
        self.loading_messages = page.locator(".loading-messages")
        self.message_rows = page.locator(".message-row")
        self.user_rows = page.locator(".message-row.user, .message-row.user-row")
        self.assistant_rows = page.locator(".message-row.assistant, .message-row.assistant-row")
        self.user_bubbles = page.locator(".message-bubble.user-bubble, .message-bubble.user")
        self.assistant_bubbles = page.locator(".message-bubble.assistant-bubble, .message-bubble.assistant")
        self.message_contents = page.locator(".message-content")
        self.markdown_previews = page.locator("app-markdown-preview")
        self.typing_indicator = page.locator(".typing-bubble")

        # Tool Traces & Citations
        self.tool_traces_section = page.locator(".tool-traces-section")
        self.tool_trace_toggle = page.locator(".tool-trace-toggle")
        self.tool_trace_toggle_btn = page.locator(".tool-trace-toggle")
        self.tool_trace_details = page.locator(".tool-trace-details, .tool-traces-details")
        self.tool_trace_cards = page.locator(".tool-trace-card")
        self.citations_section = page.locator(".citations-section")
        self.citation_tags = page.locator(".citation-tag")
        self.citation_tag = page.locator(".citation-tag")

        # Quick Prompts & Input Bar
        self.quick_prompts_bar = page.locator(".quick-prompts-bar")
        self.quick_prompt_chips = page.locator(".quick-prompts-bar .btn-chip, .prompt-chip")
        self.prompt_chips = page.locator(".quick-prompts-bar .btn-chip, .prompt-chip")
        self.chat_input = page.locator("#chatInput, textarea.chat-input, .chat-input-bar textarea")
        self.btn_send = page.locator("#btnSendMessage, button.btn-send")
        self.btn_send_message = page.locator("#btnSendMessage, button.btn-send")

    def navigate(self, project_id: str) -> None:
        """Navigate directly to a project's chat tab."""
        self.goto(f"/projects/{project_id}/chat")
        self.wait_for_url_match(f"**/projects/{project_id}/chat")

    # --- Creation Helpers ---

    def create_new_chat(self) -> None:
        """Create a new chat session using either the sidebar button or empty-state button."""
        if self.btn_new_chat.is_visible():
            self.btn_new_chat.click()
        elif self.btn_start_first_chat.is_visible():
            self.btn_start_first_chat.click()

    def click_new_chat(self) -> None:
        """Click the + New Chat button in sidebar."""
        expect(self.btn_new_chat).to_be_visible(timeout=5000)
        self.btn_new_chat.click()

    def click_start_first_chat(self) -> None:
        """Click the + Start First Chat button in empty state."""
        expect(self.btn_start_first_chat).to_be_visible(timeout=5000)
        self.btn_start_first_chat.click()

    # --- Session Selection & Deletion ---

    def select_chat(self, title_or_id: Union[str, int]) -> None:
        """Select a chat session by index (int) or title/id substring (str)."""
        if isinstance(title_or_id, int):
            item = self.session_items.nth(title_or_id)
        else:
            item = self.session_items.filter(has_text=str(title_or_id)).first
        expect(item).to_be_visible(timeout=5000)
        item.click()

    def select_session(self, index: int = 0) -> None:
        """Select a chat session by its index in the sidebar list."""
        self.select_chat(index)

    def delete_chat(self, index_or_id: Union[str, int] = 0) -> None:
        """Delete a chat session by index (int) or title/id substring (str)."""
        if isinstance(index_or_id, int):
            btn = self.delete_chat_btns.nth(index_or_id)
        else:
            item = self.session_items.filter(has_text=str(index_or_id)).first
            btn = item.locator(".btn-delete-chat")
        expect(btn).to_be_visible(timeout=5000)
        btn.click()

    def delete_session(self, index: int = 0) -> None:
        """Click the delete button for a specific session index."""
        self.delete_chat(index)

    # --- Messaging Helpers ---

    def fill_message_input(self, text: str) -> None:
        """Fill text in the chat input area."""
        expect(self.chat_input).to_be_visible(timeout=5000)
        self.chat_input.fill(text)

    def click_send(self) -> None:
        """Click the Send button."""
        expect(self.btn_send).to_be_visible(timeout=5000)
        self.btn_send.click()

    def send_message(self, text: str) -> None:
        """Convenience helper to fill message and click send."""
        self.fill_message_input(text)
        self.click_send()

    def send_message_via_keyboard(self, text: str) -> None:
        """Type message into input and press Enter to submit."""
        self.fill_message_input(text)
        self.chat_input.press("Enter")

    def send_message_via_enter(self, text: str) -> None:
        """Type message and press Enter to send."""
        self.send_message_via_keyboard(text)

    def type_multiline_message(self, lines: List[str]) -> None:
        """Type multiple lines into input using Shift+Enter between lines."""
        expect(self.chat_input).to_be_visible(timeout=5000)
        self.chat_input.focus()
        combined = "\n".join(lines)
        self.chat_input.fill(combined)

    def insert_newline_via_shift_enter(self, text: str) -> None:
        """Type message and press Shift+Enter for multiline newline."""
        self.fill_message_input(text)
        self.chat_input.press("Shift+Enter")

    def click_prompt_chip(self, chip_text: Union[str, int]) -> None:
        """Click a quick prompt chip by its visible text or index."""
        if isinstance(chip_text, int):
            chip = self.quick_prompt_chips.nth(chip_text)
        else:
            chip = self.quick_prompt_chips.filter(has_text=str(chip_text)).first
        expect(chip).to_be_visible(timeout=5000)
        chip.click()

    def click_quick_prompt(self, index: int = 0) -> None:
        """Click a quick prompt chip by index."""
        self.click_prompt_chip(index)

    # --- Tool Traces & Citations Helpers ---

    def toggle_tool_trace(self, index: int = 0) -> None:
        """Toggle tool trace collapse/expand state for a message."""
        toggle = self.tool_trace_toggle.nth(index)
        expect(toggle).to_be_visible(timeout=5000)
        toggle.click()

    def toggle_tool_traces(self, index: int = 0) -> None:
        """Alias for toggle_tool_trace."""
        self.toggle_tool_trace(index)

    def get_citations(self) -> List[str]:
        """Return text contents of all visible citation tags."""
        count = self.citation_tags.count()
        citations = []
        for i in range(count):
            citations.append(self.citation_tags.nth(i).inner_text().strip())
        return citations

    def get_messages(self) -> List[Dict[str, str]]:
        """Return list of parsed message dictionaries with sender and text content."""
        count = self.message_rows.count()
        msgs = []
        for i in range(count):
            row = self.message_rows.nth(i)
            is_user = "user" in (row.get_attribute("class") or "")
            content_elem = row.locator(".message-content")
            content_text = content_elem.inner_text().strip() if content_elem.count() > 0 else ""
            msgs.append({
                "sender": "user" if is_user else "assistant",
                "content": content_text
            })
        return msgs

    def get_session_count(self) -> int:
        """Return the number of chat session items visible in the sidebar."""
        return self.session_items.count()

    def get_message_count(self) -> int:
        """Return the total number of message rows in the conversation stream."""
        return self.message_rows.count()

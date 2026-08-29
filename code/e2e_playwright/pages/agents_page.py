"""Page Object Model for the Agent Swarm Inspector & Configuration Page (/agents)."""
from typing import Dict, List, Optional
from playwright.sync_api import Locator, Page, expect
from e2e_playwright.pages.base_page import BasePage


class AgentsPage(BasePage):
    """Page object encapsulating all interactions on the /agents page."""

    def __init__(self, page: Page, base_url: Optional[str] = None):
        super().__init__(page, base_url)
        self.nav_agents = page.locator("a[routerLink='/agents'], a[href='/agents'], #nav-agents")
        
        # Header Elements
        self.page_title = page.locator(".page-title")
        self.page_subtitle = page.locator(".page-subtitle")
        self.tier1_badge = page.locator(".system-badge-item:has-text('Tier 1') .badge-value")
        self.tier2_badge = page.locator(".system-badge-item:has-text('Tier 2') .badge-value")
        
        # Tab Buttons
        self.tab_swarm = page.locator("button.tab-btn:has-text('Swarm Hierarchy')")
        self.tab_traces = page.locator("button.tab-btn:has-text('Live Traces Inspector')")
        
        # Swarm Toolbar Locators
        self.search_input = page.locator(".search-box input.form-input")
        self.clear_search_btn = page.locator(".search-box .btn-clear")
        self.tier_filter_select = page.locator(".filter-select-group:has-text('Tier:') select.form-select")
        self.status_filter_select = page.locator(".filter-select-group:has-text('Status:') select.form-select")
        self.grid_mode_btn = page.locator(".view-mode-toggle button:has-text('Grid')")
        self.tree_mode_btn = page.locator(".view-mode-toggle button:has-text('Tree')")
        
        # Swarm Global Actions
        self.test_connection_btn = page.locator("button:has-text('Test Connection')")
        self.reset_all_btn = page.locator("button.btn-reset-all")
        self.save_all_btn = page.locator("button.btn-save-all")
        self.save_count_badge = page.locator(".save-count-badge")
        
        # Agent Cards Locators
        self.agent_cards = page.locator("app-agent-card")
        self.hierarchy_tree = page.locator(".hierarchy-tree-view")
        self.empty_state = page.locator(".empty-state")
        self.loading_state = page.locator(".loading-state")
        
        # Reset Confirmation Modal
        self.reset_modal = page.locator(".modal-dialog")
        self.reset_modal_title = page.locator(".modal-header h3")
        self.reset_modal_body = page.locator(".modal-body")
        self.reset_modal_confirm_btn = page.locator(".modal-footer button.btn-danger")
        self.reset_modal_cancel_btn = page.locator(".modal-footer button:has-text('Cancel')")
        
        # Trace Viewer Locators
        self.trace_viewer = page.locator("app-trace-viewer")
        self.trace_search_input = page.locator("app-trace-viewer .search-box input.form-input")
        self.trace_agent_select = page.locator("app-trace-viewer .filter-item:has-text('Agent:') select.form-select")
        self.trace_status_select = page.locator("app-trace-viewer .filter-item:has-text('Status:') select.form-select")
        self.trace_limit_select = page.locator("app-trace-viewer .filter-item:has-text('Limit:') select.form-select")
        self.trace_auto_refresh_btn = page.locator("app-trace-viewer button.btn-toggle")
        self.trace_refresh_btn = page.locator("app-trace-viewer button:has-text('Refresh Traces')")
        self.trace_cards = page.locator("app-trace-viewer .trace-card")
        self.traces_count_label = page.locator("app-trace-viewer .traces-counter")

    def navigate(self) -> None:
        """Navigate to /agents and wait for load."""
        self.goto("/agents")
        self.wait_for_url_match("**/agents")
        expect(self.page_title).to_be_visible(timeout=10000)

    def navigate_via_sidebar(self) -> None:
        """Click sidebar / top navbar link for Agents."""
        self.nav_agents.first.click()
        self.wait_for_url_match("**/agents")
        expect(self.page_title).to_be_visible(timeout=10000)

    # --- Agent Card Helpers ---

    def get_agent_card(self, agent_name: str) -> Locator:
        """Get the specific agent card locator by agent name."""
        return self.page.locator(f"app-agent-card:has(.agent-name-tag:has-text('{agent_name}'))")

    def get_agent_model_select(self, agent_name: str) -> Locator:
        """Get the model select dropdown for a given agent."""
        return self.page.locator(f"#model-{agent_name}")

    def get_agent_temp_slider(self, agent_name: str) -> Locator:
        """Get the temperature range slider for a given agent."""
        return self.page.locator(f"#temp-{agent_name}")

    def get_agent_topp_slider(self, agent_name: str) -> Locator:
        """Get the top-p nucleus range slider for a given agent."""
        return self.page.locator(f"#topp-{agent_name}")

    def get_agent_tokens_slider(self, agent_name: str) -> Locator:
        """Get the max tokens range slider for a given agent."""
        return self.page.locator(f"#tokens-{agent_name}")

    def get_agent_prompt_textarea(self, agent_name: str) -> Locator:
        """Get the prompt prefix textarea for a given agent."""
        return self.page.locator(f"#prompt-prefix-{agent_name}")

    def get_agent_status_badge(self, agent_name: str) -> Locator:
        """Get the status badge (Default vs Modified) for a given agent."""
        card = self.get_agent_card(agent_name)
        return card.locator(".status-badge")

    def set_agent_model(self, agent_name: str, model_value: str) -> None:
        """Select a Gemini model for an agent."""
        select = self.get_agent_model_select(agent_name)
        select.select_option(model_value)

    def set_agent_temperature(self, agent_name: str, value: float) -> None:
        """Set temperature slider value."""
        slider = self.get_agent_temp_slider(agent_name)
        slider.fill(str(value))
        slider.dispatch_event("input")
        slider.dispatch_event("change")

    def set_agent_top_p(self, agent_name: str, value: float) -> None:
        """Set top_p slider value."""
        slider = self.get_agent_topp_slider(agent_name)
        slider.fill(str(value))
        slider.dispatch_event("input")
        slider.dispatch_event("change")

    def set_agent_max_tokens(self, agent_name: str, value: int) -> None:
        """Set max_output_tokens slider value."""
        slider = self.get_agent_tokens_slider(agent_name)
        slider.fill(str(value))
        slider.dispatch_event("input")
        slider.dispatch_event("change")

    def open_prompt_editor(self, agent_name: str) -> None:
        """Expand the prompt section of an agent card if collapsed."""
        card = self.get_agent_card(agent_name)
        prompt_section = card.locator(".prompt-section")
        if "open" not in (prompt_section.get_attribute("class") or ""):
            prompt_section.locator(".section-toggle").click()
        expect(self.get_agent_prompt_textarea(agent_name)).to_be_visible(timeout=5000)

    def set_agent_prompt_prefix(self, agent_name: str, text: str) -> None:
        """Open prompt editor and fill custom prompt prefix."""
        self.open_prompt_editor(agent_name)
        textarea = self.get_agent_prompt_textarea(agent_name)
        textarea.fill(text)
        textarea.dispatch_event("input")
        textarea.dispatch_event("change")

    def open_tools_directory(self, agent_name: str) -> None:
        """Expand the registered ADK tools directory in an agent card."""
        card = self.get_agent_card(agent_name)
        tools_section = card.locator(".tools-section")
        if "open" not in (tools_section.get_attribute("class") or ""):
            tools_section.locator(".section-toggle").click()
        expect(card.locator("app-tool-directory")).to_be_visible(timeout=5000)

    def get_agent_tools(self, agent_name: str) -> Locator:
        """Get all tool items within an agent card."""
        card = self.get_agent_card(agent_name)
        return card.locator("app-tool-directory .tool-item")

    def click_reset_agent(self, agent_name: str) -> None:
        """Click the Reset to Default button in an agent card and open modal."""
        card = self.get_agent_card(agent_name)
        card.locator("button.btn-reset").click()
        expect(self.reset_modal).to_be_visible(timeout=5000)

    def confirm_reset_modal(self) -> None:
        """Confirm reset inside the modal."""
        expect(self.reset_modal).to_be_visible(timeout=5000)
        self.reset_modal_confirm_btn.click()
        expect(self.reset_modal).not_to_be_visible(timeout=5000)

    def cancel_reset_modal(self) -> None:
        """Cancel reset inside the modal."""
        expect(self.reset_modal).to_be_visible(timeout=5000)
        self.reset_modal_cancel_btn.click()
        expect(self.reset_modal).not_to_be_visible(timeout=5000)

    def save_all(self) -> None:
        """Click Save All Settings."""
        self.save_all_btn.click()

    # --- Traces Tab Helpers ---

    def switch_to_traces_tab(self) -> None:
        """Switch to Live Traces Inspector tab."""
        self.tab_traces.click()
        expect(self.trace_viewer).to_be_visible(timeout=5000)

    def switch_to_swarm_tab(self) -> None:
        """Switch to Swarm Hierarchy tab."""
        self.tab_swarm.click()
        expect(self.agent_cards.first).to_be_visible(timeout=5000)

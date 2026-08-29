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
        self.page_title = page.locator(".page-title, h1:has-text('Agent Swarm')").first
        self.page_subtitle = page.locator(".page-subtitle").first
        self.tier1_badge = page.locator(".system-badge-item:has-text('Tier 1') .badge-value").first
        self.tier2_badge = page.locator(".system-badge-item:has-text('Tier 2') .badge-value").first
        
        # Tab Buttons
        self.tab_swarm = page.locator("button.tab-btn:has-text('Swarm Hierarchy')")
        self.tab_traces = page.locator("button.tab-btn:has-text('Live Traces Inspector')")
        
        # Swarm Toolbar Locators
        self.search_input = page.locator(".search-box input.form-input")
        self.clear_search_btn = page.locator(".search-box .btn-clear")
        self.tier_filter_select = page.locator(".filter-select-group:has-text('Tier:') select.form-select")
        self.status_filter_select = page.locator(".filter-select-group:has-text('Status:') select.form-select")
        self.grid_mode_btn = page.locator(".view-mode-toggle button:has-text('Grid'), button.view-toggle-btn:has-text('Grid')")
        self.tree_mode_btn = page.locator(".view-mode-toggle button:has-text('Tree'), button.view-toggle-btn:has-text('Tree'), button.view-toggle-btn:has-text('Hierarchy Tree')")
        
        # Swarm Global Actions
        self.test_connection_btn = page.locator("button:has-text('Test Connection')")
        self.reset_all_btn = page.locator("button.btn-reset-all")
        self.save_all_btn = page.locator("button.btn-save-all")
        self.save_count_badge = page.locator(".save-count-badge, .save-badge")
        
        # Agent Cards & Hierarchy Tree Locators
        self.agent_cards = page.locator("app-agent-card")
        self.hierarchy_tree = page.locator("app-hierarchy-tree")
        self.tree_svg = page.locator("app-hierarchy-tree svg.tree-connector-svg, app-hierarchy-tree svg")
        self.tree_nodes = page.locator("app-hierarchy-tree .tree-node")
        self.agent_drawer = page.locator("app-agent-drawer .drawer-panel")
        self.empty_state = page.locator(".empty-state")
        self.loading_state = page.locator(".loading-state, .loading-grid")
        
        # Tier Management & Editor Locators (Scoped strictly inside Tier Editor Modal)
        self.manage_tiers_btn = page.locator("button.btn-manage-tiers, button:has-text('Manage Tiers')")
        self.add_tier_btn = page.locator("app-tier-editor-modal button.btn-add-tier")
        self.tier_editor_modal = page.locator("app-tier-editor-modal .modal-dialog")
        self.tier_name_input = page.locator("app-tier-editor-modal #tier-name")
        self.tier_model_select = page.locator("app-tier-editor-modal #tier-model")
        self.tier_temp_slider = page.locator("app-tier-editor-modal #tier-temp")
        self.tier_tokens_slider = page.locator("app-tier-editor-modal #tier-tokens")
        self.tier_save_btn = page.locator("app-tier-editor-modal button.btn-save-tier")
        self.tier_delete_btn = page.locator("app-tier-editor-modal button.btn-delete-tier")
        
        # Reset Confirmation Modal
        self.reset_modal = page.locator(".modal-dialog")
        self.reset_modal_title = page.locator(".modal-header h3, .modal-header h2")
        self.reset_modal_body = page.locator(".modal-body")
        self.reset_modal_confirm_btn = page.locator(".modal-footer button.btn-danger, .modal-footer button.btn-primary")
        self.reset_modal_cancel_btn = page.locator(".modal-footer button:has-text('Cancel')")
        
        # Trace Viewer Locators
        self.trace_viewer = page.locator("app-trace-viewer")
        self.trace_agent_filter = page.locator("app-trace-viewer .filter-item:has-text('Agent:') select.form-select")
        self.trace_status_filter = page.locator("app-trace-viewer .filter-item:has-text('Status:') select.form-select")
        self.trace_search_input = page.locator("app-trace-viewer .search-box input.form-input")
        self.trace_limit_select = page.locator("app-trace-viewer .filter-item:has-text('Limit:') select.form-select")
        self.trace_auto_refresh_btn = page.locator("app-trace-viewer button.btn-toggle")
        self.trace_refresh_btn = page.locator("app-trace-viewer button:has-text('Refresh Traces')")
        self.trace_cards = page.locator("app-trace-viewer .trace-card")
        self.traces_count_label = page.locator("app-trace-viewer .traces-counter")

    def navigate(self) -> None:
        """Navigate to /agents and wait for load."""
        self.goto("/agents")
        self.wait_for_url_match("**/agents")
        expect(self.page_title.first).to_be_visible(timeout=15000)

    def navigate_via_sidebar(self) -> None:
        """Click sidebar / top navbar link for Agents."""
        self.nav_agents.first.click()
        self.wait_for_url_match("**/agents")
        expect(self.page_title.first).to_be_visible(timeout=15000)

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

    def set_slider_value(self, locator: Locator, value: float | str | int) -> None:
        """Reliably set HTML range input value and dispatch input and change events."""
        locator.evaluate(
            "(el, val) => { el.value = String(val); el.dispatchEvent(new Event('input', { bubbles: true })); el.dispatchEvent(new Event('change', { bubbles: true })); }",
            str(value),
        )

    def set_agent_model(self, agent_name: str, model_value: str) -> None:
        """Select a Gemini model for an agent."""
        select = self.get_agent_model_select(agent_name)
        select.select_option(model_value)

    def set_agent_temperature(self, agent_name: str, value: float) -> None:
        """Set temperature slider value."""
        slider = self.get_agent_temp_slider(agent_name)
        self.set_slider_value(slider, value)

    def set_agent_top_p(self, agent_name: str, value: float) -> None:
        """Set top_p slider value."""
        slider = self.get_agent_topp_slider(agent_name)
        self.set_slider_value(slider, value)

    def set_agent_max_tokens(self, agent_name: str, value: int) -> None:
        """Set max_output_tokens slider value."""
        slider = self.get_agent_tokens_slider(agent_name)
        self.set_slider_value(slider, value)

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

    # --- Hierarchy Tree Helpers ---

    # --- Hierarchy Tree Helpers ---

    def close_agent_drawer(self) -> None:
        """Close the agent drawer if open."""
        if self.agent_drawer.count() > 0 and self.agent_drawer.first.is_visible():
            self.page.locator("app-agent-drawer button.btn-close, app-agent-drawer .drawer-overlay").first.click(force=True)
            expect(self.agent_drawer).not_to_be_visible(timeout=5000)

    def close_tier_editor(self) -> None:
        """Close the Tier Editor modal if open."""
        if self.tier_editor_modal.count() > 0 and self.tier_editor_modal.first.is_visible():
            self.page.locator("app-tier-editor-modal button.btn-close, app-tier-editor-modal button:has-text('Done')").first.click(force=True)
            expect(self.tier_editor_modal).not_to_be_visible(timeout=5000)

    def switch_to_tree_view(self) -> None:
        """Switch view mode to Swarm Hierarchy Tree View."""
        self.close_agent_drawer()
        self.close_tier_editor()
        self.tree_mode_btn.click()
        expect(self.hierarchy_tree).to_be_visible(timeout=5000)

    def switch_to_grid_view(self) -> None:
        """Switch view mode to Agent Card Grid View."""
        self.close_agent_drawer()
        self.close_tier_editor()
        self.grid_mode_btn.click()
        expect(self.agent_cards.first).to_be_visible(timeout=5000)

    def get_tree_node(self, agent_name: str) -> Locator:
        """Get the tree node locator for a specific agent by name."""
        return self.page.locator(f"app-hierarchy-tree .tree-node:has-text('{agent_name}')")

    def click_tree_node(self, agent_name: str) -> None:
        """Click a node in the hierarchy tree to select and open its drawer."""
        node = self.get_tree_node(agent_name)
        node.click()

    # --- Tier Management Helpers ---

    def open_tier_editor(self) -> None:
        """Open the Tier Editor modal."""
        self.close_agent_drawer()
        self.manage_tiers_btn.first.click()
        expect(self.tier_editor_modal).to_be_visible(timeout=5000)

    def create_custom_tier(
        self,
        name: str,
        model: str = "gemini-2.5-flash",
        temperature: float = 0.70,
        max_tokens: int = 8192
    ) -> None:
        """Fill and submit new custom tier form inside the Tier Editor modal."""
        if self.add_tier_btn.first.is_visible():
            self.add_tier_btn.first.click()
        
        expect(self.tier_name_input.first).to_be_visible(timeout=5000)
        self.tier_name_input.first.click()
        self.tier_name_input.first.fill(name)
        self.tier_name_input.first.dispatch_event("input")
        self.tier_name_input.first.dispatch_event("change")
        
        if self.tier_model_select.first.is_visible():
            self.tier_model_select.first.select_option(model)
        if self.tier_temp_slider.first.is_visible():
            self.set_slider_value(self.tier_temp_slider.first, temperature)
        if self.tier_tokens_slider.first.is_visible():
            self.set_slider_value(self.tier_tokens_slider.first, max_tokens)
            
        expect(self.tier_save_btn.first).to_be_enabled(timeout=5000)
        self.tier_save_btn.first.click()

    # --- Mode Toggle Helpers (Inherit vs Custom) ---

    def set_agent_mode(self, agent_name: str, mode: str) -> None:
        """Toggle an agent between 'inherit' (Inherit Tier Defaults) and 'custom' (Custom Override)."""
        card = self.get_agent_card(agent_name)
        if mode == "inherit":
            inherit_btn = card.locator(".mode-pill-btn:has-text('Inherit'), button:has-text('Inherit')")
            inherit_btn.first.click()
        else:
            custom_btn = card.locator(".mode-pill-btn:has-text('Custom'), button:has-text('Custom')")
            custom_btn.first.click()

    def set_agent_assigned_tier(self, agent_name: str, tier_id: str) -> None:
        """Set the assigned tier for an agent in inherit mode."""
        card = self.get_agent_card(agent_name)
        tier_select = card.locator("select.tier-select, #assigned-tier, select[name='assignedTier']")
        tier_select.first.select_option(tier_id)

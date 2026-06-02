import pytest
from pages.project_workspace_page import ProjectWorkspacePage

def test_tab_navigation(driver, base_url):
    page = ProjectWorkspacePage(driver, base_url)
    # Use a dummy project ID 1 for testing workspace
    page.navigate("/projects/1")
    
    tabs = ["Research", "Analysis", "Planning", "Writing", "Export"]
    for tab_name in tabs:
        page.click_tab(tab_name)
        # Check URL update
        assert tab_name.lower() in driver.current_url.lower()
        
        # Check active class
        # active tab should have 'active' class
        tab_elements = page.get_tabs()
        active_tabs = [t for t in tab_elements if "active" in t.get_attribute("class")]
        assert any(tab_name.lower() in t.text.lower() for t in active_tabs), f"{tab_name} tab is not active"

def test_default_tab_is_research(driver, base_url):
    page = ProjectWorkspacePage(driver, base_url)
    page.navigate("/projects/1")
    
    assert "research" in driver.current_url.lower(), "Default tab should be research"
    
    tab_elements = page.get_tabs()
    active_tabs = [t for t in tab_elements if "active" in t.get_attribute("class")]
    assert any("research" in t.text.lower() for t in active_tabs), "Research tab is not active by default"

def test_api_key_warning_shown(driver, base_url):
    page = ProjectWorkspacePage(driver, base_url)
    # Assumes no API key is configured initially in testing environment
    page.navigate("/projects/1")
    
    assert page.is_api_key_warning_displayed(), "API key warning banner should be visible"

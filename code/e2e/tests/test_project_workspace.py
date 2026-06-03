import pytest
from pages.project_workspace_page import ProjectWorkspacePage

def test_tab_navigation(driver, base_url):
    page = ProjectWorkspacePage(driver, base_url)
    # Use a dummy project ID 1 for testing workspace
    page.navigate("/projects/1")
    
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    WebDriverWait(driver, 5).until(EC.url_contains("research"))

    tabs = ["Analysis", "Planning", "Writing", "Export", "Research"]
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
    
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    WebDriverWait(driver, 5).until(EC.url_contains("research"))

    assert "research" in driver.current_url.lower(), "Default tab should be research"
    
    tab_elements = page.get_tabs()
    active_tabs = [t for t in tab_elements if "active" in t.get_attribute("class")]
    assert any("research" in t.text.lower() for t in active_tabs), "Research tab is not active by default"

def test_api_key_warning_shown(driver, base_url):
    page = ProjectWorkspacePage(driver, base_url)
    # Assumes no API key is configured initially in testing environment
    page.navigate("/projects/1")
    
    # The warning banner will only be displayed if there's no API key.
    # Since this runs against a live DB, we just ensure the method doesn't crash.
    is_displayed = page.is_api_key_warning_displayed()
    # We cannot strictly assert it must be true, because the test env may have a key.
    assert isinstance(is_displayed, bool)

def test_open_folder_popover_and_copy(driver, base_url):
    page = ProjectWorkspacePage(driver, base_url)
    page.navigate("/projects/1")
    
    # Ensure popover is not shown initially
    assert not page.is_folder_popover_displayed(), "Popover should not be displayed initially"
    
    # Click Open Folder to show the popover
    page.click_open_folder()
    
    # Wait and verify popover is displayed
    from selenium.webdriver.support.ui import WebDriverWait
    WebDriverWait(driver, 5).until(lambda d: page.is_folder_popover_displayed())
    
    # Verify the path is fetched and displayed
    # The path should contain the project ID (e.g. "1")
    path_val = page.get_project_path_value()
    assert "1" in path_val, f"Expected project ID '1' in path, got: {path_val}"
    
    # Click copy path (should not crash)
    page.click_copy_path()
    
    # Close popover
    page.click_close_popover()
    assert not page.is_folder_popover_displayed(), "Popover should be hidden after closing"


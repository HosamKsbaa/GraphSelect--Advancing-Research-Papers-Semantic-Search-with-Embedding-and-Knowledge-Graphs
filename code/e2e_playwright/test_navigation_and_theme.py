import pytest
from playwright.sync_api import Page, expect


def test_root_redirects_to_projects(page: Page, base_url: str):
    """Test that visiting the root path redirects to /projects."""
    page.goto(base_url)
    page.wait_for_url("**/projects", timeout=10000)
    expect(page).to_have_url(f"{base_url}/projects")


def test_sidebar_navigation_links(page: Page, base_url: str):
    """Test that sidebar contains all core navigation items."""
    page.goto(f"{base_url}/projects")
    
    # Check Logo and Title
    logo_title = page.locator(".logo-title")
    expect(logo_title).to_contain_text("ALRS")
    
    # Check Nav Items
    expect(page.locator("a[routerLink='/projects']")).to_be_visible()
    expect(page.locator("a[routerLink='/search']")).to_be_visible()
    expect(page.locator("a[routerLink='/system-status']")).to_be_visible()
    expect(page.locator("a[routerLink='/logs']")).to_be_visible()
    expect(page.locator("a[routerLink='/debug']")).to_be_visible()
    expect(page.locator("a[routerLink='/settings']")).to_be_visible()


def test_system_status_page_loads(page: Page, base_url: str):
    """Test navigating to the system status page."""
    page.goto(f"{base_url}/system-status")
    page.wait_for_selector(".system-status-container, main", timeout=10000)
    expect(page).to_have_url(f"{base_url}/system-status")


def test_settings_page_loads(page: Page, base_url: str):
    """Test navigating to settings page."""
    page.goto(f"{base_url}/settings")
    page.wait_for_selector(".settings-container, main", timeout=10000)
    expect(page).to_have_url(f"{base_url}/settings")


def test_toast_container_present(page: Page, base_url: str):
    """Test that global toast notifications container is present in the DOM."""
    page.goto(f"{base_url}/projects")
    toast_container = page.locator("alrs-toast-container")
    expect(toast_container).to_be_attached()

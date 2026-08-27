import pytest
from playwright.sync_api import Page, expect


def test_search_wizard_steps_and_navigation(page: Page, base_url: str):
    """Test the 4-step Literature Search wizard UI."""
    page.goto(f"{base_url}/search")
    
    # Check Header
    expect(page.locator("h1.page-title")).to_contain_text("New Literature Search")
    
    # Check 4 Steps indicator
    steps = page.locator(".step")
    expect(steps).to_have_count(4)
    expect(page.locator(".step:has-text('Find Paper')")).to_be_visible()
    expect(page.locator(".step:has-text('Questions')")).to_be_visible()
    expect(page.locator(".step:has-text('Crawl')")).to_be_visible()
    expect(page.locator(".step:has-text('Results')")).to_be_visible()
    
    # Step 1 input
    search_input = page.locator("input[placeholder*='Enter paper title']")
    expect(search_input).to_be_visible()
    
    search_btn = page.locator("button:has-text('Search')")
    expect(search_btn).to_be_visible()

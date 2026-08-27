import pytest
import uuid
from playwright.sync_api import Page, expect


def test_create_project_modal_and_validation(page: Page, base_url: str):
    """Test opening create project dialog and validation."""
    page.goto(f"{base_url}/projects")
    
    # Click "New Project" button
    new_btn = page.locator("button:has-text('New Project'), button:has-text('Create Your First Project')").first
    new_btn.click()
    
    # Verify dialog opens
    dialog = page.locator(".modal-container")
    expect(dialog).to_be_visible(timeout=5000)
    
    # Cancel dialog
    cancel_btn = page.locator("button:has-text('Cancel')").first
    cancel_btn.click()
    expect(dialog).not_to_be_visible(timeout=5000)


def test_create_and_open_project(page: Page, base_url: str):
    """Test creating a new project and navigating to its workspace."""
    page.goto(f"{base_url}/projects")
    
    project_title = f"Playwright Project {uuid.uuid4().hex[:6]}"
    
    # Click New Project
    new_btn = page.locator("button:has-text('New Project'), button:has-text('Create Your First Project')").first
    new_btn.click()
    
    # Fill Title specifically in modal
    page.locator("#projectName").fill(project_title)
    
    # Fill Topic
    page.locator("#projectTopic").fill("Artificial Intelligence")
    
    # Submit Create
    submit_btn = page.locator("button[type='submit']:has-text('Create Project')")
    submit_btn.click()
    
    # Should navigate to project workspace
    page.wait_for_url("**/projects/**", timeout=10000)
    expect(page.locator(".workspace-nav")).to_be_visible()
    expect(page.locator(".tab-link:has-text('Research')")).to_be_visible()

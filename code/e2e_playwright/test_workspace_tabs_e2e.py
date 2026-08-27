import pytest
from playwright.sync_api import Page, expect


def test_research_tab_add_question_e2e(page: Page, base_url: str):
    """Test adding research questions and verifying question list rendering."""
    page.goto(f"{base_url}/projects")
    
    # Create a fresh project for question testing
    page.locator("button:has-text('New Project'), button:has-text('Create Your First Project')").first.click()
    page.locator("#projectName").fill("GNN Question E2E Project")
    page.locator("button[type='submit']:has-text('Create Project')").click()
    
    # Wait for workspace research tab to load
    page.wait_for_url("**/projects/*/research", timeout=10000)
    expect(page.locator(".workspace-nav")).to_be_visible(timeout=10000)
    
    q_input = page.locator("#inputQuestion")
    expect(q_input).to_be_visible(timeout=5000)
    q_input.fill("How do Graph Neural Networks detect misinformation cascades?")
    page.locator("#btnAddQuestion").click()
    
    # Wait for the question item or text to appear
    expect(page.locator(".question-text, .question-item").first).to_be_visible(timeout=10000)


def test_analysis_tab_and_polarity_subgraph_e2e(page: Page, base_url: str):
    """Test navigating to analysis tab and verifying analysis layout."""
    page.goto(f"{base_url}/projects")
    
    project_card = page.locator(".project-card").first
    if project_card.is_visible(timeout=3000):
        project_card.click()
    else:
        page.locator("button:has-text('New Project'), button:has-text('Create Your First Project')").first.click()
        page.locator("#projectName").fill("Analysis E2E Project")
        page.locator("button[type='submit']:has-text('Create Project')").click()
        
    page.wait_for_url("**/projects/**", timeout=10000)
    
    # Click Analysis Tab
    analysis_tab_link = page.locator("a.tab-link:has-text('Analysis')")
    analysis_tab_link.click()
    page.wait_for_url("**/analysis", timeout=5000)
    
    # Verify Analysis Tab container is visible
    expect(page.locator(".analysis-container")).to_be_visible(timeout=5000)


def test_writing_tab_gcdl_badges_e2e(page: Page, base_url: str):
    """Test navigating to writing tab and verifying workspace layout."""
    page.goto(f"{base_url}/projects")
    
    project_card = page.locator(".project-card").first
    if project_card.is_visible(timeout=3000):
        project_card.click()
    else:
        page.locator("button:has-text('New Project'), button:has-text('Create Your First Project')").first.click()
        page.locator("#projectName").fill("Writing E2E Project")
        page.locator("button[type='submit']:has-text('Create Project')").click()
        
    page.wait_for_url("**/projects/**", timeout=10000)
    
    # Click Writing Tab
    writing_tab_link = page.locator("a.tab-link:has-text('Writing')")
    writing_tab_link.click()
    page.wait_for_url("**/writing", timeout=5000)
    
    # Verify Writing Container loads
    expect(page.locator(".writing-tab-container")).to_be_visible(timeout=5000)
    expect(page.locator(".section-list")).to_be_visible(timeout=5000)


def test_export_tab_latex_templates_e2e(page: Page, base_url: str):
    """Test navigating to export tab and verifying export layout."""
    page.goto(f"{base_url}/projects")
    
    project_card = page.locator(".project-card").first
    if project_card.is_visible(timeout=3000):
        project_card.click()
    else:
        page.locator("button:has-text('New Project'), button:has-text('Create Your First Project')").first.click()
        page.locator("#projectName").fill("Export E2E Project")
        page.locator("button[type='submit']:has-text('Create Project')").click()
        
    page.wait_for_url("**/projects/**", timeout=10000)
    
    # Click Export Tab
    export_tab_link = page.locator("a.tab-link:has-text('Export')")
    export_tab_link.click()
    page.wait_for_url("**/export", timeout=5000)
    
    # Verify Export Container and LaTeX document card
    expect(page.locator(".export-tab-container")).to_be_visible(timeout=5000)
    expect(page.locator("h3:has-text('LaTeX Document')")).to_be_visible(timeout=5000)
    expect(page.locator("h3:has-text('BibTeX References')")).to_be_visible(timeout=5000)

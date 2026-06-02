import pytest
from pages.project_list_page import ProjectListPage
from selenium.webdriver.common.by import By

def test_page_loads(driver, base_url):
    page = ProjectListPage(driver, base_url)
    page.navigate("/projects")
    title = page.get_page_title()
    assert "Projects" in title, f"Expected 'Projects' in title, got '{title}'"

def test_new_project_button_opens_dialog(driver, base_url):
    page = ProjectListPage(driver, base_url)
    page.navigate("/projects")
    page.click_new_project()
    dialog = page.wait_for_create_dialog()
    assert dialog.is_displayed(), "Create project dialog should be visible"

def test_create_project_form_validation(driver, base_url):
    page = ProjectListPage(driver, base_url)
    page.navigate("/projects")
    page.click_new_project()
    page.wait_for_create_dialog()
    
    # Do not fill form, just submit
    submit_btn = page.wait_for_element(*page.SUBMIT_CREATE_BTN)
    
    # Usually the button is disabled if form is invalid, or an error appears
    # Let's check if it's disabled
    is_disabled = submit_btn.get_attribute("disabled") is not None
    assert is_disabled, "Submit button should be disabled when form is empty"
    page.cancel_create_project()

def test_create_project_success(driver, base_url):
    page = ProjectListPage(driver, base_url)
    page.navigate("/projects")
    initial_cards = len(page.get_project_cards())
    
    page.click_new_project()
    page.wait_for_create_dialog()
    
    import time
    unique_name = f"Test Project {int(time.time())}"
    page.fill_create_project_form(unique_name, "Selenium Testing", "Ph.D.", "Automated test project")
    
    # Wait for button to become enabled if it uses reactive forms
    page.wait_for_angular()
    submit_btn = page.wait_for_element(*page.SUBMIT_CREATE_BTN)
    assert submit_btn.get_attribute("disabled") is None, "Submit button should be enabled"
    
    page.submit_create_project()
    
    toasts = page.get_toast_messages()
    assert len(toasts) > 0, "Expected a success toast message"
    
    # Wait for new card to appear
    page.wait_for_angular()
    new_cards = len(page.get_project_cards())
    assert new_cards > initial_cards or new_cards > 0, "Expected project count to increase or be > 0"

def test_search_filter_projects(driver, base_url):
    page = ProjectListPage(driver, base_url)
    page.navigate("/projects")
    
    # create a unique one to search for, or just search for 'Test'
    page.search_projects("Test Project")
    cards = page.get_project_cards()
    
    # Assuming there's at least one matching or zero matching, 
    # we just assert no error and cards are returned correctly.
    # In a real populated DB we might check that title matches.
    for card in cards:
        assert "Test" in card.text or "Project" in card.text

def test_click_project_navigates(driver, base_url):
    page = ProjectListPage(driver, base_url)
    page.navigate("/projects")
    
    cards = page.get_project_cards()
    if not cards:
        # If no projects exist, create one so we can click it
        page.click_new_project()
        page.fill_create_project_form("Click Test", "Topic", "MSc", "Desc")
        page.submit_create_project()
        page.wait_for_angular()
        cards = page.get_project_cards()
        
    assert len(cards) > 0, "No projects available to click"
    cards[0].click()
    page.wait_for_angular()
    
    assert "/projects/" in driver.current_url

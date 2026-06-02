import pytest
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from typing import List
from pages.base_page import BasePage

class NavigationPage(BasePage):
    """Page object for the global sidebar navigation."""
    
    SIDEBAR_LINKS = (By.CSS_SELECTOR, "nav.sidebar a")
    LOGO = (By.CSS_SELECTOR, ".logo-text, .logo")
    VERSION_BADGE = (By.CSS_SELECTOR, ".version-badge")

    def get_sidebar_links(self) -> List[WebElement]:
        self.wait_for_angular()
        return self.driver.find_elements(*self.SIDEBAR_LINKS)

    def click_link_by_text(self, text: str) -> None:
        links = self.get_sidebar_links()
        for link in links:
            if text.lower() in link.text.lower():
                link.click()
                self.wait_for_angular()
                return
        raise ValueError(f"Link with text '{text}' not found in sidebar")

    def get_logo_text(self) -> str:
        return self.wait_for_element(*self.LOGO).text.strip()

    def get_version_text(self) -> str:
        return self.wait_for_element(*self.VERSION_BADGE).text.strip()


def test_sidebar_links_present(driver, base_url):
    nav = NavigationPage(driver, base_url)
    nav.navigate("/")
    links = nav.get_sidebar_links()
    assert len(links) >= 6, f"Expected at least 6 sidebar links, got {len(links)}"
    texts = [link.text.strip().lower() for link in links]
    assert "projects" in texts or any("projects" in t for t in texts)
    assert "search" in texts or any("search" in t for t in texts)
    assert "sessions" in texts or any("sessions" in t for t in texts)
    assert "logs" in texts or any("logs" in t for t in texts)
    assert "debug" in texts or any("debug" in t for t in texts)
    assert "settings" in texts or any("settings" in t for t in texts)

def test_navigate_to_projects(driver, base_url):
    nav = NavigationPage(driver, base_url)
    nav.navigate("/")
    nav.click_link_by_text("Projects")
    assert "/projects" in driver.current_url

def test_navigate_to_search(driver, base_url):
    nav = NavigationPage(driver, base_url)
    nav.navigate("/")
    nav.click_link_by_text("Search")
    assert "/search" in driver.current_url

def test_navigate_to_sessions(driver, base_url):
    nav = NavigationPage(driver, base_url)
    nav.navigate("/")
    nav.click_link_by_text("Sessions")
    assert "/sessions" in driver.current_url

def test_navigate_to_logs(driver, base_url):
    nav = NavigationPage(driver, base_url)
    nav.navigate("/")
    nav.click_link_by_text("Logs")
    assert "/logs" in driver.current_url

def test_navigate_to_debug(driver, base_url):
    nav = NavigationPage(driver, base_url)
    nav.navigate("/")
    nav.click_link_by_text("Debug")
    assert "/debug" in driver.current_url

def test_navigate_to_settings(driver, base_url):
    nav = NavigationPage(driver, base_url)
    nav.navigate("/")
    nav.click_link_by_text("Settings")
    assert "/settings" in driver.current_url

def test_logo_and_version(driver, base_url):
    nav = NavigationPage(driver, base_url)
    nav.navigate("/")
    logo_text = nav.get_logo_text()
    assert "ALRS" in logo_text, f"Expected 'ALRS' in logo, got '{logo_text}'"
    version_text = nav.get_version_text()
    assert version_text != "", "Version badge should not be empty"

def test_no_console_errors_on_load(driver, base_url):
    nav = NavigationPage(driver, base_url)
    nav.navigate("/")
    
    logs = driver.get_log("browser")
    severe_errors = [log for log in logs if log["level"] == "SEVERE"]
    
    # Filter out known non-issue errors if needed, but per contract assert 0
    assert len(severe_errors) == 0, f"Found severe console errors: {severe_errors}"

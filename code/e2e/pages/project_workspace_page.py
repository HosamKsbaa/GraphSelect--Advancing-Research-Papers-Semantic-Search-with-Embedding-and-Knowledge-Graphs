from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from typing import List
from .base_page import BasePage

class ProjectWorkspacePage(BasePage):
    """Page object for the Project Workspace view (tabs navigation)."""

    # Locators
    TAB_LINKS = (By.CSS_SELECTOR, "a.tab-link")
    API_KEY_WARNING = (By.CSS_SELECTOR, "div.alert-banner.warning")

    def get_tabs(self) -> List[WebElement]:
        self.wait_for_angular()
        return self.driver.find_elements(*self.TAB_LINKS)

    def click_tab(self, tab_name: str) -> None:
        """Click a tab by its name/text."""
        tabs = self.get_tabs()
        for tab in tabs:
            if tab_name.lower() in tab.text.lower():
                self.driver.execute_script("arguments[0].click();", tab)
                self.wait_for_angular()
                from selenium.webdriver.support.ui import WebDriverWait
                from selenium.webdriver.support import expected_conditions as EC
                WebDriverWait(self.driver, 5).until(EC.url_contains(tab_name.lower()))
                return
        raise ValueError(f"Tab '{tab_name}' not found")

    def is_api_key_warning_displayed(self) -> bool:
        """Check if the API key warning banner is visible."""
        self.wait_for_angular()
        elements = self.driver.find_elements(*self.API_KEY_WARNING)
        return len(elements) > 0 and elements[0].is_displayed()

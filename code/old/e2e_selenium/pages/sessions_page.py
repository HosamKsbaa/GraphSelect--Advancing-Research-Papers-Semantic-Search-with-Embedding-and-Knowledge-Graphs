from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from typing import List
from .base_page import BasePage

class SessionsPage(BasePage):
    """Page object for the Sessions listing."""
    
    # Locators
    SESSION_CARDS = (By.CSS_SELECTOR, "div.session-card")
    DELETE_BTNS = (By.CSS_SELECTOR, "button.delete-btn")
    STATUS_BADGES = (By.CSS_SELECTOR, "span.status-badge")
    DOI_SPANS = (By.CSS_SELECTOR, "span.doi")
    STATS_DISPLAY = (By.CSS_SELECTOR, "div.stats-display")

    def get_session_cards(self) -> List[WebElement]:
        self.wait_for_element(self.SESSION_CARDS[0], self.SESSION_CARDS[1])
        return self.driver.find_elements(*self.SESSION_CARDS)

    def click_delete_session(self, index: int = 0) -> None:
        self.wait_for_element(self.DELETE_BTNS[0], self.DELETE_BTNS[1])
        btns = self.driver.find_elements(*self.DELETE_BTNS)
        if index < len(btns):
            btns[index].click()

    def get_status_badges(self) -> List[WebElement]:
        self.wait_for_element(self.STATUS_BADGES[0], self.STATUS_BADGES[1])
        return self.driver.find_elements(*self.STATUS_BADGES)

    def get_doi_spans(self) -> List[WebElement]:
        self.wait_for_element(self.DOI_SPANS[0], self.DOI_SPANS[1])
        return self.driver.find_elements(*self.DOI_SPANS)

    def get_stats(self) -> str:
        elem = self.wait_for_element(self.STATS_DISPLAY[0], self.STATS_DISPLAY[1])
        return elem.text

from selenium.webdriver.common.by import By
from .base_page import BasePage
from selenium.webdriver.remote.webelement import WebElement
from typing import List

class AnalysisTabPage(BasePage):
    """Page object for the Analysis tab in the project workspace."""
    
    # Locators
    COVERAGE_CARDS = (By.CSS_SELECTOR, "div.coverage-card")
    SUGGEST_QUERIES_BTN = (By.XPATH, "//button[contains(text(), 'Suggest Queries')]")
    QUERY_LIST_ITEMS = (By.CSS_SELECTOR, "li.query-item")
    STATS_PANEL = (By.CSS_SELECTOR, "div.stats-panel")
    RANKED_PAPERS_PANEL = (By.CSS_SELECTOR, "div.ranked-papers-panel")
    
    def get_coverage_cards(self) -> List[WebElement]:
        return self.driver.find_elements(*self.COVERAGE_CARDS)
        
    def click_suggest_queries(self) -> WebElement:
        return self.wait_and_click(*self.SUGGEST_QUERIES_BTN)
        
    def get_query_list_items(self) -> List[WebElement]:
        return self.driver.find_elements(*self.QUERY_LIST_ITEMS)
        
    def wait_for_stats_panel(self) -> WebElement:
        return self.wait_for_element(*self.STATS_PANEL)
        
    def wait_for_ranked_papers_panel(self) -> WebElement:
        return self.wait_for_element(*self.RANKED_PAPERS_PANEL)

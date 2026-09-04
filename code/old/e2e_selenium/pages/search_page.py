from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from typing import List
from .base_page import BasePage

class SearchPage(BasePage):
    """Page object for the multi-step Search wizard."""
    
    # Locators
    TITLE_INPUT = (By.CSS_SELECTOR, 'input[type="text"][placeholder*="paper title"]')
    SEARCH_BTN = (By.CSS_SELECTOR, "button.btn-primary")
    CANDIDATE_CARDS = (By.CSS_SELECTOR, "div.candidate-card")
    QUESTION_INPUTS = (By.CSS_SELECTOR, 'input[type="text"]')
    START_SEARCH_BTN = (By.XPATH, '//button[contains(text(),"Start Search")]')
    PROGRESS_BAR = (By.CSS_SELECTOR, "div.progress-fill")
    EVENT_ITEMS = (By.CSS_SELECTOR, "div.event-item")
    VIEW_RESULTS_BTN = (By.XPATH, '//button[contains(text(),"View Results")]')
    STEP_INDICATORS = (By.CSS_SELECTOR, "div.step-indicator")

    def enter_title(self, title: str) -> None:
        elem = self.wait_for_element(self.TITLE_INPUT[0], self.TITLE_INPUT[1])
        elem.clear()
        elem.send_keys(title)
        
    def click_search(self) -> None:
        self.wait_and_click(self.SEARCH_BTN[0], self.SEARCH_BTN[1])
        
    def get_candidate_cards(self) -> List[WebElement]:
        self.wait_for_element(self.CANDIDATE_CARDS[0], self.CANDIDATE_CARDS[1])
        return self.driver.find_elements(*self.CANDIDATE_CARDS)

    def select_candidate(self, index: int = 0) -> None:
        cards = self.get_candidate_cards()
        if index < len(cards):
            cards[index].click()

    def enter_question(self, index: int, question: str) -> None:
        self.wait_for_element(self.QUESTION_INPUTS[0], self.QUESTION_INPUTS[1])
        inputs = self.driver.find_elements(*self.QUESTION_INPUTS)
        if index < len(inputs):
            inputs[index].clear()
            inputs[index].send_keys(question)
        
    def start_search(self) -> None:
        self.wait_and_click(self.START_SEARCH_BTN[0], self.START_SEARCH_BTN[1])

    def wait_for_progress(self) -> None:
        self.wait_for_element(self.PROGRESS_BAR[0], self.PROGRESS_BAR[1])
        
    def get_event_items(self) -> List[WebElement]:
        return self.driver.find_elements(*self.EVENT_ITEMS)
        
    def click_view_results(self) -> None:
        self.wait_and_click(self.VIEW_RESULTS_BTN[0], self.VIEW_RESULTS_BTN[1])

    def get_step_indicators(self) -> List[WebElement]:
        return self.driver.find_elements(*self.STEP_INDICATORS)

from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from typing import List
from .base_page import BasePage

class ResearchTabPage(BasePage):
    """Page object for the Research Tab inside the Project Workspace."""

    # Locators
    QUESTION_INPUT = (By.CSS_SELECTOR, 'input[type="text"][placeholder*="research question"]')
    ADD_QUESTION_BTN = (By.XPATH, '//button[text()="Add"]')
    QUESTION_ITEMS = (By.CSS_SELECTOR, "li.question-item")
    DELETE_QUESTION_BTN = (By.CSS_SELECTOR, "button.delete-btn")
    PAPER_TABLE = (By.CSS_SELECTOR, "table.paper-table")
    PAPER_ROWS = (By.CSS_SELECTOR, "tr.paper-row")
    SEARCH_INPUT = (By.CSS_SELECTOR, 'input[type="text"][placeholder*="Search"]')
    SEARCH_BTN = (By.CSS_SELECTOR, "button.search-btn")
    TOP_AUTHORS = (By.CSS_SELECTOR, "ul.ranked-list")
    CONFIRM_DELETE_BTN = (By.CSS_SELECTOR, "button.btn-danger")

    def add_research_question(self, question: str) -> None:
        inp = self.wait_for_element(*self.QUESTION_INPUT)
        inp.clear()
        inp.send_keys(question)
        self.wait_and_click(*self.ADD_QUESTION_BTN)
        self.wait_for_angular()

    def get_research_question_elements(self) -> List[WebElement]:
        self.wait_for_angular()
        return self.driver.find_elements(*self.QUESTION_ITEMS)

    def delete_research_question(self, index: int) -> None:
        self.wait_for_angular()
        items = self.driver.find_elements(*self.QUESTION_ITEMS)
        if index < len(items):
            delete_btn = items[index].find_element(*self.DELETE_QUESTION_BTN)
            delete_btn.click()
            self.wait_for_angular()
        else:
            raise IndexError(f"Question index {index} out of range")

    def confirm_delete(self) -> None:
        self.wait_and_click(*self.CONFIRM_DELETE_BTN)
        self.wait_for_angular()

    def get_paper_rows(self) -> List[WebElement]:
        self.wait_for_angular()
        return self.driver.find_elements(*self.PAPER_ROWS)

    def search_papers(self, query: str) -> None:
        """Fill the paper search input with a query."""
        inp = self.wait_for_element(*self.SEARCH_INPUT)
        inp.clear()
        inp.send_keys(query)
        self.wait_for_angular()

    def click_search_web(self) -> None:
        self.wait_and_click(*self.SEARCH_BTN)
        self.wait_for_angular()

    def get_top_authors_element(self) -> WebElement:
        """Returns the unordered list element representing top authors."""
        return self.wait_for_element(*self.TOP_AUTHORS)

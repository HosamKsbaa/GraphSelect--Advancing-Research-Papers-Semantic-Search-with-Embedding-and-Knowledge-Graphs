from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from typing import List
from .base_page import BasePage

class ProjectListPage(BasePage):
    """Page object for the Project List view."""

    # Locators
    NEW_PROJECT_BTN = (By.CSS_SELECTOR, "button.btn-primary")
    PROJECT_CARDS = (By.CSS_SELECTOR, "a.project-card")
    SEARCH_INPUT = (By.CSS_SELECTOR, 'input[type="text"]')
    SHOW_ARCHIVED_TOGGLE = (By.CSS_SELECTOR, 'input[type="checkbox"]')
    CREATE_DIALOG = (By.CSS_SELECTOR, "div.modal-backdrop")
    PROJECT_NAME_INPUT = (By.ID, "projectName")
    PROJECT_TOPIC_INPUT = (By.ID, "projectTopic")
    TARGET_LEVEL_SELECT = (By.ID, "targetLevel")
    PROJECT_DESC_INPUT = (By.ID, "projectDesc")
    SUBMIT_CREATE_BTN = (By.CSS_SELECTOR, 'button[type="submit"].btn-primary')
    CANCEL_CREATE_BTN = (By.CSS_SELECTOR, "button.btn-ghost")

    def click_new_project(self) -> None:
        self.wait_and_click(*self.NEW_PROJECT_BTN)

    def get_project_cards(self) -> List[WebElement]:
        self.wait_for_angular()
        return self.driver.find_elements(*self.PROJECT_CARDS)

    def search_projects(self, query: str) -> None:
        search_input = self.wait_for_element(*self.SEARCH_INPUT)
        search_input.clear()
        search_input.send_keys(query)
        self.wait_for_angular()

    def toggle_show_archived(self) -> None:
        self.wait_and_click(*self.SHOW_ARCHIVED_TOGGLE)
        self.wait_for_angular()

    def wait_for_create_dialog(self) -> WebElement:
        return self.wait_for_element(*self.CREATE_DIALOG)

    def fill_create_project_form(self, name: str, topic: str, level: str, desc: str) -> None:
        self.wait_for_element(*self.PROJECT_NAME_INPUT).send_keys(name)
        self.wait_for_element(*self.PROJECT_TOPIC_INPUT).send_keys(topic)
        self.wait_for_element(*self.TARGET_LEVEL_SELECT).send_keys(level)
        self.wait_for_element(*self.PROJECT_DESC_INPUT).send_keys(desc)

    def submit_create_project(self) -> None:
        self.wait_and_click(*self.SUBMIT_CREATE_BTN)
        self.wait_for_angular()

    def cancel_create_project(self) -> None:
        self.wait_and_click(*self.CANCEL_CREATE_BTN)
        self.wait_for_angular()

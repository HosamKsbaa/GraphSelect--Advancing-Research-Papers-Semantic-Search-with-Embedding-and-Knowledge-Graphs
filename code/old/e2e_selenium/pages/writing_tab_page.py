from selenium.webdriver.common.by import By
from .base_page import BasePage
from selenium.webdriver.remote.webelement import WebElement
from typing import List

class WritingTabPage(BasePage):
    """Page object for the Writing tab in the project workspace."""
    
    # Locators
    SECTION_CARDS = (By.CSS_SELECTOR, "div.section-card")
    DRAFT_BTN = (By.XPATH, "//button[contains(text(), 'Draft')]")
    REVIEW_BTN = (By.XPATH, "//button[contains(text(), 'Review')]")
    MARKDOWN_EDITOR = (By.CSS_SELECTOR, "textarea.markdown-editor")
    MARKDOWN_PREVIEW = (By.CSS_SELECTOR, "div.markdown-preview")
    EDIT_TOGGLE_BTN = (By.XPATH, "//button[contains(text(), 'Edit')]")
    PREVIEW_TOGGLE_BTN = (By.XPATH, "//button[contains(text(), 'Preview')]")
    FEEDBACK_PANEL = (By.CSS_SELECTOR, "div.feedback-panel")
    EXPORT_BANNER = (By.CSS_SELECTOR, "div.export-banner")
    
    def get_section_cards(self) -> List[WebElement]:
        return self.driver.find_elements(*self.SECTION_CARDS)
        
    def click_draft_section(self) -> WebElement:
        return self.wait_and_click(*self.DRAFT_BTN)
        
    def click_review_section(self) -> WebElement:
        return self.wait_and_click(*self.REVIEW_BTN)
        
    def edit_markdown(self, text: str):
        editor = self.wait_for_element(*self.MARKDOWN_EDITOR)
        editor.clear()
        editor.send_keys(text)
        
    def get_preview_text(self) -> str:
        preview = self.wait_for_element(*self.MARKDOWN_PREVIEW)
        return preview.text
        
    def toggle_edit_mode(self) -> WebElement:
        return self.wait_and_click(*self.EDIT_TOGGLE_BTN)
        
    def toggle_preview_mode(self) -> WebElement:
        return self.wait_and_click(*self.PREVIEW_TOGGLE_BTN)
        
    def wait_for_feedback_panel(self) -> WebElement:
        return self.wait_for_element(*self.FEEDBACK_PANEL)
        
    def wait_for_export_banner(self) -> WebElement:
        return self.wait_for_element(*self.EXPORT_BANNER)

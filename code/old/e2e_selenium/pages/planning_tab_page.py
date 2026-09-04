from selenium.webdriver.common.by import By
from .base_page import BasePage
from selenium.webdriver.remote.webelement import WebElement
from typing import List

class PlanningTabPage(BasePage):
    """Page object for the Planning tab in the project workspace."""
    
    # Locators
    READINESS_SUMMARY_CARD = (By.CSS_SELECTOR, "div.readiness-summary-card")
    GENERATE_OUTLINE_BTN = (By.XPATH, "//button[contains(text(), 'Generate Outline')]")
    OUTLINE_SECTIONS = (By.CSS_SELECTOR, "div.outline-section")
    
    # Config Dialog Locators
    CONFIG_DIALOG = (By.CSS_SELECTOR, "div.modal-backdrop")
    STYLE_SELECT = (By.ID, "outlineStyle")
    NUM_SECTIONS_INPUT = (By.ID, "numSections")
    CONFIRM_GENERATE_BTN = (By.CSS_SELECTOR, "button[type='submit'].btn-primary")
    CANCEL_BTN = (By.CSS_SELECTOR, "button.btn-ghost")
    
    def wait_for_readiness_summary(self) -> WebElement:
        return self.wait_for_element(*self.READINESS_SUMMARY_CARD)
        
    def click_generate_outline(self) -> WebElement:
        return self.wait_and_click(*self.GENERATE_OUTLINE_BTN)
        
    def get_outline_sections(self) -> List[WebElement]:
        return self.driver.find_elements(*self.OUTLINE_SECTIONS)
        
    def configure_and_generate_outline(self, style: str = None, num_sections: str = None):
        # Wait for dialog to appear
        self.wait_for_element(*self.CONFIG_DIALOG)
        
        # Set style if provided
        if style:
            style_dropdown = self.wait_for_element(*self.STYLE_SELECT)
            style_dropdown.send_keys(style)
            
        # Set num sections if provided
        if num_sections:
            num_input = self.wait_for_element(*self.NUM_SECTIONS_INPUT)
            num_input.clear()
            num_input.send_keys(num_sections)
            
        # Click generate
        self.wait_and_click(*self.CONFIRM_GENERATE_BTN)
        
    def click_cancel(self) -> WebElement:
        return self.wait_and_click(*self.CANCEL_BTN)

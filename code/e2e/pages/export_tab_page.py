from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from typing import List
from .base_page import BasePage

class ExportTabPage(BasePage):
    """Page object for the Export Tab in the project workspace."""
    
    # Locators
    EXPORT_CARDS = (By.CSS_SELECTOR, "div.export-card")
    EXPORT_BTNS = (By.CSS_SELECTOR, "button.export-btn")
    LATEX_DIALOG = (By.CSS_SELECTOR, "div.latex-dialog")
    TEMPLATE_RADIOS = (By.CSS_SELECTOR, 'input[type="radio"]')
    CONFIRM_BTN = (By.CSS_SELECTOR, "button.confirm-btn")
    CANCEL_BTN = (By.CSS_SELECTOR, "button.cancel-btn")

    def get_export_cards(self) -> List[WebElement]:
        self.wait_for_element(self.EXPORT_CARDS[0], self.EXPORT_CARDS[1])
        return self.driver.find_elements(*self.EXPORT_CARDS)
        
    def get_export_buttons(self) -> List[WebElement]:
        self.wait_for_element(self.EXPORT_BTNS[0], self.EXPORT_BTNS[1])
        return self.driver.find_elements(*self.EXPORT_BTNS)

    def click_export_button(self, index: int = 0) -> None:
        btns = self.get_export_buttons()
        if index < len(btns):
            btns[index].click()

    def select_template(self, index: int = 0) -> None:
        self.wait_for_element(self.TEMPLATE_RADIOS[0], self.TEMPLATE_RADIOS[1])
        radios = self.driver.find_elements(*self.TEMPLATE_RADIOS)
        if index < len(radios):
            radios[index].click()

    def confirm_export(self) -> None:
        self.wait_and_click(self.CONFIRM_BTN[0], self.CONFIRM_BTN[1])

    def cancel_export(self) -> None:
        self.wait_and_click(self.CANCEL_BTN[0], self.CANCEL_BTN[1])
        
    def is_dialog_open(self) -> bool:
        try:
            self.wait_for_element(self.LATEX_DIALOG[0], self.LATEX_DIALOG[1], timeout=2)
            return True
        except:
            return False

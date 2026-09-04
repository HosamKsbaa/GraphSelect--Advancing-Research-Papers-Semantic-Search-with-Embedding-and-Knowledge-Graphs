import os
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.remote.webelement import WebElement
from typing import List


class BasePage:
    """Base class for all Page Objects with common interaction methods."""
    
    def __init__(self, driver: webdriver.Chrome, base_url: str = None, api_url: str = None, timeout: int = 10):
        self.driver = driver
        self.base_url = base_url or os.environ.get("ALRS_BASE_URL", "http://localhost:4200")
        self.api_url = api_url or os.environ.get("ALRS_API_URL", "http://localhost:8002")
        self.timeout = timeout

    def wait_for_angular(self, timeout: int = None) -> None:
        """Wait for Angular Zone.js stability."""
        to = timeout or self.timeout
        script = """
            return window.getAllAngularTestabilities
                ? window.getAllAngularTestabilities().findIndex(x => !x.isStable()) === -1
                : true;
        """
        try:
            WebDriverWait(self.driver, to).until(lambda d: d.execute_script(script) is True)
        except Exception:
            pass

    def navigate(self, path: str) -> None:
        """Navigate to a specific path and wait for Angular to stabilize."""
        self.driver.get(f"{self.base_url}{path}")
        self.wait_for_angular()

    def wait_for_element(self, by: str, value: str, timeout: int = None) -> WebElement:
        """Wait for an element to be present and visible."""
        to = timeout or self.timeout
        return WebDriverWait(self.driver, to).until(
            EC.visibility_of_element_located((by, value))
        )

    def wait_and_click(self, by: str, value: str, timeout: int = None) -> WebElement:
        """Wait for an element to be clickable and click it, with JS fallback for toasts."""
        to = timeout or self.timeout
        element = WebDriverWait(self.driver, to).until(
            EC.element_to_be_clickable((by, value))
        )
        try:
            element.click()
        except Exception:
            self.driver.execute_script("arguments[0].click();", element)
        return element

    def wait_for_text(self, by: str, value: str, text: str, timeout: int = None) -> bool:
        """Wait for specific text to appear within an element."""
        to = timeout or self.timeout
        return WebDriverWait(self.driver, to).until(
            EC.text_to_be_present_in_element((by, value), text)
        )

    def get_page_title(self) -> str:
        """Get the text of the main <h1> element on the page."""
        h1 = self.wait_for_element(By.TAG_NAME, "h1")
        return h1.text.strip()

    def get_toast_messages(self) -> List[str]:
        """Get all currently visible toast notification messages."""
        toasts = self.driver.find_elements(By.CSS_SELECTOR, "alrs-toast-container .toast-message")
        return [t.text.strip() for t in toasts if t.is_displayed()]

    def take_screenshot(self, name: str) -> str:
        """Manually capture a screenshot and save it to the screenshots directory."""
        screenshot_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "screenshots")
        os.makedirs(screenshot_dir, exist_ok=True)
        path = os.path.join(screenshot_dir, f"{name}.png")
        self.driver.save_screenshot(path)
        return path

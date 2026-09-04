import os
import pytest
from datetime import datetime
from typing import Generator
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

SCREENSHOT_DIR = os.path.join(os.path.dirname(__file__), "screenshots")


@pytest.fixture(scope="function")
def driver() -> Generator[webdriver.Chrome, None, None]:
    """Create a headless Chrome driver per test (parallel-safe)."""
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.set_capability("goog:loggingPrefs", {"browser": "ALL"})
    
    service = Service(ChromeDriverManager().install())
    drv = webdriver.Chrome(service=service, options=options)
    # Default implicit wait just as a fallback
    drv.implicitly_wait(2)
    
    os.makedirs(SCREENSHOT_DIR, exist_ok=True)
    
    yield drv
    
    drv.quit()


@pytest.fixture
def base_url() -> str:
    return os.environ.get("ALRS_BASE_URL", "http://localhost:4200")


@pytest.fixture
def api_url() -> str:
    return os.environ.get("ALRS_API_URL", "http://localhost:8002")


@pytest.fixture
def wait_for_angular(driver):
    """Wait for Angular Zone.js stability."""
    def _wait(timeout=10):
        script = """
            return window.getAllAngularTestabilities
                ? window.getAllAngularTestabilities().findIndex(x => !x.isStable()) === -1
                : true;
        """
        try:
            WebDriverWait(driver, timeout).until(lambda d: d.execute_script(script) is True)
        except Exception:
            pass  # Fall back to element-level expected conditions if Angular hook times out
    return _wait


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """Automatically capture a screenshot on test failure."""
    outcome = yield
    report = outcome.get_result()
    
    if report.when == "call" and report.failed:
        driver = item.funcargs.get("driver") or item.funcargs.get("browser")
        if driver:
            os.makedirs(SCREENSHOT_DIR, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            test_name = item.name.replace("[", "_").replace("]", "_")
            path = os.path.join(SCREENSHOT_DIR, f"FAIL_{test_name}_{timestamp}.png")
            try:
                driver.save_screenshot(path)
                print(f"\n📸 Screenshot saved: {path}")
            except Exception:
                pass

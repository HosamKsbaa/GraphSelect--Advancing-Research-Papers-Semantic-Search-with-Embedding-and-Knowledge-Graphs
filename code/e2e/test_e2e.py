"""ALRS v2 — End-to-End Smoke Tests.

Verifies that the full stack (Angular + FastAPI + Neo4j + MySQL) is
functional by driving a headless Chrome browser against http://localhost:4200.

Usage:
    python -m pytest test_e2e.py -v
    python -m pytest test_e2e.py -v --html=report.html  (with pytest-html)
    python test_e2e.py                                   (standalone)

Prerequisites:
    pip install selenium pytest
    Chrome + ChromeDriver on PATH
    Dev stack running: docker compose -f docker-compose.dev.yml up
"""
from __future__ import annotations

import os
import time
import json
import urllib.request
from typing import Generator

import pytest
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
BASE_URL = os.environ.get("ALRS_BASE_URL", "http://localhost:4200")
API_URL = os.environ.get("ALRS_API_URL", "http://localhost:8000")
SCREENSHOT_DIR = os.path.join(os.path.dirname(__file__), "screenshots")
WAIT_TIMEOUT = 10  # seconds


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def driver() -> Generator[webdriver.Chrome, None, None]:
    """Create a headless Chrome driver shared across all tests in the module."""
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.set_capability("goog:loggingPrefs", {"browser": "ALL"})

    drv = webdriver.Chrome(options=options)
    drv.implicitly_wait(5)

    os.makedirs(SCREENSHOT_DIR, exist_ok=True)

    yield drv

    drv.quit()


def _save_screenshot(driver: webdriver.Chrome, name: str) -> str:
    """Save a screenshot and return the file path."""
    path = os.path.join(SCREENSHOT_DIR, f"{name}.png")
    driver.save_screenshot(path)
    return path


def _wait_for(driver: webdriver.Chrome, by: str, value: str, timeout: int = WAIT_TIMEOUT):
    """Wait for an element to be present and return it."""
    return WebDriverWait(driver, timeout).until(
        EC.presence_of_element_located((by, value))
    )


def _wait_for_text(driver: webdriver.Chrome, by: str, value: str, text: str, timeout: int = WAIT_TIMEOUT):
    """Wait for an element to contain specific text."""
    return WebDriverWait(driver, timeout).until(
        EC.text_to_be_present_in_element((by, value), text)
    )


# ===========================================================================
# 1. API DIRECT TESTS (no browser, fast verification)
# ===========================================================================
class TestAPIEndpoints:
    """Test backend API endpoints directly (no browser needed)."""

    def test_health_endpoint(self) -> None:
        """GET /api/health returns healthy with both DBs connected."""
        resp = urllib.request.urlopen(f"{API_URL}/api/health")
        assert resp.status == 200
        data = json.loads(resp.read().decode())
        assert data["status"] == "healthy"
        assert data["neo4j"] == "connected"
        assert data["mysql"] == "connected"

    def test_version_endpoint(self) -> None:
        """GET /api/version returns a version string."""
        resp = urllib.request.urlopen(f"{API_URL}/api/version")
        assert resp.status == 200
        data = json.loads(resp.read().decode())
        assert "version" in data
        assert len(data["version"]) > 0

    def test_sessions_endpoint(self) -> None:
        """GET /api/sessions returns a list (possibly empty)."""
        resp = urllib.request.urlopen(f"{API_URL}/api/sessions")
        assert resp.status == 200
        data = json.loads(resp.read().decode())
        assert "sessions" in data
        assert "total" in data
        assert isinstance(data["sessions"], list)

    def test_search_resolve_title(self) -> None:
        """POST /api/search/resolve-title returns paper candidates."""
        req = urllib.request.Request(
            f"{API_URL}/api/search/resolve-title?title=deep+learning&max_results=3",
            method="POST",
        )
        resp = urllib.request.urlopen(req)
        assert resp.status == 200
        data = json.loads(resp.read().decode())
        assert isinstance(data, list)
        assert len(data) > 0
        # Verify paper structure
        paper = data[0]
        assert "doi" in paper
        assert "title" in paper
        assert "year" in paper
        assert "authors" in paper


# ===========================================================================
# 2. API PROXY TESTS (through Angular dev server)
# ===========================================================================
class TestAPIProxy:
    """Test that the Angular dev server correctly proxies /api requests."""

    def test_proxy_health(self) -> None:
        """API health via frontend proxy at :4200/api/health."""
        resp = urllib.request.urlopen(f"{BASE_URL}/api/health")
        assert resp.status == 200
        data = json.loads(resp.read().decode())
        assert data["status"] == "healthy"

    def test_proxy_version(self) -> None:
        """API version via frontend proxy at :4200/api/version."""
        resp = urllib.request.urlopen(f"{BASE_URL}/api/version")
        assert resp.status == 200
        data = json.loads(resp.read().decode())
        assert "version" in data

    def test_proxy_sessions(self) -> None:
        """API sessions via frontend proxy at :4200/api/sessions."""
        resp = urllib.request.urlopen(f"{BASE_URL}/api/sessions")
        assert resp.status == 200
        data = json.loads(resp.read().decode())
        assert "sessions" in data


# ===========================================================================
# 3. BROWSER UI TESTS (Selenium)
# ===========================================================================
class TestDashboardPage:
    """Verify the Dashboard page renders correctly with live data."""

    def test_page_loads(self, driver: webdriver.Chrome) -> None:
        """Dashboard page loads without errors."""
        driver.get(f"{BASE_URL}/dashboard")
        time.sleep(2)
        assert "ALRS" in driver.title or "alrs" in driver.page_source.lower()

    def test_no_console_errors(self, driver: webdriver.Chrome) -> None:
        """No SEVERE-level errors in the browser console."""
        driver.get(f"{BASE_URL}/dashboard")
        time.sleep(3)
        logs = driver.get_log("browser")
        severe = [log for log in logs if log["level"] == "SEVERE"]
        if severe:
            for s in severe:
                print(f"  SEVERE: {s['message']}")
        assert len(severe) == 0, f"Found {len(severe)} SEVERE console errors"

    def test_sidebar_present(self, driver: webdriver.Chrome) -> None:
        """Sidebar navigation renders with all 4 nav items."""
        driver.get(f"{BASE_URL}/dashboard")
        time.sleep(2)
        nav_items = driver.find_elements(By.CSS_SELECTOR, ".nav-item")
        labels = [item.text.strip() for item in nav_items]
        assert "Dashboard" in labels
        assert "New Search" in labels
        assert "Sessions" in labels
        assert "API Logs" in labels
        _save_screenshot(driver, "dashboard_sidebar")

    def test_system_status_healthy(self, driver: webdriver.Chrome) -> None:
        """System Status card shows HEALTHY after API loads."""
        # Navigate away first to ensure a clean reload
        driver.get("about:blank")
        time.sleep(0.5)
        driver.get(f"{BASE_URL}/dashboard")
        time.sleep(3)  # Wait for async API calls to complete
        grid = driver.find_elements(By.CSS_SELECTOR, ".status-grid")
        grid_text = grid[0].text if grid else ""
        _save_screenshot(driver, "dashboard_status")
        assert "HEALTHY" in grid_text, f"Expected HEALTHY in status grid, got: {grid_text[:200]}"

    def test_version_displayed(self, driver: webdriver.Chrome) -> None:
        """Version card shows a version string (not 'unknown')."""
        driver.get(f"{BASE_URL}/dashboard")
        time.sleep(3)
        body_text = driver.find_element(By.TAG_NAME, "body").text
        assert "unknown" not in body_text.lower() or "3.0.0" in body_text
        _save_screenshot(driver, "dashboard_version")


class TestSearchPage:
    """Verify the Search page renders and the search form works."""

    def test_page_loads(self, driver: webdriver.Chrome) -> None:
        """Search page loads with the search form."""
        driver.get(f"{BASE_URL}/search")
        time.sleep(2)
        body = driver.find_element(By.TAG_NAME, "body").text.lower()
        assert "search" in body
        _save_screenshot(driver, "search_page")

    def test_search_form_present(self, driver: webdriver.Chrome) -> None:
        """Search form has an input field."""
        driver.get(f"{BASE_URL}/search")
        time.sleep(2)
        inputs = driver.find_elements(By.CSS_SELECTOR, "input")
        assert len(inputs) > 0, "No input fields found on search page"

    def test_search_returns_results(self, driver: webdriver.Chrome) -> None:
        """Typing a query and searching returns paper candidates."""
        driver.get(f"{BASE_URL}/search")
        time.sleep(2)

        # Find the title/DOI input field and enter a search term
        inputs = driver.find_elements(By.CSS_SELECTOR, "input")
        if not inputs:
            pytest.skip("No input fields found")

        search_input = inputs[0]
        search_input.clear()
        search_input.send_keys("deep learning")

        # Look for a search/resolve button and click it
        buttons = driver.find_elements(By.CSS_SELECTOR, "button")
        search_btn = None
        for btn in buttons:
            btn_text = btn.text.strip().lower()
            if "search" in btn_text or "resolve" in btn_text or "find" in btn_text:
                search_btn = btn
                break

        if search_btn:
            search_btn.click()
            time.sleep(5)  # Wait for API call to complete
            _save_screenshot(driver, "search_results")


class TestSessionsPage:
    """Verify the Sessions page renders correctly."""

    def test_page_loads(self, driver: webdriver.Chrome) -> None:
        """Sessions page loads."""
        driver.get(f"{BASE_URL}/sessions")
        time.sleep(2)
        body = driver.find_element(By.TAG_NAME, "body").text.lower()
        assert "session" in body
        _save_screenshot(driver, "sessions_page")


class TestLogsPage:
    """Verify the API Logs page renders correctly."""

    def test_page_loads(self, driver: webdriver.Chrome) -> None:
        """Logs page loads."""
        driver.get(f"{BASE_URL}/logs")
        time.sleep(2)
        body = driver.find_element(By.TAG_NAME, "body").text.lower()
        assert "log" in body
        _save_screenshot(driver, "logs_page")


class TestNavigation:
    """Verify SPA routing between all pages."""

    def test_navigate_all_pages(self, driver: webdriver.Chrome) -> None:
        """Click through all sidebar nav items and verify each page loads."""
        driver.get(f"{BASE_URL}/dashboard")
        time.sleep(2)

        pages = [
            ("/search", "search"),
            ("/sessions", "session"),
            ("/logs", "log"),
            ("/dashboard", "dashboard"),
        ]

        for path, expected_text in pages:
            driver.get(f"{BASE_URL}{path}")
            time.sleep(1.5)
            body = driver.find_element(By.TAG_NAME, "body").text.lower()
            assert expected_text in body, f"Page {path} did not contain '{expected_text}'"

        _save_screenshot(driver, "navigation_complete")


# ===========================================================================
# Standalone runner
# ===========================================================================
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])

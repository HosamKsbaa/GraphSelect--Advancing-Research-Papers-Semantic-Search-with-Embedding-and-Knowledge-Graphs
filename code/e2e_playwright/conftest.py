import os
import pytest
import requests
import uuid
from typing import Generator
from playwright.sync_api import Playwright, Browser, BrowserContext, Page

SCREENSHOT_DIR = os.path.join(os.path.dirname(__file__), "screenshots")
os.makedirs(SCREENSHOT_DIR, exist_ok=True)

BASE_URL = os.environ.get("ALRS_BASE_URL", "http://localhost:4200")
API_URL = os.environ.get("ALRS_API_URL", "http://localhost:4200/api")


@pytest.fixture(scope="session")
def base_url() -> str:
    return BASE_URL


@pytest.fixture(scope="session")
def api_url() -> str:
    return API_URL


@pytest.fixture(scope="function")
def context(browser: Browser) -> Generator[BrowserContext, None, None]:
    context = browser.new_context(
        viewport={"width": 1920, "height": 1080},
        ignore_https_errors=True
    )
    yield context
    context.close()


@pytest.fixture(scope="function")
def page(context: BrowserContext, request) -> Generator[Page, None, None]:
    page = context.new_page()
    page.on("console", lambda msg: print(f"\n[CONSOLE {msg.type}] {msg.text}"))
    page.on("pageerror", lambda err: print(f"\n[PAGE ERROR] {err}"))
    page.on("requestfailed", lambda req: print(f"\n[REQ FAILED] {req.url} {req.failure}"))
    page.on("response", lambda res: print(f"\n[RES] {res.status} {res.url}") if "/api/" in res.url else None)
    yield page
    
    # Save screenshot on test failure
    if hasattr(request.node, "rep_call") and request.node.rep_call.failed:
        test_name = request.node.name.replace("/", "_").replace(":", "_")
        screenshot_path = os.path.join(SCREENSHOT_DIR, f"FAIL_{test_name}.png")
        try:
            page.screenshot(path=screenshot_path, full_page=True)
            print(f"\n[Playwright] Saved failure screenshot to: {screenshot_path}")
        except Exception as e:
            print(f"\n[Playwright] Failed to save screenshot: {e}")
    page.close()


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    rep = outcome.get_result()
    setattr(item, f"rep_{rep.when}", rep)


@pytest.fixture(scope="function")
def test_project():
    """Helper fixture to create a temporary test project via API."""
    project_id = f"test-e2e-{uuid.uuid4().hex[:8]}"
    payload = {
        "id": project_id,
        "name": f"E2E Test Project {project_id}",
        "description": "Automated Playwright E2E Test Suite Project"
    }
    
    # Try creating via API
    try:
        res = requests.post(f"{API_URL}/projects", json=payload, timeout=5)
        if res.status_code not in (200, 201):
            # Fallback if API needs different payload
            pass
    except Exception as e:
        print(f"Warning: could not create project via API: {e}")
        
    yield {
        "id": project_id,
        "name": payload["name"],
        "description": payload["description"]
    }
    
    # Cleanup after test
    try:
        requests.delete(f"{API_URL}/projects/{project_id}", timeout=5)
    except Exception:
        pass

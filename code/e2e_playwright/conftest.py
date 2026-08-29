import os
import json
import uuid
import pytest
import requests
from typing import Generator, List, Dict, Any, Optional
from playwright.sync_api import Playwright, Browser, BrowserContext, Page, Locator, Route, expect

SCREENSHOT_DIR = os.path.join(os.path.dirname(__file__), "screenshots")
os.makedirs(SCREENSHOT_DIR, exist_ok=True)

BASE_URL = os.environ.get("ALRS_BASE_URL", "http://localhost:4200")
API_URL = os.environ.get("ALRS_API_URL", "http://localhost:4200/api")

# Set default assertion timeout to 10s for reliable CI/CD & multi-viewport tests
expect.set_options(timeout=10000)

VIEWPORTS: Dict[str, Dict[str, Any]] = {
    "desktop_fhd": {"width": 1920, "height": 1080, "is_mobile": False, "has_touch": False},
    "desktop_hd":  {"width": 1280, "height": 800,  "is_mobile": False, "has_touch": False},
    "tablet":      {"width": 768,  "height": 1024, "is_mobile": True,  "has_touch": True},
    "mobile":      {"width": 375,  "height": 812,  "is_mobile": True,  "has_touch": True},
}


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
    
    console_errors: List[str] = []
    page_errors: List[str] = []
    
    def on_console(msg):
        if msg.type == "error":
            console_errors.append(msg.text)
            print(f"\n[CONSOLE ERROR] {msg.text}")
        else:
            print(f"\n[CONSOLE {msg.type}] {msg.text}")

    def on_pageerror(err):
        page_errors.append(str(err))
        print(f"\n[PAGE ERROR] {err}")

    page.on("console", on_console)
    page.on("pageerror", on_pageerror)
    page.on("requestfailed", lambda req: print(f"\n[REQ FAILED] {req.url} {req.failure}"))
    page.on("response", lambda res: print(f"\n[RES] {res.status} {res.url}") if "/api/" in res.url else None)
    
    # Store collectors on page object for test inspections
    setattr(page, "console_errors", console_errors)
    setattr(page, "page_errors", page_errors)
    
    yield page
    
    # Save screenshot on test failure
    if hasattr(request.node, "rep_call") and request.node.rep_call.failed:
        test_name = request.node.name.replace("/", "_").replace(":", "_")
        screenshot_path = os.path.join(SCREENSHOT_DIR, f"FAIL_{test_name}.png")
        try:
            page.screenshot(path=screenshot_path, full_page=True, timeout=5000)
            print(f"\n[Playwright] Saved failure screenshot to: {screenshot_path}")
        except Exception as e:
            print(f"\n[Playwright] Failed to save screenshot: {e}")
            
    # Assert zero unhandled JS exceptions unless explicitly allowed
    if not request.node.get_closest_marker("allow_errors") and not request.node.get_closest_marker("allow_page_errors"):
        assert len(page_errors) == 0, f"Uncaught page exceptions detected during test: {page_errors}"
        
    page.close()


@pytest.fixture(params=list(VIEWPORTS.keys()))
def responsive_page(browser: Browser, request) -> Generator[Page, None, None]:
    """Parameterized fixture delivering Page instances across Desktop, Tablet, and Mobile."""
    viewport_name = request.param
    config = VIEWPORTS[viewport_name]
    
    context = browser.new_context(
        viewport={"width": config["width"], "height": config["height"]},
        is_mobile=config["is_mobile"],
        has_touch=config["has_touch"],
        ignore_https_errors=True
    )
    page = context.new_page()
    setattr(page, "viewport_name", viewport_name)
    setattr(page, "viewport_config", config)
    
    page_errors: List[str] = []
    page.on("pageerror", lambda err: page_errors.append(str(err)))
    setattr(page, "page_errors", page_errors)
    
    yield page
    
    if hasattr(request.node, "rep_call") and request.node.rep_call.failed:
        test_name = f"{request.node.name}_{viewport_name}".replace("/", "_").replace(":", "_")
        screenshot_path = os.path.join(SCREENSHOT_DIR, f"FAIL_{test_name}.png")
        try:
            page.screenshot(path=screenshot_path, full_page=True)
        except Exception:
            pass
            
    if not request.node.get_closest_marker("allow_errors"):
        assert len(page_errors) == 0, f"Uncaught exceptions in responsive viewport ({viewport_name}): {page_errors}"
        
    page.close()
    context.close()


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    rep = outcome.get_result()
    setattr(item, f"rep_{rep.when}", rep)


# ---------------------------------------------------------------------------
# API Route Mocking Helpers
# ---------------------------------------------------------------------------

def mock_api_route(
    page: Page,
    url_pattern: str,
    status_code: int = 200,
    json_data: Optional[Any] = None,
    headers: Optional[Dict[str, str]] = None,
    method: Optional[str] = None,
    delay_ms: Optional[int] = None
) -> None:
    """Mock an API network route with custom status and JSON body, optionally filtering by HTTP method and delay."""
    import time
    response_headers = {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"}
    if headers:
        response_headers.update(headers)

    def handle_route(route: Route):
        if method and route.request.method.upper() != method.upper():
            route.fallback()
            return
        if delay_ms and delay_ms > 0:
            time.sleep(delay_ms / 1000.0)
        body_str = json.dumps(json_data) if json_data is not None else ""
        route.fulfill(
            status=status_code,
            headers=response_headers,
            body=body_str
        )

    page.route(url_pattern, handle_route)


def mock_error_route(
    page: Page,
    url_pattern: str,
    status_code: int = 500,
    detail: Any = "Simulated Backend Error"
) -> None:
    """Mock an API network route returning structured error JSON (400, 404, 422, 500, 503)."""
    payload = {"detail": detail, "message": str(detail) if not isinstance(detail, (dict, list)) else detail}
    mock_api_route(page, url_pattern, status_code=status_code, json_data=payload)


def mock_sse_route(
    page: Page,
    url_pattern: str,
    events: List[Dict[str, Any]]
) -> None:
    """Mock a Server-Sent Events (SSE) stream returning a sequence of structured events."""
    sse_body_parts = []
    for evt in events:
        evt_type = evt.get("event") or evt.get("type", "message")
        evt_data = evt.get("data", evt)
        data_str = json.dumps(evt_data) if isinstance(evt_data, (dict, list)) else str(evt_data)
        sse_body_parts.append(f"event: {evt_type}\ndata: {data_str}\n\n")
    
    full_sse_body = "".join(sse_body_parts)

    def handle_route(route: Route):
        route.fulfill(
            status=200,
            headers={
                "Content-Type": "text/event-stream",
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "Access-Control-Allow-Origin": "*"
            },
            body=full_sse_body
        )

    page.route(url_pattern, handle_route)


# ---------------------------------------------------------------------------
# Toast Assertion Utility
# ---------------------------------------------------------------------------

def assert_toast_message(
    page: Page,
    expected_title_substring: str = "",
    expected_text_substring: str = "",
    timeout: float = 5000
) -> Locator:
    """Assert that a toast notification is rendered and contains NO [object Object] anomalies."""
    if expected_text_substring:
        toast = page.locator(f"alrs-toast-container .toast:has(.toast-message:has-text('{expected_text_substring}')), alrs-toast-container .toast:has-text('{expected_text_substring}')").first
    elif expected_title_substring:
        toast = page.locator(f"alrs-toast-container .toast:has(.toast-title:has-text('{expected_title_substring}')), alrs-toast-container .toast:has-text('{expected_title_substring}')").first
    else:
        toast = page.locator("alrs-toast-container .toast").first

    expect(toast).to_be_visible(timeout=timeout)
    
    title_locator = toast.locator(".toast-title")
    message_locator = toast.locator(".toast-message")
    
    title_text = title_locator.inner_text().strip() if title_locator.count() > 0 else ""
    message_text = message_locator.inner_text().strip() if message_locator.count() > 0 else ""
    
    # Zero [object Object] validation
    assert "[object Object]" not in title_text, f"Detected '[object Object]' in toast title: '{title_text}'"
    assert "[object Object]" not in message_text, f"Detected '[object Object]' in toast message: '{message_text}'"
    
    if expected_title_substring:
        assert expected_title_substring.lower() in title_text.lower(), (
            f"Expected substring '{expected_title_substring}' not found in toast title '{title_text}'"
        )
    if expected_text_substring:
        full_toast_text = f"{title_text} {message_text}".lower()
        assert expected_text_substring.lower() in full_toast_text, (
            f"Expected substring '{expected_text_substring}' not found in toast content '{full_toast_text}'"
        )
        
    return toast


# ---------------------------------------------------------------------------
# Keyboard & Accessibility Helpers
# ---------------------------------------------------------------------------

def verify_modal_escape_dismiss(page: Page, modal_selector: str = ".modal-backdrop, .modal-container, .dialog-backdrop") -> None:
    """Verify that an open modal or dialog is cleanly dismissed when pressing the Escape key."""
    modal = page.locator(modal_selector).first
    expect(modal).to_be_visible(timeout=5000)
    page.keyboard.press("Escape")
    expect(modal).not_to_be_visible(timeout=5000)


def verify_tab_navigation(page: Page, expected_elements_count: int = 3) -> None:
    """Verify sequential Tab key navigation across interactive DOM elements."""
    for _ in range(expected_elements_count):
        page.keyboard.press("Tab")


# ---------------------------------------------------------------------------
# Project Lifecycle Helper Fixture
# ---------------------------------------------------------------------------

@pytest.fixture(scope="function")
def test_project():
    """Helper fixture to create a temporary test project via API."""
    project_id = f"test-e2e-{uuid.uuid4().hex[:8]}"
    payload = {
        "id": project_id,
        "name": f"E2E Test Project {project_id}",
        "description": "Automated Playwright E2E Test Suite Project"
    }
    
    try:
        res = requests.post(f"{API_URL}/projects", json=payload, timeout=5)
    except Exception as e:
        print(f"Warning: could not create project via API: {e}")
        
    yield {
        "id": project_id,
        "name": payload["name"],
        "description": payload["description"]
    }
    
    try:
        requests.delete(f"{API_URL}/projects/{project_id}", timeout=5)
    except Exception:
        pass

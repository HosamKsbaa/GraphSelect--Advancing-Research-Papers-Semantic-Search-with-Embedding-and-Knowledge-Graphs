"""Comprehensive Playwright E2E tests for System Tools (Requirement R1.8).

Covers:
- System Status View (/system-status):
    - Health metric badges (System Status, Neo4j, MySQL, Version, Sessions count).
    - Degraded, connected, disconnected, offline badge style classes.
    - Recent session cards with status badges (completed, running, failed), questions preview, and stats.
    - Empty sessions state and CTA button navigation.
    - Backend connection error banner handling.
    - Header 'New Search' navigation button.
- Logs & Monitoring View (/logs):
    - Tab navigation (Application Logs, Scholarly API Requests, Agent Traces).
    - Severity dropdown filters (DEBUG, INFO, WARNING, ERROR).
    - Scholar service dropdown filters (OpenAlex, OpenCitations, Gemini).
    - Agent trace filters (project selector, agent name input, since/end date inputs).
    - Row limit dropdown (25, 50, 100, 250 rows) and 'Refresh Console' action.
    - Expandable JSON payload viewer (<details>/<summary>) and clipboard copy action ('Copied!' feedback).
    - Empty logs states for each tab.
- Debug Console View (/debug):
    - Subsystem 1: OpenAlex paper retrieval test runner (DOI input, SUCCESS / FAILED result card, metadata, latency).
    - Subsystem 2: Gemini text embedding test runner (Text input, dimensions, first 5 values vector array, latency).
    - Subsystem 3: Semantic cosine similarity test runner (Paragraphs A & B, dynamic gauge bar score 0.0-1.0, color classes gauge-high / gauge-medium / gauge-low, latency).
    - Gemini API error direct toast redirection ('Go to Settings' action link to /settings).
- Settings View (/settings):
    - Backend Connection: API Base URL input configuration.
    - API Keys: Gemini API key input with show/hide toggle (password vs text masking).
    - API Keys: OpenAlex API key input with show/hide toggle (password vs text masking).
    - Active vs Not Set status badges for API keys.
    - Contact Info: OpenAlex contact email input.
    - System Info: Read-only embedding model and dimensions readout.
    - Save Settings flow with toast feedback (asserting zero [object Object] anomalies).
    - Save failure error handling and toast feedback.
- Global Navigation:
    - Sidebar navigation flow across all system tools (/system-status, /logs, /debug, /settings).
"""
import sys
import os
import json
import pytest
from playwright.sync_api import Page, expect

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from e2e_playwright.conftest import mock_api_route, mock_error_route, assert_toast_message
from e2e_playwright.pages.base_page import BasePage
from e2e_playwright.pages.system_status_page import SystemStatusPage
from e2e_playwright.pages.logs_page import LogsPage
from e2e_playwright.pages.debug_page import DebugPage
from e2e_playwright.pages.settings_page import SettingsPage


# ===========================================================================
# 1. SYSTEM STATUS VIEW TESTS (/system-status)
# ===========================================================================

def test_system_status_healthy_metrics_and_badges(page: Page, base_url: str):
    """Test System Status view displays healthy metric badges for Neo4j, MySQL, Version, and Sessions."""
    mock_api_route(page, "**/api/health*", status_code=200, json_data={
        "status": "healthy",
        "neo4j": "connected",
        "mysql": "connected"
    })
    mock_api_route(page, "**/api/version*", status_code=200, json_data={
        "version": "v3.0.0-alpha.1"
    })
    mock_api_route(page, "**/api/sessions*", status_code=200, json_data={
        "sessions": [
            {
                "session_id": "sess-001",
                "seed_doi": "10.1145/3534678.3539078",
                "research_questions": ["How to scale graph embeddings?"],
                "similarity_threshold": 0.75,
                "max_depth": 3,
                "mode": "automated",
                "status": "completed",
                "papers_discovered": 42,
                "papers_relevant": 15,
                "current_depth": 3,
                "created_at": "2026-08-27T10:00:00Z",
                "updated_at": "2026-08-27T10:05:00Z"
            },
            {
                "session_id": "sess-002",
                "seed_doi": "10.1109/SRC65875.2025.11263707",
                "research_questions": ["What are the multi-agent consensus protocols?"],
                "similarity_threshold": 0.70,
                "max_depth": 2,
                "mode": "interactive",
                "status": "running",
                "papers_discovered": 18,
                "papers_relevant": 6,
                "current_depth": 1,
                "created_at": "2026-08-27T11:00:00Z",
                "updated_at": None
            }
        ],
        "total": 2
    })

    status_page = SystemStatusPage(page, base_url)
    status_page.navigate()

    # Verify Page Title and Header
    expect(status_page.page_title).to_contain_text("SystemStatus")
    expect(page.locator(".page-header .text-secondary")).to_contain_text("Automated Literature Review System")

    # Verify Health Badges
    expect(status_page.system_status_badge).to_be_visible()
    expect(status_page.system_status_badge).to_contain_text("healthy", ignore_case=True)
    expect(status_page.system_status_badge).to_have_class("badge badge-success")

    expect(status_page.neo4j_status_badge).to_be_visible()
    expect(status_page.neo4j_status_badge).to_contain_text("connected", ignore_case=True)
    expect(status_page.neo4j_status_badge).to_have_class("badge badge-success")

    expect(status_page.mysql_status_badge).to_be_visible()
    expect(status_page.mysql_status_badge).to_contain_text("connected", ignore_case=True)
    expect(status_page.mysql_status_badge).to_have_class("badge badge-success")

    # Verify Version and Sessions Count readouts
    expect(status_page.version_display).to_contain_text("v3.0.0-alpha.1")
    expect(status_page.sessions_count_display).to_contain_text("2")

    # Verify POM helper methods
    assert status_page.get_system_health().lower() == "healthy"
    assert status_page.get_neo4j_status().lower() == "connected"
    assert status_page.get_mysql_status().lower() == "connected"
    assert status_page.get_version() == "v3.0.0-alpha.1"
    assert status_page.get_sessions_count() == 2


def test_system_status_degraded_and_offline_health_states(page: Page, base_url: str):
    """Test System Status view handles degraded system and disconnected database states."""
    mock_api_route(page, "**/api/health*", status_code=200, json_data={
        "status": "degraded",
        "neo4j": "connected",
        "mysql": "disconnected"
    })
    mock_api_route(page, "**/api/version*", status_code=200, json_data={
        "version": "3.0.0"
    })
    mock_api_route(page, "**/api/sessions*", status_code=200, json_data={
        "sessions": [],
        "total": 0
    })

    status_page = SystemStatusPage(page, base_url)
    status_page.navigate()

    # System Status badge should show degraded / warning
    expect(status_page.system_status_badge).to_contain_text("degraded", ignore_case=True)
    expect(status_page.system_status_badge).to_have_class("badge badge-warning")

    # Neo4j should show connected / success
    expect(status_page.neo4j_status_badge).to_contain_text("connected", ignore_case=True)
    expect(status_page.neo4j_status_badge).to_have_class("badge badge-success")

    # MySQL should show disconnected / error
    expect(status_page.mysql_status_badge).to_contain_text("disconnected", ignore_case=True)
    expect(status_page.mysql_status_badge).to_have_class("badge badge-error")


def test_system_status_recent_sessions_cards_and_badges(page: Page, base_url: str):
    """Test recent session cards render DOIs, status badges (completed, running, failed), questions, and stats."""
    mock_api_route(page, "**/api/health*", status_code=200, json_data={
        "status": "healthy",
        "neo4j": "connected",
        "mysql": "connected"
    })
    mock_api_route(page, "**/api/version*", status_code=200, json_data={"version": "v3.0.0"})
    mock_api_route(page, "**/api/sessions*", status_code=200, json_data={
        "sessions": [
            {
                "session_id": "sess-101",
                "seed_doi": "10.1145/3534678.3539078",
                "research_questions": [
                    "How does GraphSelect optimize embedding traversal?",
                    "What is the hybrid PageRank convergence speed?"
                ],
                "similarity_threshold": 0.80,
                "max_depth": 3,
                "mode": "automated",
                "status": "completed",
                "papers_discovered": 54,
                "papers_relevant": 21,
                "current_depth": 3,
                "created_at": "2026-08-27T08:00:00Z",
                "updated_at": "2026-08-27T08:12:00Z"
            },
            {
                "session_id": "sess-102",
                "seed_doi": "10.1109/SRC65875.2025.11263707",
                "research_questions": ["Are citation hallucinations eliminated by GCDL?"],
                "similarity_threshold": 0.70,
                "max_depth": 2,
                "mode": "interactive",
                "status": "running",
                "papers_discovered": 15,
                "papers_relevant": 5,
                "current_depth": 1,
                "created_at": "2026-08-27T09:00:00Z",
                "updated_at": None
            },
            {
                "session_id": "sess-103",
                "seed_doi": "10.1016/j.jss.2024.112000",
                "research_questions": ["Timeout failure analysis in OpenCitations crawler"],
                "similarity_threshold": 0.65,
                "max_depth": 1,
                "mode": "automated",
                "status": "failed",
                "papers_discovered": 0,
                "papers_relevant": 0,
                "current_depth": 0,
                "created_at": "2026-08-27T09:30:00Z",
                "updated_at": None
            }
        ],
        "total": 3
    })

    status_page = SystemStatusPage(page, base_url)
    status_page.navigate()

    expect(status_page.session_cards).to_have_count(3)

    # Card 1: Completed session
    card1 = status_page.session_cards.nth(0)
    expect(card1.locator(".session-header .mono")).to_contain_text("10.1145/3534678.3539078")
    expect(card1.locator(".session-header .badge")).to_contain_text("completed", ignore_case=True)
    expect(card1.locator(".session-header .badge")).to_have_class("badge badge-success")
    expect(card1.locator(".question-text").first).to_contain_text("How does GraphSelect optimize embedding traversal?")
    expect(card1.locator(".session-stats")).to_contain_text("54 papers")
    expect(card1.locator(".session-stats")).to_contain_text("21 relevant")
    expect(card1.locator(".session-stats")).to_contain_text("Depth 3/3")

    # Card 2: Running session
    card2 = status_page.session_cards.nth(1)
    expect(card2.locator(".session-header .mono")).to_contain_text("10.1109/SRC65875.2025.11263707")
    expect(card2.locator(".session-header .badge")).to_contain_text("running", ignore_case=True)
    expect(card2.locator(".session-header .badge")).to_have_class("badge badge-warning")
    expect(card2.locator(".session-stats")).to_contain_text("15 papers")
    expect(card2.locator(".session-stats")).to_contain_text("Depth 1/2")

    # Card 3: Failed session
    card3 = status_page.session_cards.nth(2)
    expect(card3.locator(".session-header .mono")).to_contain_text("10.1016/j.jss.2024.112000")
    expect(card3.locator(".session-header .badge")).to_contain_text("failed", ignore_case=True)
    expect(card3.locator(".session-header .badge")).to_have_class("badge badge-error")
    expect(card3.locator(".session-stats")).to_contain_text("0 papers")
    expect(card3.locator(".session-stats")).to_contain_text("Depth 0/1")


def test_system_status_empty_sessions_state_and_cta(page: Page, base_url: str):
    """Test System Status view renders empty state card and 'Start a Search' CTA when 0 sessions exist."""
    mock_api_route(page, "**/api/health*", status_code=200, json_data={
        "status": "healthy",
        "neo4j": "connected",
        "mysql": "connected"
    })
    mock_api_route(page, "**/api/version*", status_code=200, json_data={"version": "v3.0.0"})
    mock_api_route(page, "**/api/sessions*", status_code=200, json_data={
        "sessions": [],
        "total": 0
    })

    status_page = SystemStatusPage(page, base_url)
    status_page.navigate()

    expect(status_page.empty_sessions_state).to_be_visible()
    expect(status_page.empty_sessions_state.locator("h3")).to_contain_text("No sessions yet")
    expect(status_page.empty_sessions_state.locator("p")).to_contain_text("Start your first literature search")

    cta_link = status_page.empty_sessions_state.locator("a:has-text('Start a Search')")
    expect(cta_link).to_be_visible()
    expect(cta_link).to_have_attribute("href", "/search")

    # Click CTA link and assert navigation to /search
    cta_link.click()
    page.wait_for_url("**/search", timeout=5000)
    expect(page.locator("h1.page-title")).to_contain_text("New Literature Search")


def test_system_status_connection_error_banner(page: Page, base_url: str):
    """Test System Status view renders Connection Error banner and offline badges when backend is down."""
    mock_error_route(page, "**/api/health*", status_code=500, detail="Backend service unavailable")
    mock_error_route(page, "**/api/version*", status_code=500, detail="Service unavailable")
    mock_error_route(page, "**/api/sessions*", status_code=500, detail="Service unavailable")

    status_page = SystemStatusPage(page, base_url)
    status_page.navigate()

    # Verify error banner
    expect(status_page.error_banner).to_be_visible(timeout=5000)
    expect(status_page.error_banner.locator("strong")).to_contain_text("Connection Error")
    expect(status_page.error_banner.locator("p")).to_contain_text("Cannot connect to backend")

    # Verify fallback offline and disconnected badges
    expect(status_page.system_status_badge).to_contain_text("offline", ignore_case=True)
    expect(status_page.neo4j_status_badge).to_contain_text("disconnected", ignore_case=True)
    expect(status_page.mysql_status_badge).to_contain_text("disconnected", ignore_case=True)


def test_system_status_header_new_search_navigation(page: Page, base_url: str):
    """Test Header 'New Search' button on System Status page navigates to /search."""
    mock_api_route(page, "**/api/health*", status_code=200, json_data={
        "status": "healthy",
        "neo4j": "connected",
        "mysql": "connected"
    })
    mock_api_route(page, "**/api/version*", status_code=200, json_data={"version": "v3.0.0"})
    mock_api_route(page, "**/api/sessions*", status_code=200, json_data={"sessions": [], "total": 0})

    status_page = SystemStatusPage(page, base_url)
    status_page.navigate()

    expect(status_page.new_search_btn).to_be_visible()
    status_page.new_search_btn.click()
    page.wait_for_url("**/search", timeout=5000)
    expect(page.locator("h1.page-title")).to_contain_text("New Literature Search")


# ===========================================================================
# 2. LOGS & MONITORING VIEW TESTS (/logs)
# ===========================================================================

def test_logs_navigation_tabs_switching(page: Page, base_url: str):
    """Test Logs view tab navigation between Application Logs, Scholarly API Requests, and Agent Traces."""
    mock_api_route(page, "**/api/logs*", status_code=200, json_data=[])
    mock_api_route(page, "**/api/logs/api-requests*", status_code=200, json_data=[])
    mock_api_route(page, "**/api/logs/agent-traces*", status_code=200, json_data={"traces": [], "total": 0})
    mock_api_route(page, "**/api/projects*", status_code=200, json_data=[])

    logs_page = LogsPage(page, base_url)
    logs_page.navigate()

    expect(logs_page.page_title).to_contain_text("Logs & Monitoring")

    # Default tab is Application Logs
    expect(logs_page.tab_app_logs).to_have_class("tab-btn active")
    expect(logs_page.level_select).to_be_visible()
    expect(logs_page.service_select).not_to_be_visible()

    # Switch to Scholarly API Requests tab
    logs_page.switch_tab("api")
    expect(logs_page.tab_api_logs).to_have_class("tab-btn active")
    expect(logs_page.tab_app_logs).not_to_have_class("tab-btn active")
    expect(logs_page.service_select).to_be_visible()
    expect(logs_page.level_select).not_to_be_visible()

    # Switch to Agent Traces tab
    logs_page.switch_tab("agent")
    expect(logs_page.tab_agent_traces).to_have_class("tab-btn active")
    expect(logs_page.tab_api_logs).not_to_have_class("tab-btn active")
    expect(logs_page.project_select).to_be_visible()
    expect(logs_page.agent_name_input).to_be_visible()
    expect(logs_page.since_date_input).to_be_visible()
    expect(logs_page.end_date_input).to_be_visible()

    # Switch back to Application Logs
    logs_page.switch_tab("app")
    expect(logs_page.tab_app_logs).to_have_class("tab-btn active")
    expect(logs_page.level_select).to_be_visible()


def test_logs_application_logs_filtering_and_badges(page: Page, base_url: str):
    """Test Application Logs rendering with severity badge classes (DEBUG, INFO, WARNING, ERROR) and filtering."""
    mock_logs = [
        {
            "id": 1,
            "level": "DEBUG",
            "module": "engine.traversal",
            "message": "BFS Queue initialized with seed DOI 10.1145/3534678.3539078",
            "session_id": "sess-12345678",
            "extra": {"depth": 0, "queue_len": 1},
            "created_at": "2026-08-27T12:00:01Z"
        },
        {
            "id": 2,
            "level": "INFO",
            "module": "engine.ranker",
            "message": "Computed hybrid PageRank scores for 42 papers",
            "session_id": "sess-12345678",
            "extra": None,
            "created_at": "2026-08-27T12:00:05Z"
        },
        {
            "id": 3,
            "level": "WARNING",
            "module": "clients.opencitations",
            "message": "Rate limit threshold approaching 80%",
            "session_id": None,
            "extra": {"quota_remaining": 20},
            "created_at": "2026-08-27T12:00:10Z"
        },
        {
            "id": 4,
            "level": "ERROR",
            "module": "clients.gemini",
            "message": "Quota exceeded during embedding computation",
            "session_id": "sess-12345678",
            "extra": {"error_code": 429},
            "created_at": "2026-08-27T12:00:15Z"
        }
    ]

    mock_api_route(page, "**/api/logs*", status_code=200, json_data=mock_logs)

    logs_page = LogsPage(page, base_url)
    logs_page.navigate()

    expect(logs_page.log_rows).to_have_count(4)

    # Check row 1 (DEBUG) - target severity badge in 2nd column
    row_debug = logs_page.log_rows.nth(0)
    expect(row_debug.locator("td:nth-child(2) .badge")).to_contain_text("DEBUG")
    expect(row_debug.locator("td:nth-child(2) .badge")).to_have_class("badge badge-debug")
    expect(row_debug.locator(".log-message .message-text")).to_contain_text("BFS Queue initialized")
    expect(row_debug.locator(".session-tag")).to_contain_text("session: sess-123")

    # Check row 2 (INFO)
    row_info = logs_page.log_rows.nth(1)
    expect(row_info.locator("td:nth-child(2) .badge")).to_contain_text("INFO")
    expect(row_info.locator("td:nth-child(2) .badge")).to_have_class("badge badge-info")
    expect(row_info.locator(".log-message .message-text")).to_contain_text("Computed hybrid PageRank scores")

    # Check row 3 (WARNING)
    row_warn = logs_page.log_rows.nth(2)
    expect(row_warn.locator("td:nth-child(2) .badge")).to_contain_text("WARNING")
    expect(row_warn.locator("td:nth-child(2) .badge")).to_have_class("badge badge-warning")

    # Check row 4 (ERROR)
    row_err = logs_page.log_rows.nth(3)
    expect(row_err.locator("td:nth-child(2) .badge")).to_contain_text("ERROR")
    expect(row_err.locator("td:nth-child(2) .badge")).to_have_class("badge badge-error")

    # Test filtering by severity level
    mock_filtered = [mock_logs[3]]
    mock_api_route(page, "**/api/logs*level=ERROR*", status_code=200, json_data=mock_filtered)
    logs_page.filter_by_level("ERROR")
    expect(logs_page.log_rows).to_have_count(1)
    expect(logs_page.log_rows.first.locator("td:nth-child(2) .badge")).to_contain_text("ERROR")


def test_logs_scholarly_api_requests_filtering_and_status_codes(page: Page, base_url: str):
    """Test Scholarly API Requests logs with service badges (OpenAlex, OpenCitations, Gemini), HTTP methods, and status classes."""
    mock_api_logs = [
        {
            "id": 201,
            "service": "OpenAlex",
            "method": "GET",
            "url": "https://api.openalex.org/works/https://doi.org/10.1145/3534678.3539078",
            "status_code": 200,
            "response_time_ms": 145,
            "payload_summary": "Title: GraphSelect, Cited: 48",
            "request_body": None,
            "response_body": "{\"id\": \"W312\", \"doi\": \"10.1145/3534678.3539078\"}",
            "session_id": "sess-aabbccdd",
            "created_at": "2026-08-27T12:05:00Z"
        },
        {
            "id": 202,
            "service": "OpenCitations",
            "method": "GET",
            "url": "https://opencitations.net/index/coci/api/v1/references/10.1145/3534678.3539078",
            "status_code": 404,
            "response_time_ms": 320,
            "payload_summary": "No citation records found for DOI",
            "request_body": None,
            "response_body": "[]",
            "session_id": "sess-aabbccdd",
            "created_at": "2026-08-27T12:05:02Z"
        },
        {
            "id": 203,
            "service": "Gemini",
            "method": "POST",
            "url": "https://generativelanguage.googleapis.com/v1beta/models/gemini-embedding-2:embedContent",
            "status_code": 500,
            "response_time_ms": 890,
            "payload_summary": "Embedding request failure: Internal server error",
            "request_body": "{\"model\": \"gemini-embedding-2\", \"content\": \"Test\"}",
            "response_body": "{\"error\": {\"code\": 500, \"message\": \"Internal error\"}}",
            "session_id": None,
            "created_at": "2026-08-27T12:05:05Z"
        }
    ]

    mock_api_route(page, "**/api/logs/api-requests*", status_code=200, json_data=mock_api_logs)

    logs_page = LogsPage(page, base_url)
    logs_page.navigate()
    logs_page.switch_tab("api")

    expect(logs_page.log_rows).to_have_count(3)

    # Row 1: OpenAlex (200 OK -> badge-success)
    row1 = logs_page.log_rows.nth(0)
    expect(row1.locator("td:nth-child(2) .badge")).to_contain_text("OpenAlex")
    expect(row1.locator("td:nth-child(3)")).to_contain_text("GET")
    expect(row1.locator(".log-url .url-text")).to_contain_text("https://api.openalex.org/works")
    expect(row1.locator("td:nth-child(5) .badge")).to_contain_text("200")
    expect(row1.locator("td:nth-child(5) .badge")).to_have_class("badge badge-success")
    expect(row1.locator("td:nth-child(6)")).to_contain_text("145ms")

    # Row 2: OpenCitations (404 Not Found -> badge-warning)
    row2 = logs_page.log_rows.nth(1)
    expect(row2.locator("td:nth-child(2) .badge")).to_contain_text("OpenCitations")
    expect(row2.locator("td:nth-child(5) .badge")).to_contain_text("404")
    expect(row2.locator("td:nth-child(5) .badge")).to_have_class("badge badge-warning")
    expect(row2.locator("td:nth-child(6)")).to_contain_text("320ms")

    # Row 3: Gemini (500 Error -> badge-error)
    row3 = logs_page.log_rows.nth(2)
    expect(row3.locator("td:nth-child(2) .badge")).to_contain_text("Gemini")
    expect(row3.locator("td:nth-child(3)")).to_contain_text("POST")
    expect(row3.locator("td:nth-child(5) .badge")).to_contain_text("500")
    expect(row3.locator("td:nth-child(5) .badge")).to_have_class("badge badge-error")
    expect(row3.locator("td:nth-child(6)")).to_contain_text("890ms")

    # Filter by service dropdown
    mock_alex_only = [mock_api_logs[0]]
    mock_api_route(page, "**/api/logs/api-requests*service=OpenAlex*", status_code=200, json_data=mock_alex_only)
    logs_page.filter_by_service("OpenAlex")
    expect(logs_page.log_rows).to_have_count(1)
    expect(logs_page.log_rows.first.locator("td:nth-child(2) .badge")).to_contain_text("OpenAlex")


def test_logs_agent_traces_inspection_and_filtering(page: Page, base_url: str):
    """Test Agent Traces tab renders trace cards with agent badge, action summary, token count, outcome, and tool calls."""
    mock_projects = [
        {"id": "proj-1", "name": "Graph Neural Networks Review", "topic": "GNN"}
    ]
    mock_traces = [
        {
            "id": "trace-001",
            "project_id": "proj-1",
            "agent_name": "planner",
            "action_summary": "Generated 5-section narrative outline with DOI bindings",
            "token_count": 1240,
            "timestamp": "2026-08-27T12:10:00Z",
            "decision_outcome": "Approved sections: Introduction, Literature Review, Methodology, Results, Conclusion",
            "tool_calls": [
                {"name": "get_project_literature", "args": {"project_id": "proj-1"}},
                {"name": "format_bibtex_keys", "args": {"dois": ["10.1145/3534678.3539078"]}}
            ],
            "llm_prompt": "Generate an outline given the following 15 papers...",
            "llm_response": "{\"sections\": [{\"title\": \"Introduction\"}]}"
        },
        {
            "id": "trace-002",
            "project_id": "proj-1",
            "agent_name": "reviewer",
            "action_summary": "Executed 5-dimension rubric critique on section 2",
            "token_count": 890,
            "timestamp": "2026-08-27T12:12:00Z",
            "decision_outcome": "Score: 4.8 / 5.0 — Approved without hallucinations",
            "tool_calls": [],
            "llm_prompt": "Evaluate section 2 against rubric...",
            "llm_response": "Score 4.8/5.0. Citations are verified against Neo4j."
        }
    ]

    mock_api_route(page, "**/api/projects*", status_code=200, json_data=mock_projects)
    mock_api_route(page, "**/api/logs/agent-traces*", status_code=200, json_data={"traces": mock_traces, "total": 2})

    logs_page = LogsPage(page, base_url)
    logs_page.navigate()
    logs_page.switch_tab("agent")

    expect(logs_page.trace_cards).to_have_count(2)

    # Trace Card 1: Planner
    card1 = logs_page.trace_cards.nth(0)
    expect(card1.locator(".trace-info .badge-info")).to_contain_text("planner")
    expect(card1.locator(".trace-action")).to_contain_text("Generated 5-section narrative outline")
    expect(card1.locator(".trace-meta .badge-accent")).to_contain_text("1240 tokens")
    expect(card1.locator(".trace-outcome")).to_contain_text("Approved sections: Introduction")

    # Trace Card 2: Reviewer
    card2 = logs_page.trace_cards.nth(1)
    expect(card2.locator(".trace-info .badge-info")).to_contain_text("reviewer")
    expect(card2.locator(".trace-action")).to_contain_text("Executed 5-dimension rubric critique")
    expect(card2.locator(".trace-meta .badge-accent")).to_contain_text("890 tokens")
    expect(card2.locator(".trace-outcome")).to_contain_text("Score: 4.8 / 5.0")


def test_logs_limit_dropdown_and_refresh_action(page: Page, base_url: str):
    """Test Logs limit dropdown selection (25, 50, 100, 250 rows) and Refresh Console button trigger."""
    last_requested_limit = []

    def handle_logs_route(route):
        url = route.request.url
        last_requested_limit.append(url)
        route.fulfill(
            status=200,
            headers={"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
            body=json.dumps([])
        )

    page.route("**/api/logs*", handle_logs_route)

    logs_page = LogsPage(page, base_url)
    logs_page.navigate()

    expect(logs_page.limit_select).to_be_visible()

    # Change limit to 50
    logs_page.limit_select.select_option(label="50 rows")
    page.wait_for_timeout(300)
    assert any("limit=50" in u for u in last_requested_limit), f"Expected limit=50 in requests: {last_requested_limit}"

    # Change limit to 25
    logs_page.limit_select.select_option(label="25 rows")
    page.wait_for_timeout(300)
    assert any("limit=25" in u for u in last_requested_limit), f"Expected limit=25 in requests: {last_requested_limit}"

    # Click Refresh Console button
    before_count = len(last_requested_limit)
    logs_page.click_refresh()
    page.wait_for_timeout(300)
    assert len(last_requested_limit) > before_count, "Refresh Console did not trigger API reload"


def test_logs_expandable_json_payload_and_clipboard_copy(page: Page, base_url: str):
    """Test expandable JSON payload (<details>/<summary>) and clipboard copy button ('Copied!' feedback)."""
    mock_log_with_extra = [
        {
            "id": 99,
            "level": "INFO",
            "module": "engine.search",
            "message": "Executed semantic paper query",
            "session_id": "sess-json-test",
            "extra": {
                "query": "Deep graph neural networks",
                "similarity_threshold": 0.75,
                "filters": {"min_year": 2020}
            },
            "created_at": "2026-08-27T12:20:00Z"
        }
    ]

    mock_api_route(page, "**/api/logs*", status_code=200, json_data=mock_log_with_extra)

    logs_page = LogsPage(page, base_url)
    logs_page.navigate()

    expect(logs_page.log_rows).to_have_count(1)

    details = page.locator(".extra-details").first
    expect(details).to_be_visible()

    # Summary text
    summary = details.locator("summary")
    expect(summary).to_contain_text("View extra payload")

    # Click summary to expand details
    summary.click()

    pre_elem = details.locator("pre.extra-pre")
    expect(pre_elem).to_be_visible()
    expect(pre_elem).to_contain_text("Deep graph neural networks")
    expect(pre_elem).to_contain_text("similarity_threshold")

    # Copy JSON button
    copy_btn = details.locator("button.copy-btn")
    expect(copy_btn).to_be_visible()
    expect(copy_btn).to_contain_text("Copy JSON")

    # Click copy button and assert feedback
    copy_btn.click()
    expect(copy_btn).to_contain_text("Copied!")


def test_logs_empty_states_across_tabs(page: Page, base_url: str):
    """Test empty states display informative messages across all three tabs."""
    mock_api_route(page, "**/api/logs*", status_code=200, json_data=[])
    mock_api_route(page, "**/api/logs/api-requests*", status_code=200, json_data=[])
    mock_api_route(page, "**/api/logs/agent-traces*", status_code=200, json_data={"traces": [], "total": 0})
    mock_api_route(page, "**/api/projects*", status_code=200, json_data=[])

    logs_page = LogsPage(page, base_url)
    logs_page.navigate()

    # App tab empty state
    expect(logs_page.empty_logs_msg).to_be_visible()
    expect(logs_page.empty_logs_msg).to_contain_text("No internal application logs found")

    # API tab empty state
    logs_page.switch_tab("api")
    expect(logs_page.empty_logs_msg).to_be_visible()
    expect(logs_page.empty_logs_msg).to_contain_text("No scholarly API crawler transactions logged")

    # Agent tab empty state
    logs_page.switch_tab("agent")
    expect(logs_page.empty_logs_msg).to_be_visible()
    expect(logs_page.empty_logs_msg).to_contain_text("No agent traces found")


# ===========================================================================
# 3. DEBUG CONSOLE VIEW TESTS (/debug)
# ===========================================================================

def test_debug_paper_retrieval_success_flow(page: Page, base_url: str):
    """Test Debug Console Paper Retrieval test runner: input DOI, run test, verify SUCCESS card and metadata."""
    mock_api_route(page, "**/api/debug/test-retrieve*", status_code=200, json_data={
        "success": True,
        "elapsed_ms": 178,
        "doi": "10.1145/3534678.3539078",
        "title": "GraphSelect: Embedding-Guided Graph Traversal for Scalable Semantic Paper Search",
        "year": 2022,
        "cited_by_count": 48,
        "abstract": "Semantic paper discovery requires efficient graph traversal across citation networks with high precision."
    })

    debug_page = DebugPage(page, base_url)
    debug_page.navigate()

    expect(debug_page.page_title).to_contain_text("Debug Console")

    # Run paper retrieval test
    debug_page.test_paper_retrieval("10.1145/3534678.3539078")

    # Verify result card
    expect(debug_page.retrieve_result_card).to_be_visible()
    expect(debug_page.retrieve_result_card).to_have_class("result-card result-success")

    # Verify badge and latency
    expect(debug_page.retrieve_badge).to_contain_text("SUCCESS")
    expect(debug_page.retrieve_badge).to_have_class("result-badge badge-success")
    expect(debug_page.retrieve_result_card.locator(".result-latency")).to_contain_text("178ms")

    # Verify metadata fields
    expect(debug_page.retrieve_title_value).to_contain_text("GraphSelect: Embedding-Guided Graph Traversal")
    expect(debug_page.retrieve_result_card.locator(".result-field:has(.field-label:has-text('DOI')) .field-value")).to_contain_text("10.1145/3534678.3539078")
    expect(debug_page.retrieve_result_card.locator(".result-field:has(.field-label:has-text('Year')) .field-value")).to_contain_text("2022")
    expect(debug_page.retrieve_result_card.locator(".result-field:has(.field-label:has-text('Citations')) .field-value")).to_contain_text("48")
    expect(debug_page.retrieve_result_card.locator(".abstract-text")).to_contain_text("Semantic paper discovery requires efficient graph traversal")


def test_debug_paper_retrieval_failure_flow(page: Page, base_url: str):
    """Test Debug Console Paper Retrieval handles invalid DOI failure with FAILED badge and error message."""
    mock_api_route(page, "**/api/debug/test-retrieve*", status_code=200, json_data={
        "success": False,
        "elapsed_ms": 94,
        "error": "OpenAlex paper not found: 10.9999/invalid.nonexistent.doi"
    })

    debug_page = DebugPage(page, base_url)
    debug_page.navigate()

    debug_page.test_paper_retrieval("10.9999/invalid.nonexistent.doi")

    expect(debug_page.retrieve_result_card).to_be_visible()
    expect(debug_page.retrieve_result_card).to_have_class("result-card result-error")

    expect(debug_page.retrieve_badge).to_contain_text("FAILED")
    expect(debug_page.retrieve_badge).to_have_class("result-badge badge-error")
    expect(debug_page.retrieve_result_card.locator(".result-latency")).to_contain_text("94ms")
    expect(debug_page.retrieve_result_card.locator(".error-message")).to_contain_text("OpenAlex paper not found")


def test_debug_text_embedding_success_flow(page: Page, base_url: str):
    """Test Debug Console Text Embedding test runner: input text, run test, verify dimensions, vector values, and latency."""
    mock_api_route(page, "**/api/debug/test-embed*", status_code=200, json_data={
        "success": True,
        "elapsed_ms": 245,
        "dimensions": 768,
        "first_5_values": [0.0421, -0.0913, 0.1187, -0.0054, 0.0632]
    })

    debug_page = DebugPage(page, base_url)
    debug_page.navigate()

    debug_page.test_text_embedding("Graph neural networks operate over citation graphs to produce node embeddings.")

    expect(debug_page.embed_result_card).to_be_visible()
    expect(debug_page.embed_result_card).to_have_class("result-card result-success")

    expect(debug_page.embed_badge).to_contain_text("SUCCESS")
    expect(debug_page.embed_badge).to_have_class("result-badge badge-success")
    expect(debug_page.embed_result_card.locator(".result-latency")).to_contain_text("245ms")

    expect(debug_page.embed_dims_value).to_contain_text("768")
    expect(debug_page.embed_result_card.locator(".vector-values")).to_contain_text("[ 0.0421, -0.0913, 0.1187, -0.0054, 0.0632 … ]")


def test_debug_text_embedding_failure_and_settings_redirect_toast(page: Page, base_url: str):
    """Test Debug Console handles Gemini API error with FAILED card and redirect toast to /settings."""
    mock_api_route(page, "**/api/debug/test-embed*", status_code=200, json_data={
        "success": False,
        "elapsed_ms": 45,
        "error": "Gemini API Error: 400 INVALID_ARGUMENT API key not valid. Please pass a valid API key."
    })

    debug_page = DebugPage(page, base_url)
    debug_page.navigate()

    debug_page.test_text_embedding("Test input text for Gemini error")

    # Verify FAILED result card
    expect(debug_page.embed_result_card).to_be_visible()
    expect(debug_page.embed_result_card).to_have_class("result-card result-error")
    expect(debug_page.embed_badge).to_contain_text("FAILED")
    expect(debug_page.embed_result_card.locator(".error-message")).to_contain_text("Gemini API Error: 400")

    # Verify Toast with 'Go to Settings' action link
    toast = assert_toast_message(page, expected_title_substring="Gemini API Key Issue", expected_text_substring="check that your API key is valid in Settings")
    
    action_link = toast.locator("a.toast-action")
    expect(action_link).to_be_visible()
    expect(action_link).to_contain_text("Go to Settings")
    expect(action_link).to_have_attribute("href", "/settings")

    # Click action link to verify redirection
    action_link.click()
    page.wait_for_url("**/settings", timeout=5000)
    expect(page.locator("h1.page-title")).to_contain_text("Settings")


def test_debug_cosine_similarity_gauge_scores_and_classes(page: Page, base_url: str):
    """Test Cosine Similarity runner dynamic gauge score bar (gauge-high, gauge-medium, gauge-low classes)."""
    debug_page = DebugPage(page, base_url)

    # --- Test 1: High Similarity (0.94 -> gauge-high >= 80%) ---
    mock_api_route(page, "**/api/debug/test-similarity*", status_code=200, json_data={
        "success": True,
        "elapsed_ms": 380,
        "similarity_score": 0.94,
        "dimensions": 768
    })

    debug_page.navigate()
    debug_page.test_cosine_similarity(
        "Graph neural network architectures for citation topology embedding.",
        "GNN models for graph-based document representation learning."
    )

    expect(debug_page.sim_result_card).to_be_visible()
    expect(debug_page.sim_badge).to_contain_text("SUCCESS")
    expect(debug_page.sim_gauge_value).to_contain_text("0.94")
    expect(debug_page.sim_gauge_fill).to_have_class("gauge-fill gauge-high")
    expect(debug_page.sim_result_card.locator(".result-latency")).to_contain_text("380ms")

    # --- Test 2: Medium Similarity (0.64 -> gauge-medium 50-79%) ---
    mock_api_route(page, "**/api/debug/test-similarity*", status_code=200, json_data={
        "success": True,
        "elapsed_ms": 320,
        "similarity_score": 0.64,
        "dimensions": 768
    })

    debug_page.test_cosine_similarity(
        "Deep reinforcement learning for robot locomotion.",
        "Neural network optimization methods for robotic kinematics."
    )

    expect(debug_page.sim_gauge_value).to_contain_text("0.64")
    expect(debug_page.sim_gauge_fill).to_have_class("gauge-fill gauge-medium")

    # --- Test 3: Low Similarity (0.15 -> gauge-low < 50%) ---
    mock_api_route(page, "**/api/debug/test-similarity*", status_code=200, json_data={
        "success": True,
        "elapsed_ms": 290,
        "similarity_score": 0.15,
        "dimensions": 768
    })

    debug_page.test_cosine_similarity(
        "Quantum electrodynamics in high energy physics.",
        "Culinary recipes for Italian sourdough bread."
    )

    expect(debug_page.sim_gauge_value).to_contain_text("0.15")
    expect(debug_page.sim_gauge_fill).to_have_class("gauge-fill gauge-low")


# ===========================================================================
# 4. SETTINGS VIEW TESTS (/settings)
# ===========================================================================

def test_settings_initial_load_and_system_info_display(page: Page, base_url: str):
    """Test Settings view initial load: backend connection, key status badges, contact email, and system info."""
    mock_api_route(page, "**/api/settings*", status_code=200, json_data={
        "gemini_api_key_set": True,
        "gemini_api_key_preview": "AIzaSy...4321",
        "openalex_api_key_set": False,
        "openalex_api_key_preview": None,
        "openalex_email": "researcher@stanford.edu",
        "embedding_model": "gemini-embedding-2",
        "embedding_dimensions": 768
    })

    settings_page = SettingsPage(page, base_url)
    settings_page.navigate()

    expect(settings_page.page_title).to_contain_text("Settings")

    # Backend Connection
    expect(settings_page.api_base_url_input).to_be_visible()

    # Gemini Key Status: Active badge
    expect(settings_page.gemini_status_badge).to_contain_text("Active")
    expect(settings_page.gemini_status_badge).to_have_class("badge badge-success")
    expect(page.locator(".setting-row:has(#gemini-key) .mono")).to_contain_text("AIzaSy...4321")

    # OpenAlex Key Status: Not Set badge
    expect(settings_page.openalex_status_badge).to_contain_text("Not Set")
    expect(settings_page.openalex_status_badge).to_have_class("badge badge-warning")

    # Contact Email input
    expect(settings_page.openalex_email_input).to_have_value("researcher@stanford.edu")

    # System Info Section Readout
    expect(settings_page.embedding_model_value).to_contain_text("gemini-embedding-2")
    expect(settings_page.embedding_dims_value).to_contain_text("768")


def test_settings_api_key_visibility_toggles(page: Page, base_url: str):
    """Test Settings API key password/text masking toggles for Gemini and OpenAlex inputs."""
    mock_api_route(page, "**/api/settings*", status_code=200, json_data={
        "gemini_api_key_set": True,
        "gemini_api_key_preview": "AIza...",
        "openalex_api_key_set": True,
        "openalex_api_key_preview": "sec_...",
        "openalex_email": "user@example.com",
        "embedding_model": "gemini-embedding-2",
        "embedding_dimensions": 768
    })

    settings_page = SettingsPage(page, base_url)
    settings_page.navigate()

    # Gemini Key Toggle
    expect(settings_page.gemini_key_input).to_have_attribute("type", "password")
    settings_page.toggle_gemini_visibility()
    expect(settings_page.gemini_key_input).to_have_attribute("type", "text")
    settings_page.toggle_gemini_visibility()
    expect(settings_page.gemini_key_input).to_have_attribute("type", "password")

    # OpenAlex Key Toggle
    expect(settings_page.openalex_key_input).to_have_attribute("type", "password")
    settings_page.toggle_openalex_visibility()
    expect(settings_page.openalex_key_input).to_have_attribute("type", "text")
    settings_page.toggle_openalex_visibility()
    expect(settings_page.openalex_key_input).to_have_attribute("type", "password")


def test_settings_save_flow_and_toast_feedback_zero_objects(page: Page, base_url: str):
    """Test Save Settings flow: submit form, verify toast feedback, assert zero [object Object], reset inputs."""
    mock_api_route(page, "**/api/settings*", status_code=200, json_data={
        "gemini_api_key_set": False,
        "gemini_api_key_preview": None,
        "openalex_api_key_set": False,
        "openalex_api_key_preview": None,
        "openalex_email": "initial@example.com",
        "embedding_model": "gemini-embedding-2",
        "embedding_dimensions": 768
    })

    saved_payloads = []

    def handle_save_settings(route):
        if route.request.method == "PUT":
            saved_payloads.append(route.request.post_data_json)
            route.fulfill(
                status=200,
                headers={"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
                body=json.dumps({
                    "success": True,
                    "message": "Settings saved successfully. A server restart may be required for API key changes to take full effect."
                })
            )
        else:
            route.continue_()

    page.route("**/api/settings*", handle_save_settings)

    settings_page = SettingsPage(page, base_url)
    settings_page.navigate()

    # Enter new values
    settings_page.set_gemini_key("AIzaSyNewSecretKey_987654321")
    settings_page.set_openalex_key("openalex_premium_key_112233")
    settings_page.set_contact_email("updated-researcher@institute.org")

    # Click Save Settings
    settings_page.save_settings()

    # Assert Toast Notification & Zero [object Object] anomalies
    assert_toast_message(
        page,
        expected_title_substring="Settings Saved",
        expected_text_substring="Settings saved successfully"
    )

    # Verify submitted request payload
    assert len(saved_payloads) == 1
    assert saved_payloads[0]["gemini_api_key"] == "AIzaSyNewSecretKey_987654321"
    assert saved_payloads[0]["openalex_api_key"] == "openalex_premium_key_112233"
    assert saved_payloads[0]["openalex_email"] == "updated-researcher@institute.org"

    # Verify input fields cleared after successful save
    expect(settings_page.gemini_key_input).to_have_value("")
    expect(settings_page.openalex_key_input).to_have_value("")


def test_settings_save_failure_error_toast_handling(page: Page, base_url: str):
    """Test Save Settings handles backend error with structured error toast and zero [object Object]."""
    mock_api_route(page, "**/api/settings*", status_code=200, json_data={
        "gemini_api_key_set": True,
        "gemini_api_key_preview": "AIza...",
        "openalex_api_key_set": False,
        "openalex_api_key_preview": None,
        "openalex_email": "user@example.com",
        "embedding_model": "gemini-embedding-2",
        "embedding_dimensions": 768
    })

    def handle_save_error(route):
        if route.request.method == "PUT":
            route.fulfill(
                status=500,
                headers={"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
                body=json.dumps({
                    "detail": "Failed to write settings to .env file: Permission denied"
                })
            )
        else:
            route.continue_()

    page.route("**/api/settings*", handle_save_error)

    settings_page = SettingsPage(page, base_url)
    settings_page.navigate()

    settings_page.set_contact_email("fail-test@example.com")
    settings_page.save_settings()

    # Verify Error Toast & Zero [object Object] (Angular error interceptor catches 500)
    assert_toast_message(
        page,
        expected_title_substring="API Error",
        expected_text_substring="Failed to write settings to .env file"
    )


# ===========================================================================
# 5. SIDEBAR NAVIGATION FLOW ACROSS ALL SYSTEM TOOLS
# ===========================================================================

def test_system_tools_sidebar_navigation_flow(page: Page, base_url: str):
    """Test complete sidebar navigation flow between Projects, System Status, API Logs, Debug, and Settings."""
    mock_api_route(page, "**/api/health*", status_code=200, json_data={"status": "healthy", "neo4j": "connected", "mysql": "connected"})
    mock_api_route(page, "**/api/version*", status_code=200, json_data={"version": "v3.0.0"})
    mock_api_route(page, "**/api/sessions*", status_code=200, json_data={"sessions": [], "total": 0})
    mock_api_route(page, "**/api/logs*", status_code=200, json_data=[])
    mock_api_route(page, "**/api/settings*", status_code=200, json_data={
        "gemini_api_key_set": True, "gemini_api_key_preview": "AIza...", "openalex_api_key_set": False,
        "openalex_api_key_preview": None, "openalex_email": "", "embedding_model": "gemini-embedding-2", "embedding_dimensions": 768
    })

    base_page = BasePage(page, base_url)
    base_page.goto("/projects")

    # 1. Navigate to System Status
    base_page.navigate_to_system_status()
    expect(page.locator("h1.page-title")).to_contain_text("SystemStatus")

    # 2. Navigate to Logs
    base_page.navigate_to_logs()
    expect(page.locator("h1.page-title")).to_contain_text("Logs & Monitoring")

    # 3. Navigate to Debug
    base_page.navigate_to_debug()
    expect(page.locator("h1.page-title")).to_contain_text("Debug Console")

    # 4. Navigate to Settings
    base_page.navigate_to_settings()
    expect(page.locator("h1.page-title")).to_contain_text("Settings")

    # 5. Navigate back to Projects
    base_page.navigate_to_projects()
    expect(page.locator("h1").first).to_contain_text("Research Projects")

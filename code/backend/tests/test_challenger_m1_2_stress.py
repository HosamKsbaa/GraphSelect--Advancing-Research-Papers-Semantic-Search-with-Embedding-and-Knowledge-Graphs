"""Adversarial stress test suite for fetch_error_logs and run_agent_tests.

Authored by challenger_m1_2.
Empirically stress-tests boundary limits, fallback behaviors, malformed inputs,
security boundaries, timeout conditions, and error regex parsing.
"""
import ast
import json
import os
import subprocess
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents._service_registry import ServiceRegistry
from agents.tools.self_debug_tools import (
    BACKEND_ROOT,
    _extract_traceback,
    _parse_extra,
    _sanitize_path,
    fetch_error_logs,
    run_agent_tests,
)


# ============================================================================
# 1. Log Fetcher Stress Tests (fetch_error_logs, _parse_extra, _extract_traceback)
# ============================================================================


@pytest.mark.asyncio
async def test_fetch_error_logs_limit_clamping_zero():
    """Verify limit=0 is clamped to 1 in SQL query parameter."""
    with patch.object(ServiceRegistry, "log_service", create=True) as mock_log_service:
        mock_mysql = AsyncMock()
        mock_mysql.fetch_all.return_value = []
        mock_log_service._mysql = mock_mysql

        res = await fetch_error_logs(limit=0)
        assert res["success"] is True
        assert res["total_found"] == 0
        assert res["logs"] == []

        # Check the query params passed to fetch_all
        call_args = mock_mysql.fetch_all.call_args
        query_sql, query_params = call_args[0]
        assert query_params[-1] == 1, f"Expected clamped limit 1, got {query_params[-1]}"


@pytest.mark.asyncio
async def test_fetch_error_logs_limit_clamping_hundred():
    """Verify limit=100 is clamped to 20 in SQL query parameter."""
    with patch.object(ServiceRegistry, "log_service", create=True) as mock_log_service:
        mock_mysql = AsyncMock()
        mock_mysql.fetch_all.return_value = []
        mock_log_service._mysql = mock_mysql

        res = await fetch_error_logs(limit=100)
        assert res["success"] is True
        call_args = mock_mysql.fetch_all.call_args
        query_sql, query_params = call_args[0]
        assert query_params[-1] == 20, f"Expected clamped limit 20, got {query_params[-1]}"


@pytest.mark.asyncio
async def test_fetch_error_logs_limit_clamping_negative():
    """Verify negative limit is clamped to 1."""
    with patch.object(ServiceRegistry, "log_service", create=True) as mock_log_service:
        mock_mysql = AsyncMock()
        mock_mysql.fetch_all.return_value = []
        mock_log_service._mysql = mock_mysql

        res = await fetch_error_logs(limit=-99)
        assert res["success"] is True
        call_args = mock_mysql.fetch_all.call_args
        query_sql, query_params = call_args[0]
        assert query_params[-1] == 1, f"Expected clamped limit 1, got {query_params[-1]}"


@pytest.mark.asyncio
async def test_fetch_error_logs_service_name_filtering():
    """Verify service_name filter constructs LIKE clauses for app_logs and api_logs."""
    with patch.object(ServiceRegistry, "log_service", create=True) as mock_log_service:
        mock_mysql = AsyncMock()
        mock_mysql.fetch_all.return_value = [
            {
                "id": 101,
                "session_id": "sess_123",
                "level": "ERROR",
                "module": "backend.features.openalex",
                "message": "HTTP 429 Rate Limit Exceeded",
                "extra": json.dumps({"traceback": "Traceback:\n  RateLimit"}),
                "created_at": "2026-08-28 14:00:00",
            }
        ]
        mock_log_service._mysql = mock_mysql

        res = await fetch_error_logs(service_name="openalex", limit=5, include_api_logs=True)
        assert res["success"] is True
        assert res["total_found"] == 1
        assert res["logs"][0]["module"] == "backend.features.openalex"
        assert res["logs"][0]["logger"] == "backend.features.openalex"
        assert "Rate Limit" in res["logs"][0]["message"]
        assert "RateLimit" in res["logs"][0]["traceback"]

        # Check call count: 1 for app_logs, 1 for api_logs
        assert mock_mysql.fetch_all.call_count == 2
        app_call = mock_mysql.fetch_all.call_args_list[0][0]
        api_call = mock_mysql.fetch_all.call_args_list[1][0]

        assert "%openalex%" in app_call[1]
        assert "%openalex%" in api_call[1]


@pytest.mark.asyncio
async def test_fetch_error_logs_db_offline_none_service():
    """Verify graceful fallback when ServiceRegistry.log_service is None."""
    with patch.object(ServiceRegistry, "log_service", None):
        res = await fetch_error_logs()
        assert res["success"] is False
        assert "unavailable or uninitialized" in res["error"]
        assert res["total_found"] == 0
        assert res["logs"] == []


@pytest.mark.asyncio
async def test_fetch_error_logs_db_offline_none_mysql():
    """Verify graceful fallback when ServiceRegistry.log_service._mysql is None."""
    mock_service = MagicMock()
    mock_service._mysql = None
    with patch.object(ServiceRegistry, "log_service", mock_service):
        res = await fetch_error_logs()
        assert res["success"] is False
        assert "unavailable or uninitialized" in res["error"]
        assert res["total_found"] == 0
        assert res["logs"] == []


@pytest.mark.asyncio
async def test_fetch_error_logs_query_exception_handled():
    """Verify database query exception is caught and logged without unhandled crash."""
    with patch.object(ServiceRegistry, "log_service", create=True) as mock_log_service:
        mock_mysql = AsyncMock()
        mock_mysql.fetch_all.side_effect = RuntimeError("MySQL server has gone away (errno 2006)")
        mock_log_service._mysql = mock_mysql

        res = await fetch_error_logs()
        assert res["success"] is False
        assert "Database query error" in res["error"]
        assert "errno 2006" in res["error"]
        assert res["total_found"] == 0
        assert res["logs"] == []


def test_parse_extra_malformed_json_and_types():
    """Adversarial stress test for _parse_extra."""
    # 1. None
    assert _parse_extra(None) == {}

    # 2. Dict directly
    d = {"key": "val", "num": 42}
    assert _parse_extra(d) == d

    # 3. Valid JSON string
    assert _parse_extra('{"status": "ok"}') == {"status": "ok"}

    # 4. Malformed JSON string
    assert _parse_extra("broken { json: [") == {"raw": "broken { json: ["}

    # 5. JSON string that parses to non-dict (e.g. list, int)
    assert _parse_extra("[1, 2, 3]") == {}
    assert _parse_extra("12345") == {}
    assert _parse_extra('"just a string"') == {}

    # 6. Non-string non-dict objects
    assert _parse_extra(1234) == {}
    assert _parse_extra([1, 2, 3]) == {}
    assert _parse_extra(True) == {}


def test_extract_traceback_edge_cases():
    """Adversarial stress test for _extract_traceback."""
    # 1. Traceback in extra dict keys
    for k in ("traceback", "stack_trace", "exception", "error", "exc_info", "details"):
        res = _extract_traceback({k: "Traceback (most recent call last):\n  line 1"}, "Normal message")
        assert res is not None and "line 1" in res

    # 2. Simple single line string in extra
    res_str = _extract_traceback({"error": "Short error description"}, "msg")
    assert res_str == "Short error description"

    # 3. Nested dictionary in extra with "traceback"
    res_nested = _extract_traceback({"details": {"traceback": "nested tb string"}}, "msg")
    assert res_nested == "nested tb string"

    # 4. Nested dictionary in extra without "traceback"
    res_nested_dict = _extract_traceback({"details": {"code": 500, "info": "fatal"}}, "msg")
    assert res_nested_dict is not None
    assert "500" in res_nested_dict

    # 5. Missing extra, but message contains embedded traceback
    msg_with_tb = "Failed request\nTraceback (most recent call last):\n  File 'test.py', line 10\nValueError: bad"
    res_msg = _extract_traceback({}, msg_with_tb)
    assert res_msg is not None
    assert res_msg.startswith("Traceback (most recent call last):")
    assert "ValueError: bad" in res_msg

    # 6. Missing extra, and message has no traceback
    assert _extract_traceback({}, "Just a normal error") is None
    assert _extract_traceback(None, "") is None


# ============================================================================
# 2. Test Runner Stress Tests (run_agent_tests)
# ============================================================================


@pytest.mark.asyncio
async def test_run_agent_tests_security_path_traversal():
    """Verify run_agent_tests rejects paths outside backend repository."""
    # Traversal attempts
    for bad_path in (
        "../../etc/passwd",
        "../../../bin/sh",
        "backend/../../secret.env",
    ):
        res = await run_agent_tests(bad_path)
        assert res["success"] is False
        assert res["exit_code"] == -1
        assert res["errors"] == 1
        assert "Security Violation" in res["summary"] or "outside the backend" in res["summary"]


@pytest.mark.asyncio
async def test_run_agent_tests_nonexistent_file():
    """Verify run_agent_tests returns structured error for non-existent test file."""
    res = await run_agent_tests("tests/test_does_not_exist_99999.py")
    assert res["success"] is False
    assert res["exit_code"] == -1
    assert res["errors"] == 1
    assert "Test target not found" in res["summary"]


@pytest.mark.asyncio
async def test_run_agent_tests_timeout_handling():
    """Verify run_agent_tests handles subprocess.TimeoutExpired cleanly."""
    with patch("subprocess.run") as mock_sub:
        mock_sub.side_effect = subprocess.TimeoutExpired(cmd=["pytest"], timeout=45)

        res = await run_agent_tests("tests/test_self_debug.py")
        assert res["success"] is False
        assert res["exit_code"] == -1
        assert res["errors"] == 1
        assert res["duration_seconds"] == 45.0
        assert "timed out after 45 seconds" in res["summary"]


@pytest.mark.asyncio
async def test_run_agent_tests_subprocess_exception():
    """Verify run_agent_tests handles unexpected subprocess exceptions."""
    with patch("subprocess.run") as mock_sub:
        mock_sub.side_effect = OSError("Exec format error")

        res = await run_agent_tests("tests/test_self_debug.py")
        assert res["success"] is False
        assert res["exit_code"] == -1
        assert res["errors"] == 1
        assert "Failed to execute tests" in res["summary"]
        assert "Exec format error" in res["summary"]


@pytest.mark.asyncio
async def test_run_agent_tests_passing_node_selector():
    """Verify run_agent_tests handles pytest node selector syntax accurately."""
    res = await run_agent_tests("tests/test_self_debug.py::test_sanitize_path_security_traversal")
    assert res["success"] is True
    assert res["exit_code"] == 0
    assert res["passed"] == 1
    assert res["failed"] == 0
    assert res["errors"] == 0
    assert res["duration_seconds"] > 0.0
    assert "1 passed" in res["summary"] or "passed" in res["summary"]


@pytest.mark.asyncio
async def test_run_agent_tests_failing_execution(tmp_path, monkeypatch):
    """Verify run_agent_tests correctly captures failures, exit code, and tracebacks."""
    import agents.tools.self_debug_tools as sdt

    # Create a temporary failing test file inside actual tests directory
    tests_dir = BACKEND_ROOT / "tests"
    temp_fail_test = tests_dir / "_temp_failing_test_challenger.py"
    try:
        temp_fail_test.write_text(
            "def test_intentional_failure():\n    assert 1 == 2, 'Intentional challenger failure'\n",
            encoding="utf-8",
        )

        res = await run_agent_tests(f"tests/{temp_fail_test.name}")
        assert res["success"] is False
        assert res["exit_code"] != 0
        assert res["failed"] >= 1
        assert "Intentional challenger failure" in res["output"]
        assert "Intentional challenger failure" in res["tracebacks"] or "FAILURES" in res["tracebacks"]
    finally:
        if temp_fail_test.exists():
            temp_fail_test.unlink()


@pytest.mark.asyncio
async def test_run_agent_tests_keyword_filter():
    """Verify pytest keyword filtering (-k) works properly."""
    res = await run_agent_tests(
        "tests/test_self_debug.py",
        keyword_filter="test_sanitize_path_security_traversal",
    )
    assert res["success"] is True
    assert res["passed"] == 1
    assert res["failed"] == 0

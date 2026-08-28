"""Tests for the Self-Debug Tool Suite and DebuggerAgent."""
import ast
import pytest
from unittest.mock import AsyncMock, patch

from agents.debugger.agent import create_debugger_agent
from agents.tools.self_debug_tools import (
    _sanitize_path,
    fetch_error_logs,
    read_agent_code,
    run_agent_tests,
    validate_and_propose_patch,
)


def test_sanitize_path_security_traversal():
    """Verify that path traversal outside backend directory is blocked."""
    target, err = _sanitize_path("../../etc/passwd")
    assert target is None
    assert "Security Violation" in err

    target_ok, err_ok = _sanitize_path("agents/research/alrs_agent.py")
    assert err_ok is None
    assert target_ok is not None
    assert target_ok.name == "alrs_agent.py"


@pytest.mark.asyncio
async def test_read_agent_code_success():
    """Verify read_agent_code reads file, returns line numbers and AST symbols."""
    res = await read_agent_code("agents/debugger/agent.py")
    assert res["success"] is True
    assert res["total_lines"] > 0
    assert "create_debugger_agent" in res["symbols_in_file"]
    assert "DEBUGGER_AGENT_INSTRUCTION" in res["code"]
    assert res["syntax_valid"] is True


@pytest.mark.asyncio
async def test_read_agent_code_specific_symbol():
    """Verify focusing on a specific function extracts only that function's range."""
    res = await read_agent_code(
        "agents/debugger/agent.py",
        function_or_class_name="create_debugger_agent",
    )
    assert res["success"] is True
    assert res["focus_symbol"] == "create_debugger_agent"
    assert "def create_debugger_agent" in res["code"]


@pytest.mark.asyncio
async def test_validate_and_propose_patch_syntax_validation(tmp_path, monkeypatch):
    """Verify validate_and_propose_patch checks AST syntax and produces unified diffs."""
    import agents.tools.self_debug_tools as sdt
    monkeypatch.setattr(sdt, "BACKEND_ROOT", tmp_path)

    sample_file = tmp_path / "sample.py"
    sample_file.write_text("def hello():\n    return 'world'\n", encoding="utf-8")

    # 1. Valid replacement
    res_valid = await validate_and_propose_patch(
        file_path="sample.py",
        target_snippet="return 'world'",
        replacement_snippet="return 'universe'",
        explanation="Updated greeting target",
    )
    assert res_valid["success"] is True
    assert res_valid["syntax_valid"] is True
    assert "-    return 'world'" in res_valid["diff"]
    assert "+    return 'universe'" in res_valid["diff"]

    # 2. Invalid syntax replacement
    res_invalid = await validate_and_propose_patch(
        file_path="sample.py",
        target_snippet="return 'world'",
        replacement_snippet="return 'world' def broken syntax (",
        explanation="Testing syntax detection",
    )
    assert res_invalid["success"] is False
    assert res_invalid["syntax_valid"] is False
    assert "SyntaxError" in res_invalid["syntax_error"]


@pytest.mark.asyncio
async def test_fetch_error_logs_mocked():
    """Verify fetch_error_logs queries MySQL app_logs properly."""
    with patch("agents._service_registry.ServiceRegistry.log_service") as mock_log_service:
        mock_mysql = AsyncMock()
        mock_mysql.fetch_all.return_value = [
            {
                "id": 1,
                "timestamp": "2026-08-28 12:00:00",
                "level": "ERROR",
                "logger_name": "openalex",
                "message": "OpenAlex 401 Unauthorized",
                "exception": "Traceback (most recent call last):\n...",
            }
        ]
        mock_log_service._mysql = mock_mysql

        res = await fetch_error_logs(service_name="openalex", limit=5)
        assert res["success"] is True
        assert res["total_found"] == 1
        assert res["logs"][0]["logger"] == "openalex"
        assert "401 Unauthorized" in res["logs"][0]["message"]


@pytest.mark.asyncio
async def test_run_agent_tests_execution():
    """Verify run_agent_tests invokes pytest and captures summary."""
    res = await run_agent_tests("tests/test_self_debug.py", keyword_filter="test_sanitize_path_security_traversal")
    assert res["success"] is True
    assert res["exit_code"] == 0
    assert "passed" in res["summary"]


def test_debugger_agent_creation():
    """Verify DebuggerAgent instantiation and tool attachment."""
    agent = create_debugger_agent()
    assert agent.name == "DebuggerAgent"
    tool_names = [getattr(t, "__name__", str(t)) for t in agent.tools]
    assert "read_agent_code" in tool_names
    assert "fetch_error_logs" in tool_names
    assert "run_agent_tests" in tool_names
    assert "validate_and_propose_patch" in tool_names

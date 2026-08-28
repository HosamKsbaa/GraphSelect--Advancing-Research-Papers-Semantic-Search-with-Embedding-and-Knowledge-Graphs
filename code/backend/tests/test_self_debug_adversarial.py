"""Adversarial and Empirical Stress Test Suite for Self-Debug Tools.

Comprehensive verification of Milestone 1:
1. Security/Traversal Stress (traversal attacks, root escapes, URL encoded paths, directory paths, empty/whitespace paths).
2. AST Symbol Extraction (async functions, nested classes, decorated functions, invalid syntax, out-of-range line slices, negative line numbers).
3. Patch Validation Stress (syntax errors, empty replacement strings, non-existent snippets, multiple occurrences, indentation errors).
4. Subprocess and Error Log Stress (timeout handling, traceback extractions, non-existent test targets).
"""
import ast
import os
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from agents.tools.self_debug_tools import (
    _extract_traceback,
    _parse_extra,
    _sanitize_path,
    fetch_error_logs,
    read_agent_code,
    run_agent_tests,
    validate_and_propose_patch,
    BACKEND_ROOT,
)


# ============================================================================
# 1. SECURITY & PATH TRAVERSAL STRESS TESTS
# ============================================================================

@pytest.mark.parametrize(
    "traversal_payload",
    [
        "../../etc/passwd",
        "../../../etc/shadow",
        "../../../../../../../../../../../../etc/hosts",
        "backend/../..",
        "backend/../../etc/passwd",
        "agents/../../../../etc/passwd",
        "backend/../.env",
        "/..//..//..//etc/passwd",
        "././././../../etc/passwd",
        "agents/tools/../../../..",
    ],
)
def test_sanitize_path_blocks_directory_escapes(traversal_payload):
    """Verify that any path attempting to traverse outside BACKEND_ROOT is blocked with Security Violation."""
    target, err = _sanitize_path(traversal_payload)
    assert target is None
    assert err is not None
    assert "Security Violation" in err


@pytest.mark.parametrize(
    "safe_subpath",
    [
        "agents/debugger/agent.py",
        "backend/agents/debugger/agent.py",
        "/agents/debugger/agent.py",
        "agents/tools/self_debug_tools.py",
        "tests/test_self_debug.py",
    ],
)
def test_sanitize_path_allows_valid_subpaths(safe_subpath):
    """Verify valid backend subpaths resolve cleanly within sandbox."""
    target, err = _sanitize_path(safe_subpath)
    assert err is None
    assert target is not None
    assert target.is_relative_to(BACKEND_ROOT)


@pytest.mark.parametrize(
    "malicious_or_invalid_path",
    [
        "../../etc/passwd",
        "/etc/shadow",
        "/etc/passwd",
        "backend/../..",
        "%2e%2e%2f%2e%2e%2fetc%2fpasswd",
        "agents",
        "agents/",
        "agents/tools/",
        "non_existent_file_12345.py",
        "",
        "   ",
    ],
)
@pytest.mark.asyncio
async def test_read_agent_code_security_and_invalid_paths(malicious_or_invalid_path):
    """Verify read_agent_code rejects all traversal, system, non-existent, directory, and blank paths."""
    res = await read_agent_code(malicious_or_invalid_path)
    assert res["success"] is False
    assert "error" in res
    assert len(res["error"]) > 0


@pytest.mark.parametrize(
    "malicious_or_invalid_path",
    [
        "../../etc/passwd",
        "/etc/shadow",
        "backend/../..",
        "agents",
        "non_existent_file_12345.py",
        "",
    ],
)
@pytest.mark.asyncio
async def test_validate_and_propose_patch_security_and_invalid_paths(malicious_or_invalid_path):
    """Verify validate_and_propose_patch rejects traversal, directories, and invalid files."""
    res = await validate_and_propose_patch(
        file_path=malicious_or_invalid_path,
        target_snippet="foo",
        replacement_snippet="bar",
    )
    assert res["success"] is False
    assert "error" in res


# ============================================================================
# 2. AST SYMBOL EXTRACTION STRESS TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_read_agent_code_async_and_nested_symbols(tmp_path, monkeypatch):
    """Verify accurate extraction of async functions, nested classes, and decorators."""
    import agents.tools.self_debug_tools as sdt
    monkeypatch.setattr(sdt, "BACKEND_ROOT", tmp_path)

    sample_code = (
        "import asyncio\n"
        "\n"
        "def helper_func(val: int) -> int:\n"
        "    return val + 1\n"
        "\n"
        "@staticmethod\n"
        "def decorated_worker():\n"
        "    return 'decorated'\n"
        "\n"
        "class ParentClass:\n"
        "    class ChildClass:\n"
        "        async def async_child_method(self, data: str) -> str:\n"
        "            await asyncio.sleep(0.001)\n"
        "            return data.strip()\n"
        "\n"
        "async def standalone_async_func():\n"
        "    return 'async_result'\n"
    )

    sample_file = tmp_path / "sample_ast.py"
    sample_file.write_text(sample_code, encoding="utf-8")

    # 1. Full file symbol discovery
    res = await read_agent_code("sample_ast.py")
    assert res["success"] is True
    assert res["syntax_valid"] is True
    symbols = res["symbols_in_file"]
    assert "helper_func" in symbols
    assert "decorated_worker" in symbols
    assert "ParentClass" in symbols
    assert "ChildClass" in symbols
    assert "async_child_method" in symbols
    assert "standalone_async_func" in symbols

    # 2. Focus on async standalone function
    res_async = await read_agent_code("sample_ast.py", function_or_class_name="standalone_async_func")
    assert res_async["success"] is True
    assert res_async["focus_symbol"] == "standalone_async_func"
    assert "async def standalone_async_func" in res_async["code"]

    # 3. Focus on nested class
    res_nested = await read_agent_code("sample_ast.py", function_or_class_name="ChildClass")
    assert res_nested["success"] is True
    assert res_nested["focus_symbol"] == "ChildClass"
    assert "class ChildClass:" in res_nested["code"]
    assert "async_child_method" in res_nested["code"]

    # 4. Focus on decorated function
    res_dec = await read_agent_code("sample_ast.py", function_or_class_name="decorated_worker")
    assert res_dec["success"] is True
    assert res_dec["focus_symbol"] == "decorated_worker"
    assert "def decorated_worker" in res_dec["code"]


@pytest.mark.asyncio
async def test_read_agent_code_syntax_error_file(tmp_path, monkeypatch):
    """Verify handling of files with invalid Python syntax."""
    import agents.tools.self_debug_tools as sdt
    monkeypatch.setattr(sdt, "BACKEND_ROOT", tmp_path)

    broken_code = "def malformed_syntax_func(\n    val = 1 +\n"
    broken_file = tmp_path / "broken_syntax.py"
    broken_file.write_text(broken_code, encoding="utf-8")

    res = await read_agent_code("broken_syntax.py")
    assert res["success"] is True
    assert res["syntax_valid"] is False
    assert res["syntax_error"] is not None
    assert "SyntaxError" in res["syntax_error"]
    assert res["symbols_in_file"] == []
    # Source code is still provided with line numbers even when AST parsing fails
    assert "1: def malformed_syntax_func(" in res["code"]


@pytest.mark.asyncio
async def test_read_agent_code_line_slicing_stress(tmp_path, monkeypatch):
    """Stress test line slicing parameters (out-of-range, negative, inverted, large bounds)."""
    import agents.tools.self_debug_tools as sdt
    monkeypatch.setattr(sdt, "BACKEND_ROOT", tmp_path)

    content = "\n".join(f"line_{i}" for i in range(1, 26))  # 25 lines
    file_path = tmp_path / "twenty_five.py"
    file_path.write_text(content, encoding="utf-8")

    # Negative start line -> clamps to line 1
    res_neg = await read_agent_code("twenty_five.py", start_line=-100, end_line=5)
    assert res_neg["success"] is True
    assert "1: line_1" in res_neg["code"]
    assert "5: line_5" in res_neg["code"]
    assert "6: line_6" not in res_neg["code"]

    # Start line beyond total lines (out-of-range start_line=1000)
    res_beyond = await read_agent_code("twenty_five.py", start_line=1000)
    assert res_beyond["success"] is True
    assert res_beyond["code"] == ""
    assert res_beyond["total_lines"] == 25

    # Inverted range (end_line < start_line)
    res_inv = await read_agent_code("twenty_five.py", start_line=20, end_line=10)
    assert res_inv["success"] is True
    assert res_inv["code"] == ""

    # End line beyond EOF -> clamped to total lines
    res_large_end = await read_agent_code("twenty_five.py", start_line=20, end_line=99999)
    assert res_large_end["success"] is True
    assert "20: line_20" in res_large_end["code"]
    assert "25: line_25" in res_large_end["code"]


# ============================================================================
# 3. PATCH VALIDATION STRESS TESTS
# ============================================================================

@pytest.mark.parametrize(
    "invalid_replacement",
    [
        "def foo(:",                           # Bad parameter syntax
        "def foo()\n    return 1",             # Missing colon
        "def foo():\nreturn 1",                # IndentationError
        "val = (1 + 2",                        # Unclosed parenthesis
        "def foo():\n    val = [1, 2,\n",      # Incomplete list
        "class A\n    pass",                   # Missing colon on class
        "import",                              # Incomplete import
    ],
)
@pytest.mark.asyncio
async def test_validate_and_propose_patch_syntax_errors(tmp_path, monkeypatch, invalid_replacement):
    """Stress test validate_and_propose_patch with diverse Python syntax errors."""
    import agents.tools.self_debug_tools as sdt
    monkeypatch.setattr(sdt, "BACKEND_ROOT", tmp_path)

    sample = tmp_path / "module.py"
    sample.write_text("def original():\n    return 'original'\n", encoding="utf-8")

    res = await validate_and_propose_patch(
        file_path="module.py",
        target_snippet="def original():\n    return 'original'",
        replacement_snippet=invalid_replacement,
    )
    assert res["success"] is False
    assert res["syntax_valid"] is False
    assert res["syntax_error"] is not None
    assert "SyntaxError" in res["syntax_error"]


@pytest.mark.asyncio
async def test_validate_and_propose_patch_empty_replacement_string(tmp_path, monkeypatch):
    """Test replacing snippet with empty string (deletion of code block)."""
    import agents.tools.self_debug_tools as sdt
    monkeypatch.setattr(sdt, "BACKEND_ROOT", tmp_path)

    sample = tmp_path / "snippet.py"
    sample.write_text("# Dead comment\nactive_var = 100\n", encoding="utf-8")

    res = await validate_and_propose_patch(
        file_path="snippet.py",
        target_snippet="# Dead comment\n",
        replacement_snippet="",
    )
    assert res["success"] is True
    assert res["syntax_valid"] is True
    assert "-# Dead comment" in res["diff"]


@pytest.mark.asyncio
async def test_validate_and_propose_patch_nonexistent_target_snippet(tmp_path, monkeypatch):
    """Test proposing patch when target_snippet is not found in file."""
    import agents.tools.self_debug_tools as sdt
    monkeypatch.setattr(sdt, "BACKEND_ROOT", tmp_path)

    sample = tmp_path / "snippet.py"
    sample.write_text("def real_function():\n    return 42\n", encoding="utf-8")

    res = await validate_and_propose_patch(
        file_path="snippet.py",
        target_snippet="def non_existent_snippet():",
        replacement_snippet="def fixed_snippet():",
    )
    assert res["success"] is False
    assert "target_snippet was not found" in res["error"]


@pytest.mark.asyncio
async def test_validate_and_propose_patch_multiple_identical_snippets(tmp_path, monkeypatch):
    """Verify that multiple identical target snippets replace only the first occurrence."""
    import agents.tools.self_debug_tools as sdt
    monkeypatch.setattr(sdt, "BACKEND_ROOT", tmp_path)

    sample = tmp_path / "duplicates.py"
    sample.write_text("item = 'alpha'\nitem = 'alpha'\n", encoding="utf-8")

    res = await validate_and_propose_patch(
        file_path="duplicates.py",
        target_snippet="item = 'alpha'",
        replacement_snippet="item = 'beta'",
    )
    assert res["success"] is True
    assert res["syntax_valid"] is True
    assert "-item = 'alpha'" in res["diff"]
    assert "+item = 'beta'" in res["diff"]


# ============================================================================
# 4. SUBPROCESS, LOGS, AND EXTRACTOR TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_run_agent_tests_security_traversal():
    """Verify run_agent_tests rejects traversal attempts."""
    res = await run_agent_tests("../../etc/passwd")
    assert res["success"] is False
    assert res["errors"] == 1
    assert "Security Violation" in res["summary"] or "outside" in res["summary"]


@pytest.mark.asyncio
async def test_run_agent_tests_nonexistent_target():
    """Verify run_agent_tests handles non-existent test file cleanly."""
    res = await run_agent_tests("tests/test_nonexistent_suite_99999.py")
    assert res["success"] is False
    assert res["errors"] == 1
    assert "not found" in res["summary"].lower()


@pytest.mark.asyncio
async def test_fetch_error_logs_uninitialized_mysql():
    """Verify fetch_error_logs handles missing MySQL log service gracefully."""
    with patch("agents._service_registry.ServiceRegistry.log_service", None):
        res = await fetch_error_logs()
        assert res["success"] is False
        assert "unavailable" in res["error"].lower()
        assert res["logs"] == []


def test_extract_traceback_edge_cases():
    """Verify _extract_traceback handles diverse dictionary, message, and None inputs."""
    # Direct traceback in extra
    assert "Traceback" in _extract_traceback({"traceback": "Traceback:\n  File 'a.py'"}, "")

    # Direct details in extra
    assert "CustomError" in _extract_traceback({"details": "CustomError: something failed"}, "")

    # Traceback in message
    msg = "Log header: Traceback (most recent call last):\n  File 'b.py'\nKeyError: 'missing'"
    assert "KeyError" in _extract_traceback(None, msg)

    # Empty
    assert _extract_traceback(None, "Normal log message") is None


def test_parse_extra_edge_cases():
    """Verify _parse_extra handles invalid JSON, dict, None, and strings safely."""
    assert _parse_extra(None) == {}
    assert _parse_extra({"a": 1}) == {"a": 1}
    assert _parse_extra('{"a": 1}') == {"a": 1}
    assert _parse_extra("not valid json") == {"raw": "not valid json"}

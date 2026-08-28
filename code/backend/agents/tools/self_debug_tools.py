"""Self-Debug Tool Suite for Google ADK agents.

Provides sandboxed capabilities for inspecting backend source code, querying
runtime error logs, executing unit tests in a subshell, and validating proposed
patches via AST syntax checking.
"""
from __future__ import annotations

import ast
import difflib
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from agents._service_registry import ServiceRegistry

logger = logging.getLogger(__name__)

# Backend base directory boundary for path sandboxing
BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent


def _sanitize_path(relative_path: str) -> tuple[Path | None, str | None]:
    """Sanitize and validate that a relative path stays within BACKEND_ROOT."""
    clean = relative_path.lstrip("/\\")
    target = (BACKEND_ROOT / clean).resolve()
    try:
        target.relative_to(BACKEND_ROOT)
        return target, None
    except ValueError:
        return None, f"Security Violation: Path '{relative_path}' is outside the backend repository."


async def read_agent_code(
    file_path: str,
    function_or_class_name: str | None = None,
    start_line: int = 1,
    end_line: int | None = None,
) -> dict[str, Any]:
    """Safely inspect backend source code with line numbers and AST validation.

    Use this tool to read and understand backend Python modules, agents, services,
    or tool definitions when diagnosing an error or exploring implementation logic.

    Args:
        file_path: Relative path to backend file (e.g., 'agents/research/alrs_agent.py').
        function_or_class_name: Optional name of function or class to focus on.
        start_line: Starting line number (1-indexed, default: 1).
        end_line: Optional ending line number.

    Returns:
        A dict with file metadata, syntax check, symbol inventory, and numbered source code.
    """
    target, err = _sanitize_path(file_path)
    if err or target is None:
        return {"error": err, "success": False}

    if not target.exists() or not target.is_file():
        return {"error": f"File not found: '{file_path}'", "success": False}

    try:
        content = target.read_text(encoding="utf-8")
    except Exception as exc:
        return {"error": f"Could not read file: {exc}", "success": False}

    lines = content.splitlines()
    total_lines = len(lines)

    # 1. AST Validation & Symbol Indexing
    syntax_error = None
    symbols: list[str] = []
    try:
        tree = ast.parse(content, filename=str(target))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                symbols.append(node.name)
    except SyntaxError as exc:
        syntax_error = f"SyntaxError at line {exc.lineno}: {exc.msg}"

    # 2. Targeted symbol extraction
    extracted_focus = False
    if function_or_class_name and not syntax_error:
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if node.name == function_or_class_name:
                    start_line = node.lineno
                    end_line = getattr(node, "end_lineno", total_lines)
                    extracted_focus = True
                    break

    # 3. Line Slicing & Numbering
    start_idx = max(1, start_line)
    end_idx = min(total_lines, end_line if end_line is not None else (start_idx + 150))
    
    selected = lines[start_idx - 1 : end_idx]
    numbered = "\n".join(f"{i + start_idx:4d}: {line}" for i, line in enumerate(selected))

    return {
        "success": True,
        "file_path": file_path,
        "total_lines": total_lines,
        "showing_range": f"{start_idx}-{end_idx}",
        "focus_symbol": function_or_class_name if extracted_focus else None,
        "syntax_valid": syntax_error is None,
        "syntax_error": syntax_error,
        "symbols_in_file": symbols,
        "code": numbered,
    }


async def fetch_error_logs(
    service_name: str | None = None,
    limit: int = 5,
) -> dict[str, Any]:
    """Retrieve recent unhandled runtime exceptions and error tracebacks.

    Use this tool to see recent 4xx/5xx HTTP errors, failed tool invocations,
    or exception stack traces logged by backend services.

    Args:
        service_name: Optional filter for service name (e.g. 'OpenAlex', 'Gemini', 'LLMService').
        limit: Maximum number of recent error records to retrieve (1-20, default: 5).

    Returns:
        A dict containing a list of recent error events with stack traces and timestamps.
    """
    limit = max(1, min(limit, 20))
    try:
        log_service = ServiceRegistry.log_service
        mysql = getattr(log_service, "_mysql", None)
        if mysql is None:
            return {
                "success": False,
                "error": "Log database service is currently unavailable.",
                "logs": [],
            }

        # Query app_logs for ERROR or CRITICAL entries
        query = (
            "SELECT id, timestamp, level, logger_name, message, exception "
            "FROM app_logs "
            "WHERE level IN ('ERROR', 'CRITICAL') "
        )
        params: list[Any] = []
        if service_name:
            query += "AND logger_name LIKE %s "
            params.append(f"%{service_name}%")
        
        query += "ORDER BY id DESC LIMIT %s"
        params.append(limit)

        rows = await mysql.fetch_all(query, *params)
        
        formatted_logs = []
        for r in rows:
            formatted_logs.append({
                "id": r.get("id"),
                "timestamp": str(r.get("timestamp")),
                "level": r.get("level"),
                "logger": r.get("logger_name"),
                "message": r.get("message"),
                "traceback": r.get("exception"),
            })

        return {
            "success": True,
            "total_found": len(formatted_logs),
            "logs": formatted_logs,
        }
    except Exception as exc:
        logger.error("fetch_error_logs query failed: %s", exc)
        return {"success": False, "error": str(exc), "logs": []}


async def validate_and_propose_patch(
    file_path: str,
    target_snippet: str,
    replacement_snippet: str,
    explanation: str = "",
) -> dict[str, Any]:
    """Validate a proposed code fix for syntax correctness and produce a unified diff.

    Use this tool to verify that a code change is syntactically valid Python before
    suggesting or applying it.

    Args:
        file_path: Relative path to backend file to patch.
        target_snippet: The exact original code chunk to replace.
        replacement_snippet: The new replacement code chunk.
        explanation: Clear reasoning for why this patch fixes the bug.

    Returns:
        A dict with AST syntax validation result, diff preview, and patch metadata.
    """
    target, err = _sanitize_path(file_path)
    if err or target is None:
        return {"error": err, "success": False}

    if not target.exists() or not target.is_file():
        return {"error": f"File not found: '{file_path}'", "success": False}

    original_content = target.read_text(encoding="utf-8")

    if target_snippet not in original_content:
        return {
            "success": False,
            "error": "target_snippet was not found in the original file. Ensure exact whitespace and content match.",
            "file_path": file_path,
        }

    patched_content = original_content.replace(target_snippet, replacement_snippet, 1)

    # Validate AST syntax of the patched result
    syntax_error = None
    try:
        ast.parse(patched_content, filename=str(target))
    except SyntaxError as exc:
        syntax_error = f"SyntaxError in proposed patch at line {exc.lineno}: {exc.msg}"

    # Generate unified diff
    orig_lines = original_content.splitlines(keepends=True)
    patch_lines = patched_content.splitlines(keepends=True)
    diff = difflib.unified_diff(
        orig_lines,
        patch_lines,
        fromfile=f"a/{file_path}",
        tofile=f"b/{file_path}",
        lineterm="",
    )
    diff_text = "".join(diff)

    return {
        "success": syntax_error is None,
        "file_path": file_path,
        "syntax_valid": syntax_error is None,
        "syntax_error": syntax_error,
        "diff": diff_text,
        "explanation": explanation or "Proposed patch validated against Python AST.",
    }


async def run_agent_tests(
    test_path: str = "tests",
    keyword_filter: str | None = None,
) -> dict[str, Any]:
    """Execute pytest on targeted test files in a sandbox and return structured results.

    Use this tool to reproduce bugs, test hypotheses, or verify that a proposed fix
    passes the test suite.

    Args:
        test_path: Relative test path or file (e.g. 'tests/test_settings.py' or 'tests/test_self_debug.py').
        keyword_filter: Optional pytest -k keyword filter.

    Returns:
        A dict with exit code, summary stats (passed, failed, warnings), and stdout snippet.
    """
    clean_test_path = test_path.lstrip("/\\")
    if not clean_test_path.startswith("tests") and not clean_test_path.startswith("backend/tests"):
        clean_test_path = f"tests/{clean_test_path}"

    venv_pytest = BACKEND_ROOT / ".venv" / "bin" / "pytest"
    pytest_bin = str(venv_pytest) if venv_pytest.exists() else sys.executable + " -m pytest"

    cmd = [pytest_bin, clean_test_path, "-v", "--tb=short"]
    if keyword_filter:
        cmd.extend(["-k", keyword_filter])

    try:
        env = os.environ.copy()
        env["PYTHONPATH"] = str(BACKEND_ROOT)
        
        proc = subprocess.run(
            cmd,
            cwd=str(BACKEND_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=45,
            env=env,
        )

        output = proc.stdout or ""
        lines = output.splitlines()

        # Parse passed / failed summary line
        summary_line = lines[-1] if lines else "No output"

        return {
            "success": proc.returncode == 0,
            "exit_code": proc.returncode,
            "test_target": clean_test_path,
            "summary": summary_line,
            "output_tail": "\n".join(lines[-30:]) if len(lines) > 30 else output,
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error": "Test execution timed out after 45 seconds.",
            "test_target": clean_test_path,
        }
    except Exception as exc:
        return {
            "success": False,
            "error": f"Failed to execute tests: {exc}",
            "test_target": clean_test_path,
        }

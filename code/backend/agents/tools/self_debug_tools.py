"""Self-Debug Tool Suite for Google ADK agents.

Provides sandboxed capabilities for inspecting backend source code, querying
runtime error logs from MySQL app_logs and api_logs, executing unit tests
in a sandboxed subshell, and validating proposed patches via AST syntax checking.
"""
from __future__ import annotations

import ast
import difflib
import json
import logging
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from agents._service_registry import ServiceRegistry

logger = logging.getLogger(__name__)

# Backend base directory boundary for path sandboxing
BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent


def _sanitize_path(relative_path: str) -> tuple[Path | None, str | None]:
    """Sanitize and validate that a relative path stays strictly within BACKEND_ROOT."""
    if not relative_path:
        return None, "Security Violation: Empty path provided."
    clean = relative_path.strip().lstrip("/\\")
    if clean.startswith("backend/"):
        clean = clean[len("backend/"):]
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
    tree = None
    try:
        tree = ast.parse(content, filename=str(target))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                symbols.append(node.name)
    except SyntaxError as exc:
        syntax_error = f"SyntaxError at line {exc.lineno}: {exc.msg}"

    # 2. Targeted symbol extraction
    extracted_focus = False
    if function_or_class_name and tree and not syntax_error:
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

    if start_idx <= total_lines:
        selected = lines[start_idx - 1 : end_idx]
        numbered = "\n".join(f"{i + start_idx:4d}: {line}" for i, line in enumerate(selected))
    else:
        numbered = ""

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


def _extract_traceback(extra: dict[str, Any] | None, message: str) -> str | None:
    """Extract full traceback or stack trace from extra JSON or log message."""
    if extra and isinstance(extra, dict):
        for key in ("traceback", "stack_trace", "exception", "error", "exc_info", "details"):
            val = extra.get(key)
            if val:
                if isinstance(val, str) and ("Traceback" in val or "\n" in val):
                    return val
                elif isinstance(val, str):
                    return val
                elif isinstance(val, dict):
                    if "traceback" in val:
                        return str(val["traceback"])
                    return json.dumps(val, default=str)

    if message and "Traceback (most recent call last):" in message:
        idx = message.find("Traceback (most recent call last):")
        return message[idx:]

    return None


def _parse_extra(extra_raw: Any) -> dict[str, Any]:
    """Safely parse extra JSON data returned from MySQL."""
    if extra_raw is None:
        return {}
    if isinstance(extra_raw, dict):
        return extra_raw
    if isinstance(extra_raw, str):
        try:
            parsed = json.loads(extra_raw)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            return {"raw": extra_raw}
    return {}


async def fetch_error_logs(
    service_name: str | None = None,
    limit: int = 5,
    include_api_logs: bool = False,
) -> dict[str, Any]:
    """Retrieve recent unhandled runtime exceptions and error tracebacks.

    Queries MySQL app_logs (and optionally api_logs) using non-locking MVCC snapshot
    reads to retrieve recent ERROR/CRITICAL logs with extracted stack traces.

    Args:
        service_name: Optional filter for module/service name (e.g. 'openalex', 'gemini', 'crawler').
        limit: Maximum number of recent error records to retrieve (1-20, default: 5).
        include_api_logs: If True, also query api_logs for HTTP 4xx/5xx responses.

    Returns:
        A dict containing success status, total records, and formatted log objects with tracebacks.
    """
    clamped_limit = max(1, min(limit, 20))
    try:
        log_service = ServiceRegistry.log_service
        mysql = getattr(log_service, "_mysql", None) if log_service else None
        if mysql is None:
            return {
                "success": False,
                "error": "Log database service is currently unavailable or uninitialized.",
                "total_found": 0,
                "logs": [],
            }

        # MVCC Non-locking consistent read on valid app_logs schema columns
        query = (
            "SELECT id, session_id, level, module, message, extra, created_at "
            "FROM app_logs "
            "WHERE level IN ('ERROR', 'CRITICAL') "
        )
        params: list[Any] = []
        if service_name:
            query += "AND (module LIKE %s OR message LIKE %s) "
            pattern = f"%{service_name}%"
            params.extend([pattern, pattern])

        query += "ORDER BY id DESC LIMIT %s"
        params.append(clamped_limit)

        rows = await mysql.fetch_all(query, tuple(params))

        formatted_logs: list[dict[str, Any]] = []
        for r in rows:
            extra_dict = _parse_extra(r.get("extra"))
            msg = str(r.get("message") or "")
            tb = _extract_traceback(extra_dict, msg) or r.get("exception")
            created = r.get("created_at") or r.get("timestamp")
            module_name = r.get("module") or r.get("logger_name") or r.get("service")

            formatted_logs.append({
                "id": r.get("id"),
                "timestamp": str(created) if created is not None else None,
                "level": r.get("level"),
                "module": module_name,
                "logger": module_name,  # Alias for backward compatibility
                "message": msg,
                "traceback": tb,
                "extra": extra_dict,
                "session_id": r.get("session_id"),
            })

        result: dict[str, Any] = {
            "success": True,
            "total_found": len(formatted_logs),
            "logs": formatted_logs,
        }

        if include_api_logs:
            api_query = (
                "SELECT id, session_id, service, method, url, status_code, "
                "response_time_ms, payload_summary, request_body, response_body, created_at "
                "FROM api_logs "
                "WHERE status_code >= 400 "
            )
            api_params: list[Any] = []
            if service_name:
                api_query += "AND (service LIKE %s OR url LIKE %s) "
                api_pattern = f"%{service_name}%"
                api_params.extend([api_pattern, api_pattern])

            api_query += "ORDER BY id DESC LIMIT %s"
            api_params.append(clamped_limit)

            api_rows = await mysql.fetch_all(api_query, tuple(api_params))
            formatted_api_logs = []
            for ar in api_rows:
                formatted_api_logs.append({
                    "id": ar.get("id"),
                    "timestamp": str(ar.get("created_at")) if ar.get("created_at") else None,
                    "service": ar.get("service"),
                    "method": ar.get("method"),
                    "url": ar.get("url"),
                    "status_code": ar.get("status_code"),
                    "response_time_ms": ar.get("response_time_ms"),
                    "payload_summary": ar.get("payload_summary"),
                    "response_body": ar.get("response_body"),
                    "session_id": ar.get("session_id"),
                })
            result["api_errors"] = formatted_api_logs

        return result
    except Exception as exc:
        logger.error("fetch_error_logs query failed: %s", exc)
        return {
            "success": False,
            "error": f"Database query error: {exc}",
            "total_found": 0,
            "logs": [],
        }


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
    """Execute pytest on targeted test files in a sandboxed subprocess and return structured results.

    Use this tool to reproduce bugs, test hypotheses, or verify that a proposed fix
    passes the test suite.

    Args:
        test_path: Relative test path, file, or test node (e.g. 'tests/test_settings.py'
                   or 'tests/test_self_debug.py::test_sanitize_path_security_traversal').
        keyword_filter: Optional pytest -k keyword filter.

    Returns:
        A structured dict: {"success": bool, "summary": str, "passed": int, "failed": int, "errors": int, "output": str, ...}
    """
    clean_test_path = test_path.strip().lstrip("/\\")

    # Handle pytest node selector syntax (e.g. tests/test_foo.py::test_bar)
    node_part = ""
    if "::" in clean_test_path:
        file_part, node_part = clean_test_path.split("::", 1)
        node_part = "::" + node_part
    else:
        file_part = clean_test_path

    if file_part.startswith("backend/"):
        file_part = file_part[len("backend/"):]
    if not file_part.startswith("tests"):
        file_part = f"tests/{file_part}"

    target, err = _sanitize_path(file_part)
    if err or target is None:
        return {
            "success": False,
            "summary": err or f"Security Violation: Path '{test_path}' is outside the backend repository.",
            "passed": 0,
            "failed": 0,
            "errors": 1,
            "output": err or "Security violation: path traversal blocked.",
            "duration_seconds": 0.0,
            "exit_code": -1,
            "test_target": test_path,
            "tracebacks": "",
        }

    if not target.exists():
        msg = f"Test target not found: '{file_part}'"
        return {
            "success": False,
            "summary": msg,
            "passed": 0,
            "failed": 0,
            "errors": 1,
            "output": msg,
            "duration_seconds": 0.0,
            "exit_code": -1,
            "test_target": file_part,
            "tracebacks": "",
        }

    # Binary detection: .venv/bin/pytest -> .venv/bin/python3 -m pytest -> sys.executable -m pytest
    venv_pytest = BACKEND_ROOT / ".venv" / "bin" / "pytest"
    venv_python = BACKEND_ROOT / ".venv" / "bin" / "python3"
    if venv_pytest.exists():
        cmd = [str(venv_pytest)]
    elif venv_python.exists():
        cmd = [str(venv_python), "-m", "pytest"]
    else:
        cmd = [sys.executable, "-m", "pytest"]

    # Target path relative to BACKEND_ROOT + optional node selector
    rel_target = f"{target.relative_to(BACKEND_ROOT)}{node_part}"
    cmd.extend([rel_target, "-v", "--tb=short"])
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
            shell=False,
        )

        output = proc.stdout or ""

        # Parse metrics using regex
        passed_m = re.search(r"(\d+)\s+passed", output)
        failed_m = re.search(r"(\d+)\s+failed", output)
        error_m = re.search(r"(\d+)\s+error", output)
        time_m = re.search(r"in\s+([\d\.]+)s", output)

        passed = int(passed_m.group(1)) if passed_m else 0
        failed = int(failed_m.group(1)) if failed_m else 0
        errors = int(error_m.group(1)) if error_m else 0
        duration = float(time_m.group(1)) if time_m else 0.0

        # Summary line extraction
        summary_match = re.search(
            r"=+\s*((?:(?:\d+\s+\w+(?:,\s*)?|no tests ran).*?in\s+[\d\.]+s.*?))=+",
            output,
        )
        if summary_match:
            summary = summary_match.group(1).strip()
        else:
            non_empty = [l.strip() for l in output.splitlines() if l.strip()]
            summary = non_empty[-1] if non_empty else f"Exit code {proc.returncode}"

        if proc.returncode != 0 and failed == 0 and errors == 0:
            errors = 1

        # Extract failure/error tracebacks section
        tracebacks = ""
        fail_section_m = re.search(
            r"(=+\s*(?:FAILURES|ERRORS)\s*=+.*?)(?:=+\s*short test summary info|\Z)",
            output,
            re.DOTALL,
        )
        if fail_section_m:
            tracebacks = fail_section_m.group(1).strip()

        return {
            "success": proc.returncode == 0,
            "summary": summary,
            "passed": passed,
            "failed": failed,
            "errors": errors,
            "output": output,
            "duration_seconds": duration,
            "exit_code": proc.returncode,
            "test_target": rel_target,
            "tracebacks": tracebacks,
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "summary": "Test execution timed out after 45 seconds.",
            "passed": 0,
            "failed": 0,
            "errors": 1,
            "output": "TimeoutExpired: Test execution exceeded 45s threshold.",
            "duration_seconds": 45.0,
            "exit_code": -1,
            "test_target": rel_target,
            "tracebacks": "",
        }
    except Exception as exc:
        return {
            "success": False,
            "summary": f"Failed to execute tests: {exc}",
            "passed": 0,
            "failed": 0,
            "errors": 1,
            "output": f"Execution exception: {exc}",
            "duration_seconds": 0.0,
            "exit_code": -1,
            "test_target": rel_target,
            "tracebacks": "",
        }


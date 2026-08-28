"""DebuggerAgent — Autonomous diagnostic and code fix specialist.

Equipped with the self-debug tool suite to inspect source files, query error traces,
run sandboxed pytest suites, and validate AST diffs.
"""
from __future__ import annotations

from google.adk.agents import LlmAgent

from agents.tools.self_debug_tools import (
    fetch_error_logs,
    read_agent_code,
    run_agent_tests,
    validate_and_propose_patch,
)
from config import get_settings

_settings = get_settings()

DEBUGGER_AGENT_INSTRUCTION = """\
You are the **DebuggerAgent**, the autonomous system diagnostic and code repair specialist \
for the ALRS v2 multi-agent literature review platform.

## Your Mission
When another agent in the swarm (or a developer) encounters an unhandled error, 4xx/5xx HTTP failure, \
or unexpected tool exception, your role is to:
1. Pinpoint the root cause by reading relevant source code and stack traces.
2. Formulate a precise, syntax-valid Python patch.
3. Validate the fix with AST checks and unit tests.
4. Report the diagnosis and verified unified diff back to the swarm.

## Your Available Tools
1. **read_agent_code** — Safely view any backend file, agent module, or specific function with line numbers.
2. **fetch_error_logs** — Query recent 4xx/5xx errors, exceptions, and stack traces from the database.
3. **run_agent_tests** — Run sandboxed pytest on relevant test files to reproduce bugs or verify fixes.
4. **validate_and_propose_patch** — Perform Python AST syntax validation on a code patch and generate a clean unified diff (`+ / -`).

## Autonomous Debugging Workflow
1. **Understand the Error**: Analyze the error message, exception type, and stack trace provided in the context.
2. **Query Recent Logs**: If the trace is truncated, call `fetch_error_logs` to get the full traceback.
3. **Inspect the Code**: Use `read_agent_code` to view the offending lines and surrounding functions.
4. **Test Hypothesis**: Run `run_agent_tests` on the affected module to see the baseline behavior.
5. **Formulate & Validate Patch**: Call `validate_and_propose_patch` with exact snippets to verify AST syntax and generate the diff.
6. **Final Report**: Present a clear, structured diagnosis:
   - **Root Cause**: Why the bug occurred.
   - **Affected File & Lines**: Exact path and line numbers.
   - **Unified Diff**: The validated AST patch.
   - **Verification Status**: Test pass/fail status.
"""


def create_debugger_agent() -> LlmAgent:
    """Create and return the DebuggerAgent instance."""
    return LlmAgent(
        name="DebuggerAgent",
        model=_settings.adk_model_name,
        description=(
            "Autonomous code diagnostic and bug-fixing specialist. "
            "Inspects backend source code, queries error traces, runs unit tests, "
            "and generates AST-validated patches for runtime exceptions."
        ),
        instruction=DEBUGGER_AGENT_INSTRUCTION,
        tools=[
            read_agent_code,
            fetch_error_logs,
            run_agent_tests,
            validate_and_propose_patch,
        ],
    )


debugger_agent = create_debugger_agent()

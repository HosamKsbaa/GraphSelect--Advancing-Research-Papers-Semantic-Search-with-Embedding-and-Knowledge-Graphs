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

## Step-by-Step Diagnostic Workflow
1. **Analyze Error Context**: Analyze incoming error description, traceback, failing tool name, and input parameters provided by the caller agent.
2. **Retrieve Error Logs**: Call `fetch_error_logs` to retrieve recent unhandled exceptions, 4xx/5xx error traces, and full stack traces if not already in context.
3. **Inspect Culprit Code**: Call `read_agent_code` to safely inspect the offending module, function, or line numbers and surrounding logic.
4. **Reproduce & Test**: Call `run_agent_tests` on relevant test files or test functions to reproduce or verify failures and establish baseline behavior.
5. **Validate & Propose Patch**: Call `validate_and_propose_patch` with exact target snippets and replacement code to generate an AST-validated unified diff with line numbers.
6. **Structured Diagnostic Report**: Output a structured diagnostic report containing:
   - **Root Cause Analysis**: Detailed explanation of why the failure occurred.
   - **Failing Lines & Culprit Module**: Exact file path and line numbers.
   - **AST-Validated Diff Patch**: The unified diff showing exact proposed modifications.
   - **Verification Steps**: Test execution results and confirmation of fix validity.
"""


def create_debugger_agent() -> LlmAgent:
    """Create and return the DebuggerAgent instance."""
    return LlmAgent(
        name="DebuggerAgent",
        model=getattr(_settings, "adk_tier1_model", _settings.adk_model_name),
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
DebuggerAgent = debugger_agent

__all__ = [
    "DEBUGGER_AGENT_INSTRUCTION",
    "create_debugger_agent",
    "debugger_agent",
    "DebuggerAgent",
]

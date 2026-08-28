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


def test_debugger_agent_exports():
    """Verify DebuggerAgent exports in agents, agents.agent, and agents.debugger."""
    import agents
    import agents.agent
    import agents.debugger

    assert hasattr(agents, "DebuggerAgent")
    assert hasattr(agents, "create_debugger_agent")
    assert hasattr(agents, "debugger_agent")

    assert hasattr(agents.agent, "DebuggerAgent")
    assert hasattr(agents.agent, "create_debugger_agent")
    assert hasattr(agents.agent, "debugger_agent")

    assert hasattr(agents.debugger, "DebuggerAgent")
    assert hasattr(agents.debugger, "create_debugger_agent")
    assert hasattr(agents.debugger, "debugger_agent")

    assert agents.debugger.debugger_agent.name == "DebuggerAgent"


def test_orchestrator_debugger_registration():
    """Verify DebuggerAgent is registered inside ProjectAgent and root_agent sub-agents."""
    from agents.agent import root_agent

    root_sub_agent_names = [a.name for a in root_agent.sub_agents]
    assert "ResearchAgent" in root_sub_agent_names
    assert "PlannerAgent" in root_sub_agent_names
    assert "WriterAgent" in root_sub_agent_names
    assert "DebuggerAgent" in root_sub_agent_names


def test_swarm_wide_global_error_delegation_protocol():
    """Verify that all 9 ALRS swarm agents have ## Global Error Delegation Protocol configured."""
    from agents.orchestrator.agent import ORCHESTRATOR_INSTRUCTION
    from agents.research.agent import RESEARCH_AGENT_INSTRUCTION
    from agents.research.alrs_agent import ALRS_AGENT_INSTRUCTION
    from agents.research.gap_finder import GAP_FINDER_INSTRUCTION
    from agents.research.evidence_synthesizer import EVIDENCE_SYNTHESIZER_INSTRUCTION
    from agents.planner.agent import PLANNER_INSTRUCTION
    from agents.writing.agent import WRITER_INSTRUCTION
    from agents.writing.drafting_agent import DRAFTING_INSTRUCTION
    from agents.writing.reviewer_agent import REVIEWER_INSTRUCTION

    instructions = {
        "ProjectAgent": ORCHESTRATOR_INSTRUCTION,
        "ResearchAgent": RESEARCH_AGENT_INSTRUCTION,
        "ALRSAgent": ALRS_AGENT_INSTRUCTION,
        "GapFinderAgent": GAP_FINDER_INSTRUCTION,
        "EvidenceSynthesizerAgent": EVIDENCE_SYNTHESIZER_INSTRUCTION,
        "PlannerAgent": PLANNER_INSTRUCTION,
        "WriterAgent": WRITER_INSTRUCTION,
        "DraftingAgent": DRAFTING_INSTRUCTION,
        "ReviewerAgent": REVIEWER_INSTRUCTION,
    }

    for agent_name, inst in instructions.items():
        assert "## Global Error Delegation Protocol" in inst, f"{agent_name} missing '## Global Error Delegation Protocol'"
        assert "DebuggerAgent" in inst, f"{agent_name} does not reference DebuggerAgent"
        assert "failing" in inst.lower(), f"{agent_name} does not specify failing tool/parameter capture"
        assert "project_id" in inst or "project" in inst.lower(), f"{agent_name} missing project context"


def test_repeated_factory_instantiation():
    """Verify that create_root_agent and create_orchestrator_agent can be invoked multiple times without ValidationError."""
    from agents.agent import create_root_agent
    from agents.orchestrator.agent import create_orchestrator_agent
    from agents.planner.agent import create_planner_agent
    from agents.writing.agent import create_writer_agent
    from agents.writing.drafting_agent import create_drafting_agent
    from agents.writing.reviewer_agent import create_reviewer_agent
    from agents.research.agent import create_research_agent
    from agents.debugger.agent import create_debugger_agent

    roots = []
    orchestrators = []
    for i in range(5):
        root = create_root_agent()
        orch = create_orchestrator_agent(project_id=f"proj-test-{i}")
        planner = create_planner_agent()
        writer = create_writer_agent()
        drafting = create_drafting_agent()
        reviewer = create_reviewer_agent()
        research = create_research_agent()
        debugger = create_debugger_agent()

        assert root.name == "ProjectAgent"
        assert orch.name == "ProjectAgent"
        assert planner.name == "PlannerAgent"
        assert writer.name == "WriterAgent"
        assert drafting.name == "DraftingAgent"
        assert reviewer.name == "ReviewerAgent"
        assert research.name == "ResearchAgent"
        assert debugger.name == "DebuggerAgent"

        # Check sub-agents hierarchy
        sub_names = [sa.name for sa in orch.sub_agents]
        assert "ResearchAgent" in sub_names
        assert "PlannerAgent" in sub_names
        assert "WriterAgent" in sub_names
        assert "DebuggerAgent" in sub_names

        roots.append(root)
        orchestrators.append(orch)

    # Verify each iteration constructed fresh, distinct instances
    for i in range(len(roots)):
        for j in range(i + 1, len(roots)):
            assert roots[i] is not roots[j]
            assert orchestrators[i] is not orchestrators[j]





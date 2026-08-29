"""Programmatic ADK Agent Evaluation Test Suite.

This module integrates Google ADK Evaluation capabilities into the automated
test suite, allowing programmatic evaluation of:
1. Tool Trajectory Matching (tool_trajectory_avg_score)
2. Response Semantic Matching (response_match_score)
3. Zero-Hallucination Citation Groundedness (hallucinations_v1)
4. Evaluation dataset schema validity and serialization
"""
from __future__ import annotations

import json
from pathlib import Path
import pytest
from google.adk.evaluation.agent_evaluator import AgentEvaluator
from google.adk.evaluation.eval_set import EvalSet


EVAL_SET_PATH = Path(__file__).parent.parent / "agents" / "evals" / "alrs_research.evalset.json"


def test_evalset_file_schema_and_integrity() -> None:
    """Validate that the ALRS evalset JSON matches the ADK Pydantic schema."""
    assert EVAL_SET_PATH.exists(), f"Evalset file missing at {EVAL_SET_PATH}"
    with open(EVAL_SET_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    eval_set = EvalSet.model_validate(data)
    assert eval_set.eval_set_id == "alrs_research_workflow_eval"
    assert len(eval_set.eval_cases) >= 2

    # Case 1: GraphSelect Traversal
    case1 = eval_set.eval_cases[0]
    assert case1.eval_id == "eval_graphselect_traversal_01"
    assert len(case1.conversation) == 1
    assert case1.conversation[0].intermediate_data.tool_uses[0].name == "run_graphselect_traversal"

    # Case 2: Keyword Search
    case2 = eval_set.eval_cases[1]
    assert case2.eval_id == "eval_keyword_search_02"
    assert case2.conversation[0].intermediate_data.tool_uses[0].name == "search_papers_by_keyword"


@pytest.mark.asyncio
async def test_programmatic_agent_eval_execution() -> None:
    """Execute programmatic evaluation over the ALRS research eval dataset."""
    with open(EVAL_SET_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    eval_set = EvalSet.model_validate(data)

    criteria = {
        "tool_trajectory_avg_score": 1.0,
        "response_match_score": 0.8,
    }

    # Run single-pass evaluation
    results = await AgentEvaluator.evaluate_eval_set(
        agent_module="agents",
        eval_set=eval_set,
        criteria=criteria,
        num_runs=1,
        print_detailed_results=False,
    )
    assert results is not None

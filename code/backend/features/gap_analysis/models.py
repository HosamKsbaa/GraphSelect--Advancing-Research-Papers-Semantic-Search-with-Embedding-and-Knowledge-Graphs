"""Pydantic v2 domain models for Autonomous Gap-Driven Search Remediation.

Complies with Constitution v2.2.1:
- C7: Strict static typing without bare signatures.
- C9: Granular sub-routines under 25 lines.
- C11: Intention-revealing domain types and predicate booleans.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


class RemediationMode(str, Enum):
    """Execution mode for autonomous research question gap remediation."""

    EXPLORATION = "exploration"
    REFINEMENT = "refinement"
    TARGETED = "targeted"


class RemediationCycleStatus(str, Enum):
    """Terminal or in-progress status of an autonomous remediation cycle."""

    CONVERGED = "converged"
    MAX_ITERATIONS_PAUSED = "paused_awaiting_input"
    OPEN_RESEARCH_FRONTIER = "open_research_frontier"
    IN_PROGRESS = "in_progress"


class GapRemediationCycle(BaseModel):
    """Records one targeted search iteration for an under-covered research question."""

    cycle_id: str = Field(..., description="UUID for this remediation cycle")
    iteration: int = Field(..., ge=1, le=3, description="Current iteration (1, 2, or 3)")
    target_rq_id: str = Field(..., description="UUID of deficient ResearchQuestion")
    initial_coverage: float = Field(..., ge=0.0, le=1.0)
    queries_generated: list[str] = Field(..., min_length=1, max_length=5)
    retrieved_candidate_dois: list[str] = Field(default_factory=list, max_length=3)
    accepted_dois: list[str] = Field(default_factory=list)
    resulting_coverage: float = Field(..., ge=0.0, le=1.0)
    coverage_delta: float = Field(..., description="Delta = resulting_coverage - initial_coverage")
    status: RemediationCycleStatus
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class RunAutonomousGapRemediationInput(BaseModel):
    """Input contract for autonomous gap-driven literature acquisition."""

    project_id: str = Field(..., description="Active research project UUID")
    rq_id: str = Field(..., description="Target ResearchQuestion UUID")
    mode: RemediationMode = Field(default=RemediationMode.EXPLORATION, description="Active campaign mode")
    max_iterations: int = Field(default=3, ge=1, le=3, description="Maximum allowed loops (capped at 3)")
    run_id: str = Field(..., description="Active workflow execution / run UUID per Constitution C5, A15, A49")
    stage_index: int = Field(default=2, description="Workflow stage index")


class RunAutonomousGapRemediationOutput(BaseModel):
    """Output contract after completing autonomous remediation cycle."""

    status: RemediationCycleStatus = Field(..., description="Final cycle status")
    rq_id: str = Field(..., description="Target ResearchQuestion UUID")
    iterations_executed: int = Field(..., ge=1, le=3, description="Total loops completed")
    initial_coverage: float = Field(..., ge=0.0, le=1.0, description="Initial C(RQ_i)")
    final_coverage: float = Field(..., ge=0.0, le=1.0, description="Final C(RQ_i)")
    papers_ingested: list[str] = Field(default_factory=list, description="List of DOIs ingested during loop")
    mode: RemediationMode = Field(..., description="Execution mode applied")
    is_open_frontier: bool = Field(default=False, description="True if marked as Open Research Frontier")

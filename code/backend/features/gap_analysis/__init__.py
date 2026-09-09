"""Gap Analysis and Autonomous Search Remediation feature module.

Exports Pydantic v2 domain models, coverage calculator, and remediation service.
"""
from __future__ import annotations

from features.gap_analysis.coverage_calculator import (
    CALCULATE_RQ_COVERAGE_CYPHER,
    calculate_coverage_from_embeddings,
    calculate_question_coverage,
    compute_cosine_similarity,
    normalize_coverage_score,
)
from features.gap_analysis.models import (
    GapRemediationCycle,
    RemediationCycleStatus,
    RemediationMode,
    RunAutonomousGapRemediationInput,
    RunAutonomousGapRemediationOutput,
)
from features.gap_analysis.remediation_service import (
    RemediationService,
    fallback_targeted_queries,
)

__all__ = [
    "CALCULATE_RQ_COVERAGE_CYPHER",
    "GapRemediationCycle",
    "RemediationCycleStatus",
    "RemediationMode",
    "RemediationService",
    "RunAutonomousGapRemediationInput",
    "RunAutonomousGapRemediationOutput",
    "calculate_coverage_from_embeddings",
    "calculate_question_coverage",
    "compute_cosine_similarity",
    "fallback_targeted_queries",
    "normalize_coverage_score",
]

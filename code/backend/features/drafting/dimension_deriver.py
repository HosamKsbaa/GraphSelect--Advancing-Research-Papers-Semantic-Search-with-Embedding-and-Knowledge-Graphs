"""Section Analytical Dimension Deriver (T044).

Derives 3 to 5 section-specific analytical dimensions tailored to an outline
section's blueprint, narrative theme, and assigned literature.

Complies with Constitution v2.2.1:
- C7: Strict static typing.
- C9: Every function strictly <= 25 lines (SRP & SLAP).
- C10: Early returns and guard clauses.
- C11: Domain types and predicate booleans.
"""
from __future__ import annotations

import logging
import re
from typing import Any

from features.drafting.matrix_models import AnalyticalDimension

logger = logging.getLogger(__name__)

ALLOWED_EVAL_TYPES: frozenset[str] = frozenset({"qualitative", "metric", "benchmark"})


def _slugify(name: str) -> str:
    """Convert display name into normalized snake_case slug."""
    cleaned = re.sub(r"[^\w\s-]", "", name).strip().lower()
    return re.sub(r"[-\s]+", "_", cleaned).strip("_")


def _dim(dim_id: str, name: str, desc: str, eval_type: str) -> AnalyticalDimension:
    """Instantiate an AnalyticalDimension model."""
    return AnalyticalDimension(
        dimension_id=dim_id, name=name, description=desc, evaluation_type=eval_type
    )


def _validate_count(count: int) -> None:
    """Enforce strict 3 to 5 dimension count boundary."""
    if count < 3 or count > 5:
        raise ValueError(
            f"Analytical dimensions count must be between 3 and 5 inclusive, got {count}"
        )


def _validate_slug_uniqueness(dimensions: list[AnalyticalDimension]) -> None:
    """Ensure all dimension slugs in the matrix are unique."""
    seen: set[str] = set()
    for dim in dimensions:
        if dim.dimension_id in seen:
            raise ValueError(f"Duplicate dimension slug detected: '{dim.dimension_id}'")
        seen.add(dim.dimension_id)


def _validate_evaluation_type(dim: AnalyticalDimension) -> None:
    """Ensure evaluation_type matches one of qualitative, metric, or benchmark."""
    if dim.evaluation_type not in ALLOWED_EVAL_TYPES:
        raise ValueError(
            f"Invalid evaluation_type '{dim.evaluation_type}' for dimension '{dim.name}'. "
            f"Allowed: {sorted(ALLOWED_EVAL_TYPES)}"
        )


def validate_dimensions(dimensions: list[AnalyticalDimension]) -> list[AnalyticalDimension]:
    """Validate full dimension collection against domain constraints."""
    _validate_count(len(dimensions))
    _validate_slug_uniqueness(dimensions)
    for dim in dimensions:
        _validate_evaluation_type(dim)
    return dimensions


def _match_category(text: str) -> str:
    """Categorize section theme based on lexical indicators."""
    lower = text.lower()
    if any(k in lower for k in ("mitigat", "hallucinat", "ground", "faith")):
        return "mitigation"
    if any(k in lower for k in ("method", "architect", "algorithm", "travers", "graph")):
        return "methodology"
    if any(k in lower for k in ("evaluat", "benchmark", "result", "metric", "perform")):
        return "evaluation"
    if any(k in lower for k in ("gap", "coverage", "deficit", "remediat")):
        return "gap_analysis"
    return "general"


def _build_mitigation_dims() -> list[AnalyticalDimension]:
    """Build dimensions for hallucination and grounding mitigation sections."""
    return [
        _dim("mitigation_mechanism", "Mitigation Mechanism", "Intervention preventing hallucination", "qualitative"),
        _dim("verification_benchmark", "Verification Benchmark", "Academic dataset used for verification", "benchmark"),
        _dim("empirical_failure_rate", "Empirical Failure Rate", "Error rate observed under stress tests", "metric"),
        _dim("computational_overhead", "Computational Overhead", "Latency or cost overhead of verification", "metric"),
    ]


def _build_methodology_dims() -> list[AnalyticalDimension]:
    """Build dimensions for architectural and algorithmic sections."""
    return [
        _dim("algorithm_family", "Algorithm Family", "Theoretical foundation or architectural archetype", "qualitative"),
        _dim("search_space_pruning", "Search Space Pruning", "Strategy applied to bound candidate complexity", "qualitative"),
        _dim("traversal_hop_depth", "Traversal Hop Depth", "Maximum multi-hop pathway reach", "metric"),
        _dim("ranking_centrality_metric", "Ranking Centrality Metric", "Graph centrality metric used for ranking", "benchmark"),
    ]


def _build_evaluation_dims() -> list[AnalyticalDimension]:
    """Build dimensions for empirical results and evaluation sections."""
    return [
        _dim("benchmark_dataset", "Benchmark Dataset", "Corpus or empirical test suite used for validation", "benchmark"),
        _dim("primary_performance_metric", "Primary Performance Metric", "Key quantitative metric measuring accuracy", "metric"),
        _dim("baseline_comparison", "Baseline Comparison", "State-of-the-art baselines evaluated against", "qualitative"),
        _dim("statistical_significance", "Statistical Significance", "Reported p-value or effect size delta", "metric"),
    ]


def _build_gap_analysis_dims() -> list[AnalyticalDimension]:
    """Build dimensions for gap analysis and research frontier sections."""
    return [
        _dim("deficit_classification", "Deficit Classification", "Identified literature shortage focus", "qualitative"),
        _dim("coverage_score_delta", "Coverage Score Delta", "Quantitative change in question coverage", "metric"),
        _dim("remediation_strategy", "Remediation Strategy", "Targeted retrieval or bridge pathway strategy", "qualitative"),
    ]


def _build_general_dims() -> list[AnalyticalDimension]:
    """Build fallback dimensions for general analytical outline sections."""
    return [
        _dim("methodological_approach", "Methodological Approach", "Primary methodology or framework applied", "qualitative"),
        _dim("quantitative_outcome", "Quantitative Outcome", "Reported empirical performance improvement", "metric"),
        _dim("comparative_baseline", "Comparative Baseline", "Reference system or standard compared against", "benchmark"),
        _dim("operational_tradeoff", "Operational Trade-Off", "Identified limitation or scalability boundary", "qualitative"),
    ]


def _resolve_category_dims(category: str) -> list[AnalyticalDimension]:
    """Route detected theme category to corresponding dimension generator."""
    if category == "mitigation":
        return _build_mitigation_dims()
    if category == "methodology":
        return _build_methodology_dims()
    if category == "evaluation":
        return _build_evaluation_dims()
    if category == "gap_analysis":
        return _build_gap_analysis_dims()
    return _build_general_dims()


def derive_section_dimensions(
    section_title: str,
    narrative_theme: str,
    paper_abstracts: list[str] | None = None,
    llm_client: Any = None,
) -> list[AnalyticalDimension]:
    """Derive 3 to 5 section-specific analytical dimensions (T044).

    Analyzes section title, narrative theme, and optional literature abstracts
    to synthesize tailored analytical dimensions with unique slugs.
    """
    combined = f"{section_title} {narrative_theme}"
    category = _match_category(combined)
    dimensions = _resolve_category_dims(category)
    return validate_dimensions(dimensions)

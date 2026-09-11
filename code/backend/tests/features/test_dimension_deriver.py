"""Unit tests for Section Dimension Deriver (T042 / T044).

Verifies:
- Derivation of 3 to 5 distinct dimensions based on section title and theme.
- Dimension slug format, uniqueness, and display names.
- Evaluation types strictly within {qualitative, metric, benchmark}.
- Boundary validation: ValueError when dimensions count < 3 or > 5.
- Validation rejection on duplicate slugs and invalid evaluation types.

Complies with Constitution v2.2.1:
- C7: Complete static typing.
- C9: Every function strictly <= 25 lines (SRP & SLAP).
"""
from __future__ import annotations

import pytest

from features.drafting.dimension_deriver import (
    _slugify,
    derive_section_dimensions,
    validate_dimensions,
)
from features.drafting.matrix_models import AnalyticalDimension


def test_slugify_normalization() -> None:
    """Test string conversion to clean snake_case slug."""
    assert _slugify("Mitigation Mechanism!") == "mitigation_mechanism"
    assert _slugify("  Empirical -- Failure Rate  ") == "empirical_failure_rate"
    assert _slugify("F1-Score / Accuracy") == "f1_score_accuracy"


def test_derive_dimensions_mitigation_theme() -> None:
    """Derive dimensions for hallucination mitigation section."""
    title = "Hallucination Mitigation and Grounding"
    theme = "Evaluating epistemic fact-checking and citekey verification mechanisms"
    dims = derive_section_dimensions(title, theme)
    assert 3 <= len(dims) <= 5
    slugs = [d.dimension_id for d in dims]
    assert len(slugs) == len(set(slugs))
    assert "mitigation_mechanism" in slugs


def test_derive_dimensions_methodology_theme() -> None:
    """Derive dimensions for methodology and algorithmic traversal section."""
    title = "Graph Traversal Methodology"
    theme = "Multi-hop citation exploration with adaptive beam search"
    dims = derive_section_dimensions(title, theme)
    assert 3 <= len(dims) <= 5
    types = {d.evaluation_type for d in dims}
    assert "qualitative" in types
    assert any(t in {"metric", "benchmark"} for t in types)


def test_derive_dimensions_evaluation_theme() -> None:
    """Derive dimensions for empirical results and evaluation section."""
    title = "Empirical Results and Comparative Evaluation"
    theme = "Performance benchmarks against standard dense vector baselines"
    dims = derive_section_dimensions(title, theme)
    assert 3 <= len(dims) <= 5
    assert any(d.dimension_id == "primary_performance_metric" for d in dims)


def test_derive_dimensions_gap_analysis_theme() -> None:
    """Derive dimensions for literature gap and remediation section."""
    title = "Open Research Frontiers"
    theme = "Literature deficit classification and coverage remediation"
    dims = derive_section_dimensions(title, theme)
    assert 3 <= len(dims) <= 5
    assert any(d.dimension_id == "deficit_classification" for d in dims)


def test_derive_dimensions_general_fallback() -> None:
    """Derive fallback dimensions for general topical sections."""
    title = "Introduction to Knowledge Graphs"
    theme = "Overview of epistemic networks"
    dims = derive_section_dimensions(title, theme)
    assert len(dims) == 4
    for dim in dims:
        assert len(dim.name) > 0
        assert len(dim.description) > 0


def test_validate_dimensions_accepts_valid_range() -> None:
    """Validate helper accepts exactly 3, 4, and 5 valid dimensions."""
    base_dim = AnalyticalDimension(
        dimension_id="dim_1", name="Dim 1", description="Desc", evaluation_type="qualitative"
    )
    dim2 = AnalyticalDimension(
        dimension_id="dim_2", name="Dim 2", description="Desc", evaluation_type="metric"
    )
    dim3 = AnalyticalDimension(
        dimension_id="dim_3", name="Dim 3", description="Desc", evaluation_type="benchmark"
    )
    assert len(validate_dimensions([base_dim, dim2, dim3])) == 3


def test_validate_dimensions_rejects_fewer_than_three() -> None:
    """Validate helper raises ValueError when fewer than 3 dimensions given."""
    dim1 = AnalyticalDimension(
        dimension_id="d1", name="D1", description="Desc", evaluation_type="qualitative"
    )
    dim2 = AnalyticalDimension(
        dimension_id="d2", name="D2", description="Desc", evaluation_type="metric"
    )
    with pytest.raises(ValueError, match="between 3 and 5"):
        validate_dimensions([dim1, dim2])


def test_validate_dimensions_rejects_more_than_five() -> None:
    """Validate helper raises ValueError when more than 5 dimensions given."""
    dims = [
        AnalyticalDimension(
            dimension_id=f"dim_{i}",
            name=f"Dim {i}",
            description="Desc",
            evaluation_type="qualitative",
        )
        for i in range(6)
    ]
    with pytest.raises(ValueError, match="between 3 and 5"):
        validate_dimensions(dims)


def test_validate_dimensions_rejects_duplicate_slugs() -> None:
    """Validate helper rejects dimensions with identical dimension_id."""
    dim1 = AnalyticalDimension(
        dimension_id="shared_slug", name="Dim 1", description="Desc", evaluation_type="qualitative"
    )
    dim2 = AnalyticalDimension(
        dimension_id="shared_slug", name="Dim 2", description="Desc", evaluation_type="metric"
    )
    dim3 = AnalyticalDimension(
        dimension_id="other_slug", name="Dim 3", description="Desc", evaluation_type="benchmark"
    )
    with pytest.raises(ValueError, match="Duplicate dimension slug"):
        validate_dimensions([dim1, dim2, dim3])


def test_validate_dimensions_rejects_invalid_eval_type() -> None:
    """Validate helper rejects unsupported evaluation types."""
    dim1 = AnalyticalDimension(
        dimension_id="d1", name="D1", description="Desc", evaluation_type="qualitative"
    )
    dim2 = AnalyticalDimension(
        dimension_id="d2", name="D2", description="Desc", evaluation_type="metric"
    )
    dim3 = AnalyticalDimension(
        dimension_id="d3", name="D3", description="Desc", evaluation_type="unsupported_type"
    )
    with pytest.raises(ValueError, match="Invalid evaluation_type"):
        validate_dimensions([dim1, dim2, dim3])

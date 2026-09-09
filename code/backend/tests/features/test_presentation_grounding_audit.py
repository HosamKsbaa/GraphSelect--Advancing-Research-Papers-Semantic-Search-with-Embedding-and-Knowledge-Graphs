"""Unit and property tests for dialectical grounding audit (User Story 1 & 3).

Verifies Citation Hallucination Rate calculation (CHR), metric fidelity checks,
and Pydantic model validator enforcement of CHR == 0.0%.
"""
from __future__ import annotations

from typing import Any
import pytest

from features.export.fact_auditor import PresentationFactAuditor
from features.export.presentation_models import (
    PresentationSlide,
    PresenterNotes,
    PresenterQuestionAnswer,
    SlideGroundingCriticReport,
    SlideLayoutType,
)


@pytest.fixture
def fully_grounded_slides() -> list[PresentationSlide]:
    """Slide sequence with 100% grounded Neo4j DOIs."""
    return [
        PresentationSlide(
            slide_id="s1",
            index=1,
            title="Title Slide",
            category="Introduction",
            layout_type=SlideLayoutType.TITLE,
            content_html="<div>Introduction citing 10.1145/3292500.3330919</div>",
            presenter_notes=PresenterNotes(
                talking_points=["Point 1", "Point 2"],
                estimated_duration_seconds=60,
                anticipated_questions=[
                    PresenterQuestionAnswer(question="Q?", model_answer="A.")
                ],
            ),
            grounding_provenance=["10.1145/3292500.3330919"],
        ),
        PresentationSlide(
            slide_id="s2",
            index=2,
            title="SVPL Bridge Pathways",
            category="Synthesis",
            layout_type=SlideLayoutType.CITATION_NETWORK,
            content_html="<div>Pathways citing 10.1145/3394486.3403063 and 10.1109/tkde.2020.3012345</div>",
            presenter_notes=PresenterNotes(
                talking_points=["Bridge analysis", "Empirical confirmation"],
                estimated_duration_seconds=120,
            ),
            grounding_provenance=["10.1145/3394486.3403063", "10.1109/TKDE.2020.3012345"],
        ),
    ]


@pytest.fixture
def hallucinated_slides() -> list[PresentationSlide]:
    """Slide sequence containing a hallucinated/ungrounded DOI."""
    return [
        PresentationSlide(
            slide_id="s-hallucinated",
            index=1,
            title="Hallucinated Slide",
            category="Findings",
            layout_type=SlideLayoutType.FINDINGS_GRID,
            content_html="<div>Invented claim citing 10.9999/fake-paper-doi</div>",
            presenter_notes=PresenterNotes(
                talking_points=["Speculative point"],
                estimated_duration_seconds=60,
            ),
            grounding_provenance=["10.9999/fake-paper-doi"],
        )
    ]


@pytest.mark.asyncio
async def test_audit_fully_grounded_deck(
    mock_presentation_neo4j_service: Any,
    fully_grounded_slides: list[PresentationSlide],
) -> None:
    """Verify 100% grounded citations achieve CHR == 0.0% and pass audit."""
    auditor = PresentationFactAuditor(mock_presentation_neo4j_service)
    report = await auditor.audit_slides("test-campaign-001", fully_grounded_slides)

    assert report.is_grounded is True
    assert report.measured_chr == 0.0
    assert report.composite_score >= 0.95
    assert len(report.violations) == 0


@pytest.mark.asyncio
async def test_audit_hallucinated_deck_rejection(
    mock_presentation_neo4j_service: Any,
    hallucinated_slides: list[PresentationSlide],
) -> None:
    """Verify hallucinated DOI produces measured_chr > 0% and is_grounded = False."""
    auditor = PresentationFactAuditor(mock_presentation_neo4j_service)
    report = await auditor.audit_slides("test-campaign-001", hallucinated_slides)

    assert report.is_grounded is False
    assert report.measured_chr > 0.0
    assert any("10.9999/fake-paper-doi" in v for v in report.violations)
    assert len(report.actionable_directives) > 0


@pytest.mark.asyncio
async def test_audit_empty_citations_deck(
    mock_presentation_neo4j_service: Any,
) -> None:
    """Verify slide deck with zero citations evaluates to CHR == 0.0% without error."""
    slides = [
        PresentationSlide(
            slide_id="s-empty",
            index=1,
            title="Scoping Overview",
            category="Scoping",
            layout_type=SlideLayoutType.TITLE,
            content_html="<div>No explicit citations</div>",
            presenter_notes=PresenterNotes(
                talking_points=["Scoping explanation"],
                estimated_duration_seconds=45,
            ),
            grounding_provenance=[],
        )
    ]
    auditor = PresentationFactAuditor(mock_presentation_neo4j_service)
    report = await auditor.audit_slides("test-campaign-001", slides)

    assert report.is_grounded is True
    assert report.measured_chr == 0.0


def test_validator_rejects_inconsistent_grounding_flag() -> None:
    """Verify SlideGroundingCriticReport Pydantic validator rejects is_grounded=True when CHR > 0."""
    with pytest.raises(ValueError, match="Zero Hallucination Invariant Violated"):
        SlideGroundingCriticReport(
            is_grounded=True,
            measured_chr=10.0,
            composite_score=0.9,
            dimension_scores={"accuracy": 0.8},
            violations=["Ungrounded DOI"],
            actionable_directives=["Remove DOI"],
        )


def test_validator_rejects_is_grounded_with_violations() -> None:
    """Verify SlideGroundingCriticReport validator rejects is_grounded=True when violations exist."""
    with pytest.raises(ValueError, match="Grounding Invariant Violated"):
        SlideGroundingCriticReport(
            is_grounded=True,
            measured_chr=0.0,
            composite_score=0.9,
            dimension_scores={"accuracy": 0.8},
            violations=["Slide 1 is missing talking points"],
            actionable_directives=["Synthesize points"],
        )


@pytest.mark.asyncio
async def test_audit_missing_presenter_notes_fails(
    mock_presentation_neo4j_service: Any,
) -> None:
    """Verify slide deck missing presenter notes fails audit even with zero citations (T019 Case 4)."""
    slides = [
        PresentationSlide(
            slide_id="s-no-notes",
            index=1,
            title="Slide Without Notes",
            category="Overview",
            layout_type=SlideLayoutType.TITLE,
            content_html="<div>Content</div>",
            presenter_notes=PresenterNotes(
                talking_points=["   "],  # Whitespace-only notes
                estimated_duration_seconds=60,
            ),
            grounding_provenance=[],
        )
    ]
    auditor = PresentationFactAuditor(mock_presentation_neo4j_service)
    report = await auditor.audit_slides("test-campaign-001", slides)
    assert report.is_grounded is False
    assert any("missing speaker talking points" in v for v in report.violations)


@pytest.mark.asyncio
async def test_audit_paper_count_discrepancy(
    mock_presentation_neo4j_service: Any,
) -> None:
    """Verify slide claiming contradictory paper count fails audit (T019 Case 3)."""
    slides = [
        PresentationSlide(
            slide_id="s-metrics-drift",
            index=1,
            title="Drifted Metrics",
            category="Knowledge Base",
            layout_type=SlideLayoutType.SPLIT_METRICS,
            content_html='<div class="stat-number">999</div><div class="stat-label">Indexed Papers</div>',
            presenter_notes=PresenterNotes(
                talking_points=["Cover 999 ingested academic papers across literature."],
                estimated_duration_seconds=90,
            ),
            grounding_provenance=[],
        )
    ]
    auditor = PresentationFactAuditor(mock_presentation_neo4j_service)
    report = await auditor.audit_slides("test-campaign-001", slides)
    assert report.is_grounded is False
    assert any("Metric drift" in v for v in report.violations)


@pytest.mark.asyncio
async def test_audit_doi_normalization_and_url_prefixes(
    mock_presentation_neo4j_service: Any,
) -> None:
    """Verify DOIs with URL prefixes or punctuation match Neo4j without false rejection."""
    slides = [
        PresentationSlide(
            slide_id="s-doi-prefixes",
            index=1,
            title="Normalized DOI Slide",
            category="Evidence",
            layout_type=SlideLayoutType.MATRIX_TABLE,
            content_html="<div>Citing (10.1145/3292500.3330919). and https://doi.org/10.1145/3394486.3403063</div>",
            presenter_notes=PresenterNotes(
                talking_points=["Valid talking points"],
                estimated_duration_seconds=60,
            ),
            grounding_provenance=[
                "https://doi.org/10.1145/3292500.3330919",
                "(10.1145/3394486.3403063).",
            ],
        )
    ]
    auditor = PresentationFactAuditor(mock_presentation_neo4j_service)
    report = await auditor.audit_slides("test-campaign-001", slides)
    assert report.is_grounded is True
    assert report.measured_chr == 0.0
    assert len(report.violations) == 0

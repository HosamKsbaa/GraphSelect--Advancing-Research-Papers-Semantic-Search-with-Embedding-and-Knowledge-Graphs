"""Unit tests for presentation template compilation and standalone asset inlining (User Story 2 & 4).

Validates Jinja2 template rendering, CSS/JS inlining, auto-escaping, and SHA-256 fingerprinting.
"""
from __future__ import annotations

import hashlib
from typing import Any
import pytest

from features.export.presentation_models import (
    PresentationAudienceProfile,
    PresentationDeckRequest,
    PresentationSlide,
    PresentationTheme,
    PresenterNotes,
    PresenterQuestionAnswer,
    ProjectEpistemicFacts,
    SlideLayoutType,
)
from features.export.template_engine import PresentationTemplateEngine


@pytest.fixture
def sample_slides() -> list[PresentationSlide]:
    """Provide minimal sample slides for template testing."""
    return [
        PresentationSlide(
            slide_id="slide-001",
            index=1,
            title="Graph-Centric Dual-Loop Architecture",
            category="Overview",
            layout_type=SlideLayoutType.TITLE,
            content_html="<div class='hero'>Hero Slide Content</div>",
            presenter_notes=PresenterNotes(
                talking_points=["Introduce thesis research scope.", "Highlight Neo4j SSOT."],
                estimated_duration_seconds=90,
                anticipated_questions=[
                    PresenterQuestionAnswer(
                        question="Why pure Neo4j?",
                        model_answer="Graph-native adjacency prevents relational joins.",
                    )
                ],
            ),
            grounding_provenance=["10.1145/3292500.3330919"],
        ),
        PresentationSlide(
            slide_id="slide-002",
            index=2,
            title="Scientometric Foundation",
            category="Methodology",
            layout_type=SlideLayoutType.SPLIT_METRICS,
            content_html="<div class='metrics'>Metric stat cards</div>",
            presenter_notes=PresenterNotes(
                talking_points=["Explain 42 ingested papers.", "Highlight 1,845 citations."],
                estimated_duration_seconds=120,
            ),
            grounding_provenance=[],
        ),
    ]


def test_inline_assets() -> None:
    """Verify CSS, JS, and minified Mermaid assets are inlined from local storage."""
    engine = PresentationTemplateEngine()
    assets_with_mermaid = engine.inline_assets(enable_mermaid=True)
    assert len(assets_with_mermaid["inlined_css"]) > 1000
    assert len(assets_with_mermaid["inlined_js"]) > 1000
    assert len(assets_with_mermaid["inlined_mermaid"]) > 100000

    assets_without_mermaid = engine.inline_assets(enable_mermaid=False)
    assert assets_without_mermaid["inlined_mermaid"] == ""


def test_master_deck_rendering(
    sample_slides: list[PresentationSlide],
    mock_presentation_project_facts: dict[str, Any],
) -> None:
    """Verify master Jinja2 HTML layout renders complete standalone deck."""
    engine = PresentationTemplateEngine()
    facts = ProjectEpistemicFacts.model_validate(mock_presentation_project_facts)
    req = PresentationDeckRequest(
        project_id="test-campaign-001",
        audience_profile=PresentationAudienceProfile.SUPERVISOR,
        target_slide_count=12,
        theme=PresentationTheme.DARK,
        enable_mermaid=True,
    )
    html = engine.render_deck(req, sample_slides, facts)

    assert "<!DOCTYPE html>" in html
    assert "Graph-Centric Dual-Loop Architecture" in html
    assert "id=\"deck-viewport\"" in html
    assert "id=\"notes-drawer\"" in html
    assert "id=\"overview-modal\"" in html
    assert "id=\"progress-fill\"" in html
    assert "Slide 1: Graph-Centric Dual-Loop Architecture" in html
    assert "Slide 2: Scientometric Foundation" in html
    assert "Why pure Neo4j?" in html


def test_sha256_fingerprint() -> None:
    """Verify SHA-256 fingerprinting calculation produces valid 64-char hex hash."""
    engine = PresentationTemplateEngine()
    test_str = "<html><body>Test Presentation</body></html>"
    expected = hashlib.sha256(test_str.encode("utf-8")).hexdigest()
    calculated = engine.calculate_sha256(test_str)
    assert len(calculated) == 64
    assert calculated == expected


def test_autoescape_behavior(
    sample_slides: list[PresentationSlide],
    mock_presentation_project_facts: dict[str, Any],
) -> None:
    """Verify Jinja2 template auto-escapes unsafe user inputs in non-safe fields."""
    engine = PresentationTemplateEngine()
    facts_data = dict(mock_presentation_project_facts)
    facts_data["project_name"] = "<script>alert('xss')</script>"
    facts = ProjectEpistemicFacts.model_validate(facts_data)

    req = PresentationDeckRequest(project_id="test-campaign-001")
    html = engine.render_deck(req, sample_slides, facts)

    # project_name in <title> and header must be HTML-escaped
    assert "<script>alert('xss')</script>" not in html
    assert "&lt;script&gt;alert(&#39;xss&#39;)&lt;/script&gt;" in html


def test_macros_group1(mock_presentation_project_facts: dict[str, Any]) -> None:
    """Verify title, metrics, and funnel macros render valid HTML."""
    from features.export.deck_generator import PresentationDeckGenerator

    facts = ProjectEpistemicFacts.model_validate(mock_presentation_project_facts)
    gen = PresentationDeckGenerator()
    req = PresentationDeckRequest(project_id="test-campaign-001")

    title_html, _ = gen._render_slide_content(SlideLayoutType.TITLE, facts, req)
    assert "hero-heading" in title_html
    assert "Graph-Centric Dual-Loop Architecture" in title_html

    metrics_html, _ = gen._render_slide_content(SlideLayoutType.SPLIT_METRICS, facts, req)
    assert "Publication Timeline" in metrics_html
    assert "42" in metrics_html

    funnel_html, _ = gen._render_slide_content(SlideLayoutType.FUNNEL_DIAGRAM, facts, req)
    assert "Epistemic Funnel" in funnel_html or "Scoping" in funnel_html


def test_macros_group2(mock_presentation_project_facts: dict[str, Any]) -> None:
    """Verify swarm, synthesis matrix, and citation network macros render valid HTML."""
    from features.export.deck_generator import PresentationDeckGenerator

    facts = ProjectEpistemicFacts.model_validate(mock_presentation_project_facts)
    gen = PresentationDeckGenerator()
    req = PresentationDeckRequest(project_id="test-campaign-001")

    swarm_html, _ = gen._render_slide_content(SlideLayoutType.ARCHITECTURE_SWARM, facts, req)
    assert "Fast Loop" in swarm_html
    assert "Slow Loop" in swarm_html

    matrix_html, _ = gen._render_slide_content(SlideLayoutType.MATRIX_TABLE, facts, req)
    assert "matrix-table" in matrix_html
    assert "Taxonomy of Epistemic Graph Architectures" in matrix_html

    citation_html, _ = gen._render_slide_content(SlideLayoutType.CITATION_NETWORK, facts, req)
    assert "mermaid" in citation_html or "SVPL" in citation_html


def test_macros_group3(mock_presentation_project_facts: dict[str, Any]) -> None:
    """Verify gap radar and discussion QA macros render valid HTML."""
    from features.export.deck_generator import PresentationDeckGenerator

    facts = ProjectEpistemicFacts.model_validate(mock_presentation_project_facts)
    gen = PresentationDeckGenerator()
    req = PresentationDeckRequest(project_id="test-campaign-001")

    gap_html, _ = gen._render_slide_content(SlideLayoutType.GAP_RADAR, facts, req)
    assert "Semantic Coverage" in gap_html
    assert "rq-001" in gap_html

    qa_html, _ = gen._render_slide_content(SlideLayoutType.QA_DISCUSSION, facts, req)
    assert "Grounded Model Rebuttal" in qa_html


def test_slide_sequence_structuring(mock_presentation_project_facts: dict[str, Any]) -> None:
    """Verify slide sequence engine structures appropriate slide counts per audience."""
    from features.export.deck_generator import PresentationDeckGenerator

    facts = ProjectEpistemicFacts.model_validate(mock_presentation_project_facts)
    gen = PresentationDeckGenerator()

    # Supervisor: 12 slides
    req_sup = PresentationDeckRequest(
        project_id="test-campaign-001",
        audience_profile=PresentationAudienceProfile.SUPERVISOR,
        target_slide_count=12,
    )
    slides_sup = gen.build_slide_sequence(facts, req_sup)
    assert len(slides_sup) == 12
    assert slides_sup[0].layout_type == SlideLayoutType.TITLE
    assert slides_sup[0].index == 1
    assert slides_sup[11].index == 12

    # Quick status: 8 slides
    req_quick = PresentationDeckRequest(
        project_id="test-campaign-001",
        audience_profile=PresentationAudienceProfile.QUICK_STATUS,
        target_slide_count=8,
    )
    slides_quick = gen.build_slide_sequence(facts, req_quick)
    assert len(slides_quick) == 8


def test_all_audience_profiles_reach_maximum_20_slides(
    mock_presentation_project_facts: dict[str, Any],
) -> None:
    """Verify target_slide_count=20 generates exactly 20 slides across all 4 audience profiles."""
    from features.export.deck_generator import PresentationDeckGenerator

    facts = ProjectEpistemicFacts.model_validate(mock_presentation_project_facts)
    gen = PresentationDeckGenerator()

    for profile in [
        PresentationAudienceProfile.SUPERVISOR,
        PresentationAudienceProfile.THESIS_DEFENSE,
        PresentationAudienceProfile.SEMINAR,
        PresentationAudienceProfile.QUICK_STATUS,
    ]:
        req = PresentationDeckRequest(
            project_id="test-campaign-001",
            audience_profile=profile,
            target_slide_count=20,
        )
        slides = gen.build_slide_sequence(facts, req)
        assert len(slides) == 20, f"Profile {profile} failed to generate 20 slides (got {len(slides)})"
        assert [s.index for s in slides] == list(range(1, 21))
        assert all(len(s.presenter_notes.talking_points) >= 1 for s in slides)


def test_speaker_note_synthesis(mock_presentation_project_facts: dict[str, Any]) -> None:
    """Verify speaker note synthesis generates bullet points, durations, and Q&A."""
    from features.export.deck_generator import PresentationDeckGenerator

    facts = ProjectEpistemicFacts.model_validate(mock_presentation_project_facts)
    gen = PresentationDeckGenerator()

    notes = gen.synthesize_presenter_notes(
        SlideLayoutType.CITATION_NETWORK, facts, PresentationAudienceProfile.SUPERVISOR
    )
    assert len(notes.talking_points) >= 3
    assert 30 <= notes.estimated_duration_seconds <= 300
    assert len(notes.anticipated_questions) >= 1
    assert len(notes.anticipated_questions[0].question) > 5
    assert len(notes.anticipated_questions[0].model_answer) > 10


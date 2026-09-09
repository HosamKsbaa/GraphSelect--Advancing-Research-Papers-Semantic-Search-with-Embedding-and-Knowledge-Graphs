"""Contract and execution tests for Google ADK Presentation Tools (User Story 5).

Verifies generate_presentation_deck_tool and audit_slide_grounding_tool
conforming to ADR-001 and Constitution A28, A33, A36, C7.
"""
from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock
import pytest

from agents.tools.presentation_tools import (
    audit_slide_grounding_tool,
    generate_presentation_deck_tool,
)
from features.export.presentation_models import (
    AuditSlideGroundingRequest,
    PresentationAudienceProfile,
    PresentationDeckRequest,
    PresentationDeckResponse,
    PresentationErrorCode,
    PresentationSlide,
    PresentationTheme,
    PresenterNotes,
    SlideGroundingCriticReport,
    SlideLayoutType,
)
from features.export.presentation_service import PresentationService


@pytest.fixture
def mock_tool_context(mock_presentation_neo4j_service: Any, tmp_path: Any) -> MagicMock:
    """Construct mock ToolContext with bound PresentationService."""
    ctx = MagicMock()
    service = PresentationService(
        neo4j=mock_presentation_neo4j_service,
        projects_dir=tmp_path / "campaigns",
    )
    registry = MagicMock()
    registry.presentation_service = service
    registry.neo4j = mock_presentation_neo4j_service
    ctx.service_registry = registry
    return ctx


@pytest.mark.asyncio
async def test_generate_tool_success(mock_tool_context: MagicMock) -> None:
    """Verify generate_presentation_deck_tool produces a valid PresentationDeckResponse."""
    req = PresentationDeckRequest(
        project_id="test-campaign-001",
        audience_profile=PresentationAudienceProfile.SUPERVISOR,
        target_slide_count=10,
        theme=PresentationTheme.DARK,
        enable_mermaid=True,
    )
    resp: PresentationDeckResponse = await generate_presentation_deck_tool(req, mock_tool_context)

    assert resp.success is True
    assert resp.slide_count == 10
    assert resp.file_path.endswith(".html")
    assert len(resp.sha256_hash) == 64
    assert resp.error is None


@pytest.mark.asyncio
async def test_generate_tool_invalid_slide_range(mock_tool_context: MagicMock) -> None:
    """Verify tool catches invalid slide count outside [8, 20] and returns structured error."""
    # Bypass Pydantic validator to test service/tool defensive boundary
    req = PresentationDeckRequest.model_construct(
        project_id="test-campaign-001",
        target_slide_count=4,
        audience_profile=PresentationAudienceProfile.SUPERVISOR,
        theme=PresentationTheme.DARK,
        enable_mermaid=True,
        included_topics=None,
    )
    resp: PresentationDeckResponse = await generate_presentation_deck_tool(req, mock_tool_context)

    assert resp.success is False
    assert resp.error is not None
    assert resp.error.code == PresentationErrorCode.INVALID_SLIDE_RANGE


@pytest.mark.asyncio
async def test_generate_tool_project_not_found(mock_tool_context: MagicMock) -> None:
    """Verify tool handles non-existent project and returns PROJECT_NOT_FOUND."""
    req = PresentationDeckRequest(
        project_id="non-existent-campaign",
        target_slide_count=10,
    )
    resp: PresentationDeckResponse = await generate_presentation_deck_tool(req, mock_tool_context)

    assert resp.success is False
    assert resp.error is not None
    assert resp.error.code == PresentationErrorCode.PROJECT_NOT_FOUND


@pytest.mark.asyncio
async def test_audit_tool_execution(mock_tool_context: MagicMock) -> None:
    """Verify audit_slide_grounding_tool evaluates candidate slides accurately."""
    slides = [
        PresentationSlide(
            slide_id="s1",
            index=1,
            title="Grounding Check",
            category="Synthesis",
            layout_type=SlideLayoutType.TITLE,
            content_html="<div>Citing 10.1145/3292500.3330919</div>",
            presenter_notes=PresenterNotes(
                talking_points=["Point 1"],
                estimated_duration_seconds=60,
            ),
            grounding_provenance=["10.1145/3292500.3330919"],
        )
    ]
    req = AuditSlideGroundingRequest(project_id="test-campaign-001", slides=slides)
    report: SlideGroundingCriticReport = await audit_slide_grounding_tool(req, mock_tool_context)

    assert report.is_grounded is True
    assert report.measured_chr == 0.0
    assert report.composite_score >= 0.9


@pytest.mark.asyncio
async def test_audit_tool_uninitialized_neo4j() -> None:
    """Verify audit_slide_grounding_tool returns deterministic rejection report if Neo4j is absent."""
    from unittest.mock import patch
    from agents._service_registry import ServiceRegistry

    slides = [
        PresentationSlide(
            slide_id="s-uninit",
            index=1,
            title="Grounding Check",
            category="Synthesis",
            layout_type=SlideLayoutType.TITLE,
            content_html="<div>Citing 10.1145/3292500.3330919</div>",
            presenter_notes=PresenterNotes(
                talking_points=["Point 1"],
                estimated_duration_seconds=60,
            ),
            grounding_provenance=["10.1145/3292500.3330919"],
        )
    ]
    req = AuditSlideGroundingRequest(project_id="test-campaign-001", slides=slides)
    with patch.object(ServiceRegistry, "neo4j", None):
        report = await audit_slide_grounding_tool(req, tool_context=None)
    assert report.is_grounded is False
    assert report.measured_chr == 100.0
    assert any("Neo4j SSOT service unavailable" in v for v in report.violations)

"""Unit and integration tests for Epistemic Fact Extraction Service (User Story 1 🎯 MVP).

Validates parameterized Cypher query orchestration, Pydantic v2 mapping,
and graceful empty-library fallback packaging without NaN or division by zero.
"""
from __future__ import annotations

from typing import Any
import pytest

from features.export.fact_extractor import PresentationFactExtractor
from features.export.presentation_models import (
    PresentationErrorCode,
    ProjectEpistemicFacts,
    ResearchQuestionFact,
    ScientometricFacts,
    SvplPathwayFact,
    SynthesisMatrixFact,
)


@pytest.mark.asyncio
async def test_extract_metadata_and_rqs(mock_presentation_neo4j_service: Any) -> None:
    """Verify Query 1 extracts project metadata and maps research questions correctly."""
    extractor = PresentationFactExtractor(mock_presentation_neo4j_service)
    meta, rqs = await extractor.extract_project_metadata_and_rqs("test-campaign-001")

    assert meta["project_id"] == "test-campaign-001"
    assert meta["project_name"] == "Graph-Centric Dual-Loop Architecture"
    assert len(rqs) == 2
    assert isinstance(rqs[0], ResearchQuestionFact)
    assert rqs[0].rq_id == "rq-001"
    assert rqs[0].coverage_score == 0.88
    assert rqs[0].status == "grounded"
    assert rqs[1].status == "open_frontier"


@pytest.mark.asyncio
async def test_extract_scientometrics(mock_presentation_neo4j_service: Any) -> None:
    """Verify Query 2 aggregates paper counts, citations, authors, and histograms."""
    extractor = PresentationFactExtractor(mock_presentation_neo4j_service)
    sciento = await extractor.extract_scientometrics("test-campaign-001")

    assert isinstance(sciento, ScientometricFacts)
    assert sciento.total_papers == 42
    assert sciento.total_citations == 1845
    assert sciento.unique_authors == 112
    assert sciento.year_distribution[2023] == 15
    assert len(sciento.top_venues) == 2
    assert sciento.top_venues[0]["venue"] == "NeurIPS"
    assert len(sciento.top_authors) == 1
    assert sciento.top_authors[0]["author"] == "Vaswani, A."


@pytest.mark.asyncio
async def test_extract_landmark_papers(mock_presentation_neo4j_service: Any) -> None:
    """Verify Query 3 extracts top landmark papers ranked by centrality."""
    extractor = PresentationFactExtractor(mock_presentation_neo4j_service)
    landmarks = await extractor.extract_landmark_papers("test-campaign-001", limit=6)

    assert len(landmarks) == 1
    paper = landmarks[0]
    assert paper["doi"] == "10.1145/3292500.3330919"
    assert paper["year"] == 2019
    assert paper["external_citations"] == 5000
    assert paper["in_graph_citations"] == 14


@pytest.mark.asyncio
async def test_extract_matrices_and_pathways(mock_presentation_neo4j_service: Any) -> None:
    """Verify Query 4 & 5 extract synthesis matrices and SVPL multi-hop pathways."""
    extractor = PresentationFactExtractor(mock_presentation_neo4j_service)
    matrices = await extractor.extract_synthesis_matrices("test-campaign-001")
    pathways = await extractor.extract_svpl_pathways("test-campaign-001")

    assert len(matrices) == 1
    assert isinstance(matrices[0], SynthesisMatrixFact)
    assert matrices[0].section_id == "sec-01"
    assert "0.0% CHR" in matrices[0].matrix_markdown
    assert matrices[0].paper_count == 8

    assert len(pathways) == 1
    assert isinstance(pathways[0], SvplPathwayFact)
    assert pathways[0].from_doi == "10.1145/3292500.3330919"
    assert pathways[0].to_doi == "10.1145/3394486.3403063"
    assert pathways[0].hop_count == 2
    assert pathways[0].bridge_mechanism == "steiner"


@pytest.mark.asyncio
async def test_empty_library_fallback(mock_presentation_neo4j_service: Any) -> None:
    """Verify zero-paper campaign triggers graceful empty library scoping fallback."""
    extractor = PresentationFactExtractor(mock_presentation_neo4j_service)
    facts = await extractor.extract_all_project_facts("empty-campaign-002")

    assert isinstance(facts, ProjectEpistemicFacts)
    assert facts.project_id == "empty-campaign-002"
    assert facts.empty_library_warning is True
    assert facts.scientometrics.total_papers == 0
    assert facts.scientometrics.total_citations == 0
    assert len(facts.research_questions) == 1
    assert len(facts.synthesis_matrices) == 0
    assert len(facts.svpl_pathways) == 0


@pytest.mark.asyncio
async def test_project_not_found(mock_presentation_neo4j_service: Any) -> None:
    """Verify unknown project raises ValueError with PROJECT_NOT_FOUND classification."""
    extractor = PresentationFactExtractor(mock_presentation_neo4j_service)
    with pytest.raises(ValueError, match="PROJECT_NOT_FOUND"):
        await extractor.extract_all_project_facts("non-existent-campaign")

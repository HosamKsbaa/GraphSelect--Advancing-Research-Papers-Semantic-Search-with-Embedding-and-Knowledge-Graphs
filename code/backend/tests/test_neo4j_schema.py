"""Tests for Neo4j schema DDL, constraints, and vector indexes (T019).

Validates that initialize_schema applies 12 uniqueness constraints,
composite indexes, and 3 Matryoshka vector indexes per data-model.md §1.3.
"""
from __future__ import annotations

from unittest.mock import AsyncMock
import pytest

from core.db.neo4j_schema import (
    COMPOSITE_INDEXES,
    UNIQUENESS_CONSTRAINTS,
    VECTOR_INDEXES,
    initialize_schema,
)
from core.db.neo4j_service import Neo4jService


def test_schema_definitions_completeness() -> None:
    """Verify all 12 required node label constraints are defined."""
    required_labels = [
        ":ResearchCampaign",
        ":ResearchQuestion",
        ":Paper",
        ":Author",
        ":Venue",
        ":Claim",
        ":StageSubstate",
        ":PublicBoardMessage",
        ":CritiqueVector",
        ":Method",
        ":Dataset",
        ":MetricResult",
    ]
    constraints_text = " ".join(UNIQUENESS_CONSTRAINTS)
    for label in required_labels:
        assert label in constraints_text, f"Missing constraint for required label {label}"

    assert len(VECTOR_INDEXES) == 3
    index_names = {idx[0] for idx in VECTOR_INDEXES}
    assert index_names == {"paper_embeddings", "question_embeddings", "claim_embeddings"}
    assert len(COMPOSITE_INDEXES) >= 6


@pytest.mark.asyncio
async def test_initialize_schema_execution() -> None:
    """Verify initialize_schema executes all constraints, indexes, and vector indexes."""
    mock_service = AsyncMock(spec=Neo4jService)
    mock_service.execute_write = AsyncMock(return_value=[])

    await initialize_schema(mock_service, embedding_dimensions=768)

    # Expected calls count: len(UNIQUENESS_CONSTRAINTS) + len(COMPOSITE_INDEXES) + len(VECTOR_INDEXES)
    expected_calls = len(UNIQUENESS_CONSTRAINTS) + len(COMPOSITE_INDEXES) + len(VECTOR_INDEXES)
    assert mock_service.execute_write.call_count == expected_calls

    queries = [call.args[0] for call in mock_service.execute_write.call_args_list]
    joined = " ".join(queries)
    assert "paper_embeddings" in joined
    assert "question_embeddings" in joined
    assert "claim_embeddings" in joined
    assert "768" in joined
    assert "cosine" in joined


def test_presentation_schema() -> None:
    """Verify Feature 008 presentation constraints and indexes exist in DDL definitions."""
    constraints_text = " ".join(UNIQUENESS_CONSTRAINTS)
    assert ":PresentationDeck" in constraints_text
    assert "d.deck_id IS UNIQUE" in constraints_text
    assert ":PresentationSlide" in constraints_text
    assert "s.slide_id IS UNIQUE" in constraints_text

    indexes_text = " ".join(COMPOSITE_INDEXES)
    assert "presentation_deck_project_idx" in indexes_text
    assert "presentation_slide_deck_idx" in indexes_text


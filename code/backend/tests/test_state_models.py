"""Comprehensive unit tests for authoritative Pydantic v2 workflow state models.

Verifies:
- Complete Pydantic v2 validation and serialization (model_dump, model_dump_json, model_validate).
- All 5 stages follow the 4-quadrant topology (meta, inputs, artifacts, notes).
- Board message creation, typed classification enforcement, canonical DOI normalization, and acknowledgment tracking.
- Dot-path extraction across nested stages and quadrants.
"""
from __future__ import annotations

import json
import pytest
from pydantic import ValidationError

from features.workflow.state_models import (
    AnalysisArtifacts,
    AnalysisInputs,
    AnalysisSubstate,
    BoardClassification,
    BoardMessage,
    ComparisonDimension,
    ExportArtifacts,
    ExportInputs,
    ExportSubstate,
    OutlineStructure,
    PaperCluster,
    PaperFinding,
    PaperMetadata,
    PaperRanking,
    PlanningArtifacts,
    PlanningInputs,
    PlanningSubstate,
    ProjectState,
    ResearchArtifacts,
    ResearchGap,
    ResearchInputs,
    ResearchSubstate,
    SectionBlueprint,
    SectionDraft,
    SectionReview,
    Stage1ResearchState,
    Stage2AnalysisState,
    Stage3PlanningState,
    Stage4WritingState,
    Stage5ExportState,
    StageMeta,
    StageNote,
    StructuredComparisonMatrix,
    WritingArtifacts,
    WritingInputs,
    WritingSubstate,
    normalize_doi,
    normalize_stage_name,
    utc_now,
)


# ---------------------------------------------------------------------------
# Test 1: Canonical DOI Normalization
# ---------------------------------------------------------------------------

class TestDoiNormalization:
    """Test DOI cleaning and normalization across various academic resolver formats."""

    def test_normalize_doi_https_resolver(self) -> None:
        raw = "https://doi.org/10.1145/3292500.3330964"
        assert normalize_doi(raw) == "10.1145/3292500.3330964"

    def test_normalize_doi_dx_http_resolver(self) -> None:
        raw = "http://dx.doi.org/10.1016/j.artint.2020.103342"
        assert normalize_doi(raw) == "10.1016/j.artint.2020.103342"

    def test_normalize_doi_prefix_doi_colon(self) -> None:
        raw = "doi: 10.1109/TKDE.2021.3060000"
        assert normalize_doi(raw) == "10.1109/tkde.2021.3060000"

    def test_normalize_doi_whitespace_and_casing(self) -> None:
        raw = "  HTTPS://DOI.ORG/10.1000/182_ABC  "
        assert normalize_doi(raw) == "10.1000/182_abc"

    def test_normalize_doi_empty_and_none(self) -> None:
        assert normalize_doi("") == ""
        assert normalize_doi(None) == ""


# ---------------------------------------------------------------------------
# Test 2: BoardMessage & Public Message Board (R3)
# ---------------------------------------------------------------------------

class TestBoardMessage:
    """Test BoardMessage model, typed classifications, DOI normalization, and acknowledgments."""

    @pytest.mark.parametrize(
        "msg_type",
        ["insight", "serendipity", "gap", "warning", "decision", "hypothesis"],
    )
    def test_valid_message_types(self, msg_type: BoardClassification) -> None:
        msg = BoardMessage(
            author_agent="ALRSAgent",
            message_type=msg_type,
            title=f"Sample {msg_type} headline",
            content="Detailed markdown discovery.",
            stage="stage_1_research",
            tags=["graph", "benchmark"],
            related_paper_dois=["https://doi.org/10.1145/12345"],
        )
        assert msg.message_type == msg_type
        assert msg.classification == msg_type
        assert msg.related_paper_dois == ["10.1145/12345"]
        assert msg.relevant_dois == ["10.1145/12345"]
        assert len(msg.acknowledged_by) == 0

    def test_invalid_message_type_rejected(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            BoardMessage(
                author_agent="UnknownAgent",
                message_type="invalid_type",  # type: ignore[arg-type]
                title="Invalid Message",
                content="This should fail.",
            )
        assert "message_type" in str(exc_info.value)

    def test_doi_normalization_in_board_message(self) -> None:
        msg = BoardMessage(
            author_agent="GapFinderAgent",
            message_type="gap",
            title="Coverage Gap",
            content="Missing inductive evaluation.",
            related_paper_dois=[
                "https://doi.org/10.1145/111",
                "http://dx.doi.org/10.1016/222",
                "doi: 10.1109/333",
                "10.1000/444",
            ],
        )
        assert msg.related_paper_dois == [
            "10.1145/111",
            "10.1016/222",
            "10.1109/333",
            "10.1000/444",
        ]

    def test_alias_support_for_classification_and_relevant_dois(self) -> None:
        # Legacy/survey compatibility: passing classification and relevant_dois
        msg = BoardMessage(
            author_agent="PlannerAgent",
            classification="decision",  # type: ignore[call-arg]
            title="Structural Decision",
            content="Adopting 4-theme outline structure.",
            relevant_dois=["https://doi.org/10.1145/999"],  # type: ignore[call-arg]
        )
        assert msg.message_type == "decision"
        assert msg.related_paper_dois == ["10.1145/999"]

    def test_acknowledgment_workflow(self) -> None:
        msg = BoardMessage(
            author_agent="ResearchAgent",
            message_type="warning",
            title="Contradiction in Benchmark",
            content="Conflicting claims between Cora and Citeseer results.",
        )
        assert not msg.is_acknowledged_by("PlannerAgent")
        assert not msg.is_acknowledged_by("WriterAgent")

        msg.acknowledge("PlannerAgent")
        assert msg.is_acknowledged_by("PlannerAgent")
        assert not msg.is_acknowledged_by("WriterAgent")
        assert msg.acknowledged_by == ["PlannerAgent"]

        # Duplicate acknowledgment should be idempotent
        msg.acknowledge("PlannerAgent")
        assert msg.acknowledged_by == ["PlannerAgent"]

        msg.acknowledge("WriterAgent")
        assert msg.acknowledged_by == ["PlannerAgent", "WriterAgent"]


# ---------------------------------------------------------------------------
# Test 3: 4-Quadrant Substate Topology (R2)
# ---------------------------------------------------------------------------

class TestFourQuadrantTopology:
    """Verify all 5 stages conform to the identical 4-quadrant layout: meta, inputs, artifacts, notes."""

    def test_stage_1_research_topology(self) -> None:
        stage = Stage1ResearchState()
        assert hasattr(stage, "meta")
        assert hasattr(stage, "inputs")
        assert hasattr(stage, "artifacts")
        assert hasattr(stage, "notes")

        assert isinstance(stage.meta, StageMeta)
        assert isinstance(stage.inputs, ResearchInputs)
        assert isinstance(stage.artifacts, ResearchArtifacts)
        assert isinstance(stage.notes, list)

        # Artifacts specifics for stage 1
        assert hasattr(stage.artifacts, "papers")
        assert hasattr(stage.artifacts, "search_queries")
        assert hasattr(stage.artifacts, "crawl_queue")
        assert hasattr(stage.artifacts, "citation_edges")
        assert hasattr(stage.artifacts, "bfs_graph_edges")

    def test_stage_2_analysis_topology(self) -> None:
        stage = Stage2AnalysisState()
        assert hasattr(stage, "meta")
        assert hasattr(stage, "inputs")
        assert hasattr(stage, "artifacts")
        assert hasattr(stage, "notes")

        assert isinstance(stage.meta, StageMeta)
        assert isinstance(stage.inputs, AnalysisInputs)
        assert isinstance(stage.artifacts, AnalysisArtifacts)

        # Artifacts specifics for stage 2
        assert hasattr(stage.artifacts, "rankings")
        assert hasattr(stage.artifacts, "clusters")
        assert hasattr(stage.artifacts, "gaps")
        assert hasattr(stage.artifacts, "research_gaps")
        assert hasattr(stage.artifacts, "embeddings_metadata")
        assert hasattr(stage.artifacts, "similarity_matrix")

    def test_stage_3_planning_topology(self) -> None:
        stage = Stage3PlanningState()
        assert hasattr(stage, "meta")
        assert hasattr(stage, "inputs")
        assert hasattr(stage, "artifacts")
        assert hasattr(stage, "notes")

        assert isinstance(stage.meta, StageMeta)
        assert isinstance(stage.inputs, PlanningInputs)
        assert isinstance(stage.artifacts, PlanningArtifacts)

        # Artifacts specifics for stage 3
        assert hasattr(stage.artifacts, "outline")
        assert hasattr(stage.artifacts, "section_blueprints")
        assert hasattr(stage.artifacts, "doi_mappings")
        assert hasattr(stage.artifacts, "doi_to_section_map")

    def test_stage_4_writing_topology(self) -> None:
        stage = Stage4WritingState()
        assert hasattr(stage, "meta")
        assert hasattr(stage, "inputs")
        assert hasattr(stage, "artifacts")
        assert hasattr(stage, "notes")

        assert isinstance(stage.meta, StageMeta)
        assert isinstance(stage.inputs, WritingInputs)
        assert isinstance(stage.artifacts, WritingArtifacts)

        # Artifacts specifics for stage 4
        assert hasattr(stage.artifacts, "section_drafts")
        assert hasattr(stage.artifacts, "draft_sections_markdown")
        assert hasattr(stage.artifacts, "section_reviews")
        assert hasattr(stage.artifacts, "peer_review_feedback")
        assert hasattr(stage.artifacts, "citation_groundings")

    def test_stage_5_export_topology(self) -> None:
        stage = Stage5ExportState()
        assert hasattr(stage, "meta")
        assert hasattr(stage, "inputs")
        assert hasattr(stage, "artifacts")
        assert hasattr(stage, "notes")

        assert isinstance(stage.meta, StageMeta)
        assert isinstance(stage.inputs, ExportInputs)
        assert isinstance(stage.artifacts, ExportArtifacts)

        # Artifacts specifics for stage 5
        assert hasattr(stage.artifacts, "latex_templates")
        assert hasattr(stage.artifacts, "bibtex_entries")
        assert hasattr(stage.artifacts, "compiled_document_metadata")
        assert hasattr(stage.artifacts, "tex_path")
        assert hasattr(stage.artifacts, "bib_path")

    def test_substate_aliases(self) -> None:
        assert ResearchSubstate is Stage1ResearchState
        assert AnalysisSubstate is Stage2AnalysisState
        assert PlanningSubstate is Stage3PlanningState
        assert WritingSubstate is Stage4WritingState
        assert ExportSubstate is Stage5ExportState


# ---------------------------------------------------------------------------
# Test 4: Unified ProjectState Model & Helper Methods (R2 & R3)
# ---------------------------------------------------------------------------

class TestProjectStateModel:
    """Test root ProjectState creation, attributes, helper methods, and serialization."""

    def test_project_state_initialization(self) -> None:
        project = ProjectState(
            name="Graph Neural Networks Literature Review",
            topic="Computer Science / Graph Representation Learning",
            target_level="phd",
            token_budget=750000,
        )
        assert project.name == "Graph Neural Networks Literature Review"
        assert project.target_level == "phd"
        assert project.token_budget == 750000
        assert project.tokens_used == 0
        assert project.status == "active"
        assert project.current_stage == "stage_1_research"
        assert project.project_id is not None
        assert project.id == project.project_id
        assert len(project.message_board) == 0

    def test_public_message_board_posting_and_acknowledgment(self) -> None:
        project = ProjectState(name="Test Project")
        initial_updated_at = project.updated_at

        # 1. Post message via post_message
        msg = project.post_message(
            author_agent="ALRSAgent",
            message_type="insight",
            title="Transformer Scaling on Sparse Graphs",
            content="Discovered sparse attention scales linearly.",
            stage="stage_1_research",
            tags=["sparse", "scaling"],
            related_paper_dois=["https://doi.org/10.1145/99999"],
        )
        assert len(project.message_board) == 1
        assert msg.related_paper_dois == ["10.1145/99999"]
        assert project.updated_at >= initial_updated_at

        # 2. Acknowledge message
        success = project.acknowledge_message(msg.id, "PlannerAgent")
        assert success is True
        assert "PlannerAgent" in msg.acknowledged_by

        # 3. Acknowledge unknown message returns False
        unknown_success = project.acknowledge_message("non-existent-uuid", "PlannerAgent")
        assert unknown_success is False

    def test_add_message_alias(self) -> None:
        project = ProjectState(name="Alias Test")
        msg = project.add_message(
            author_agent="WriterAgent",
            message_type="hypothesis",
            title="Hypothesis on Synthesis",
            content="Testing narrative flow.",
        )
        assert len(project.message_board) == 1
        assert msg.title == "Hypothesis on Synthesis"

    def test_update_stage_quadrant(self) -> None:
        project = ProjectState(name="Stage Update Test")

        # 1. Update meta in stage 1
        project.update_stage_quadrant(
            stage="stage_1_research",
            quadrant="meta",
            data={"status": "in_progress", "progress_percentage": 45.0},
        )
        assert project.stage_1_research.meta.status == "in_progress"
        assert project.stage_1_research.meta.progress_percentage == 45.0

        # 2. Update inputs using friendly stage name 'analysis'
        project.update_stage_quadrant(
            stage="analysis",
            quadrant="inputs",
            data={"similarity_weight": 0.8, "clustering_k": 5},
        )
        assert project.stage_2_analysis.inputs.similarity_weight == 0.8
        assert project.stage_2_analysis.inputs.clustering_k == 5

        # 3. Update notes in stage 3
        project.update_stage_quadrant(
            stage="stage_3_planning",
            quadrant="notes",
            data=[
                StageNote(author="PlannerAgent", content="Consider inductive vs transductive split."),
                {"author": "ReviewerAgent", "content": "Ensure benchmark dataset section is included."},
            ],
        )
        assert len(project.stage_3_planning.notes) == 2
        assert project.stage_3_planning.notes[0].author == "PlannerAgent"
        assert project.stage_3_planning.notes[1].author == "ReviewerAgent"

    def test_update_stage_quadrant_validation_errors(self) -> None:
        project = ProjectState(name="Error Handling Test")
        with pytest.raises(ValueError) as exc:
            project.update_stage_quadrant(stage="unknown_stage", quadrant="meta", data={})
        assert "Invalid workflow stage" in str(exc.value)

        with pytest.raises(ValueError) as exc:
            project.update_stage_quadrant(stage="stage_1_research", quadrant="invalid_quadrant", data={})
        assert "Invalid quadrant" in str(exc.value)


# ---------------------------------------------------------------------------
# Test 5: Dot-Path Extraction (Selective State Querying)
# ---------------------------------------------------------------------------

class TestDotPathExtraction:
    """Test get_by_dot_path for selective navigation without LLM context explosion."""

    def test_root_and_stage_attribute_paths(self) -> None:
        project = ProjectState(
            name="Deep Learning Review",
            token_budget=600000,
            status="active",
        )
        assert project.get_by_dot_path("name") == "Deep Learning Review"
        assert project.get_by_dot_path("token_budget") == 600000
        assert project.get_by_dot_path("stage_1_research.meta.status") == "not_started"
        assert project.get_by_dot_path("stage_2_analysis.inputs.similarity_weight") == 0.6

    def test_deep_list_indexing_path(self) -> None:
        project = ProjectState(name="Section Test")
        section1 = SectionBlueprint(title="Introduction", order=1, level=1)
        section2 = SectionBlueprint(title="Theoretical Background", order=2, level=1)
        project.stage_3_planning.artifacts.outline.sections = [section1, section2]

        title_0 = project.get_by_dot_path("stage_3_planning.artifacts.outline.sections.0.title")
        assert title_0 == "Introduction"

        order_1 = project.get_by_dot_path("stage_3_planning.artifacts.outline.sections.1.order")
        assert order_1 == 2

    def test_compound_key_doi_with_dots(self) -> None:
        project = ProjectState(name="DOI Test")
        paper = PaperMetadata(
            doi="https://doi.org/10.1145/3292500.3330964",
            title="Seminal GNN Survey",
            year=2019,
        )
        # Store under normalized DOI key (10.1145/3292500.3330964)
        project.stage_1_research.artifacts.papers[paper.doi] = paper

        # 1. Query full PaperMetadata object using DOI with dots
        result_paper = project.get_by_dot_path("stage_1_research.artifacts.papers.10.1145/3292500.3330964")
        assert isinstance(result_paper, PaperMetadata)
        assert result_paper.title == "Seminal GNN Survey"

        # 2. Query specific attribute on the paper object
        result_title = project.get_by_dot_path("stage_1_research.artifacts.papers.10.1145/3292500.3330964.title")
        assert result_title == "Seminal GNN Survey"

        result_year = project.get_by_dot_path("stage_1_research.artifacts.papers.10.1145/3292500.3330964.year")
        assert result_year == 2019

    def test_empty_or_whitespace_path_returns_self(self) -> None:
        project = ProjectState(name="Self Test")
        assert project.get_by_dot_path("") is project
        assert project.get_by_dot_path("   ") is project

    def test_invalid_dot_path_errors(self) -> None:
        project = ProjectState(name="Invalid Path Test")
        with pytest.raises(KeyError):
            project.get_by_dot_path("stage_1_research.non_existent_quadrant")

        with pytest.raises(ValueError):
            project.get_by_dot_path("stage_3_planning.artifacts.outline.sections.not_an_int")


# ---------------------------------------------------------------------------
# Test 6: Pydantic v2 Serialization & Deserialization
# ---------------------------------------------------------------------------

class TestSerializationRoundtrip:
    """Test full Pydantic v2 serialization, dump_json, and model_validate."""

    def test_complete_roundtrip(self) -> None:
        project = ProjectState(
            name="Comprehensive GNN Literature Review",
            topic="Deep Learning on Graphs",
            target_level="phd",
            token_budget=1000000,
            tokens_used=45200,
            current_stage="stage_2_analysis",
        )

        # Populate Stage 1
        paper = PaperMetadata(
            doi="https://doi.org/10.1145/12345",
            title="Foundations of GNNs",
            year=2021,
            citation_count=150,
        )
        project.stage_1_research.artifacts.papers[paper.doi] = paper
        project.stage_1_research.artifacts.citation_edges = [("10.1145/12345", "10.1145/67890")]

        # Populate Message Board
        msg = project.post_message(
            author_agent="ALRSAgent",
            message_type="serendipity",
            title="Found Hyperbolic GNN paper",
            content="Relevant to curved manifold representations.",
            stage="stage_1_research",
            tags=["hyperbolic", "manifold"],
            related_paper_dois=["https://doi.org/10.1145/12345"],
        )
        msg.acknowledge("PlannerAgent")

        # Dump to JSON
        json_str = project.model_dump_json(indent=2)
        assert isinstance(json_str, str)

        # Deserialize back
        reconstructed = ProjectState.model_validate_json(json_str)
        assert reconstructed.project_id == project.project_id
        assert reconstructed.name == project.name
        assert reconstructed.token_budget == 1000000
        assert reconstructed.tokens_used == 45200
        assert reconstructed.current_stage == "stage_2_analysis"

        # Verify Stage 1 papers preserved
        assert "10.1145/12345" in reconstructed.stage_1_research.artifacts.papers
        rec_paper = reconstructed.stage_1_research.artifacts.papers["10.1145/12345"]
        assert rec_paper.title == "Foundations of GNNs"
        assert rec_paper.citation_count == 150

        # Verify Message Board preserved
        assert len(reconstructed.message_board) == 1
        rec_msg = reconstructed.message_board[0]
        assert rec_msg.message_type == "serendipity"
        assert rec_msg.title == "Found Hyperbolic GNN paper"
        assert rec_msg.related_paper_dois == ["10.1145/12345"]
        assert rec_msg.acknowledged_by == ["PlannerAgent"]

    def test_get_summary_format(self) -> None:
        project = ProjectState(name="Summary Test")
        summary = project.get_summary()

        assert summary["name"] == "Summary Test"
        assert "stages" in summary
        assert "stage_1_research" in summary["stages"]
        assert "stage_2_analysis" in summary["stages"]
        assert "stage_3_planning" in summary["stages"]
        assert "stage_4_writing" in summary["stages"]
        assert "stage_5_export" in summary["stages"]
        assert summary["message_board_total"] == 0

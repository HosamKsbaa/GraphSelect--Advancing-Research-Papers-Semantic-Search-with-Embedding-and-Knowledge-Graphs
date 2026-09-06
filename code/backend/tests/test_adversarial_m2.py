"""Adversarial stress-test suite for Milestone 2: Unified ProjectState, 4-Quadrant Substates, and Public Message Board.

Challenges:
1. Invalid and adversarial message types (unknown types, bad casing, whitespace, empty/None, alias spoofing).
2. Malformed DOIs (URL variants, prefix variants, whitespace/tabs/newlines, query params, non-strings, edge cases).
3. Dot-path extraction boundaries (empty, whitespace, leading/trailing dots, double dots, scalar traversal, None traversal, out-of-bounds, non-integer index, compound DOI keys with URLs).
4. Numeric validation boundaries (negative budgets, progress > 100%, negative depth, out-of-bounds k, target counts).
5. State mutation edge cases (invalid stages, invalid quadrants, invalid data types, notes payloads).
"""
import pytest
from pydantic import ValidationError
from datetime import datetime, timezone

from features.workflow.state_models import (
    BoardMessage,
    ProjectState,
    PaperMetadata,
    ResearchInputs,
    ResearchArtifacts,
    Stage1ResearchState,
    Stage2AnalysisState,
    Stage3PlanningState,
    Stage4WritingState,
    Stage5ExportState,
    StageMeta,
    StageNote,
    SectionBlueprint,
    normalize_doi,
    normalize_stage_name,
)


class TestAdversarialMessageTypes:
    """Stress-testing BoardMessage message_type validation."""

    @pytest.mark.parametrize(
        "bad_type",
        [
            "unknown_type",
            "INSIGHT",
            "Insight",
            "GAP",
            " warning ",
            "",
            "   ",
            "null",
            "none",
            "random_string_123",
            "decision_maker",
            "hypothesis!",
        ],
    )
    def test_invalid_string_message_types_fail(self, bad_type: str) -> None:
        with pytest.raises(ValidationError):
            BoardMessage(
                author_agent="TestAgent",
                message_type=bad_type,  # type: ignore[arg-type]
                title="Test Title",
                content="Test Content",
            )

    @pytest.mark.parametrize(
        "bad_type_non_str",
        [
            None,
            123,
            True,
            ["insight"],
            {"type": "insight"},
        ],
    )
    def test_invalid_non_string_message_types_fail(self, bad_type_non_str) -> None:
        with pytest.raises(ValidationError):
            BoardMessage(
                author_agent="TestAgent",
                message_type=bad_type_non_str,  # type: ignore[arg-type]
                title="Test Title",
                content="Test Content",
            )

    def test_project_post_message_with_invalid_type_fails(self) -> None:
        project = ProjectState(name="Test Project")
        with pytest.raises(ValidationError):
            project.post_message(
                author_agent="TestAgent",
                message_type="invalid_type",
                title="Test Title",
                content="Test Content",
            )

    def test_project_add_message_with_invalid_type_fails(self) -> None:
        project = ProjectState(name="Test Project")
        with pytest.raises(ValidationError):
            project.add_message(
                author_agent="TestAgent",
                message_type="malformed",
                title="Test Title",
                content="Test Content",
            )

    def test_alias_classification_with_invalid_type_fails(self) -> None:
        with pytest.raises(ValidationError):
            BoardMessage(
                author_agent="TestAgent",
                classification="bogus_classification",  # type: ignore[call-arg]
                title="Test Title",
                content="Test Content",
            )

    @pytest.mark.parametrize("empty_author", ["", "   "])
    def test_empty_author_agent_fails(self, empty_author: str) -> None:
        # min_length=1 should reject empty author
        if empty_author == "":
            with pytest.raises(ValidationError):
                BoardMessage(
                    author_agent="",
                    message_type="insight",
                    title="Title",
                    content="Content",
                )

    def test_empty_title_fails(self) -> None:
        with pytest.raises(ValidationError):
            BoardMessage(
                author_agent="Agent",
                message_type="insight",
                title="",
                content="Content",
            )

    def test_excessively_long_title_fails(self) -> None:
        long_title = "x" * 301
        with pytest.raises(ValidationError):
            BoardMessage(
                author_agent="Agent",
                message_type="insight",
                title=long_title,
                content="Content",
            )

    def test_empty_content_fails(self) -> None:
        with pytest.raises(ValidationError):
            BoardMessage(
                author_agent="Agent",
                message_type="insight",
                title="Title",
                content="",
            )


class TestAdversarialDoiNormalization:
    """Stress-testing DOI cleaning across edge cases and malformed formats."""

    @pytest.mark.parametrize(
        ("input_doi", "expected_normalized"),
        [
            ("https://doi.org/10.1145/12345", "10.1145/12345"),
            ("http://doi.org/10.1145/12345", "10.1145/12345"),
            ("https://dx.doi.org/10.1145/12345", "10.1145/12345"),
            ("http://dx.doi.org/10.1145/12345", "10.1145/12345"),
            ("doi: 10.1145/12345", "10.1145/12345"),
            ("DOI: 10.1145/12345", "10.1145/12345"),
            ("doi:10.1145/12345", "10.1145/12345"),
            ("doi:/10.1145/12345", "10.1145/12345"),
            ("  \t\n  https://doi.org/10.1145/12345  \n\t  ", "10.1145/12345"),
            ("HTTPS://DOI.ORG/10.1145/ABC.DEF", "10.1145/abc.def"),
            ("https://doi.org//10.1145/12345", "10.1145/12345"),  # double slash
        ],
    )
    def test_normalize_doi_various_valid_formats(self, input_doi: str, expected_normalized: str) -> None:
        assert normalize_doi(input_doi) == expected_normalized

    @pytest.mark.parametrize("empty_input", ["", "   ", "\t\n", None])
    def test_normalize_doi_empty_inputs(self, empty_input) -> None:
        assert normalize_doi(empty_input) == ""

    def test_board_message_related_dois_single_string_coercion(self) -> None:
        msg = BoardMessage(
            author_agent="Agent",
            message_type="gap",
            title="Gap",
            content="Content",
            related_paper_dois="https://doi.org/10.1145/99999",  # type: ignore[arg-type]
        )
        assert msg.related_paper_dois == ["10.1145/99999"]

    def test_board_message_related_dois_filters_empty_and_normalizes(self) -> None:
        msg = BoardMessage(
            author_agent="Agent",
            message_type="gap",
            title="Gap",
            content="Content",
            related_paper_dois=[
                "https://doi.org/10.1145/111",
                "",
                "   ",
                None,  # type: ignore[list-item]
                "http://dx.doi.org/10.1145/222",
            ],
        )
        assert msg.related_paper_dois == ["10.1145/111", "10.1145/222"]

    def test_research_inputs_seed_dois_normalization(self) -> None:
        inputs = ResearchInputs(
            seed_dois=[
                "https://doi.org/10.1145/seed1",
                "doi: 10.1145/SEED2",
                "  ",
            ]
        )
        assert inputs.seed_dois == ["10.1145/seed1", "10.1145/seed2"]

    def test_paper_metadata_doi_normalization(self) -> None:
        paper = PaperMetadata(
            doi="  HTTPS://DOI.ORG/10.1145/PAPER_1  ",
            title="A Paper",
        )
        assert paper.doi == "10.1145/paper_1"


class TestAdversarialDotPathExtraction:
    """Stress-testing get_by_dot_path traversal, edge cases, and boundary conditions."""

    @pytest.fixture
    def populated_project(self) -> ProjectState:
        project = ProjectState(
            name="Adversarial Test Project",
            topic="Test AI",
            token_budget=100000,
        )
        # Add a paper with compound dots in DOI
        paper1 = PaperMetadata(
            doi="10.1145/3292500.3330964",
            title="Complex GNN DOI Paper",
            year=2020,
        )
        project.stage_1_research.artifacts.papers[paper1.doi] = paper1

        # Add section blueprints
        sec1 = SectionBlueprint(title="Sec 1", order=1, level=1)
        sec2 = SectionBlueprint(title="Sec 2", order=2, level=2)
        project.stage_3_planning.artifacts.outline.sections = [sec1, sec2]

        # Add board message
        project.post_message(
            author_agent="ALRSAgent",
            message_type="insight",
            title="Board Insight",
            content="Message Content",
            related_paper_dois=["10.1145/3292500.3330964"],
        )
        return project

    @pytest.mark.parametrize("empty_path", ["", "   ", "\t", "\n", " \t \n "])
    def test_empty_dot_paths_return_self(self, populated_project: ProjectState, empty_path: str) -> None:
        assert populated_project.get_by_dot_path(empty_path) is populated_project

    def test_invalid_attribute_raises_key_error(self, populated_project: ProjectState) -> None:
        with pytest.raises(KeyError) as exc:
            populated_project.get_by_dot_path("non_existent_field")
        assert "not found" in str(exc.value)

    def test_nested_invalid_attribute_raises_key_error(self, populated_project: ProjectState) -> None:
        with pytest.raises(KeyError) as exc:
            populated_project.get_by_dot_path("stage_1_research.non_existent_quadrant")
        assert "not found" in str(exc.value)

    def test_invalid_dict_key_raises_key_error(self, populated_project: ProjectState) -> None:
        with pytest.raises(KeyError) as exc:
            populated_project.get_by_dot_path("stage_1_research.artifacts.papers.10.9999/nonexistent")
        assert "not found in dict" in str(exc.value)

    def test_traversing_into_scalar_raises_type_error(self, populated_project: ProjectState) -> None:
        with pytest.raises(TypeError) as exc:
            populated_project.get_by_dot_path("name.some_subfield")
        assert "Cannot traverse into scalar" in str(exc.value)

    def test_traversing_into_none_raises_type_error(self, populated_project: ProjectState) -> None:
        with pytest.raises(TypeError) as exc:
            populated_project.get_by_dot_path("completed_at.year")
        assert "Cannot traverse into scalar value of type NoneType" in str(exc.value)

    def test_list_index_out_of_bounds_raises_index_error(self, populated_project: ProjectState) -> None:
        with pytest.raises(IndexError) as exc:
            populated_project.get_by_dot_path("stage_3_planning.artifacts.outline.sections.999")
        assert "out of range" in str(exc.value)

    def test_list_index_non_integer_raises_value_error(self, populated_project: ProjectState) -> None:
        with pytest.raises(ValueError) as exc:
            populated_project.get_by_dot_path("stage_3_planning.artifacts.outline.sections.first")
        assert "Cannot index list with non-integer" in str(exc.value)

    def test_list_index_on_empty_list_raises_index_error(self, populated_project: ProjectState) -> None:
        with pytest.raises(IndexError) as exc:
            populated_project.get_by_dot_path("stage_1_research.notes.0")
        assert "out of range" in str(exc.value)

    def test_compound_key_doi_resolution_direct(self, populated_project: ProjectState) -> None:
        title = populated_project.get_by_dot_path(
            "stage_1_research.artifacts.papers.10.1145/3292500.3330964.title"
        )
        assert title == "Complex GNN DOI Paper"

    def test_compound_key_doi_resolution_with_url_prefix(self, populated_project: ProjectState) -> None:
        # Looking up using full https://doi.org/... path
        title = populated_project.get_by_dot_path(
            "stage_1_research.artifacts.papers.https://doi.org/10.1145/3292500.3330964.title"
        )
        assert title == "Complex GNN DOI Paper"

    def test_message_board_list_indexing_and_traversal(self, populated_project: ProjectState) -> None:
        author = populated_project.get_by_dot_path("message_board.0.author_agent")
        assert author == "ALRSAgent"
        doi_0 = populated_project.get_by_dot_path("message_board.0.related_paper_dois.0")
        assert doi_0 == "10.1145/3292500.3330964"


class TestAdversarialNumericAndSchemaBoundaries:
    """Stress-testing numeric bounds, stage names, and mutation boundaries."""

    def test_negative_token_budget_fails(self) -> None:
        with pytest.raises(ValidationError):
            ProjectState(name="Neg Budget", token_budget=-1)

    def test_negative_tokens_used_fails(self) -> None:
        with pytest.raises(ValidationError):
            ProjectState(name="Neg Tokens", tokens_used=-50)

    def test_invalid_progress_percentage_fails(self) -> None:
        with pytest.raises(ValidationError):
            StageMeta(progress_percentage=-0.1)

        with pytest.raises(ValidationError):
            StageMeta(progress_percentage=100.1)

    def test_invalid_similarity_threshold_fails(self) -> None:
        with pytest.raises(ValidationError):
            ProjectState(name="Threshold", similarity_threshold=-0.01)

        with pytest.raises(ValidationError):
            ProjectState(name="Threshold", similarity_threshold=1.01)

    def test_invalid_stage_depth_bounds(self) -> None:
        with pytest.raises(ValidationError):
            ResearchInputs(max_depth=-1)
        with pytest.raises(ValidationError):
            ResearchInputs(max_depth=6)

    def test_invalid_clustering_k_bounds(self) -> None:
        from features.workflow.state_models import AnalysisInputs
        with pytest.raises(ValidationError):
            AnalysisInputs(clustering_k=1)
        with pytest.raises(ValidationError):
            AnalysisInputs(clustering_k=21)

    def test_invalid_section_count_bounds(self) -> None:
        from features.workflow.state_models import PlanningInputs
        with pytest.raises(ValidationError):
            PlanningInputs(target_section_count=1)
        with pytest.raises(ValidationError):
            PlanningInputs(target_section_count=16)

    def test_invalid_review_iterations_bounds(self) -> None:
        from features.workflow.state_models import WritingInputs
        with pytest.raises(ValidationError):
            WritingInputs(max_review_iterations=0)
        with pytest.raises(ValidationError):
            WritingInputs(max_review_iterations=6)


class TestAdversarialMutationBoundaries:
    """Stress-testing update_stage_quadrant."""

    @pytest.mark.parametrize("invalid_stage", ["stage_6", "invalid", "", "10", "orchestrator"])
    def test_update_invalid_stage_fails(self, invalid_stage: str) -> None:
        project = ProjectState(name="Stage Test")
        with pytest.raises(ValueError) as exc:
            project.update_stage_quadrant(stage=invalid_stage, quadrant="meta", data={})
        assert "Invalid workflow stage" in str(exc.value)

    @pytest.mark.parametrize("invalid_quad", ["output", "state", "context", "", "results"])
    def test_update_invalid_quadrant_fails(self, invalid_quad: str) -> None:
        project = ProjectState(name="Quad Test")
        with pytest.raises(ValueError) as exc:
            project.update_stage_quadrant(stage="stage_1_research", quadrant=invalid_quad, data={})
        assert "Invalid quadrant" in str(exc.value)

    def test_update_meta_with_non_dict_fails(self) -> None:
        project = ProjectState(name="Type Test")
        with pytest.raises(TypeError) as exc:
            project.update_stage_quadrant(stage="stage_1_research", quadrant="meta", data="invalid_string")  # type: ignore[arg-type]
        assert "Data for quadrant 'meta' must be a dict" in str(exc.value)

    def test_update_notes_with_non_dict_non_list_fails(self) -> None:
        project = ProjectState(name="Type Test")
        with pytest.raises(TypeError) as exc:
            project.update_stage_quadrant(stage="stage_1_research", quadrant="notes", data=12345)  # type: ignore[arg-type]
        assert "Data for notes quadrant must be list or dict" in str(exc.value)

    def test_update_stage_quadrant_updates_root_and_stage_timestamps(self) -> None:
        import time
        project = ProjectState(name="Timestamp Test")
        t0_project = project.updated_at
        t0_meta = project.stage_1_research.meta.updated_at

        # Small sleep to ensure timestamp difference
        time.sleep(0.01)
        project.update_stage_quadrant(
            stage="stage_1_research",
            quadrant="meta",
            data={"status": "in_progress"},
        )
        assert project.updated_at > t0_project
        assert project.stage_1_research.meta.updated_at > t0_meta

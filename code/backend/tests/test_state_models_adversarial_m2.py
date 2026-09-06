"""Adversarial stress and verification tests for Milestone 2:
Unified ProjectState, 4-Quadrant Substate Models, and Public Message Board.

Authored by Challenger 2 for empirical validation of:
1. Pydantic v2 JSON serialization and deserialization (model_dump, model_dump_json, model_validate_json),
   type fidelity, timezone awareness, tuple preservation, compound key handling, extra field tolerance,
   and malformed JSON rejection.
2. Full lifecycle roundtrip of ProjectState with all 5 stages heavily populated with complex artifacts.
3. Public message board stress operations: high-volume messages, duplicate DOIs, normalizations,
   multi-agent acknowledgments, idempotence, and state touch invariants.
4. Edge cases, boundary condition mining, Unicode, large payloads, and defensive error contracts.
"""
from __future__ import annotations

import copy
import json
import uuid
from datetime import datetime, timezone
from typing import Any

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


# ===========================================================================
# 1. Pydantic v2 JSON Serialization & Deserialization Adversarial Verification
# ===========================================================================

class TestPydanticV2SerializationAdversarial:
    """Adversarially verify Pydantic v2 serialization, deserialization, type fidelity, and error boundaries."""

    def test_model_dump_and_model_dump_json_consistency(self) -> None:
        """Verify model_dump (Python dict) and model_dump_json (JSON string) are mutually consistent."""
        project = ProjectState(
            name="Consistency Test Review",
            topic="Reinforcement Learning from Human Feedback",
            target_level="phd",
            token_budget=800000,
            tokens_used=12345,
            similarity_threshold=0.75,
        )

        # Python dict dump
        dumped_dict = project.model_dump()
        assert isinstance(dumped_dict, dict)
        assert dumped_dict["name"] == "Consistency Test Review"
        assert dumped_dict["token_budget"] == 800000
        assert dumped_dict["tokens_used"] == 12345
        assert dumped_dict["similarity_threshold"] == 0.75
        assert "stage_1_research" in dumped_dict
        assert "message_board" in dumped_dict

        # JSON string dump
        dumped_json = project.model_dump_json()
        assert isinstance(dumped_json, str)
        parsed_json = json.loads(dumped_json)
        assert parsed_json["name"] == "Consistency Test Review"
        assert parsed_json["token_budget"] == 800000

        # Validate deserialization from both formats
        from_dict = ProjectState.model_validate(dumped_dict)
        from_json = ProjectState.model_validate_json(dumped_json)

        assert from_dict.project_id == project.project_id
        assert from_json.project_id == project.project_id
        assert from_dict.name == from_json.name
        assert from_dict.similarity_threshold == from_json.similarity_threshold

    def test_timezone_aware_datetime_roundtrip(self) -> None:
        """Verify datetime fields serialize with UTC timezone and deserialize back to aware datetime."""
        fixed_dt = datetime(2026, 9, 4, 11, 30, 45, tzinfo=timezone.utc)
        note = StageNote(
            author="AuditorAgent",
            content="Temporal verification check.",
            timestamp=fixed_dt,
        )
        json_str = note.model_dump_json()
        reconstructed = StageNote.model_validate_json(json_str)

        assert isinstance(reconstructed.timestamp, datetime)
        assert reconstructed.timestamp == fixed_dt
        assert reconstructed.timestamp.tzinfo is not None

    def test_tuple_preservation_across_json_roundtrip(self) -> None:
        """Verify tuples in citation_edges, bfs_graph_edges, and year_range survive json roundtrip."""
        project = ProjectState(name="Tuple Roundtrip Test")
        project.stage_1_research.inputs.year_range = (2018, 2024)
        project.stage_1_research.artifacts.citation_edges = [
            ("10.1145/100", "10.1145/200"),
            ("10.1145/200", "10.1145/300"),
        ]
        project.stage_1_research.artifacts.bfs_graph_edges = [
            ("10.1145/seed", "10.1145/hop1"),
            ("10.1145/hop1", "10.1145/hop2"),
        ]

        # Serialization to JSON converts tuples to arrays: [["10.1145/100", "10.1145/200"], ...]
        raw_json = project.model_dump_json()
        data = json.loads(raw_json)
        assert isinstance(data["stage_1_research"]["artifacts"]["citation_edges"][0], list)

        # Deserialization must reconstitute them as tuples
        reconstructed = ProjectState.model_validate_json(raw_json)
        assert reconstructed.stage_1_research.inputs.year_range == (2018, 2024)
        assert isinstance(reconstructed.stage_1_research.inputs.year_range, tuple)

        assert len(reconstructed.stage_1_research.artifacts.citation_edges) == 2
        edge_0 = reconstructed.stage_1_research.artifacts.citation_edges[0]
        assert isinstance(edge_0, tuple)
        assert edge_0 == ("10.1145/100", "10.1145/200")

        bfs_0 = reconstructed.stage_1_research.artifacts.bfs_graph_edges[0]
        assert isinstance(bfs_0, tuple)
        assert bfs_0 == ("10.1145/seed", "10.1145/hop1")

    def test_extra_fields_tolerance_via_config_extra_allow(self) -> None:
        """Verify ConfigDict(extra='allow') allows downstream extensions without throwing validation errors."""
        raw_payload = {
            "name": "Extension Resilience Test",
            "token_budget": 500000,
            "future_experimental_flag": True,
            "custom_metadata_bag": {"origin": "adk_bridge", "version": 42},
            "stage_1_research": {
                "meta": {
                    "status": "in_progress",
                    "worker_heartbeat_id": "whb-9999",
                },
                "inputs": {
                    "max_depth": 3,
                    "experimental_rag_branch": "hybrid_rerank",
                },
                "artifacts": {},
                "notes": [],
            },
        }

        # Validate from JSON with unexpected fields
        project = ProjectState.model_validate(raw_payload)
        assert project.name == "Extension Resilience Test"
        # Access extra fields via model extra dictionary
        assert project.model_extra is not None
        assert project.stage_1_research.meta.model_extra is not None
        assert project.stage_1_research.inputs.model_extra is not None
        assert project.model_extra["future_experimental_flag"] is True
        assert project.model_extra["custom_metadata_bag"]["version"] == 42
        assert project.stage_1_research.meta.model_extra["worker_heartbeat_id"] == "whb-9999"
        assert project.stage_1_research.inputs.model_extra["experimental_rag_branch"] == "hybrid_rerank"

        # Verify extra fields survive another serialization roundtrip
        json_dumped = project.model_dump_json()
        reconstructed = ProjectState.model_validate_json(json_dumped)
        assert reconstructed.model_extra is not None
        assert reconstructed.model_extra["future_experimental_flag"] is True

    def test_unicode_special_characters_and_math_formatting(self) -> None:
        """Verify models correctly serialize and deserialize Unicode, non-ASCII characters, and math formulas."""
        project = ProjectState(
            name="Arabic & CJK & Math Review: بحث التعلم العميق / 深度学习综述 / $\\alpha \\le \\beta$",
            topic="Multilingual Representation / 多语言表示",
        )
        # Add a note with math formulas and code blocks
        project.stage_1_research.notes.append(
            StageNote(
                author="ResearchAgent_عالم_研究员",
                content=(
                    "### Mathematical Grounding\n"
                    "Loss function is defined as:\n"
                    "$$\\mathcal{L}_{GNN} = - \\sum_{v \\in V} y_v \\log(\\sigma(h_v^T W))$$\n"
                    "Special characters: ä, ö, ü, é, ñ, 🚀, 🔬, 📊"
                ),
                tags=["math", "رياضيات", "数学"],
            )
        )

        json_str = project.model_dump_json()
        reconstructed = ProjectState.model_validate_json(json_str)

        assert "بحث التعلم العميق" in reconstructed.name
        assert "深度学习综述" in reconstructed.name
        assert "$\\alpha \\le \\beta$" in reconstructed.name
        note = reconstructed.stage_1_research.notes[0]
        assert "عالم_研究员" in note.author
        assert "\\mathcal{L}_{GNN}" in note.content
        assert "🚀" in note.content
        assert "رياضيات" in note.tags

    def test_malformed_json_and_validation_error_boundaries(self) -> None:
        """Verify strict error rejection on invalid types, out-of-range parameters, and malformed inputs."""
        # 1. Broken JSON syntax
        with pytest.raises(Exception):  # ValueError / json.JSONDecodeError
            ProjectState.model_validate_json("{ broken json payload: missing quote }")

        # 2. Negative token budget
        with pytest.raises(ValidationError) as exc_budget:
            ProjectState(name="Bad Budget", token_budget=-500)
        assert "token_budget" in str(exc_budget.value)

        # 3. Invalid status literal
        with pytest.raises(ValidationError) as exc_status:
            ProjectState(name="Bad Status", status="corrupted_state")  # type: ignore[arg-type]
        assert "status" in str(exc_status.value)

        # 4. Out of range progress percentage (> 100.0)
        with pytest.raises(ValidationError) as exc_prog:
            StageMeta(progress_percentage=100.5)
        assert "progress_percentage" in str(exc_prog.value)

        # 5. Out of range progress percentage (< 0.0)
        with pytest.raises(ValidationError) as exc_prog_neg:
            StageMeta(progress_percentage=-1.0)
        assert "progress_percentage" in str(exc_prog_neg.value)

        # 6. Out of range similarity threshold (> 1.0)
        with pytest.raises(ValidationError) as exc_sim:
            ProjectState(name="Bad Sim", similarity_threshold=1.5)
        assert "similarity_threshold" in str(exc_sim.value)

        # 7. Out of range max_depth (> 5)
        with pytest.raises(ValidationError) as exc_depth:
            ResearchInputs(max_depth=9)
        assert "max_depth" in str(exc_depth.value)

        # 8. Empty project name rejected
        with pytest.raises(ValidationError) as exc_name:
            ProjectState(name="")
        assert "name" in str(exc_name.value)

        # 9. Invalid message_type rejected
        with pytest.raises(ValidationError) as exc_msg_type:
            BoardMessage(
                author_agent="ALRSAgent",
                message_type="unsupported_type",  # type: ignore[arg-type]
                title="Bad Message",
                content="Content",
            )
        assert "message_type" in str(exc_msg_type.value)

        # 10. Empty title on BoardMessage rejected
        with pytest.raises(ValidationError) as exc_title:
            BoardMessage(
                author_agent="ALRSAgent",
                message_type="insight",
                title="",
                content="Valid content",
            )
        assert "title" in str(exc_title.value)

    def test_successive_multi_cycle_roundtrip_idempotency(self) -> None:
        """Verify successive serialize-deserialize-serialize cycles produce 100% stable payloads without drift."""
        original = ProjectState(
            name="Idempotency Cycle Review",
            topic="Graph Transformers",
            target_level="phd",
            token_budget=650000,
        )
        paper = PaperMetadata(
            doi="https://doi.org/10.1145/3292500.3330964",
            title="A Comprehensive Survey on Graph Neural Networks",
            year=2020,
            citation_count=5420,
        )
        original.stage_1_research.artifacts.papers[paper.doi] = paper
        original.post_message(
            author_agent="ALRSAgent",
            message_type="insight",
            title="Attention in Graphs",
            content="Sparse edge attention dominates dense softmax.",
            related_paper_dois=[paper.doi],
        )

        # Cycle 1: Dump from in-memory constructor
        json_1 = original.model_dump_json()
        state_1 = ProjectState.model_validate_json(json_1)

        # On first deserialization, handle_project_id_alias populates 'id' in model_extra
        assert state_1.model_extra is not None
        assert "id" in state_1.model_extra
        assert state_1.model_extra["id"] == original.project_id

        # Cycle 2: Dump from reconstructed state (now contains serialized 'id')
        json_2 = state_1.model_dump_json()
        state_2 = ProjectState.model_validate_json(json_2)

        # Cycle 3: Dump from second reconstruction
        json_3 = state_2.model_dump_json()
        state_3 = ProjectState.model_validate_json(json_3)

        # Once serialized with id alias, cycles 2 and 3 are 100% idempotent and stable
        assert json_2 == json_3
        assert state_1.project_id == state_2.project_id == state_3.project_id
        assert state_1.stage_1_research.artifacts.papers.keys() == state_3.stage_1_research.artifacts.papers.keys()


# ===========================================================================
# 2. Full 5-Stage Lifecycle Roundtrip with Complex Artifacts
# ===========================================================================

class TestFullLifecycleFiveStagesRoundtrip:
    """Stress test full lifecycle roundtrip with deeply populated models across all 5 stages."""

    @pytest.fixture
    def fully_populated_project(self) -> ProjectState:
        """Construct an exhaustive, production-grade ProjectState with all 5 stages active and filled."""
        project = ProjectState(
            project_id="alrs-proj-lifecycle-test-2026",
            name="Geometric Deep Learning & Equivariant Networks for Drug Discovery",
            description="Autonomous multi-agent comprehensive literature review on SE(3) and SO(3) equivariant graph representations.",
            topic="Machine Learning / Computational Chemistry",
            status="active",
            target_level="phd",
            similarity_threshold=0.68,
            token_budget=1500000,
            tokens_used=142890,
            current_stage="stage_4_writing",
        )

        # -------------------------------------------------------------------
        # Stage 1: Research
        # -------------------------------------------------------------------
        project.stage_1_research.meta.status = "completed"
        project.stage_1_research.meta.agent_name = "ResearchAgent"
        project.stage_1_research.meta.progress_percentage = 100.0
        project.stage_1_research.meta.started_at = datetime(2026, 9, 1, 8, 0, 0, tzinfo=timezone.utc)
        project.stage_1_research.meta.completed_at = datetime(2026, 9, 1, 14, 30, 0, tzinfo=timezone.utc)

        project.stage_1_research.inputs.research_questions = [
            "How do SE(3)-equivariant neural networks guarantee roto-translation invariance in 3D molecular conformations?",
            "What are the computational trade-offs between spherical harmonic tensor products and scalar invariant representations?",
        ]
        project.stage_1_research.inputs.seed_dois = [
            "https://doi.org/10.48550/arxiv.2102.09844",  # EGNN
            "10.5555/3546258.3546500",  # SchNet
        ]
        project.stage_1_research.inputs.keywords = ["equivariant", "se3", "molecular graph", "spherical harmonics"]
        project.stage_1_research.inputs.search_queries = [
            "SE(3) equivariant graph neural networks molecular docking",
            "spherical harmonics Clebsch-Gordan tensor product efficiency",
        ]
        project.stage_1_research.inputs.max_depth = 3
        project.stage_1_research.inputs.similarity_threshold = 0.68
        project.stage_1_research.inputs.max_papers = 200
        project.stage_1_research.inputs.year_range = (2018, 2025)

        # Populate 4 realistic papers
        p1 = PaperMetadata(
            doi="10.48550/arxiv.2102.09844",
            title="E(n) Equivariant Graph Neural Networks",
            authors=["Victor Garcia Satorras", "Emiel Hoogeboom", "Max Welling"],
            year=2021,
            venue="ICML 2021",
            abstract="We introduce E(n) equivariant Graph Neural Networks that do not require expensive spherical harmonics.",
            citation_count=1850,
            openalex_id="W3134987123",
            pdf_url="https://arxiv.org/pdf/2102.09844.pdf",
            is_seed=True,
            hop_distance=0,
        )
        p2 = PaperMetadata(
            doi="10.1063/1.5019779",
            title="SchNet: A continuous-filter convolutional neural network for quantum chemistry",
            authors=["Kristof Schutt", "Huziel Sauceda", "Peter Kindermans", "Alexandre Tkatchenko", "Klaus-Robert Muller"],
            year=2018,
            venue="J. Chem. Phys.",
            abstract="SchNet models molecular energies and forces with continuous-filter convolutions.",
            citation_count=2300,
            is_seed=True,
            hop_distance=0,
        )
        p3 = PaperMetadata(
            doi="10.5555/3524938.3525120",
            title="SE(3)-Transformers: 3D Roto-Translation Equivariant Attention Networks",
            authors=["Fabian Fuchs", "Daniel Worrall", "Volker Fischer", "Max Welling"],
            year=2020,
            venue="NeurIPS 2020",
            abstract="Self-attention networks equivariant to continuous 3D roto-translations.",
            citation_count=890,
            is_seed=False,
            hop_distance=1,
        )
        p4 = PaperMetadata(
            doi="10.1145/3292500.3330964",
            title="Geometric Deep Learning: Grids, Groups, Graphs, Geodesics, and Gauges",
            authors=["Michael Bronstein", "Joan Bruna", "Taco Cohen", "Petar Velickovic"],
            year=2021,
            venue="IEEE SPM",
            abstract="Blueprint for unifying machine learning architectures from geometric principles.",
            citation_count=3200,
            is_seed=False,
            hop_distance=1,
        )
        for p in (p1, p2, p3, p4):
            project.stage_1_research.artifacts.papers[p.doi] = p

        project.stage_1_research.artifacts.crawl_queue = ["10.1038/s41586-021-03819-2"]
        project.stage_1_research.artifacts.visited_dois = [p1.doi, p2.doi, p3.doi, p4.doi]
        project.stage_1_research.artifacts.citation_edges = [
            (p1.doi, p2.doi),
            (p3.doi, p1.doi),
            (p4.doi, p3.doi),
        ]
        project.stage_1_research.artifacts.bfs_graph_edges = copy.deepcopy(project.stage_1_research.artifacts.citation_edges)
        project.stage_1_research.artifacts.top_authors = [
            {"name": "Max Welling", "count": 2},
            {"name": "Michael Bronstein", "count": 1},
        ]
        project.stage_1_research.artifacts.top_venues = [
            {"venue": "NeurIPS", "count": 1},
            {"venue": "ICML", "count": 1},
        ]
        project.stage_1_research.artifacts.total_discovered = 184
        project.stage_1_research.artifacts.total_relevant = 42

        project.stage_1_research.notes.append(
            StageNote(
                author="ResearchAgent",
                category="trade_off",
                content="Spherical harmonic based networks exhibit O(L^6) Clebsch-Gordan bottleneck vs scalar invariants.",
                tags=["spherical-harmonics", "clebsch-gordan"],
            )
        )

        # -------------------------------------------------------------------
        # Stage 2: Analysis
        # -------------------------------------------------------------------
        project.stage_2_analysis.meta.status = "completed"
        project.stage_2_analysis.meta.agent_name = "GapFinderAgent"
        project.stage_2_analysis.meta.progress_percentage = 100.0

        project.stage_2_analysis.inputs.similarity_weight = 0.65
        project.stage_2_analysis.inputs.pagerank_weight = 0.35
        project.stage_2_analysis.inputs.embedding_model = "gemini-embedding-2"
        project.stage_2_analysis.inputs.clustering_k = 3
        project.stage_2_analysis.inputs.target_dimensions = ["computational_complexity", "inductive_bias", "scalability"]

        project.stage_2_analysis.artifacts.embeddings_metadata = {
            "model": "gemini-embedding-2",
            "dimensionality": 768,
            "vector_count": 42,
        }
        project.stage_2_analysis.artifacts.clusters = [
            PaperCluster(
                cluster_id="cluster-se3-equivariant",
                label="Equivariant Spherical Harmonic Transformers",
                paper_dois=[p3.doi],
                top_keywords=["clebsch-gordan", "spherical-harmonics", "roto-translation"],
                summary="Architectures utilizing irreducible SO(3) representations.",
            ),
            PaperCluster(
                cluster_id="cluster-scalar-invariant",
                label="Coordinate Invariant Distance Convolutions",
                paper_dois=[p1.doi, p2.doi],
                top_keywords=["radial-basis", "coordinate-update", "vector-field"],
                summary="Lightweight invariant and equivariant models avoiding tensor product overhead.",
            ),
        ]
        project.stage_2_analysis.artifacts.gaps = [
            ResearchGap(
                gap_id="gap-dynamic-conformations",
                question="How well do static SE(3) architectures generalize to flexible binding pockets with large conformational entropy?",
                description="Current models evaluate almost exclusively on rigid crystal ligand-receptor complexes.",
                severity="critical",
                suggested_queries=["SE(3) molecular dynamics conformational ensembles", "flexible receptor docking GNN"],
                covered_by_dois=[p1.doi, p3.doi],
            )
        ]
        project.stage_2_analysis.artifacts.rankings = [
            PaperRanking(
                doi=p1.doi,
                title=p1.title,
                year=2021,
                similarity_score=0.94,
                pagerank_score=0.88,
                hybrid_score=0.919,
                rank=1,
            ),
            PaperRanking(
                doi=p3.doi,
                title=p3.title,
                year=2020,
                similarity_score=0.91,
                pagerank_score=0.79,
                hybrid_score=0.868,
                rank=2,
            ),
        ]
        project.stage_2_analysis.artifacts.findings_by_doi = {
            p1.doi: PaperFinding(
                doi=p1.doi,
                title=p1.title,
                year=2021,
                methodology="Equivariant coordinate updates via relative distance scaling without spherical harmonics.",
                key_findings=["Matches or exceeds TFN accuracy with 10x faster inference.", "Scales to thousands of atoms."],
                datasets_or_benchmarks=["QM9", "MD17", "N-body simulation"],
                limitations=["Cannot directly capture higher-order angular moments."],
            )
        }
        project.stage_2_analysis.artifacts.comparison_matrix = StructuredComparisonMatrix(
            project_id=project.project_id,
            dimensions=[
                ComparisonDimension(
                    dimension_name="Asymptotic Complexity",
                    findings_by_doi={
                        p1.doi: "O(E * D) - Linear in edges and hidden dimension",
                        p3.doi: "O(E * L^3 * D) - Cubic in maximum spherical harmonic degree L",
                    },
                    consensus="Scalar message passing is drastically cheaper computationally.",
                    divergence="Debate remains whether higher angular frequencies are essential for anisotropic forces.",
                )
            ],
            synthesis_narrative="The literature exhibits a clear divergence between spherical harmonic completeness and scalar efficiency.",
        )

        # -------------------------------------------------------------------
        # Stage 3: Planning
        # -------------------------------------------------------------------
        project.stage_3_planning.meta.status = "completed"
        project.stage_3_planning.meta.agent_name = "PlannerAgent"
        project.stage_3_planning.meta.progress_percentage = 100.0

        project.stage_3_planning.inputs.style = "thematic"
        project.stage_3_planning.inputs.target_word_count = 9500
        project.stage_3_planning.inputs.min_papers_per_section = 2
        project.stage_3_planning.inputs.target_section_count = 4

        sec_intro = SectionBlueprint(
            section_id="sec-intro",
            title="1. Introduction & Geometric Preliminaries",
            order=1,
            level=1,
            description="Foundations of group symmetry, SE(3) equivariance, and physical symmetries in molecules.",
            theme="Foundations",
            assigned_dois=[p4.doi],
            target_word_count=1800,
        )
        sec_spherical = SectionBlueprint(
            section_id="sec-spherical",
            title="2. Spherical Harmonic & Clebsch-Gordan Architectures",
            order=2,
            level=1,
            description="Detailed review of irreducible representation networks (TFN, SE(3)-Transformers, Cormorant).",
            theme="Spherical Harmonics",
            assigned_dois=[p3.doi],
            target_word_count=2600,
        )
        sec_scalar = SectionBlueprint(
            section_id="sec-scalar",
            title="3. Coordinate Vector & Distance Invariant Frameworks",
            order=3,
            level=1,
            description="Lightweight architectures bypassing tensor products (EGNN, SchNet, DimeNet).",
            theme="Scalar Invariants",
            assigned_dois=[p1.doi, p2.doi],
            target_word_count=2800,
        )
        sec_gaps = SectionBlueprint(
            section_id="sec-gaps",
            title="4. Open Challenges, Dynamic Conformations, and Benchmarks",
            order=4,
            level=1,
            description="Synthesis of coverage deficiencies, flexible receptor docking, and scaling to whole proteins.",
            theme="Synthesis",
            assigned_dois=[p1.doi, p3.doi],
            target_word_count=2300,
        )

        project.stage_3_planning.artifacts.outline = OutlineStructure(
            title="Equivariant Graph Neural Networks: A Comprehensive Structural Review",
            narrative_arc="Mathematical symmetry foundations -> Tensor product models -> Invariant accelerations -> Open frontiers.",
            sections=[sec_intro, sec_spherical, sec_scalar, sec_gaps],
        )
        project.stage_3_planning.artifacts.section_blueprints = [sec_intro, sec_spherical, sec_scalar, sec_gaps]
        project.stage_3_planning.artifacts.doi_mappings = {
            p1.doi: ["sec-scalar", "sec-gaps"],
            p2.doi: ["sec-scalar"],
            p3.doi: ["sec-spherical", "sec-gaps"],
            p4.doi: ["sec-intro"],
        }

        # -------------------------------------------------------------------
        # Stage 4: Writing
        # -------------------------------------------------------------------
        project.stage_4_writing.meta.status = "in_progress"
        project.stage_4_writing.meta.agent_name = "WriterAgent"
        project.stage_4_writing.meta.progress_percentage = 65.0

        project.stage_4_writing.inputs.target_level = "phd"
        project.stage_4_writing.inputs.tone = "academic"
        project.stage_4_writing.inputs.max_review_iterations = 3
        project.stage_4_writing.inputs.min_approval_score = 0.82

        project.stage_4_writing.artifacts.section_drafts["sec-intro"] = SectionDraft(
            section_id="sec-intro",
            title=sec_intro.title,
            markdown="# Introduction\n\nSymmetries in Euclidean space govern molecular physics...",
            word_count=1840,
            cited_dois=[p4.doi],
            version=2,
        )
        project.stage_4_writing.artifacts.section_drafts["sec-scalar"] = SectionDraft(
            section_id="sec-scalar",
            title=sec_scalar.title,
            markdown="# Coordinate Vector Models\n\nBy parameterizing coordinate offsets directly...",
            word_count=2780,
            cited_dois=[p1.doi, p2.doi],
            version=1,
        )

        project.stage_4_writing.artifacts.section_reviews["sec-intro"] = [
            SectionReview(
                iteration=1,
                approved=True,
                overall_score=0.91,
                scores={"coverage": 0.95, "coherence": 0.90, "synthesis": 0.88},
                feedback=["Excellent geometric framing.", "Clear definition of equivariance vs invariance."],
                missing_citations=[],
            )
        ]
        project.stage_4_writing.artifacts.peer_review_feedback = [
            {"section_id": "sec-intro", "agent": "ReviewerAgent", "score": 0.91, "verdict": "APPROVED"}
        ]
        project.stage_4_writing.artifacts.citation_groundings = {
            p1.doi: {"verified": True, "claim": "EGNN runs 10x faster than TFN without Clebsch-Gordan tensor products."},
            p4.doi: {"verified": True, "claim": "Geometric Deep Learning unifies convolutional and graph operations."},
        }
        project.stage_4_writing.artifacts.full_draft_markdown = (
            "# Equivariant Graph Neural Networks Review\n\n"
            "## 1. Introduction\nSymmetries govern molecular physics...\n\n"
            "## 3. Coordinate Vector Models\nBy parameterizing coordinate offsets directly...\n"
        )
        project.stage_4_writing.artifacts.citation_grounding_verified = True

        # -------------------------------------------------------------------
        # Stage 5: Export
        # -------------------------------------------------------------------
        project.stage_5_export.meta.status = "not_started"
        project.stage_5_export.meta.agent_name = "WriterAgent"
        project.stage_5_export.meta.progress_percentage = 0.0

        project.stage_5_export.inputs.template = "ieee"
        project.stage_5_export.inputs.include_citation_graph = True
        project.stage_5_export.inputs.compile_pdf = False

        project.stage_5_export.artifacts.latex_templates = {
            "preamble": "\\documentclass[journal]{IEEEtran}\n\\usepackage{amsmath,amssymb}",
            "body": "\\section{Introduction}\nSymmetries in Euclidean space...",
        }
        project.stage_5_export.artifacts.bibtex_entries = [
            "@article{satorras2021en,\n  title={E(n) equivariant graph neural networks},\n  author={Satorras, Victor Garcia and Hoogeboom, Emiel and Welling, Max},\n  journal={ICML},\n  year={2021}\n}",
            "@article{schutt2018schnet,\n  title={SchNet: A continuous-filter convolutional neural network for quantum chemistry},\n  author={Sch{\\\"u}tt, Kristof and Sauceda, Huziel and Kindermans, Peter and Tkatchenko, Alexandre and M{\\\"u}ller, Klaus-Robert},\n  journal={J. Chem. Phys.},\n  year={2018}\n}",
        ]
        project.stage_5_export.artifacts.tex_path = "export/review.tex"
        project.stage_5_export.artifacts.bib_path = "export/references.bib"
        project.stage_5_export.artifacts.bibtex_entry_count = 2
        project.stage_5_export.artifacts.tex_section_count = 4

        # -------------------------------------------------------------------
        # Public Message Board: Populate all 6 message types
        # -------------------------------------------------------------------
        for m_type in ("insight", "serendipity", "gap", "warning", "decision", "hypothesis"):
            msg = project.post_message(
                author_agent="ALRSAgent",
                message_type=m_type,
                title=f"Discovered {m_type.upper()} during synthesis",
                content=f"Detailed evidence for {m_type} in equivariant graph literature.",
                stage="stage_2_analysis",
                tags=[m_type, "geometric-dl"],
                related_paper_dois=[p1.doi, p3.doi],
            )
            msg.acknowledge("PlannerAgent")

        return project

    def test_full_lifecycle_roundtrip_fidelity(self, fully_populated_project: ProjectState) -> None:
        """Verify that a project populated across all 5 stages serializes and deserializes without data loss."""
        # 1. Dump to JSON string
        json_str = fully_populated_project.model_dump_json(indent=2)
        assert isinstance(json_str, str)
        assert len(json_str) > 5000

        # 2. Reconstruct via model_validate_json
        reconstructed = ProjectState.model_validate_json(json_str)

        # 3. Verify Root Level
        assert reconstructed.project_id == fully_populated_project.project_id
        assert reconstructed.name == fully_populated_project.name
        assert reconstructed.description == fully_populated_project.description
        assert reconstructed.topic == fully_populated_project.topic
        assert reconstructed.status == "active"
        assert reconstructed.target_level == "phd"
        assert reconstructed.similarity_threshold == 0.68
        assert reconstructed.token_budget == 1500000
        assert reconstructed.tokens_used == 142890
        assert reconstructed.current_stage == "stage_4_writing"

        # 4. Verify Stage 1 (Research)
        s1 = reconstructed.stage_1_research
        assert s1.meta.status == "completed"
        assert s1.meta.progress_percentage == 100.0
        assert len(s1.inputs.research_questions) == 2
        assert len(s1.inputs.seed_dois) == 2
        assert s1.inputs.year_range == (2018, 2025)
        assert len(s1.artifacts.papers) == 4
        assert "10.48550/arxiv.2102.09844" in s1.artifacts.papers
        p1_rec = s1.artifacts.papers["10.48550/arxiv.2102.09844"]
        assert p1_rec.title == "E(n) Equivariant Graph Neural Networks"
        assert p1_rec.authors == ["Victor Garcia Satorras", "Emiel Hoogeboom", "Max Welling"]
        assert p1_rec.citation_count == 1850
        assert len(s1.artifacts.citation_edges) == 3
        assert len(s1.notes) == 1
        assert s1.notes[0].category == "trade_off"

        # 5. Verify Stage 2 (Analysis)
        s2 = reconstructed.stage_2_analysis
        assert s2.meta.status == "completed"
        assert s2.inputs.similarity_weight == 0.65
        assert len(s2.artifacts.clusters) == 2
        assert s2.artifacts.clusters[0].label == "Equivariant Spherical Harmonic Transformers"
        assert len(s2.artifacts.gaps) == 1
        assert s2.artifacts.gaps[0].severity == "critical"
        assert len(s2.artifacts.rankings) == 2
        assert s2.artifacts.rankings[0].rank == 1
        assert s2.artifacts.comparison_matrix is not None
        assert len(s2.artifacts.comparison_matrix.dimensions) == 1
        assert s2.artifacts.comparison_matrix.dimensions[0].dimension_name == "Asymptotic Complexity"

        # 6. Verify Stage 3 (Planning)
        s3 = reconstructed.stage_3_planning
        assert s3.meta.status == "completed"
        assert len(s3.artifacts.outline.sections) == 4
        assert s3.artifacts.outline.sections[0].title == "1. Introduction & Geometric Preliminaries"
        assert s3.artifacts.outline.sections[1].target_word_count == 2600
        assert len(s3.artifacts.doi_mappings) == 4

        # 7. Verify Stage 4 (Writing)
        s4 = reconstructed.stage_4_writing
        assert s4.meta.status == "in_progress"
        assert s4.meta.progress_percentage == 65.0
        assert len(s4.artifacts.section_drafts) == 2
        assert s4.artifacts.section_drafts["sec-intro"].version == 2
        assert len(s4.artifacts.section_reviews["sec-intro"]) == 1
        assert s4.artifacts.section_reviews["sec-intro"][0].overall_score == 0.91
        assert s4.artifacts.citation_grounding_verified is True

        # 8. Verify Stage 5 (Export)
        s5 = reconstructed.stage_5_export
        assert s5.meta.status == "not_started"
        assert len(s5.artifacts.bibtex_entries) == 2
        assert s5.artifacts.tex_path == "export/review.tex"
        assert s5.artifacts.bibtex_entry_count == 2

        # 9. Verify Message Board
        assert len(reconstructed.message_board) == 6
        for msg in reconstructed.message_board:
            assert "PlannerAgent" in msg.acknowledged_by
            assert msg.related_paper_dois == ["10.48550/arxiv.2102.09844", "10.5555/3524938.3525120"]

    def test_post_roundtrip_methods_and_dot_path_integrity(self, fully_populated_project: ProjectState) -> None:
        """Verify helper methods, dot-path queries, and mutations continue to function normally on reconstructed state."""
        reconstructed = ProjectState.model_validate_json(fully_populated_project.model_dump_json())

        # Test dot-path navigation into deep objects
        intro_words = reconstructed.get_by_dot_path("stage_3_planning.artifacts.outline.sections.0.target_word_count")
        assert intro_words == 1800

        # Query compound DOI with slashes and dots
        paper_venue = reconstructed.get_by_dot_path(
            "stage_1_research.artifacts.papers.10.48550/arxiv.2102.09844.venue"
        )
        assert paper_venue == "ICML 2021"

        # Query comparison dimension
        dimension_name = reconstructed.get_by_dot_path(
            "stage_2_analysis.artifacts.comparison_matrix.dimensions.0.dimension_name"
        )
        assert dimension_name == "Asymptotic Complexity"

        # Test summary generation
        summary = reconstructed.get_summary()
        assert summary["name"] == fully_populated_project.name
        assert summary["stages"]["stage_1_research"]["paper_count"] == 4
        assert summary["stages"]["stage_2_analysis"]["clusters_count"] == 2
        assert summary["stages"]["stage_3_planning"]["section_count"] == 4
        assert summary["stages"]["stage_4_writing"]["drafted_sections"] == 2
        assert summary["stages"]["stage_5_export"]["has_tex"] is True
        assert summary["message_board_total"] == 6

        # Test mutating reconstructed state via update_stage_quadrant
        reconstructed.update_stage_quadrant(
            stage="stage_4_writing",
            quadrant="meta",
            data={"progress_percentage": 90.0, "status": "in_progress"},
        )
        assert reconstructed.stage_4_writing.meta.progress_percentage == 90.0

        # Test posting and acknowledging message on reconstructed state
        new_msg = reconstructed.post_message(
            author_agent="WriterAgent",
            message_type="decision",
            title="Adopted Unified IEEE Notation",
            content="Standardized all coordinate vectors as bold lowercase x_i.",
        )
        assert len(reconstructed.message_board) == 7
        ack_success = reconstructed.acknowledge_message(new_msg.id, "LeadAgent")
        assert ack_success is True
        assert "LeadAgent" in new_msg.acknowledged_by


# ===========================================================================
# 3. Public Message Board Stress Operations & Invariants
# ===========================================================================

class TestMessageBoardOperationsAdversarial:
    """Stress test public message board with high volume, duplicate DOIs, multi-agent acknowledgments, and state touches."""

    def test_high_volume_multi_agent_message_stream(self) -> None:
        """Simulate high volume (60+) cross-agent messages across multiple stages."""
        project = ProjectState(name="Message Stream Concurrency Project")
        agents = ["ALRSAgent", "GapFinderAgent", "PlannerAgent", "WriterAgent", "ReviewerAgent"]
        classifications: list[BoardClassification] = ["insight", "serendipity", "gap", "warning", "decision", "hypothesis"]

        message_ids: set[str] = set()

        for i in range(60):
            agent = agents[i % len(agents)]
            cls_type = classifications[i % len(classifications)]
            stage_name = f"stage_{(i % 5) + 1}_test"

            msg = project.post_message(
                author_agent=agent,
                message_type=cls_type,
                title=f"Message #{i:03d} by {agent}",
                content=f"Discovery body {i} with cross-cutting implications.",
                stage=stage_name,
                tags=[f"tag_{i}", agent.lower()],
                related_paper_dois=[f"10.1145/{1000 + i}"],
            )
            assert msg.id not in message_ids
            message_ids.add(msg.id)

        assert len(project.message_board) == 60
        assert len(message_ids) == 60

        # Verify ordering is preserved
        for i, msg in enumerate(project.message_board):
            assert msg.title == f"Message #{i:03d} by {agents[i % len(agents)]}"

    def test_duplicate_and_messy_dois_in_single_and_multiple_messages(self) -> None:
        """Verify handling of redundant, duplicate, and unnormalized DOIs."""
        project = ProjectState(name="Messy DOI Test")

        # 1. Single message with redundant duplicate DOIs across different resolver formats
        msg = project.post_message(
            author_agent="ALRSAgent",
            message_type="insight",
            title="Redundant DOIs in Single Post",
            content="Message referencing the same paper 4 different ways.",
            related_paper_dois=[
                "10.1145/3292500.3330964",
                "https://doi.org/10.1145/3292500.3330964",
                "http://dx.doi.org/10.1145/3292500.3330964",
                "  DOI: 10.1145/3292500.3330964  ",
                "10.1016/j.artint.2020.103342",
            ],
        )

        # All resolver formats must normalize to the canonical lowercase string
        assert all(doi.startswith("10.") for doi in msg.related_paper_dois)
        assert msg.related_paper_dois.count("10.1145/3292500.3330964") >= 1

        # 2. Multiple independent messages referencing the exact same canonical DOI
        canonical_doi = "10.1145/3292500.3330964"
        msg2 = project.post_message(
            author_agent="PlannerAgent",
            message_type="decision",
            title="Allocate Survey Paper to Section 1",
            content="Assigning Bronstein survey.",
            related_paper_dois=[canonical_doi],
        )
        msg3 = project.post_message(
            author_agent="WriterAgent",
            message_type="warning",
            title="Check Citation Context for Bronstein",
            content="Verify definition of Gauge symmetry.",
            related_paper_dois=[canonical_doi],
        )

        # Query messages referencing this DOI
        matching = [m for m in project.message_board if canonical_doi in m.related_paper_dois]
        assert len(matching) >= 3

    def test_multi_agent_acknowledgment_and_idempotency(self) -> None:
        """Verify multiple agents acknowledging the same message and idempotent duplicate acks."""
        project = ProjectState(name="Ack Workflow Test")
        msg = project.post_message(
            author_agent="GapFinderAgent",
            message_type="gap",
            title="Critical Evaluation Gap Detected",
            content="Need benchmark on inductive graph classification.",
        )

        # 1. Initial state: unacknowledged
        assert len(msg.acknowledged_by) == 0
        assert not msg.is_acknowledged_by("PlannerAgent")

        # Record timestamp before ack
        t_before = project.updated_at

        # 2. Agent 1 acknowledges
        success1 = project.acknowledge_message(msg.id, "PlannerAgent")
        assert success1 is True
        assert msg.acknowledged_by == ["PlannerAgent"]
        assert msg.is_acknowledged_by("PlannerAgent")
        assert project.updated_at >= t_before

        # 3. Agent 1 acknowledges AGAIN (idempotency check)
        t_after_first = project.updated_at
        success1_dup = project.acknowledge_message(msg.id, "PlannerAgent")
        assert success1_dup is True
        assert msg.acknowledged_by == ["PlannerAgent"]  # No duplicate element added!

        # 4. Agent 2 acknowledges
        success2 = project.acknowledge_message(msg.id, "WriterAgent")
        assert success2 is True
        assert msg.acknowledged_by == ["PlannerAgent", "WriterAgent"]

        # 5. Agent 3 acknowledges
        success3 = project.acknowledge_message(msg.id, "ReviewerAgent")
        assert success3 is True
        assert msg.acknowledged_by == ["PlannerAgent", "WriterAgent", "ReviewerAgent"]

        # 6. Acknowledging invalid UUID returns False and does not alter board
        bad_ack = project.acknowledge_message(str(uuid.uuid4()), "PlannerAgent")
        assert bad_ack is False
        assert msg.acknowledged_by == ["PlannerAgent", "WriterAgent", "ReviewerAgent"]

    def test_direct_board_message_acknowledge_method(self) -> None:
        """Verify BoardMessage.acknowledge() unit method directly."""
        msg = BoardMessage(
            author_agent="System",
            message_type="warning",
            title="Resource Pressure",
            content="Token budget 80% consumed.",
        )
        msg.acknowledge("ProjectAgent")
        assert msg.acknowledged_by == ["ProjectAgent"]
        # Redundant acknowledgment should be no-op
        msg.acknowledge("ProjectAgent")
        assert msg.acknowledged_by == ["ProjectAgent"]
        msg.acknowledge("ResearchAgent")
        assert msg.acknowledged_by == ["ProjectAgent", "ResearchAgent"]


# ===========================================================================
# 4. Defensive Boundary Conditions & Error Contracts
# ===========================================================================

class TestDefensiveBoundariesAndContracts:
    """Adversarially probe boundary conditions, edge cases, and helper method exceptions."""

    def test_normalize_doi_extreme_inputs(self) -> None:
        """Verify normalize_doi behaves safely on bizarre, null, or extreme inputs."""
        assert normalize_doi(None) == ""
        assert normalize_doi("") == ""
        assert normalize_doi("   ") == ""
        assert normalize_doi("///") == ""
        assert normalize_doi("https://doi.org/") == ""
        assert normalize_doi("http://dx.doi.org/") == ""
        assert normalize_doi("doi:") == ""
        assert normalize_doi("DOI:   10.1000/182   ") == "10.1000/182"
        assert normalize_doi("https://doi.org/10.1000/182#page=1") == "10.1000/182#page=1"

    def test_normalize_stage_name_coverage(self) -> None:
        """Verify alias normalization across numeric, short, and canonical stage names."""
        for alias, expected in [
            ("1", "stage_1_research"),
            ("stage_1", "stage_1_research"),
            ("research", "stage_1_research"),
            ("stage_1_research", "stage_1_research"),
            ("2", "stage_2_analysis"),
            ("stage_2", "stage_2_analysis"),
            ("analysis", "stage_2_analysis"),
            ("stage_2_analysis", "stage_2_analysis"),
            ("3", "stage_3_planning"),
            ("stage_3", "stage_3_planning"),
            ("planning", "stage_3_planning"),
            ("stage_3_planning", "stage_3_planning"),
            ("4", "stage_4_writing"),
            ("stage_4", "stage_4_writing"),
            ("writing", "stage_4_writing"),
            ("stage_4_writing", "stage_4_writing"),
            ("5", "stage_5_export"),
            ("stage_5", "stage_5_export"),
            ("export", "stage_5_export"),
            ("stage_5_export", "stage_5_export"),
        ]:
            assert normalize_stage_name(alias) == expected
            assert normalize_stage_name(alias.upper()) == expected

    def test_get_by_dot_path_exception_contracts(self) -> None:
        """Verify exact exception types raised by get_by_dot_path on bad paths."""
        project = ProjectState(name="Contract Test")

        # 1. Non-existent field on BaseModel -> KeyError
        with pytest.raises(KeyError) as exc_attr:
            project.get_by_dot_path("stage_1_research.meta.non_existent_field")
        assert "not found" in str(exc_attr.value)

        # 2. Non-existent key in dict -> KeyError
        with pytest.raises(KeyError) as exc_dict:
            project.get_by_dot_path("stage_1_research.artifacts.papers.missing_doi")
        assert "not found in dict" in str(exc_dict.value)

        # 3. Non-integer index into list -> ValueError
        with pytest.raises(ValueError) as exc_list_nan:
            project.get_by_dot_path("stage_1_research.inputs.research_questions.not_a_number")
        assert "Cannot index list with non-integer" in str(exc_list_nan.value)

        # 4. Out of bounds index into list -> IndexError
        with pytest.raises(IndexError) as exc_list_oob:
            project.get_by_dot_path("stage_1_research.inputs.research_questions.999")
        assert "out of range" in str(exc_list_oob.value)

        # 5. Traversal through scalar primitive -> TypeError
        with pytest.raises(TypeError) as exc_scalar:
            project.get_by_dot_path("name.sub_token")
        assert "Cannot traverse into scalar value" in str(exc_scalar.value)

    def test_update_stage_quadrant_notes_variants(self) -> None:
        """Verify update_stage_quadrant handles various note formats (list of StageNote, list of dicts, strings)."""
        project = ProjectState(name="Notes Variant Test")

        # 1. List of StageNote objects
        project.update_stage_quadrant(
            stage="stage_1_research",
            quadrant="notes",
            data=[StageNote(author="AgentA", content="Note A")],
        )
        assert len(project.stage_1_research.notes) == 1
        assert project.stage_1_research.notes[0].content == "Note A"

        # 2. List of raw dicts
        project.update_stage_quadrant(
            stage="stage_1_research",
            quadrant="notes",
            data=[{"author": "AgentB", "content": "Note B"}],
        )
        assert len(project.stage_1_research.notes) == 2
        assert project.stage_1_research.notes[1].content == "Note B"

        # 3. List of strings (auto-wrapped)
        project.update_stage_quadrant(
            stage="stage_1_research",
            quadrant="notes",
            data=["Direct note string"],
        )
        assert len(project.stage_1_research.notes) == 3
        assert project.stage_1_research.notes[2].content == "Direct note string"

        # 4. Dict with single note content
        project.update_stage_quadrant(
            stage="stage_1_research",
            quadrant="notes",
            data={"author": "AgentD", "content": "Note D from dict"},
        )
        assert len(project.stage_1_research.notes) == 4
        assert project.stage_1_research.notes[3].content == "Note D from dict"

    def test_update_stage_quadrant_invalid_types_raise_type_error(self) -> None:
        """Verify update_stage_quadrant rejects non-dict data for meta/inputs/artifacts."""
        project = ProjectState(name="Type Error Test")

        with pytest.raises(TypeError) as exc:
            project.update_stage_quadrant(
                stage="stage_1_research",
                quadrant="inputs",
                data=["not", "a", "dict"],  # type: ignore[arg-type]
            )
        assert "must be a dict" in str(exc.value)


# ===========================================================================
# 5. Empirical Proofs of Discovered Vulnerabilities & Performance Benchmarks
# ===========================================================================

class TestDiscoveredVulnerabilitiesAndFindings:
    """Empirical demonstrations of identified edge-case bugs, schema drifts, and performance limits."""

    def test_empirical_proof_of_assignment_validation_bypass(self) -> None:
        """Finding 1: update_stage_quadrant allows assigning out-of-range values because validate_assignment=True is missing.
        
        The invalid mutated state serializes cleanly, but when subsequently reloaded with model_validate_json,
        it crashes with ValidationError, rendering disk/MySQL persistence corrupted and unrecoverable.
        """
        project = ProjectState(name="Assignment Bypass Test")

        # Directly setting progress_percentage=500.0 via update_stage_quadrant succeeds in-memory
        project.update_stage_quadrant(
            stage="stage_1_research",
            quadrant="meta",
            data={"progress_percentage": 500.0},
        )
        assert project.stage_1_research.meta.progress_percentage == 500.0

        # It also dumps to JSON without error
        corrupted_json = project.model_dump_json()

        # BUT when loaded back by the persistence layer (load_state / model_validate_json), it fails!
        with pytest.raises(ValidationError) as exc:
            ProjectState.model_validate_json(corrupted_json)
        assert "progress_percentage" in str(exc.value)
        assert "less than or equal to 100" in str(exc.value)

    def test_empirical_proof_of_id_alias_model_extra_injection(self) -> None:
        """Finding 2: handle_project_id_alias injects 'id' into model_extra because 'id' is a property, not a field.
        
        This introduces a schema asymmetry: original.model_dump() does NOT contain 'id', but
        reconstructed.model_dump() DOES contain 'id' as an extra field in model_extra.
        """
        project = ProjectState(name="ID Alias Schema Drift Test")
        dump_initial = project.model_dump()
        assert "id" not in dump_initial
        assert project.model_extra == {}

        # First JSON roundtrip
        json_str = project.model_dump_json()
        reconstructed = ProjectState.model_validate_json(json_str)

        dump_reconstructed = reconstructed.model_dump()
        assert "id" in dump_reconstructed  # Injected into model_extra!
        assert reconstructed.model_extra == {"id": project.project_id}

    def test_duplicate_dois_not_deduplicated_in_related_paper_dois(self) -> None:
        """Finding 3: clean_related_paper_dois normalizes DOIs but does NOT deduplicate them.
        
        Passing redundant or duplicate DOIs leaves duplicates in related_paper_dois.
        """
        msg = BoardMessage(
            author_agent="ALRSAgent",
            message_type="insight",
            title="Duplicate DOIs",
            content="Testing duplicate DOIs in list.",
            related_paper_dois=[
                "10.1145/3292500.3330964",
                "https://doi.org/10.1145/3292500.3330964",
                "http://dx.doi.org/10.1145/3292500.3330964",
            ],
        )
        # All three normalize to the exact same canonical string, but are not deduplicated
        assert len(msg.related_paper_dois) == 3
        assert msg.related_paper_dois == [
            "10.1145/3292500.3330964",
            "10.1145/3292500.3330964",
            "10.1145/3292500.3330964",
        ]

    def test_large_scale_state_performance_and_payload_limits(self) -> None:
        """Stress test roundtrip throughput with 200 papers, 199 edges, and 50 messages."""
        import time

        project = ProjectState(name="Stress Performance Review")
        for i in range(200):
            doi = f"10.1145/{i:06d}"
            project.stage_1_research.artifacts.papers[doi] = PaperMetadata(
                doi=doi,
                title=f"Paper Title {i}",
                authors=[f"Author {i}A", f"Author {i}B"],
                year=2020 + (i % 5),
                citation_count=i * 10,
            )
            if i > 0:
                project.stage_1_research.artifacts.citation_edges.append((f"10.1145/{i-1:06d}", doi))

        for i in range(50):
            project.post_message(
                author_agent="AgentA",
                message_type="insight",
                title=f"Insight {i}",
                content=f"Content {i}",
                related_paper_dois=[f"10.1145/{i:06d}"],
            )

        t0 = time.perf_counter()
        raw = project.model_dump_json()
        dump_ms = (time.perf_counter() - t0) * 1000

        t1 = time.perf_counter()
        reconstructed = ProjectState.model_validate_json(raw)
        load_ms = (time.perf_counter() - t1) * 1000

        assert len(reconstructed.stage_1_research.artifacts.papers) == 200
        assert len(reconstructed.stage_1_research.artifacts.citation_edges) == 199
        assert len(reconstructed.message_board) == 50
        # Performance budget: serialize and deserialize in under 100ms
        assert dump_ms < 100.0, f"model_dump_json took {dump_ms:.2f}ms (expected < 100ms)"
        assert load_ms < 100.0, f"model_validate_json took {load_ms:.2f}ms (expected < 100ms)"


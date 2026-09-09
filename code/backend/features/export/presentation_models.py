"""Domain models, enums, and request/response schemas for Presentation Deck Generation.

Complies with Constitution v2.2.1 (C7 static typing, C9 sub-25 line functions,
A28 typed ADK tool contracts, A37 zero citation hallucination).
"""
from __future__ import annotations

from enum import Enum
from typing import Any
from pydantic import BaseModel, ConfigDict, Field, model_validator


class PresentationAudienceProfile(str, Enum):
    """Target audience profile steering slide content depth and tone."""
    SUPERVISOR = "supervisor"
    THESIS_DEFENSE = "thesis_defense"
    SEMINAR = "seminar"
    QUICK_STATUS = "quick_status"


class PresentationTheme(str, Enum):
    """Visual theme applied to the rendered HTML deck."""
    DARK = "dark"
    LIGHT = "light"


class SlideLayoutType(str, Enum):
    """Structural layout archetypes for slide rendering."""
    TITLE = "title"
    SPLIT_METRICS = "split_metrics"
    FUNNEL_DIAGRAM = "funnel_diagram"
    ARCHITECTURE_SWARM = "architecture_swarm"
    MATRIX_TABLE = "matrix_table"
    CITATION_NETWORK = "citation_network"
    GAP_RADAR = "gap_radar"
    TWO_COLUMN_CARDS = "two_column_cards"
    FINDINGS_GRID = "findings_grid"
    ROADMAP_TIMELINE = "roadmap_timeline"
    QA_DISCUSSION = "qa_discussion"


class PresentationErrorCode(str, Enum):
    """Deterministic error codes conforming to Constitution A28."""
    PROJECT_NOT_FOUND = "PROJECT_NOT_FOUND"
    EMPTY_LIBRARY_WARNING = "EMPTY_LIBRARY_WARNING"
    UNINITIALIZED_GRAPH = "UNINITIALIZED_GRAPH"
    GROUNDING_VERIFICATION_FAILED = "GROUNDING_VERIFICATION_FAILED"
    INVALID_SLIDE_RANGE = "INVALID_SLIDE_RANGE"
    PERSISTENCE_ERROR = "PERSISTENCE_ERROR"


class PresentationErrorDetail(BaseModel):
    """Structured error payload conforming to fail-loud error taxonomy."""
    model_config = ConfigDict(frozen=True)

    code: PresentationErrorCode = Field(..., description="Deterministic error classification code")
    message: str = Field(..., description="Human-readable explanation of the error condition")
    details: dict[str, Any] = Field(default_factory=dict, description="Contextual error diagnostics")
    recovery_guidance: str = Field(..., description="Actionable instruction on how to remediate the error")


class ResearchQuestionFact(BaseModel):
    """Verified research question extracted directly from Neo4j."""
    model_config = ConfigDict(frozen=True)

    question_id: str = Field(..., description="Unique UUID of the research question")
    rq_id: str = Field(..., description="Backward-compatible alias for question_id")
    text: str = Field(default="", description="Primary research question text")
    finer_text: str = Field(..., description="FINER formatted research question string")
    coverage_score: float = Field(..., ge=0.0, le=1.0, description="Semantic coverage score C(RQ_i)")
    status: str = Field(..., description="Status: 'grounded' or 'open_frontier'")
    grounded_paper_count: int = Field(..., ge=0, description="Number of supporting papers in Neo4j")


class ScientometricFacts(BaseModel):
    """Deterministically aggregated literature metrics from Neo4j."""
    model_config = ConfigDict(frozen=True)

    total_papers: int = Field(..., ge=0, description="Total indexed papers in campaign")
    total_citations: int = Field(..., ge=0, description="Cumulative citation count")
    unique_authors: int = Field(..., ge=0, description="Unique author count in citation graph")
    year_distribution: dict[int, int] = Field(..., description="Map of publication year to paper count")
    top_venues: list[dict[str, Any]] = Field(..., description="Top publication venues ranked by paper volume")
    top_authors: list[dict[str, Any]] = Field(..., description="Top authors ranked by publication frequency")
    landmark_papers: list[dict[str, Any]] = Field(..., description="Top papers ranked by PageRank / centrality")


class SynthesisMatrixFact(BaseModel):
    """Approved section synthesis matrix extracted from Neo4j."""
    model_config = ConfigDict(frozen=True)

    section_id: str = Field(..., description="Target outline section UUID")
    section_title: str = Field(..., description="Title of the review section")
    dimensions: list[str] = Field(..., description="Analytical comparison dimensions")
    matrix_markdown: str = Field(..., description="Rendered markdown table of synthesis evidence")
    paper_count: int = Field(..., ge=0, description="Count of reviewed papers in this matrix")


class SvplPathwayFact(BaseModel):
    """Discovered multi-hop citation bridge between seminal papers."""
    model_config = ConfigDict(frozen=True)

    from_doi: str = Field(..., description="Source seminal paper canonical DOI")
    to_doi: str = Field(..., description="Target seminal paper canonical DOI")
    intermediate_dois: list[str] = Field(default_factory=list, description="Bridge paper canonical DOIs along the path")
    bridge_mechanism: str = Field(default="direct", description="Mechanism: direct, co_citation, coupling, steiner")
    hop_count: int = Field(..., ge=1, le=3, description="Path distance in hops")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Bridge confidence score")


class ProjectEpistemicFacts(BaseModel):
    """Consolidated ground-truth facts extracted from Neo4j for slide generation."""
    model_config = ConfigDict(frozen=True)

    project_id: str = Field(..., description="Project UUID in Neo4j")
    project_name: str = Field(..., description="Human-readable project title")
    domain: str = Field(..., description="Academic domain or research discipline")
    description: str = Field(..., description="Project description or thesis scope")
    creation_date: str = Field(..., description="ISO 8601 creation timestamp")
    workflow_stage: str = Field(..., description="Current campaign workflow stage")
    research_questions: list[ResearchQuestionFact] = Field(default_factory=list)
    scientometrics: ScientometricFacts
    synthesis_matrices: list[SynthesisMatrixFact] = Field(default_factory=list)
    svpl_pathways: list[SvplPathwayFact] = Field(default_factory=list)
    empty_library_warning: bool = Field(default=False, description="Flag indicating zero-paper scoping deck fallback")


class PresenterQuestionAnswer(BaseModel):
    """Anticipated supervisor / committee question with verified rebuttal."""
    model_config = ConfigDict(frozen=True)

    question: str = Field(..., description="Anticipated challenging technical question")
    model_answer: str = Field(..., description="Suggested graph-grounded answer / rebuttal")


class PresenterNotes(BaseModel):
    """Structured speaker guidance attached to each slide."""
    model_config = ConfigDict(frozen=True)

    talking_points: list[str] = Field(..., min_length=1, description="3-5 bulleted speaker talking points")
    estimated_duration_seconds: int = Field(..., ge=30, le=300, description="Estimated speaking time (seconds)")
    anticipated_questions: list[PresenterQuestionAnswer] = Field(default_factory=list)


class PresentationSlide(BaseModel):
    """Structured representation of an individual presentation slide."""
    model_config = ConfigDict(frozen=True)

    slide_id: str = Field(..., description="Unique slide identifier (UUID)")
    index: int = Field(..., ge=1, description="1-indexed sequence position")
    title: str = Field(..., min_length=3, description="Slide heading text")
    category: str = Field(..., min_length=2, description="Context category badge")
    layout_type: SlideLayoutType = Field(..., description="Slide structural archetype")
    content_html: str = Field(..., description="Sanitized, self-contained HTML body for the slide")
    presenter_notes: PresenterNotes = Field(..., description="Contextual speaker notes")
    grounding_provenance: list[str] = Field(default_factory=list, description="List of verified Neo4j DOIs/IDs")


class SlideGroundingCriticReport(BaseModel):
    """Structured critique emitted by SlideGroundingCritic evaluating grounding."""
    model_config = ConfigDict(frozen=True)

    is_grounded: bool = Field(..., description="True if CHR == 0.0% and all metrics match Neo4j")
    measured_chr: float = Field(..., ge=0.0, le=100.0, description="Measured Citation Hallucination Rate")
    composite_score: float = Field(..., ge=0.0, le=1.0, description="Weighted multi-criteria rubric score")
    dimension_scores: dict[str, float] = Field(..., description="Breakdown across d1, d2, d3, d4")
    violations: list[str] = Field(default_factory=list, description="Explicit factual discrepancy items")
    actionable_directives: list[str] = Field(default_factory=list, description="Corrective directives for builder")

    @model_validator(mode="after")
    def verify_chr_and_grounding(self) -> "SlideGroundingCriticReport":
        """Enforces hard constraint: is_grounded cannot be True if measured_chr > 0.0%."""
        if self.measured_chr > 0.0 and self.is_grounded:
            raise ValueError(
                f"Zero Hallucination Invariant Violated: is_grounded cannot be True when measured_chr ({self.measured_chr}%) > 0.0%"
            )
        if len(self.violations) > 0 and self.is_grounded:
            raise ValueError(
                f"Grounding Invariant Violated: is_grounded cannot be True when violations exist ({len(self.violations)} detected)"
            )
        return self


class PresentationDeckRequest(BaseModel):
    """Input payload for presentation deck generation."""
    model_config = ConfigDict(frozen=True)

    project_id: str = Field(..., description="Target project UUID")
    audience_profile: PresentationAudienceProfile = Field(
        default=PresentationAudienceProfile.SUPERVISOR,
        description="Target audience profile",
    )
    target_slide_count: int = Field(
        default=12,
        ge=8,
        le=20,
        description="Desired slide count (constrained between 8 and 20)",
    )
    theme: PresentationTheme = Field(
        default=PresentationTheme.DARK,
        description="Default visual color theme",
    )
    enable_mermaid: bool = Field(
        default=True,
        description="Whether to bundle and initialize inline Mermaid.js diagrams",
    )
    included_topics: list[str] | None = Field(
        default=None,
        description="Optional list of specific section keys to prioritize",
    )


class PresentationDeckResponse(BaseModel):
    """Response payload returned upon tool or API execution."""
    model_config = ConfigDict(frozen=True)

    success: bool = Field(..., description="True if generation succeeded and passed verification")
    file_path: str = Field(..., description="Absolute filesystem path to the generated HTML deck")
    slide_count: int = Field(..., ge=0, description="Total count of rendered slides")
    generated_timestamp: str = Field(..., description="ISO 8601 generation timestamp")
    facts_verified_count: int = Field(..., ge=0, description="Total verified facts and citations grounded")
    preview_html: str = Field(..., description="Sanitized HTML preview snippet of Slide 1")
    sha256_hash: str = Field(..., description="Cryptographic SHA-256 fingerprint of the HTML file")
    error: PresentationErrorDetail | None = Field(default=None, description="Error details if success is False")


class PresentationDeckArtifact(BaseModel):
    """Persistent database record of a generated presentation deck."""
    model_config = ConfigDict(frozen=True)

    artifact_id: str = Field(..., description="Unique deck artifact UUID")
    project_id: str = Field(..., description="Parent project UUID")
    filename: str = Field(..., description="Filename (e.g. presentation_20260909_180000.html)")
    file_path: str = Field(..., description="Absolute path on filesystem")
    file_size_bytes: int = Field(..., ge=0, description="File size on disk in bytes")
    sha256_hash: str = Field(..., description="SHA-256 fingerprint")
    slide_count: int = Field(..., ge=1, description="Number of slides in deck")
    audience_profile: str = Field(..., description="Target audience profile")
    theme: str = Field(..., description="Default theme")
    facts_verified_count: int = Field(..., ge=0, description="Total grounded facts verified")
    created_at: str = Field(..., description="ISO 8601 creation timestamp")


class PresentationAgentConfig(BaseModel):
    """Google ADK agent definition and configuration model."""
    model_config = ConfigDict(frozen=True)

    agent_name: str = Field(default="PresentationAgent", description="Canonical ADK agent identifier")
    role: str = Field(default="PresentationDeckGenerator", description="Functional system role")
    critic_agent: str = Field(default="SlideGroundingCritic", description="Paired adversarial auditor")
    model_name: str = Field(default="gemini-2.5-flash", description="Underlying Gemini LLM model")
    temperature: float = Field(default=0.1, ge=0.0, le=1.0, description="Low temperature for high factual fidelity")
    bound_tools: list[str] = Field(
        default_factory=lambda: ["generate_presentation_deck_tool", "get_project_state"],
        description="Bound Google ADK tool names",
    )


class AuditSlideGroundingRequest(BaseModel):
    """Input payload for adversarial slide grounding audit tool."""
    model_config = ConfigDict(frozen=True)

    project_id: str = Field(..., description="The unique UUID or identifier slug of the research project campaign.")
    slides: list[PresentationSlide] = Field(..., description="Draft list of synthesized presentation slides to be verified.")

"""Authoritative Pydantic v2 schemas for Unified ProjectState, 4-Quadrant Substates,
and the Public Message Board.

Implements requirements R2 & R3 for the Agentic Literature Review System (ALRS v2).
"""
from __future__ import annotations

import copy
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Generic, Literal, TypeVar
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# Common Primitives & Utilities
# ---------------------------------------------------------------------------

def utc_now() -> datetime:
    """Return current UTC timestamp with timezone."""
    return datetime.now(timezone.utc)


def normalize_doi(doi: str | None) -> str:
    """Normalize DOI string by stripping URL prefixes, resolvers, and whitespace.

    Examples:
        - "https://doi.org/10.1145/3292500.3330964" -> "10.1145/3292500.3330964"
        - "http://dx.doi.org/10.1016/j.artint.2020.103342" -> "10.1016/j.artint.2020.103342"
        - "doi: 10.1109/TKDE.2021.3060000" -> "10.1109/tkde.2021.3060000"
        - "  10.1000/182  " -> "10.1000/182"
    """
    if not doi:
        return ""
    clean = str(doi).strip()
    clean = re.sub(r"^https?://(dx\.)?doi\.org/", "", clean, flags=re.IGNORECASE)
    clean = re.sub(r"^doi:\s*", "", clean, flags=re.IGNORECASE)
    clean = clean.lstrip("/")
    return clean.strip().lower()


def normalize_stage_name(stage: str) -> str:
    """Map common stage aliases or indices to the canonical stage attribute name."""
    s = stage.strip().lower()
    mapping = {
        "1": "stage_1_research",
        "stage_1": "stage_1_research",
        "research": "stage_1_research",
        "stage_1_research": "stage_1_research",
        "2": "stage_2_analysis",
        "stage_2": "stage_2_analysis",
        "analysis": "stage_2_analysis",
        "stage_2_analysis": "stage_2_analysis",
        "3": "stage_3_planning",
        "stage_3": "stage_3_planning",
        "planning": "stage_3_planning",
        "stage_3_planning": "stage_3_planning",
        "4": "stage_4_writing",
        "stage_4": "stage_4_writing",
        "writing": "stage_4_writing",
        "stage_4_writing": "stage_4_writing",
        "5": "stage_5_export",
        "stage_5": "stage_5_export",
        "export": "stage_5_export",
        "stage_5_export": "stage_5_export",
    }
    return mapping.get(s, s)


def deep_merge(target: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge source dictionary into target dictionary in-place.

    Nested dicts are merged recursively. Scalar values in source overwrite
    target values, and new keys are added. Lists in source replace target lists.
    """
    for key, value in source.items():
        if key in target and isinstance(target[key], dict) and isinstance(value, dict):
            deep_merge(target[key], value)
        else:
            target[key] = copy.deepcopy(value)
    return target


StageStatus = Literal["not_started", "in_progress", "completed", "failed", "paused"]
WorkflowStageName = Literal[
    "stage_1_research",
    "stage_2_analysis",
    "stage_3_planning",
    "stage_4_writing",
    "stage_5_export",
]


# ---------------------------------------------------------------------------
# Quadrants Topology (The 4 Quadrants: Meta, Inputs, Artifacts, Notes)
# ---------------------------------------------------------------------------

class StageMeta(BaseModel):
    """Q1: Operational metadata for any workflow stage."""
    model_config = ConfigDict(extra="allow")

    status: StageStatus = Field(default="not_started", description="Current execution state")
    agent_name: str = Field(default="", description="Primary agent responsible for this stage")
    started_at: datetime | None = Field(default=None, description="Timestamp when stage commenced")
    completed_at: datetime | None = Field(default=None, description="Timestamp when stage concluded")
    updated_at: datetime = Field(default_factory=utc_now, description="Timestamp of latest mutation")
    progress_percentage: float = Field(default=0.0, ge=0.0, le=100.0, description="Estimated completion percentage")
    iteration_count: int = Field(default=0, ge=0, description="Iteration or retry counter")
    error_message: str | None = Field(default=None, description="Last error message if status is failed")

    @field_validator("status", mode="before")
    @classmethod
    def _normalize_status(cls, v: Any) -> Any:
        if isinstance(v, str):
            clean = v.strip().lower()
            if clean in ("pending", "not-started", "notstarted"):
                return "not_started"
            if clean in ("in-progress", "inprogress", "running"):
                return "in_progress"
            if clean in ("done", "complete", "finished"):
                return "completed"
            return clean
        return v


class StageNote(BaseModel):
    """Q4: Qualitative note, scratchpad reflection, or caveat recorded by an agent."""
    model_config = ConfigDict(extra="allow")

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Note UUID")
    timestamp: datetime = Field(default_factory=utc_now, description="UTC creation timestamp")
    author: str = Field(..., description="Agent or user who recorded the note")
    category: str = Field(default="general", description="Category: e.g. trade_off, caveat, observation")
    content: str = Field(..., min_length=1, description="Textual markdown content of the note")
    tags: list[str] = Field(default_factory=list, description="Categorical tags")


MetaT = TypeVar("MetaT", bound=StageMeta)
InputsT = TypeVar("InputsT", bound=BaseModel)
ArtifactsT = TypeVar("ArtifactsT", bound=BaseModel)
NotesT = TypeVar("NotesT", bound=list[StageNote])


class StageSubstate(BaseModel, Generic[MetaT, InputsT, ArtifactsT, NotesT]):
    """Generic 4-quadrant container enforcing topology across all workflow stages."""
    model_config = ConfigDict(extra="allow")

    meta: MetaT
    inputs: InputsT
    artifacts: ArtifactsT
    notes: NotesT = Field(default_factory=list)  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Stage 1: Research (Discovery, Crawling, Seed Papers, Paper Library)
# ---------------------------------------------------------------------------

class PaperMetadata(BaseModel):
    """Domain model for a discovered academic paper."""
    model_config = ConfigDict(extra="allow")

    doi: str = Field(..., description="Normalized DOI identifier")
    title: str = Field(..., description="Paper title")
    authors: list[str] = Field(default_factory=list, description="Author names")
    year: int | None = Field(default=None, description="Publication year")
    venue: str | None = Field(default=None, description="Journal or conference venue")
    abstract: str | None = Field(default=None, description="Paper abstract text")
    citation_count: int = Field(default=0, description="Reported citation count")
    openalex_id: str | None = Field(default=None, description="OpenAlex Work ID")
    pdf_url: str | None = Field(default=None, description="Open access PDF URL")
    is_seed: bool = Field(default=False, description="Whether this paper was an initial seed")
    hop_distance: int = Field(default=0, description="BFS citation traversal depth from seed")

    @field_validator("doi", mode="before")
    @classmethod
    def clean_doi(cls, v: Any) -> str:
        return normalize_doi(str(v)) if v else ""


class ResearchInputs(BaseModel):
    """Q2 for Stage 1: Research configurations and query specifications."""
    model_config = ConfigDict(extra="allow")

    research_questions: list[str] = Field(default_factory=list, description="Core research questions")
    seed_dois: list[str] = Field(default_factory=list, description="Starting seed paper DOIs")
    keywords: list[str] = Field(default_factory=list, description="Search keywords")
    search_queries: list[str] = Field(default_factory=list, description="Target search query strings")
    max_depth: int = Field(default=2, ge=0, le=5, description="Maximum BFS citation crawl depth")
    similarity_threshold: float = Field(default=0.6, ge=0.0, le=1.0, description="Relevance cutoff")
    max_papers: int = Field(default=50, ge=1, le=500, description="Upper bound on paper collection")
    year_range: tuple[int | None, int | None] = Field(default=(None, None), description="Publication year bounds")

    @field_validator("seed_dois", mode="before")
    @classmethod
    def clean_seed_dois(cls, v: Any) -> list[str]:
        if isinstance(v, str):
            v = [v]
        if isinstance(v, (list, tuple, set)):
            return [normalize_doi(str(d)) for d in v if d and normalize_doi(str(d))]
        return []


class ResearchArtifacts(BaseModel):
    """Q3 for Stage 1: Concrete discovery outputs."""
    model_config = ConfigDict(extra="allow")

    papers: dict[str, PaperMetadata] = Field(default_factory=dict, description="Paper library keyed by normalized DOI")
    search_queries: list[str] = Field(default_factory=list, description="Executed search queries")
    crawl_queue: list[str] = Field(default_factory=list, description="Pending candidate DOIs for citation crawling")
    visited_dois: list[str] = Field(default_factory=list, description="Already expanded DOIs")
    citation_edges: list[tuple[str, str]] = Field(default_factory=list, description="Directed citation pairs: (citing_doi, cited_doi)")
    bfs_graph_edges: list[tuple[str, str]] = Field(default_factory=list, description="BFS citation traversal graph edges")
    top_authors: list[dict[str, Any]] = Field(default_factory=list, description="Aggregated prominent authors")
    top_venues: list[dict[str, Any]] = Field(default_factory=list, description="Aggregated top journals/conferences")
    total_discovered: int = Field(default=0, description="Total papers scraped before filtering")
    total_relevant: int = Field(default=0, description="Total papers satisfying similarity threshold")

    @model_validator(mode="before")
    @classmethod
    def sync_edges(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "bfs_graph_edges" in data and "citation_edges" not in data:
                data["citation_edges"] = data["bfs_graph_edges"]
            elif "citation_edges" in data and "bfs_graph_edges" not in data:
                data["bfs_graph_edges"] = data["citation_edges"]
        return data


class Stage1ResearchState(BaseModel):
    """Authoritative Substate for Stage 1 (Research)."""
    model_config = ConfigDict(extra="allow")

    meta: StageMeta = Field(default_factory=lambda: StageMeta(agent_name="ResearchAgent"))
    inputs: ResearchInputs = Field(default_factory=ResearchInputs)
    artifacts: ResearchArtifacts = Field(default_factory=ResearchArtifacts)
    notes: list[StageNote] = Field(default_factory=list)


ResearchSubstate = Stage1ResearchState


# ---------------------------------------------------------------------------
# Stage 2: Analysis (Embeddings, Clustering, Ranking, Gap Analysis, Matrices)
# ---------------------------------------------------------------------------

class PaperRanking(BaseModel):
    """Hybrid ranking assessment for a paper."""
    model_config = ConfigDict(extra="allow")

    doi: str
    title: str
    year: int | None = None
    similarity_score: float = 0.0
    pagerank_score: float = 0.0
    hybrid_score: float = 0.0
    rank: int = 0

    @field_validator("doi", mode="before")
    @classmethod
    def clean_doi(cls, v: Any) -> str:
        return normalize_doi(str(v)) if v else ""


class PaperCluster(BaseModel):
    """Semantic topic cluster of papers."""
    model_config = ConfigDict(extra="allow")

    cluster_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    label: str = Field(..., description="Descriptive theme or cluster name")
    paper_dois: list[str] = Field(default_factory=list)
    top_keywords: list[str] = Field(default_factory=list)
    summary: str = Field(default="")

    @field_validator("paper_dois", mode="before")
    @classmethod
    def clean_paper_dois(cls, v: Any) -> list[str]:
        if isinstance(v, str):
            v = [v]
        if isinstance(v, (list, tuple, set)):
            return [normalize_doi(str(d)) for d in v if d and normalize_doi(str(d))]
        return []


class ResearchGap(BaseModel):
    """Identified coverage deficiency in literature."""
    model_config = ConfigDict(extra="allow")

    gap_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    question: str = Field(..., description="Target research question lacking adequate coverage")
    description: str = Field(..., description="Nature of the literature deficit")
    severity: Literal["low", "medium", "high", "critical"] = "medium"
    suggested_queries: list[str] = Field(default_factory=list)
    covered_by_dois: list[str] = Field(default_factory=list)

    @field_validator("covered_by_dois", mode="before")
    @classmethod
    def clean_covered_by_dois(cls, v: Any) -> list[str]:
        if isinstance(v, str):
            v = [v]
        if isinstance(v, (list, tuple, set)):
            return [normalize_doi(str(d)) for d in v if d and normalize_doi(str(d))]
        return []


class PaperFinding(BaseModel):
    """Detailed evidence extraction from a single paper."""
    model_config = ConfigDict(extra="allow")

    doi: str
    title: str
    year: int | None = None
    methodology: str = ""
    key_findings: list[str] = Field(default_factory=list)
    datasets_or_benchmarks: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)

    @field_validator("doi", mode="before")
    @classmethod
    def clean_doi(cls, v: Any) -> str:
        return normalize_doi(str(v)) if v else ""


class ComparisonDimension(BaseModel):
    """Comparative dimension across literature."""
    model_config = ConfigDict(extra="allow")

    dimension_name: str
    findings_by_doi: dict[str, str] = Field(default_factory=dict)
    consensus: str = ""
    divergence: str = ""


class StructuredComparisonMatrix(BaseModel):
    """Literature comparison matrix across dimensions."""
    model_config = ConfigDict(extra="allow")

    project_id: str = ""
    dimensions: list[ComparisonDimension] = Field(default_factory=list)
    synthesis_narrative: str = ""


class AnalysisInputs(BaseModel):
    """Q2 for Stage 2: Analysis parameters."""
    model_config = ConfigDict(extra="allow")

    similarity_weight: float = Field(default=0.6, ge=0.0, le=1.0)
    pagerank_weight: float = Field(default=0.4, ge=0.0, le=1.0)
    embedding_model: str = Field(default="gemini-embedding-2")
    clustering_k: int | None = Field(default=None, ge=2, le=20)
    target_dimensions: list[str] = Field(default_factory=list)


class AnalysisArtifacts(BaseModel):
    """Q3 for Stage 2: Analysis artifacts."""
    model_config = ConfigDict(extra="allow")

    embeddings_metadata: dict[str, Any] = Field(default_factory=dict, description="Embedding models, dims, counts")
    similarity_matrix: Any = Field(default_factory=dict, description="Similarity matrix or mapping")
    clusters: list[PaperCluster] = Field(default_factory=list, description="Semantic clusters")
    gaps: list[ResearchGap] = Field(default_factory=list, description="Coverage gaps")
    research_gaps: list[ResearchGap] = Field(default_factory=list, description="Coverage gaps alias")
    rankings: list[PaperRanking] = Field(default_factory=list, description="Hybrid paper rankings")
    findings_by_doi: dict[str, PaperFinding] = Field(default_factory=dict, description="Evidence extraction by DOI")
    comparison_matrix: StructuredComparisonMatrix | None = None

    @model_validator(mode="before")
    @classmethod
    def sync_gaps(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "research_gaps" in data and "gaps" not in data:
                data["gaps"] = data["research_gaps"]
            elif "gaps" in data and "research_gaps" not in data:
                data["research_gaps"] = data["gaps"]
        return data


class Stage2AnalysisState(BaseModel):
    """Authoritative Substate for Stage 2 (Analysis)."""
    model_config = ConfigDict(extra="allow")

    meta: StageMeta = Field(default_factory=lambda: StageMeta(agent_name="GapFinderAgent"))
    inputs: AnalysisInputs = Field(default_factory=AnalysisInputs)
    artifacts: AnalysisArtifacts = Field(default_factory=AnalysisArtifacts)
    notes: list[StageNote] = Field(default_factory=list)


AnalysisSubstate = Stage2AnalysisState


# ---------------------------------------------------------------------------
# Stage 3: Planning (Outline, Section Blueprints, DOI Allocation)
# ---------------------------------------------------------------------------

class SectionBlueprint(BaseModel):
    """Structural blueprint for an individual review section."""
    model_config = ConfigDict(extra="allow")

    section_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str = Field(..., min_length=1)
    order: int = Field(default=1, ge=1)
    level: int = Field(default=1, ge=1, le=3)
    description: str = Field(default="", description="Scope and instructions for drafting this section")
    theme: str = Field(default="")
    assigned_dois: list[str] = Field(default_factory=list)
    target_word_count: int = Field(default=1500, ge=100)

    @field_validator("assigned_dois", mode="before")
    @classmethod
    def clean_assigned_dois(cls, v: Any) -> list[str]:
        if isinstance(v, str):
            v = [v]
        if isinstance(v, (list, tuple, set)):
            return [normalize_doi(str(d)) for d in v if d and normalize_doi(str(d))]
        return []


class OutlineStructure(BaseModel):
    """Full outline of the literature review document."""
    model_config = ConfigDict(extra="allow")

    title: str = Field(default="Literature Review")
    narrative_arc: str = Field(default="", description="High-level framing and progression of the review")
    sections: list[SectionBlueprint] = Field(default_factory=list)


class PlanningInputs(BaseModel):
    """Q2 for Stage 3: Outline configuration."""
    model_config = ConfigDict(extra="allow")

    style: Literal["thematic", "chronological", "methodological"] = "thematic"
    target_word_count: int = Field(default=8000, ge=1000)
    min_papers_per_section: int = Field(default=3, ge=1)
    target_section_count: int = Field(default=5, ge=2, le=15)
    custom_guidelines: str | None = None


class PlanningArtifacts(BaseModel):
    """Q3 for Stage 3: Planning deliverables."""
    model_config = ConfigDict(extra="allow")

    outline: OutlineStructure = Field(default_factory=OutlineStructure, description="Outline blueprint")
    section_blueprints: list[SectionBlueprint] = Field(default_factory=list, description="Section blueprints")
    doi_mappings: dict[str, list[str]] = Field(default_factory=dict, description="DOI to section_ids mapping")
    doi_to_section_map: dict[str, list[str]] = Field(default_factory=dict, description="DOI to section_ids alias")
    unassigned_dois: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def sync_doi_maps(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "doi_mappings" in data and "doi_to_section_map" not in data:
                data["doi_to_section_map"] = data["doi_mappings"]
            elif "doi_to_section_map" in data and "doi_mappings" not in data:
                data["doi_mappings"] = data["doi_to_section_map"]
            if "outline" in data and isinstance(data["outline"], dict) and "sections" in data["outline"]:
                if "section_blueprints" not in data or not data["section_blueprints"]:
                    data["section_blueprints"] = data["outline"]["sections"]
        return data


class Stage3PlanningState(BaseModel):
    """Authoritative Substate for Stage 3 (Planning)."""
    model_config = ConfigDict(extra="allow")

    meta: StageMeta = Field(default_factory=lambda: StageMeta(agent_name="PlannerAgent"))
    inputs: PlanningInputs = Field(default_factory=PlanningInputs)
    artifacts: PlanningArtifacts = Field(default_factory=PlanningArtifacts)
    notes: list[StageNote] = Field(default_factory=list)


PlanningSubstate = Stage3PlanningState


# ---------------------------------------------------------------------------
# Stage 4: Writing (Drafting, Review Cycles, Citation Grounding)
# ---------------------------------------------------------------------------

class SectionDraft(BaseModel):
    """Drafted content for a single section."""
    model_config = ConfigDict(extra="allow")

    section_id: str
    title: str
    markdown: str = ""
    word_count: int = 0
    cited_dois: list[str] = Field(default_factory=list)
    version: int = 1
    updated_at: datetime = Field(default_factory=utc_now)

    @field_validator("cited_dois", mode="before")
    @classmethod
    def clean_cited_dois(cls, v: Any) -> list[str]:
        if isinstance(v, str):
            v = [v]
        if isinstance(v, (list, tuple, set)):
            return [normalize_doi(str(d)) for d in v if d and normalize_doi(str(d))]
        return []


class SectionReview(BaseModel):
    """Peer review evaluation for a drafted section."""
    model_config = ConfigDict(extra="allow")

    review_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    iteration: int = 1
    approved: bool = False
    overall_score: float = Field(default=0.0, ge=0.0, le=1.0)
    scores: dict[str, float] = Field(default_factory=dict, description="e.g. coverage, coherence, synthesis")
    feedback: list[str] = Field(default_factory=list)
    missing_citations: list[str] = Field(default_factory=list)
    reviewed_at: datetime = Field(default_factory=utc_now)


class WritingInputs(BaseModel):
    """Q2 for Stage 4: Writing guidelines and limits."""
    model_config = ConfigDict(extra="allow")

    target_level: Literal["master", "phd"] = "master"
    tone: str = "academic"
    max_review_iterations: int = Field(default=3, ge=1, le=5)
    min_approval_score: float = Field(default=0.75, ge=0.0, le=1.0)


class WritingArtifacts(BaseModel):
    """Q3 for Stage 4: Drafts, reviews, and groundings."""
    model_config = ConfigDict(extra="allow")

    section_drafts: dict[str, SectionDraft] = Field(default_factory=dict, description="section_id -> SectionDraft")
    draft_sections_markdown: dict[str, str] = Field(default_factory=dict, description="section_id -> raw markdown")
    section_reviews: dict[str, list[SectionReview]] = Field(default_factory=dict, description="section_id -> list[SectionReview]")
    peer_review_feedback: list[dict[str, Any]] = Field(default_factory=list, description="Aggregated peer review entries")
    citation_groundings: dict[str, Any] = Field(default_factory=dict, description="Verified citation groundings")
    full_draft_markdown: str = Field(default="")
    citation_grounding_verified: bool = False
    unverified_citations: list[str] = Field(default_factory=list)


class Stage4WritingState(BaseModel):
    """Authoritative Substate for Stage 4 (Writing)."""
    model_config = ConfigDict(extra="allow")

    meta: StageMeta = Field(default_factory=lambda: StageMeta(agent_name="WriterAgent"))
    inputs: WritingInputs = Field(default_factory=WritingInputs)
    artifacts: WritingArtifacts = Field(default_factory=WritingArtifacts)
    notes: list[StageNote] = Field(default_factory=list)


WritingSubstate = Stage4WritingState


# ---------------------------------------------------------------------------
# Stage 5: Export (LaTeX, BibTeX, GraphML, Publication Bundles)
# ---------------------------------------------------------------------------

class ExportInputs(BaseModel):
    """Q2 for Stage 5: Output format configurations."""
    model_config = ConfigDict(extra="allow")

    template: Literal["ieee", "acm", "plain"] = "ieee"
    include_citation_graph: bool = True
    compile_pdf: bool = False


class ExportArtifacts(BaseModel):
    """Q3 for Stage 5: Output file references and metadata."""
    model_config = ConfigDict(extra="allow")

    latex_templates: dict[str, str] = Field(default_factory=dict, description="Custom LaTeX template snippets/configs")
    bibtex_entries: list[str] = Field(default_factory=list, description="Raw BibTeX citations")
    compiled_document_metadata: dict[str, Any] = Field(default_factory=dict, description="Compiled document stats")
    tex_path: str | None = None
    bib_path: str | None = None
    pdf_path: str | None = None
    json_graph_path: str | None = None
    graphml_path: str | None = None
    bibtex_entry_count: int = 0
    tex_section_count: int = 0
    preview_snippet: str | None = None


class Stage5ExportState(BaseModel):
    """Authoritative Substate for Stage 5 (Export)."""
    model_config = ConfigDict(extra="allow")

    meta: StageMeta = Field(default_factory=lambda: StageMeta(agent_name="WriterAgent"))
    inputs: ExportInputs = Field(default_factory=ExportInputs)
    artifacts: ExportArtifacts = Field(default_factory=ExportArtifacts)
    notes: list[StageNote] = Field(default_factory=list)


ExportSubstate = Stage5ExportState


# ---------------------------------------------------------------------------
# R3: Public Message Board (Shared Blackboard)
# ---------------------------------------------------------------------------

BoardClassification = Literal[
    "insight",      # Synthesized domain discovery
    "serendipity",  # Unexpected relevant paper/connection
    "gap",          # Identified literature deficit
    "warning",      # Contradiction, anomaly, or quality risk
    "decision",     # Scoping, architectural, or structural choice
    "hypothesis",   # Testable proposition for downstream agents
]


class BoardMessage(BaseModel):
    """Cross-cutting discovery message posted to the public message board."""
    model_config = ConfigDict(extra="allow")

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Message UUID")
    timestamp: datetime = Field(default_factory=utc_now, description="UTC publication timestamp")
    author_agent: str = Field(..., min_length=1, description="Agent identifier (e.g. ALRSAgent, PlannerAgent)")
    message_type: BoardClassification = Field(..., description="Message classification type")
    title: str = Field(..., min_length=1, max_length=300, description="Descriptive headline")
    content: str = Field(..., min_length=1, description="Markdown content detailing the discovery")
    stage: str = Field(default="global", description="Associated stage name or 'global'")
    tags: list[str] = Field(default_factory=list, description="Categorical keywords")
    related_paper_dois: list[str] = Field(default_factory=list, description="Referenced normalized academic DOIs")
    acknowledged_by: list[str] = Field(default_factory=list, description="Agent names that consumed this message")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Arbitrary supplemental metadata")

    @model_validator(mode="before")
    @classmethod
    def handle_aliases(cls, data: Any) -> Any:
        if isinstance(data, dict):
            # Support classification as alias for message_type
            if "classification" in data and "message_type" not in data:
                data["message_type"] = data["classification"]
            # Support relevant_dois as alias for related_paper_dois
            if "relevant_dois" in data and "related_paper_dois" not in data:
                data["related_paper_dois"] = data["relevant_dois"]
        return data

    @field_validator("related_paper_dois", mode="before")
    @classmethod
    def clean_related_paper_dois(cls, v: Any) -> list[str]:
        if isinstance(v, str):
            v = [v]
        if isinstance(v, (list, tuple, set)):
            return [normalize_doi(str(d)) for d in v if d and normalize_doi(str(d))]
        return []

    @property
    def message_id(self) -> str:
        """Alias for id."""
        return self.id

    @property
    def classification(self) -> BoardClassification:
        """Alias for message_type."""
        return self.message_type

    @property
    def relevant_dois(self) -> list[str]:
        """Alias for related_paper_dois."""
        return self.related_paper_dois

    def acknowledge(self, agent_name: str) -> None:
        """Mark this message as acknowledged by a specific agent."""
        if agent_name not in self.acknowledged_by:
            self.acknowledged_by.append(agent_name)

    def is_acknowledged_by(self, agent_name: str) -> bool:
        """Check if an agent has acknowledged this message."""
        return agent_name in self.acknowledged_by


# ---------------------------------------------------------------------------
# Authoritative Root ProjectState
# ---------------------------------------------------------------------------

class ProjectState(BaseModel):
    """Authoritative root state representing an entire literature review project."""
    model_config = ConfigDict(extra="allow")

    # Project Core Metadata
    project_id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Project UUID")
    name: str = Field(..., min_length=1, max_length=200, description="Project human-readable title")
    description: str | None = Field(default=None, description="Detailed project description")
    topic: str | None = Field(default=None, description="Primary research domain")
    status: Literal["active", "paused", "completed", "failed", "archived"] = Field(
        default="active", description="Lifecycle operational status"
    )
    target_level: Literal["master", "phd"] = Field(
        default="master", description="Target academic rigor level"
    )
    similarity_threshold: float = Field(default=0.6, ge=0.0, le=1.0)

    # Resource Metrics
    token_budget: int = Field(default=500000, ge=0, description="Allocated LLM token budget")
    tokens_used: int = Field(default=0, ge=0, description="Cumulative tokens consumed")

    # Lifecycle Timestamps
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    completed_at: datetime | None = Field(default=None)

    # Active Stage Indicator
    current_stage: str = Field(
        default="stage_1_research",
        description="Active stage (e.g. stage_1_research, stage_2_analysis, etc.)",
    )

    # 4-Quadrant Stage Substates
    stage_1_research: Stage1ResearchState = Field(default_factory=Stage1ResearchState)
    stage_2_analysis: Stage2AnalysisState = Field(default_factory=Stage2AnalysisState)
    stage_3_planning: Stage3PlanningState = Field(default_factory=Stage3PlanningState)
    stage_4_writing: Stage4WritingState = Field(default_factory=Stage4WritingState)
    stage_5_export: Stage5ExportState = Field(default_factory=Stage5ExportState)

    # Public Message Board (Shared Blackboard)
    message_board: list[BoardMessage] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def handle_project_id_alias(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "id" in data and ("project_id" not in data or not data["project_id"]):
                data["project_id"] = data["id"]
            elif "project_id" in data and "id" not in data:
                data["id"] = data["project_id"]
        return data

    @property
    def id(self) -> str:
        """Alias for project_id."""
        return self.project_id

    def touch(self) -> None:
        """Update root timestamp to indicate mutation."""
        self.updated_at = utc_now()

    def get_by_dot_path(self, path: str) -> Any:
        """Traverse nested attributes, dicts, or lists using a dot-delimited path.

        Handles:
            - Model attributes: e.g. 'stage_1_research.meta.status'
            - Dict lookups: e.g. 'stage_1_research.artifacts.papers'
            - List indexing: e.g. 'stage_3_planning.artifacts.outline.sections.0.title'
            - Keys containing dots (e.g. academic DOIs): dynamically combines path segments
        """
        if not path or not path.strip():
            return self

        tokens = path.strip().split(".")
        if any(p.startswith("_") for p in tokens):
            raise ValueError(
                f"Access to private or dunder attribute is prohibited (full path: '{path}')"
            )

        curr: Any = self
        idx = 0
        n = len(tokens)

        while idx < n:
            token = tokens[idx]
            if isinstance(curr, BaseModel):
                if hasattr(curr, token):
                    curr = getattr(curr, token)
                    idx += 1
                elif isinstance(curr.model_extra, dict) and token in curr.model_extra:
                    curr = curr.model_extra[token]
                    idx += 1
                else:
                    raise KeyError(
                        f"Attribute or field '{token}' not found on {type(curr).__name__} (full path: '{path}')"
                    )
            elif isinstance(curr, dict):
                # First check exact token match
                if token in curr:
                    curr = curr[token]
                    idx += 1
                else:
                    # Check for compound keys (e.g. DOI containing dots like '10.1145/3292500.3330964')
                    matched = False
                    for end in range(n, idx, -1):
                        compound_key = ".".join(tokens[idx:end])
                        if compound_key in curr:
                            curr = curr[compound_key]
                            idx = end
                            matched = True
                            break
                        norm_key = normalize_doi(compound_key)
                        if norm_key in curr:
                            curr = curr[norm_key]
                            idx = end
                            matched = True
                            break
                    if not matched:
                        raise KeyError(
                            f"Key '{token}' not found in dict. Available keys: {list(curr.keys())[:10]} (full path: '{path}')"
                        )
            elif isinstance(curr, (list, tuple)):
                try:
                    list_idx = int(token)
                    curr = curr[list_idx]
                    idx += 1
                except ValueError:
                    raise ValueError(
                        f"Cannot index list with non-integer token '{token}' (full path: '{path}')"
                    )
                except IndexError:
                    raise IndexError(
                        f"Index {list_idx} out of range for list of length {len(curr)} (full path: '{path}')"
                    )
            else:
                raise TypeError(
                    f"Cannot traverse into scalar value of type {type(curr).__name__} at token '{token}' (full path: '{path}')"
                )

        return curr

    def post_message(
        self,
        author_agent: str,
        message_type: BoardClassification | str,
        title: str,
        content: str,
        stage: str = "global",
        tags: list[str] | None = None,
        related_paper_dois: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> BoardMessage:
        """Create and append a message to the public message board."""
        msg = BoardMessage(
            author_agent=author_agent,
            message_type=message_type,  # type: ignore[arg-type]
            title=title,
            content=content,
            stage=stage,
            tags=tags or [],
            related_paper_dois=related_paper_dois or [],
            metadata=metadata or {},
            **kwargs,
        )
        self.message_board.append(msg)
        self.touch()
        return msg

    def add_message(
        self,
        author_agent: str,
        message_type: BoardClassification | str,
        title: str,
        content: str,
        stage: str = "global",
        tags: list[str] | None = None,
        related_paper_dois: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> BoardMessage:
        """Alias for post_message."""
        return self.post_message(
            author_agent=author_agent,
            message_type=message_type,
            title=title,
            content=content,
            stage=stage,
            tags=tags,
            related_paper_dois=related_paper_dois,
            metadata=metadata,
            **kwargs,
        )

    def acknowledge_message(self, message_id: str, agent_name: str) -> bool:
        """Acknowledge a message on the public message board for a specific agent."""
        for msg in self.message_board:
            if msg.id == message_id:
                if agent_name not in msg.acknowledged_by:
                    msg.acknowledged_by.append(agent_name)
                    self.touch()
                return True
        return False

    def update_stage_quadrant(
        self,
        stage: str,
        quadrant: str,
        data: dict[str, Any] | list[Any],
    ) -> None:
        """Update a specific quadrant in one of the 5 stage substates."""
        normalized_stage = normalize_stage_name(stage)
        if not hasattr(self, normalized_stage):
            raise ValueError(
                f"Invalid workflow stage '{stage}'. Expected one of: "
                "stage_1_research, stage_2_analysis, stage_3_planning, stage_4_writing, stage_5_export"
            )

        if quadrant not in ("meta", "inputs", "artifacts", "notes"):
            raise ValueError(
                f"Invalid quadrant '{quadrant}'. Must be one of: 'meta', 'inputs', 'artifacts', 'notes'"
            )

        substate = getattr(self, normalized_stage)

        if quadrant == "notes":
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, StageNote):
                        substate.notes.append(item)
                    elif isinstance(item, dict):
                        substate.notes.append(StageNote(**item))
                    elif isinstance(item, str):
                        substate.notes.append(StageNote(author="system", content=item))
            elif isinstance(data, dict):
                if "notes" in data and isinstance(data["notes"], list):
                    for item in data["notes"]:
                        if isinstance(item, StageNote):
                            substate.notes.append(item)
                        elif isinstance(item, dict):
                            substate.notes.append(StageNote(**item))
                elif "content" in data:
                    substate.notes.append(StageNote(**data))
                else:
                    for k, v in data.items():
                        substate.notes.append(StageNote(author=k, content=str(v)))
            else:
                raise TypeError(
                    f"Data for notes quadrant must be list or dict, got {type(data).__name__}"
                )
        else:
            target_quadrant = getattr(substate, quadrant)
            if isinstance(data, dict):
                for k, v in data.items():
                    if hasattr(target_quadrant, k):
                        setattr(target_quadrant, k, v)
                    elif hasattr(target_quadrant, "__pydantic_extra__"):
                        if target_quadrant.__pydantic_extra__ is None:
                            target_quadrant.__pydantic_extra__ = {}
                        target_quadrant.__pydantic_extra__[k] = v
                    else:
                        setattr(target_quadrant, k, v)
            else:
                raise TypeError(
                    f"Data for quadrant '{quadrant}' must be a dict, got {type(data).__name__}"
                )

        substate.meta.updated_at = utc_now()
        self.touch()

    def get_summary(self) -> dict[str, Any]:
        """Generate a lightweight summary to prevent LLM context overflow."""
        return {
            "project_id": self.project_id,
            "name": self.name,
            "topic": self.topic,
            "target_level": self.target_level,
            "current_stage": self.current_stage,
            "status": self.status,
            "token_budget": self.token_budget,
            "tokens_used": self.tokens_used,
            "stages": {
                "stage_1_research": {
                    "status": self.stage_1_research.meta.status,
                    "paper_count": len(self.stage_1_research.artifacts.papers),
                    "questions_count": len(self.stage_1_research.inputs.research_questions),
                },
                "stage_2_analysis": {
                    "status": self.stage_2_analysis.meta.status,
                    "rankings_count": len(self.stage_2_analysis.artifacts.rankings),
                    "gaps_count": len(self.stage_2_analysis.artifacts.gaps),
                    "clusters_count": len(self.stage_2_analysis.artifacts.clusters),
                },
                "stage_3_planning": {
                    "status": self.stage_3_planning.meta.status,
                    "section_count": len(self.stage_3_planning.artifacts.outline.sections),
                },
                "stage_4_writing": {
                    "status": self.stage_4_writing.meta.status,
                    "drafted_sections": len(self.stage_4_writing.artifacts.section_drafts),
                },
                "stage_5_export": {
                    "status": self.stage_5_export.meta.status,
                    "has_tex": bool(self.stage_5_export.artifacts.tex_path),
                    "has_bib": bool(self.stage_5_export.artifacts.bib_path),
                },
            },
            "message_board_total": len(self.message_board),
            "updated_at": self.updated_at.isoformat(),
        }

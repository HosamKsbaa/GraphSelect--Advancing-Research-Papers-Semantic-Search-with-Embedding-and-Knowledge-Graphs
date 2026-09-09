from __future__ import annotations

from pydantic import BaseModel, Field


class RankedPaper(BaseModel):
    doi: str
    title: str
    year: int | None = None
    cited_by_count: int = 0
    similarity_score: float = 0.0
    pagerank_score: float = 0.0
    hybrid_score: float = 0.0
    question_group: str = ''
    abstract_snippet: str | None = None
    authors: list[str] = Field(default_factory=list)


class QuestionGroup(BaseModel):
    question: str
    papers: list[RankedPaper] = Field(default_factory=list)
    avg_similarity: float = 0.0
    paper_count: int = 0


class GroupedResults(BaseModel):
    session_id: str
    groups: list[QuestionGroup] = Field(default_factory=list)
    total_papers: int = 0
    similarity_threshold: float = 0.5
    similarity_weight: float = 0.7
    pagerank_weight: float = 0.3


from features.search.models import CandidatePaperState as CandidatePaperState  # noqa: E402


class SteeringActionOption(BaseModel):
    """Actionable steering choice presented to the user after 1-hop traversal."""

    option_id: str
    action_type: str = Field(
        description="'expand_deeper' | 'add_to_library' | 'branch_seed' | 'conclude'"
    )
    target_doi: str | None = None
    target_title: str | None = None
    label: str
    rationale: str


class TraversalAppraisalResult(BaseModel):
    """Structured appraisal payload returned by 1-hop traversal and agent evaluation."""

    seed_doi: str
    seed_title: str
    cycle_level: int = 1
    total_discovered: int = 0
    total_new: int = 0
    foundational_prior_art: list[CandidatePaperState] = Field(default_factory=list)
    contemporary_breakthroughs: list[CandidatePaperState] = Field(default_factory=list)
    topological_bridges: list[CandidatePaperState] = Field(default_factory=list)
    strategic_recommendation: str = ""
    steering_options: list[SteeringActionOption] = Field(default_factory=list)


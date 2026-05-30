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

"""Validated ALRS search settings and retrieval profile catalog.

Ported from archive commit 865cd08 (`code/backend/alrs_tool/search/settings.py`).
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator


class SearchProfile(str, Enum):
    """Selectable Stage 1 candidate retrieval profiles for ALRS search."""

    CONTENT_EXPANDED_CITATION_RRF = "content_expanded_citation_rrf"
    CONTENT_ORIGINAL_EXPANDED_RRF = "content_original_expanded_rrf"
    DEFAULT_BM25 = "default_bm25"


class SearchProfileMetadata(BaseModel):
    """Metadata, empirical baselines, and parameter specification for a search profile."""

    model_config = ConfigDict(extra="forbid")

    id: SearchProfile
    name: str
    description: str
    is_default: bool = False
    stage: str = "Stage 1 Candidate Retrieval"
    recall_at_20_holdout: float | None = None
    recall_at_20_sample: float | None = None
    expansion_weight: float = 1.0
    citation_neighbor_weight: float = 0.0
    candidate_depth: int = 20
    parameters: dict[str, JsonValue] = Field(default_factory=dict)


SEARCH_PROFILE_CATALOG: dict[SearchProfile, SearchProfileMetadata] = {
    SearchProfile.CONTENT_EXPANDED_CITATION_RRF: SearchProfileMetadata(
        id=SearchProfile.CONTENT_EXPANDED_CITATION_RRF,
        name="Content + Query Expansion + Citation RRF (High-Recall Baseline)",
        description=(
            "High-recall Stage 1 candidate retrieval baseline combining BM25 lexical matching "
            "on cleaned content tokens, BM25 matching on expanded query terms, and local citation "
            "graph neighbor expansion via Reciprocal Rank Fusion (RRF)."
        ),
        is_default=True,
        stage="Stage 1 Candidate Retrieval",
        recall_at_20_holdout=0.70389,
        recall_at_20_sample=0.71667,
        expansion_weight=1.0,
        citation_neighbor_weight=0.25,
        candidate_depth=20,
        parameters={
            "lexical_index": "SparseBM25",
            "query_cleaning": "content_tokens_alphanumeric",
            "query_expansion": "gemini_synonym_expansion",
            "expansion_weight": 1.0,
            "citation_neighbor_expansion": True,
            "citation_neighbor_weight": 0.25,
            "citation_neighbor_top_k": 10,
            "rrf_k": 60,
            "candidate_pool_depth": 20,
        },
    ),
    SearchProfile.CONTENT_ORIGINAL_EXPANDED_RRF: SearchProfileMetadata(
        id=SearchProfile.CONTENT_ORIGINAL_EXPANDED_RRF,
        name="Content + Query Expansion RRF (Lexical Only)",
        description=(
            "Lexical Stage 1 retrieval fusing original query BM25 with expanded query BM25 via "
            "Reciprocal Rank Fusion, omitting citation graph neighbor traversal."
        ),
        is_default=False,
        stage="Stage 1 Candidate Retrieval",
        expansion_weight=1.0,
        citation_neighbor_weight=0.0,
        candidate_depth=20,
        parameters={
            "lexical_index": "SparseBM25",
            "query_cleaning": "content_tokens_alphanumeric",
            "query_expansion": "gemini_synonym_expansion",
            "expansion_weight": 1.0,
            "citation_neighbor_expansion": False,
            "citation_neighbor_weight": 0.0,
            "rrf_k": 60,
            "candidate_pool_depth": 20,
        },
    ),
    SearchProfile.DEFAULT_BM25: SearchProfileMetadata(
        id=SearchProfile.DEFAULT_BM25,
        name="Standard BM25 (Unexpanded Baseline)",
        description="Standard single-query BM25 lexical retrieval without query expansion or citation graph traversal.",
        is_default=False,
        stage="Stage 1 Candidate Retrieval",
        recall_at_20_holdout=0.60329,
        recall_at_20_sample=0.56111,
        expansion_weight=0.0,
        citation_neighbor_weight=0.0,
        candidate_depth=20,
        parameters={
            "lexical_index": "SparseBM25",
            "query_cleaning": "content_tokens_alphanumeric",
            "query_expansion": None,
            "expansion_weight": 0.0,
            "citation_neighbor_expansion": False,
            "citation_neighbor_weight": 0.0,
            "candidate_pool_depth": 20,
        },
    ),
}

PROFILE_ALIASES: dict[str, SearchProfile] = {
    "content_expanded_rrf": SearchProfile.CONTENT_ORIGINAL_EXPANDED_RRF,
    "content_bm25": SearchProfile.DEFAULT_BM25,
}


def normalize_search_profile(value: str | SearchProfile) -> SearchProfile:
    """Normalize string or alias into a canonical SearchProfile enum."""
    if isinstance(value, SearchProfile):
        return value
    cleaned = str(value).strip().lower()
    if cleaned in PROFILE_ALIASES:
        return PROFILE_ALIASES[cleaned]
    try:
        return SearchProfile(cleaned)
    except ValueError as err:
        valid_profiles = [p.value for p in SearchProfile]
        raise ValueError(
            f"Unsupported search profile '{value}'. Supported profiles: {valid_profiles}"
        ) from err


def get_search_profile_metadata(profile: str | SearchProfile) -> SearchProfileMetadata:
    """Retrieve metadata and parameters for a search profile, resolving aliases."""
    canonical = normalize_search_profile(profile)
    return SEARCH_PROFILE_CATALOG[canonical]


def list_search_profiles() -> list[SearchProfileMetadata]:
    """List all registered search profiles, with default profile first."""
    profiles = list(SEARCH_PROFILE_CATALOG.values())
    return sorted(profiles, key=lambda p: (not p.is_default, p.name))


class ALRSSearchSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile_version: Literal["alrs-v1"] = "alrs-v1"
    retrieval_profile: SearchProfile = Field(default=SearchProfile.CONTENT_EXPANDED_CITATION_RRF)
    max_depth: int = Field(default=2, ge=1, le=3, strict=True)
    max_papers: int = Field(default=50, ge=1, le=100, strict=True)
    max_requests: int = Field(default=20, ge=1, le=100, strict=True)
    max_active_seconds: int = Field(default=180, ge=30, le=600, strict=True)
    max_retries: int = Field(default=2, ge=0, le=2, strict=True)
    similarity_threshold: float = Field(default=0.5, ge=0, le=1)
    similarity_weight: float = Field(default=0.7, ge=0, le=1)
    density_gated_pagerank: bool = Field(
        default=False,
        description="Enable candidate subgraph density gating for PageRank (w_pr_eff = w_pr * tanh(20 * rho))",
    )
    density_gate_steepness: float = Field(
        default=20.0,
        ge=1.0,
        le=100.0,
        description="Steepness parameter for tanh candidate subgraph density gate",
    )

    @field_validator("retrieval_profile", mode="before")
    @classmethod
    def validate_and_normalize_profile(cls, value: object) -> object:
        if isinstance(value, (str, SearchProfile)):
            return normalize_search_profile(value)
        return value

    @property
    def pagerank_weight(self) -> float:
        return 1.0 - self.similarity_weight

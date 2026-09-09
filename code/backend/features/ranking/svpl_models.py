"""Pydantic v2 domain models for SVPL Multi-Hop Bridge Discovery.

Complies with Constitution v2.2.1:
- C7: Strict static typing without bare signatures.
- C9: Granular sub-routines under 25 lines.
- C11: Intention-revealing domain types and predicate booleans.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


class BridgeMechanism(str, Enum):
    """Scientometric bridging mechanism discovered between source and target."""

    DIRECTED_2HOP = "directed_2hop"  # A -> U -> C (cited_by:A, cites:C)
    REVERSE_DIRECTED_2HOP = "reverse_directed_2hop"  # C -> U -> A (cites:A, cited_by:C)
    BIBLIOGRAPHIC_COUPLING = "bibliographic_coupling"  # A -> U <- C (cited_by:A, cited_by:C)
    CO_CITATION = "co_citation"  # A <- U -> C (cites:A, cites:C)
    PIPE_DISJUNCTIVE_3HOP = "pipe_disjunctive_3hop"  # A -> U1 -> U2 -> C
    STEINER_BEAM_3HOP = "steiner_beam_3hop"  # Layer 3 concept-guided Steiner A*


class MultiHopTriggerReason(str, Enum):
    """Enforces FR-015: Bridge discovery must not run unless strictly authorized."""

    EXPLICIT_USER_DIRECTIVE = "explicit_user_directive"
    EMPTY_GAP_REMEDIATION = "empty_gap_remediation"


class MultiHopAuthorization(BaseModel):
    """Gate payload enforcing FR-015 strict necessity gating."""

    trigger_reason: MultiHopTriggerReason
    requester: str = Field(..., description="Researcher session ID or Agent name")
    context_description: str = Field(..., min_length=10, description="Justification for invoking multi-hop")
    is_authorized: bool = Field(default=True)


class BridgeHopCandidate(BaseModel):
    """Candidate paper discovered during intermediate hop evaluation."""

    openalex_id: str
    doi: str | None = None
    title: str
    year: int | None = None
    hop_level: int = Field(..., ge=1, le=3)
    cosine_similarity: float = Field(..., ge=-1.0, le=1.0)
    pagerank_score: float = Field(default=0.0, ge=0.0)
    adaptive_threshold_tau: float = Field(..., description="Computed tau_h pruning threshold")
    is_pruned: bool = Field(default=False)


class BridgeNodeSummary(BaseModel):
    """Summary of an intermediate bridge node in a multi-hop pathway."""

    openalex_id: str = Field(..., description="OpenAlex Work identifier (e.g. W12345)")
    doi: str | None = Field(default=None, description="Canonical DOI if available")
    title: str = Field(..., description="Paper title")
    year: int | None = Field(default=None, description="Publication year")
    cited_by_count: int | None = Field(default=None, description="Inbound citation count")
    is_stub: bool = Field(default=False, description="True if only stub metadata exists")


class MultiHopBridgePathway(BaseModel):
    """Materialized epistemic pathway between source paper and library target."""

    pathway_id: str = Field(..., description="UUID of the discovered pathway")
    source_doi: str
    target_doi: str
    intermediate_nodes: list[BridgeNodeSummary] = Field(
        default_factory=list, description="Ordered intermediate nodes in traversal pathway"
    )
    mechanism: BridgeMechanism
    discovered_layer: int = Field(..., ge=0, le=3, description="SVPL layer: 0=Local, 1=1-shot, 2=Pipe, 3=Steiner")
    confidence: float = Field(..., ge=0.0, le=1.0)
    hop_distance: int = Field(..., ge=1, le=3)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SVPLMultiHopDiscoveryInput(BaseModel):
    """Input contract for multi-hop path discovery tool."""

    source_doi: str = Field(..., min_length=5, description="Normalized starting paper DOI")
    target_doi: str = Field(..., min_length=5, description="Normalized library target paper DOI")
    project_id: str = Field(..., description="Active research project UUID")
    trigger_reason: MultiHopTriggerReason = Field(
        ..., description="'explicit_user_directive' | 'empty_gap_remediation' (FR-015)"
    )
    max_hops: int = Field(default=3, ge=1, le=3, description="Search depth limit")
    run_id: str = Field(..., description="Active workflow execution / run UUID per Constitution C5, A15, A49")
    stage_index: int = Field(default=2, description="Workflow stage index")
    authorization_token: str | None = Field(default=None, description="Optional auth token")


class SVPLMultiHopDiscoveryOutput(BaseModel):
    """Output contract returned upon finding or exhausting multi-hop pathways."""

    status: str = Field(default="success", description="'success' | 'no_path_found'")
    pathway_id: str | None = Field(default=None, description="UUID of discovered pathway in Neo4j")
    source_doi: str = Field(..., description="Source paper DOI")
    target_doi: str = Field(..., description="Target library paper DOI")
    hop_distance: int = Field(default=1, ge=1, le=3, description="Number of hops in path")
    discovered_layer: int = Field(default=0, ge=0, le=3, description="SVPL layer: 0=Local, 1=1-shot, 2=Pipe, 3=Steiner")
    mechanism: BridgeMechanism | None = Field(default=None, description="Bridge relationship typology")
    intermediate_nodes: list[BridgeNodeSummary] = Field(default_factory=list, description="Ordered bridge papers")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Overall pathway confidence score")

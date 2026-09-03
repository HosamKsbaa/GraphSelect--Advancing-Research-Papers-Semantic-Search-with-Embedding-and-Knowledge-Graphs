"""Pydantic v2 data models for the ALRS Epistemic Fact Graph (GraphRAG).

Defines the 9 core epistemic node types, relationship schemas with mandatory
rich-text descriptions, and response models for graph traversal and debate extraction.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
import uuid

from pydantic import BaseModel, ConfigDict, Field, model_validator


# ============================================================================
# Enums
# ============================================================================

class FactStatus(str, Enum):
    """Epistemic status of a factual assertion."""
    TENTATIVE = "tentative"
    SUPPORTED = "supported"
    DEBATED = "debated"
    REFUTED = "refuted"
    CONSENSUS = "consensus"


class ProofPolarity(str, Enum):
    """Epistemic stance of a proof with respect to a fact."""
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    INCONCLUSIVE = "inconclusive"


class ProofType(str, Enum):
    """Category of empirical or formal evidence."""
    EMPIRICAL_BENCHMARK = "empirical_benchmark"
    ABLATION = "ablation"
    MATHEMATICAL_PROOF = "mathematical_proof"
    STATISTICAL_ANALYSIS = "statistical_analysis"
    META_ANALYSIS = "meta_analysis"
    CASE_STUDY = "case_study"


class MethodologyCategory(str, Enum):
    """Categorization of experimental or analytical methodology."""
    EVALUATION_PROTOCOL = "evaluation_protocol"
    OPTIMIZATION_ALGORITHM = "optimization_algorithm"
    SAMPLING_STRATEGY = "sampling_strategy"
    DATA_CURATION = "data_curation"
    MODEL_ARCHITECTURE = "model_architecture"


class LimitationSeverity(str, Enum):
    """Severity of an identified methodological or empirical limitation."""
    MINOR = "minor"
    MODERATE = "moderate"
    CRITICAL = "critical"
    SCOPE_RESTRICTION = "scope_restriction"


class RelationshipType(str, Enum):
    """Valid epistemic relationship types in the GraphRAG backend."""
    SUPPORTED_BY = "SUPPORTED_BY"
    CONTRADICTED_BY = "CONTRADICTED_BY"
    USES_METHOD = "USES_METHOD"
    EVALUATED_ON = "EVALUATED_ON"
    EXTRACTED_FROM = "EXTRACTED_FROM"
    ADDRESSES = "ADDRESSES"
    RELATES_TO_CONCEPT = "RELATES_TO_CONCEPT"
    HAS_LIMITATION = "HAS_LIMITATION"
    BELONGS_TO_COMMUNITY = "BELONGS_TO_COMMUNITY"


# ============================================================================
# 9 Node Models
# ============================================================================

def _clean_neo4j_dict(data: Any) -> Any:
    """Recursively convert neo4j types (like neo4j.time.DateTime) to standard python types."""
    if isinstance(data, dict):
        clean = dict(data)
        for k, v in clean.items():
            if hasattr(v, "to_native"):
                clean[k] = v.to_native()
            elif isinstance(v, (dict, list)):
                clean[k] = _clean_neo4j_dict(v)
        return clean
    elif isinstance(data, list):
        return [_clean_neo4j_dict(item) for item in data]
    return data


class Fact(BaseModel):
    """A central empirical or theoretical claim extracted from academic discourse."""
    model_config = ConfigDict(populate_by_name=True, extra="allow")

    fact_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    statement: str = Field(..., min_length=5, description="Propositional assertion statement")
    status: FactStatus = Field(default=FactStatus.TENTATIVE)
    confidence_score: float = Field(default=0.5, ge=0.0, le=1.0)
    domain: str = Field(default="general")
    project_id: str = Field(default="", description="Scoping project UUID")
    embedding: list[float] | None = Field(default=None, description="768-dim vector embedding")
    embedding_model: str | None = Field(default=None)
    created_by_agent: str | None = Field(default=None)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _normalize_aliases(cls, data: Any) -> Any:
        data = _clean_neo4j_dict(data)
        if isinstance(data, dict):
            if "id" in data and "fact_id" not in data:
                data["fact_id"] = data["id"]
            if "epistemic_status" in data and "status" not in data:
                data["status"] = data["epistemic_status"]
        return data

    @property
    def id(self) -> str:
        return self.fact_id

    @property
    def epistemic_status(self) -> FactStatus:
        return self.status


class Proof(BaseModel):
    """Empirical or theoretical evidence supporting or contradicting a Fact."""
    model_config = ConfigDict(populate_by_name=True, extra="allow")

    proof_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    summary: str = Field(..., min_length=5, description="Concise summary of the empirical finding")
    polarity: ProofPolarity = Field(default=ProofPolarity.SUPPORTS)
    proof_type: ProofType = Field(default=ProofType.EMPIRICAL_BENCHMARK)
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    extracted_quote: str | None = Field(default=None, description="Direct quote from literature")
    metrics: dict[str, Any] = Field(default_factory=dict, description="Extracted numerical results")
    location: str | None = Field(default=None, description="Section, Table, or Figure reference")
    source_paper_id: str | None = Field(default=None, description="Originating Paper DOI or ID")
    agent_id: str = Field(default="agent", description="Asserting agent identifier")
    created_by_agent: str | None = Field(default=None)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _normalize_aliases(cls, data: Any) -> Any:
        data = _clean_neo4j_dict(data)
        if isinstance(data, dict):
            if "id" in data and "proof_id" not in data:
                data["proof_id"] = data["id"]
            if "quote" in data and "extracted_quote" not in data:
                data["extracted_quote"] = data["quote"]
            if "created_by_agent" in data and ("agent_id" not in data or data["agent_id"] == "agent"):
                data["agent_id"] = data["created_by_agent"]
            if isinstance(data.get("metrics"), str):
                import json
                try:
                    data["metrics"] = json.loads(data["metrics"])
                except Exception:
                    pass
        return data

    @property
    def id(self) -> str:
        return self.proof_id

    @property
    def quote(self) -> str | None:
        return self.extracted_quote


class Methodology(BaseModel):
    """Experimental setup, model configuration, or evaluation protocol."""
    model_config = ConfigDict(populate_by_name=True, extra="allow")

    methodology_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str = Field(..., min_length=2, description="Canonical name of the method")
    description: str = Field(default="", description="Technical specification of the protocol")
    category: MethodologyCategory = Field(default=MethodologyCategory.EVALUATION_PROTOCOL)
    hyperparameters: dict[str, Any] = Field(default_factory=dict)
    parameters: str | None = Field(default=None)
    code_url: str | None = Field(default=None)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _normalize_aliases(cls, data: Any) -> Any:
        data = _clean_neo4j_dict(data)
        if isinstance(data, dict):
            if "id" in data and "methodology_id" not in data:
                data["methodology_id"] = data["id"]
            if isinstance(data.get("hyperparameters"), str):
                import json
                try:
                    data["hyperparameters"] = json.loads(data["hyperparameters"])
                except Exception:
                    pass
        return data

    @property
    def id(self) -> str:
        return self.methodology_id


class Source(BaseModel):
    """Bibliographic source / publication grounding facts and proofs."""
    model_config = ConfigDict(populate_by_name=True, extra="allow")

    source_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str = Field(..., min_length=1, description="Publication title")
    doi: str | None = Field(default=None)
    openalex_id: str | None = Field(default=None)
    authors: list[str] = Field(default_factory=list)
    year: int | None = Field(default=None)
    venue: str | None = Field(default=None)
    url: str | None = Field(default=None)
    citation_count: int = Field(default=0, ge=0)
    citation_key: str | None = Field(default=None)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _normalize_aliases(cls, data: Any) -> Any:
        data = _clean_neo4j_dict(data)
        if isinstance(data, dict):
            if "id" in data and "source_id" not in data:
                data["source_id"] = data["id"]
        return data

    @property
    def id(self) -> str:
        return self.source_id


class Concept(BaseModel):
    """Ontological domain term or theoretical concept."""
    model_config = ConfigDict(populate_by_name=True, extra="allow")

    concept_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str = Field(..., min_length=2, description="Canonical concept name")
    definition: str = Field(default="", description="Formal scientific definition")
    domain: str | None = Field(default=None)
    aliases: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _normalize_aliases(cls, data: Any) -> Any:
        data = _clean_neo4j_dict(data)
        if isinstance(data, dict):
            if "id" in data and "concept_id" not in data:
                data["concept_id"] = data["id"]
        return data

    @property
    def id(self) -> str:
        return self.concept_id


class Dataset(BaseModel):
    """Benchmark, corpus, or evaluation set on which proofs are evaluated."""
    model_config = ConfigDict(populate_by_name=True, extra="allow")

    dataset_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str = Field(..., min_length=1, description="Canonical dataset or benchmark name")
    version: str = Field(default="1.0")
    description: str = Field(default="")
    modality: str | None = Field(default=None)
    modalities: list[str] = Field(default_factory=lambda: ["text"])
    size: str | None = Field(default=None)
    task_type: str | None = Field(default=None)
    url: str | None = Field(default=None)
    license: str | None = Field(default=None)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _normalize_aliases(cls, data: Any) -> Any:
        data = _clean_neo4j_dict(data)
        if isinstance(data, dict):
            if "id" in data and "dataset_id" not in data:
                data["dataset_id"] = data["id"]
        return data

    @property
    def id(self) -> str:
        return self.dataset_id


class Question(BaseModel):
    """Epistemic inquiry or research hypothesis motivating the graph."""
    model_config = ConfigDict(populate_by_name=True, extra="allow")

    question_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    text: str = Field(..., min_length=5, description="Question or research inquiry")
    status: str = Field(default="open")
    project_id: str = Field(default="", description="Scoping project UUID")
    session_id: str | None = Field(default=None)
    embedding: list[float] | None = Field(default=None, description="768-dim vector embedding")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _normalize_aliases(cls, data: Any) -> Any:
        data = _clean_neo4j_dict(data)
        if isinstance(data, dict):
            if "id" in data and "question_id" not in data:
                data["question_id"] = data["id"]
        return data

    @property
    def id(self) -> str:
        return self.question_id


class Limitation(BaseModel):
    """Boundary condition, failure mode, or caveat on evidence."""
    model_config = ConfigDict(populate_by_name=True, extra="allow")

    limitation_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    statement: str = Field(..., min_length=5, description="Limitation or boundary condition")
    severity: LimitationSeverity = Field(default=LimitationSeverity.MODERATE)
    category: str = Field(default="general")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _normalize_aliases(cls, data: Any) -> Any:
        data = _clean_neo4j_dict(data)
        if isinstance(data, dict):
            if "id" in data and "limitation_id" not in data:
                data["limitation_id"] = data["id"]
        return data

    @property
    def id(self) -> str:
        return self.limitation_id


class Community(BaseModel):
    """High-level thematic cluster or community summary in GraphRAG."""
    model_config = ConfigDict(populate_by_name=True, extra="allow")

    community_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str = Field(..., min_length=3, description="Cluster or community title")
    name: str | None = Field(default=None)
    summary: str = Field(default="", description="Synthesized narrative of cluster findings")
    level: int = Field(default=0, ge=0, description="Hierarchical clustering level")
    keywords: list[str] = Field(default_factory=list)
    findings: list[str] = Field(default_factory=list)
    rating: float = Field(default=1.0)
    fact_count: int = Field(default=0, ge=0)
    proof_count: int = Field(default=0, ge=0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _normalize_aliases(cls, data: Any) -> Any:
        data = _clean_neo4j_dict(data)
        if isinstance(data, dict):
            if "id" in data and "community_id" not in data:
                data["community_id"] = data["id"]
            if "name" in data and not data.get("title"):
                data["title"] = data["name"]
            elif "title" in data and not data.get("name"):
                data["name"] = data["title"]
        return data

    @property
    def id(self) -> str:
        return self.community_id


# Alias classes matching Create naming convention in architecture report
FactCreate = Fact
ProofCreate = Proof
MethodologyCreate = Methodology
SourceCreate = Source
ConceptCreate = Concept
DatasetCreate = Dataset
QuestionCreate = Question
LimitationCreate = Limitation
CommunityCreate = Community


# ============================================================================
# Relationship Models with Mandatory Rich-Text Description
# ============================================================================

class RelationshipEdge(BaseModel):
    """Base model for any edge in the graph with mandatory rich-text description."""
    model_config = ConfigDict(extra="allow")

    source_id: str = Field(..., description="Source node identifier")
    target_id: str = Field(..., description="Target node identifier")
    rel_type: str = Field(..., description="Relationship label / type")
    description: str = Field(
        ...,
        min_length=5,
        description="Mandatory rich-text explanation of context, nuance, or experimental conditions",
    )
    properties: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @model_validator(mode="before")
    @classmethod
    def _sanitize_data(cls, data: Any) -> Any:
        return _clean_neo4j_dict(data)

    @model_validator(mode="after")
    def validate_description_not_blank(self) -> "RelationshipEdge":
        if not self.description or len(self.description.strip()) < 5:
            raise ValueError("Edge description must be a non-empty rich-text explanation (at least 5 characters).")
        return self


class SupportedByRel(RelationshipEdge):
    """Edge linking Fact to Proof that supports the claim."""
    rel_type: str = Field(default=RelationshipType.SUPPORTED_BY.value)
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    strength: str = Field(default="moderate")
    agent_id: str = Field(default="agent")


class ContradictedByRel(RelationshipEdge):
    """Edge linking Fact to Proof that contradicts the claim."""
    rel_type: str = Field(default=RelationshipType.CONTRADICTED_BY.value)
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    contradiction_type: str = Field(default="empirical_divergence")
    agent_id: str = Field(default="agent")


class UsesMethodRel(RelationshipEdge):
    """Edge linking Proof or Fact to Methodology."""
    rel_type: str = Field(default=RelationshipType.USES_METHOD.value)
    role: str = Field(default="primary")


class EvaluatedOnRel(RelationshipEdge):
    """Edge linking Proof or Methodology to Dataset."""
    rel_type: str = Field(default=RelationshipType.EVALUATED_ON.value)
    split: str = Field(default="test")
    metric_value: str | None = None
    sample_size: int | None = None


class ExtractedFromRel(RelationshipEdge):
    """Edge linking Proof or Fact to Source publication."""
    rel_type: str = Field(default=RelationshipType.EXTRACTED_FROM.value)
    section: str | None = None
    page_number: str | None = None
    table_figure: str | None = None


class AddressesRel(RelationshipEdge):
    """Edge linking Fact to Question."""
    rel_type: str = Field(default=RelationshipType.ADDRESSES.value)
    relevance_score: float = Field(default=1.0, ge=0.0, le=1.0)
    is_direct_answer: bool = Field(default=True)


class RelatesToConceptRel(RelationshipEdge):
    """Edge linking Fact, Methodology, or Proof to Concept."""
    rel_type: str = Field(default=RelationshipType.RELATES_TO_CONCEPT.value)
    relation_type: str = Field(default="applies")
    prominence: float = Field(default=1.0, ge=0.0, le=1.0)


class HasLimitationRel(RelationshipEdge):
    """Edge linking Proof, Fact, or Methodology to Limitation."""
    rel_type: str = Field(default=RelationshipType.HAS_LIMITATION.value)
    impact_severity: str = Field(default="moderate")


class BelongsToCommunityRel(RelationshipEdge):
    """Edge linking Fact to Community."""
    rel_type: str = Field(default=RelationshipType.BELONGS_TO_COMMUNITY.value)
    membership_weight: float = Field(default=1.0, ge=0.0, le=1.0)


# ============================================================================
# Graph Traversal & Response Models
# ============================================================================

class SubgraphNode(BaseModel):
    """A generic node representation in a returned subgraph."""
    id: str
    labels: list[str]
    properties: dict[str, Any] = Field(default_factory=dict)


class SubgraphRelationship(BaseModel):
    """A generic directed edge representation in a returned subgraph."""
    source: str
    target: str
    type: str
    description: str
    properties: dict[str, Any] = Field(default_factory=dict)


class DebateSubgraph(BaseModel):
    """Hierarchical and structured representation of an epistemic debate."""
    central_fact: Fact
    supporting_proofs: list[Proof] = Field(default_factory=list)
    contradicting_proofs: list[Proof] = Field(default_factory=list)
    methodologies: list[Methodology] = Field(default_factory=list)
    datasets: list[Dataset] = Field(default_factory=list)
    sources: list[Source] = Field(default_factory=list)
    limitations: list[Limitation] = Field(default_factory=list)
    relationships: list[SubgraphRelationship] = Field(default_factory=list)
    nodes: list[SubgraphNode] = Field(default_factory=list)


class EpistemicClaimResult(BaseModel):
    """Atomic result of appending an epistemic claim."""
    fact: Fact
    proof: Proof
    methodology: Methodology | None = None
    dataset: Dataset | None = None
    source: Source | None = None
    relationship_type: str
    edge_description: str
    status: FactStatus

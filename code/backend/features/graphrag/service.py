"""EpistemicGraphService: Async API wrapper for autonomous agents to interact with GraphRAG.

Provides non-destructive, append-only knowledge graph manipulation, atomic composite
epistemic assertions, rich-text relationship validation, and depth-2 debate subgraph retrieval.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from core.db.neo4j_service import Neo4jService
from features.graphrag.conflict import (
    calculate_epistemic_status,
    validate_edge_confidence,
    validate_relationship_type,
    validate_rich_description,
    verify_append_only_transition,
)
from features.graphrag.models import (
    Community,
    Concept,
    Dataset,
    DebateSubgraph,
    EpistemicClaimResult,
    Fact,
    FactStatus,
    Limitation,
    Methodology,
    Proof,
    ProofPolarity,
    Question,
    RelationshipEdge,
    RelationshipType,
    Source,
    SubgraphNode,
    SubgraphRelationship,
)
from features.graphrag.queries import (
    ATOMIC_COMPOSITE_CLAIM,
    GET_CONNECTED_PROOFS_FOR_FACT,
    GET_DEBATE_SUBGRAPH_DEPTH1,
    GET_DEBATE_SUBGRAPH_DEPTH2,
    GET_FACT,
    GET_NODE_BY_ID,
    LINK_FACT_TO_COMMUNITY,
    LINK_FACT_TO_CONTRADICTING_PROOF,
    LINK_FACT_TO_QUESTION,
    LINK_FACT_TO_SUPPORTING_PROOF,
    LINK_PROOF_TO_DATASET,
    LINK_PROOF_TO_METHODOLOGY,
    LINK_TO_CONCEPT,
    LINK_TO_LIMITATION,
    LINK_TO_SOURCE,
    LIST_CONTESTED_FACTS,
    MERGE_COMMUNITY,
    MERGE_CONCEPT,
    MERGE_DATASET,
    MERGE_FACT,
    MERGE_LIMITATION,
    MERGE_METHODOLOGY,
    MERGE_PROOF,
    MERGE_QUESTION,
    MERGE_SOURCE,
    UPDATE_FACT_STATUS,
)
from features.graphrag.schema import init_graphrag_schema

logger = logging.getLogger(__name__)


def _sanitize_neo4j_dict(d: Any) -> Any:
    """Recursively convert neo4j specific scalar types (e.g. neo4j.time.DateTime) to standard python types."""
    if isinstance(d, dict):
        out = {}
        for k, v in d.items():
            if hasattr(v, "to_native"):
                out[k] = v.to_native()
            elif isinstance(v, (dict, list)):
                out[k] = _sanitize_neo4j_dict(v)
            else:
                out[k] = v
        return out
    elif isinstance(d, list):
        return [_sanitize_neo4j_dict(v) for v in d]
    elif hasattr(d, "to_native"):
        return d.to_native()
    return d


class EpistemicGraphService:
    """Async API wrapper for the Epistemic Fact Graph (GraphRAG) backend."""

    def __init__(self, neo4j: Neo4jService) -> None:
        self._neo4j = neo4j

    async def initialize_schema(self, embedding_dimensions: int = 768) -> None:
        """Initialize all GraphRAG DDL constraints, B-Tree indexes, and vector indexes."""
        await init_graphrag_schema(self._neo4j, embedding_dimensions)

    # ========================================================================
    # 9 Node Creation & Append Methods
    # ========================================================================

    async def append_fact(self, fact: Fact) -> str:
        """Append or merge a central Fact node into the epistemic graph.

        Enforces 100% append-only immutability: attempting to mutate an existing
        fact's propositional statement raises EpistemicIntegrityError.
        """
        existing = await self.get_fact(fact.fact_id)
        if existing is not None:
            verify_append_only_transition(existing.statement, fact.statement)

        params = {
            "fact_id": fact.fact_id,
            "statement": fact.statement,
            "status": fact.status.value if isinstance(fact.status, FactStatus) else str(fact.status),
            "confidence_score": float(fact.confidence_score),
            "domain": fact.domain,
            "project_id": fact.project_id,
            "embedding": fact.embedding,
            "embedding_model": fact.embedding_model,
            "created_by_agent": fact.created_by_agent,
        }
        records = await self._neo4j.execute_write(MERGE_FACT, params)
        logger.info("Appended Fact node %s", fact.fact_id)
        return str(records[0]["fact_id"]) if records else fact.fact_id

    async def create_fact(self, fact: Fact) -> dict[str, Any]:
        """Alias for append_fact returning dict representation."""
        fid = await self.append_fact(fact)
        node = await self.get_node_by_id(fid)
        return node["properties"] if node else fact.model_dump()

    async def append_proof(
        self,
        proof: Proof,
        fact_id: str | None = None,
        relationship_type: str | None = None,
        description: str | None = None,
        confidence: float = 0.8,
        agent_id: str = "agent",
    ) -> str:
        """Append an empirical or theoretical Proof node.
        
        If fact_id, relationship_type, and description are passed, atomically
        links the Proof to the Fact and recalculates the Fact's epistemic status.
        """
        params = {
            "proof_id": proof.proof_id,
            "summary": proof.summary,
            "polarity": proof.polarity.value if isinstance(proof.polarity, ProofPolarity) else str(proof.polarity),
            "proof_type": proof.proof_type.value if hasattr(proof.proof_type, "value") else str(proof.proof_type),
            "confidence": float(proof.confidence),
            "extracted_quote": proof.extracted_quote,
            "metrics": json.dumps(proof.metrics) if isinstance(proof.metrics, dict) else (proof.metrics or "{}"),
            "location": proof.location,
            "source_paper_id": proof.source_paper_id,
            "agent_id": proof.agent_id or agent_id,
        }
        records = await self._neo4j.execute_write(MERGE_PROOF, params)
        pid = str(records[0]["proof_id"]) if records else proof.proof_id
        logger.info("Appended Proof node %s", pid)

        if fact_id and relationship_type and description:
            await self.link_fact_to_proof(
                fact_id=fact_id,
                proof_id=pid,
                polarity=relationship_type,
                description=description,
                confidence=confidence,
                agent_id=proof.agent_id or agent_id,
            )

        return pid

    async def create_proof(self, proof: Proof) -> dict[str, Any]:
        """Alias for append_proof returning dict representation."""
        pid = await self.append_proof(proof)
        node = await self.get_node_by_id(pid)
        return node["properties"] if node else proof.model_dump()

    async def append_methodology(self, methodology: Methodology) -> str:
        """Append or merge a Methodology protocol node."""
        params = {
            "methodology_id": methodology.methodology_id,
            "name": methodology.name,
            "description": methodology.description,
            "category": methodology.category.value if hasattr(methodology.category, "value") else str(methodology.category),
            "hyperparameters": json.dumps(methodology.hyperparameters) if isinstance(methodology.hyperparameters, dict) else (methodology.hyperparameters or "{}"),
            "code_url": methodology.code_url,
        }
        records = await self._neo4j.execute_write(MERGE_METHODOLOGY, params)
        mid = str(records[0]["methodology_id"]) if records else methodology.methodology_id
        logger.info("Appended Methodology node %s", mid)
        return mid

    async def create_methodology(self, methodology: Methodology) -> dict[str, Any]:
        mid = await self.append_methodology(methodology)
        node = await self.get_node_by_id(mid)
        return node["properties"] if node else methodology.model_dump()

    async def append_source(self, source: Source) -> str:
        """Append or merge a publication Source node."""
        params = {
            "source_id": source.source_id,
            "title": source.title,
            "doi": source.doi,
            "openalex_id": source.openalex_id,
            "authors": source.authors,
            "year": source.year,
            "venue": source.venue,
            "url": source.url,
            "citation_count": source.citation_count,
        }
        records = await self._neo4j.execute_write(MERGE_SOURCE, params)
        sid = str(records[0]["source_id"]) if records else source.source_id
        logger.info("Appended Source node %s", sid)
        return sid

    async def create_source(self, source: Source) -> dict[str, Any]:
        sid = await self.append_source(source)
        node = await self.get_node_by_id(sid)
        return node["properties"] if node else source.model_dump()

    async def append_concept(self, concept: Concept) -> str:
        """Append or merge an ontological Concept node."""
        params = {
            "concept_id": concept.concept_id,
            "name": concept.name,
            "definition": concept.definition,
            "domain": concept.domain,
            "aliases": concept.aliases,
        }
        records = await self._neo4j.execute_write(MERGE_CONCEPT, params)
        cid = str(records[0]["concept_id"]) if records else concept.concept_id
        logger.info("Appended Concept node %s", cid)
        return cid

    async def create_concept(self, concept: Concept) -> dict[str, Any]:
        cid = await self.append_concept(concept)
        node = await self.get_node_by_id(cid)
        return node["properties"] if node else concept.model_dump()

    async def append_dataset(self, dataset: Dataset) -> str:
        """Append or merge an evaluation Dataset benchmark node."""
        params = {
            "dataset_id": dataset.dataset_id,
            "name": dataset.name,
            "version": dataset.version,
            "description": dataset.description,
            "modality": dataset.modality,
            "modalities": dataset.modalities,
            "size": dataset.size,
            "task_type": dataset.task_type,
            "url": dataset.url,
            "license": dataset.license,
        }
        records = await self._neo4j.execute_write(MERGE_DATASET, params)
        did = str(records[0]["dataset_id"]) if records else dataset.dataset_id
        logger.info("Appended Dataset node %s", did)
        return did

    async def create_dataset(self, dataset: Dataset) -> dict[str, Any]:
        did = await self.append_dataset(dataset)
        node = await self.get_node_by_id(did)
        return node["properties"] if node else dataset.model_dump()

    async def append_question(self, question: Question) -> str:
        """Append or merge an epistemic Question node."""
        params = {
            "question_id": question.question_id,
            "text": question.text,
            "status": question.status,
            "project_id": question.project_id,
            "session_id": question.session_id,
            "embedding": question.embedding,
        }
        records = await self._neo4j.execute_write(MERGE_QUESTION, params)
        qid = str(records[0]["question_id"]) if records else question.question_id
        logger.info("Appended Question node %s", qid)
        return qid

    async def create_question(self, question: Question) -> dict[str, Any]:
        qid = await self.append_question(question)
        node = await self.get_node_by_id(qid)
        return node["properties"] if node else question.model_dump()

    async def append_limitation(self, limitation: Limitation) -> str:
        """Append or merge a Limitation caveat node."""
        params = {
            "limitation_id": limitation.limitation_id,
            "statement": limitation.statement,
            "severity": limitation.severity.value if hasattr(limitation.severity, "value") else str(limitation.severity),
            "category": limitation.category,
        }
        records = await self._neo4j.execute_write(MERGE_LIMITATION, params)
        lid = str(records[0]["limitation_id"]) if records else limitation.limitation_id
        logger.info("Appended Limitation node %s", lid)
        return lid

    async def create_limitation(self, limitation: Limitation) -> dict[str, Any]:
        lid = await self.append_limitation(limitation)
        node = await self.get_node_by_id(lid)
        return node["properties"] if node else limitation.model_dump()

    async def append_community(self, community: Community) -> str:
        """Append or merge a Community cluster node."""
        params = {
            "community_id": community.community_id,
            "title": community.title,
            "name": community.name or community.title,
            "summary": community.summary,
            "level": int(community.level),
            "keywords": community.keywords,
            "findings": community.findings,
            "rating": float(community.rating),
            "fact_count": int(community.fact_count),
            "proof_count": int(community.proof_count),
        }
        records = await self._neo4j.execute_write(MERGE_COMMUNITY, params)
        cmid = str(records[0]["community_id"]) if records else community.community_id
        logger.info("Appended Community node %s", cmid)
        return cmid

    async def create_community(self, community: Community) -> dict[str, Any]:
        cmid = await self.append_community(community)
        node = await self.get_node_by_id(cmid)
        return node["properties"] if node else community.model_dump()

    # ========================================================================
    # Relationship Linking with Mandatory Rich-Text Description
    # ========================================================================

    async def link_fact_to_proof(
        self,
        fact_id: str,
        proof_id: str,
        polarity: str | ProofPolarity,
        description: str,
        confidence: float = 0.8,
        agent_id: str = "agent",
        **extra_attrs: Any,
    ) -> bool:
        """Link Fact to Proof via SUPPORTED_BY or CONTRADICTED_BY edge with mandatory description."""
        validate_rich_description(description)
        valid_confidence = validate_edge_confidence(confidence)

        pol_str = (polarity.value if isinstance(polarity, ProofPolarity) else str(polarity)).strip().upper()
        if pol_str in ("SUPPORTS", "SUPPORTED_BY"):
            query = LINK_FACT_TO_SUPPORTING_PROOF
            params = {
                "fact_id": fact_id,
                "proof_id": proof_id,
                "description": description,
                "confidence": valid_confidence,
                "strength": extra_attrs.get("strength", "conclusive"),
                "agent_id": agent_id,
            }
        elif pol_str in ("CONTRADICTS", "CONTRADICTED_BY"):
            query = LINK_FACT_TO_CONTRADICTING_PROOF
            params = {
                "fact_id": fact_id,
                "proof_id": proof_id,
                "description": description,
                "confidence": valid_confidence,
                "contradiction_type": extra_attrs.get("contradiction_type", "empirical_divergence"),
                "agent_id": agent_id,
            }
        else:
            raise ValueError(f"Polarity must be SUPPORTS or CONTRADICTS. Got: {polarity}")

        records = await self._neo4j.execute_write(query, params)
        if not records:
            logger.warning(
                "Failed to link Fact '%s' to Proof '%s': source or target node does not exist in graph.",
                fact_id,
                proof_id,
            )
            return False

        # Recalculate Fact epistemic status dynamically only when link succeeded
        await self.resolve_fact_status(fact_id)
        return True

    async def link_proof_to_methodology(
        self,
        proof_id: str,
        methodology_id: str,
        description: str,
        role: str = "primary",
    ) -> bool:
        """Link Proof to Methodology via USES_METHOD with mandatory description."""
        validate_rich_description(description)
        params = {
            "proof_id": proof_id,
            "methodology_id": methodology_id,
            "description": description,
            "role": role,
        }
        records = await self._neo4j.execute_write(LINK_PROOF_TO_METHODOLOGY, params)
        if not records:
            logger.warning(
                "Failed to link Proof '%s' to Methodology '%s': source or target node does not exist.",
                proof_id,
                methodology_id,
            )
            return False
        return True

    async def link_proof_to_dataset(
        self,
        proof_id: str,
        dataset_id: str,
        description: str,
        split: str = "test",
        metric_value: str | None = None,
        sample_size: int | None = None,
    ) -> bool:
        """Link Proof to Dataset via EVALUATED_ON with mandatory description."""
        validate_rich_description(description)
        params = {
            "proof_id": proof_id,
            "dataset_id": dataset_id,
            "description": description,
            "split": split,
            "metric_value": metric_value,
            "sample_size": sample_size,
        }
        records = await self._neo4j.execute_write(LINK_PROOF_TO_DATASET, params)
        if not records:
            logger.warning(
                "Failed to link Proof '%s' to Dataset '%s': source or target node does not exist.",
                proof_id,
                dataset_id,
            )
            return False
        return True

    async def link_to_source(
        self,
        source_id: str,
        target_source_id: str,
        description: str,
        section: str | None = None,
        page_number: str | None = None,
        table_figure: str | None = None,
    ) -> bool:
        """Link Proof or Fact to Source publication via EXTRACTED_FROM with mandatory description."""
        validate_rich_description(description)
        params = {
            "source_id": source_id,
            "target_id": target_source_id,
            "description": description,
            "section": section,
            "page_number": page_number,
            "table_figure": table_figure,
        }
        records = await self._neo4j.execute_write(LINK_TO_SOURCE, params)
        if not records:
            logger.warning(
                "Failed to link entity '%s' to Source '%s': source or target node does not exist.",
                source_id,
                target_source_id,
            )
            return False
        return True

    async def link_fact_to_question(
        self,
        fact_id: str,
        question_id: str,
        description: str,
        relevance_score: float = 1.0,
        is_direct_answer: bool = True,
    ) -> bool:
        """Link Fact to Question via ADDRESSES with mandatory description."""
        validate_rich_description(description)
        params = {
            "fact_id": fact_id,
            "question_id": question_id,
            "description": description,
            "relevance_score": float(relevance_score),
            "is_direct_answer": bool(is_direct_answer),
        }
        records = await self._neo4j.execute_write(LINK_FACT_TO_QUESTION, params)
        if not records:
            logger.warning(
                "Failed to link Fact '%s' to Question '%s': source or target node does not exist.",
                fact_id,
                question_id,
            )
            return False
        return True

    async def link_to_concept(
        self,
        source_id: str,
        concept_id: str,
        description: str,
        relation_type: str = "applies",
        prominence: float = 1.0,
    ) -> bool:
        """Link Fact, Methodology, or Proof to Concept via RELATES_TO_CONCEPT with mandatory description."""
        validate_rich_description(description)
        params = {
            "source_id": source_id,
            "concept_id": concept_id,
            "description": description,
            "relation_type": relation_type,
            "prominence": float(prominence),
        }
        records = await self._neo4j.execute_write(LINK_TO_CONCEPT, params)
        if not records:
            logger.warning(
                "Failed to link entity '%s' to Concept '%s': source or target node does not exist.",
                source_id,
                concept_id,
            )
            return False
        return True

    async def link_to_limitation(
        self,
        source_id: str,
        limitation_id: str,
        description: str,
        impact_severity: str = "moderate",
    ) -> bool:
        """Link Proof, Fact, or Methodology to Limitation via HAS_LIMITATION with mandatory description."""
        validate_rich_description(description)
        params = {
            "source_id": source_id,
            "limitation_id": limitation_id,
            "description": description,
            "impact_severity": impact_severity,
        }
        records = await self._neo4j.execute_write(LINK_TO_LIMITATION, params)
        if not records:
            logger.warning(
                "Failed to link entity '%s' to Limitation '%s': source or target node does not exist.",
                source_id,
                limitation_id,
            )
            return False
        return True

    async def link_fact_to_community(
        self,
        fact_id: str,
        community_id: str,
        description: str,
        membership_weight: float = 1.0,
    ) -> bool:
        """Link Fact to Community via BELONGS_TO_COMMUNITY with mandatory description."""
        validate_rich_description(description)
        params = {
            "fact_id": fact_id,
            "community_id": community_id,
            "description": description,
            "membership_weight": float(membership_weight),
        }
        records = await self._neo4j.execute_write(LINK_FACT_TO_COMMUNITY, params)
        if not records:
            logger.warning(
                "Failed to link Fact '%s' to Community '%s': source or target node does not exist.",
                fact_id,
                community_id,
            )
            return False
        return True

    async def link_nodes(
        self,
        source_id: str,
        target_id: str,
        rel_type: str,
        description: str,
        **properties: Any,
    ) -> bool:
        """Generic relationship creation validating non-empty description and allowed rel types."""
        validate_rich_description(description)
        norm_type = validate_relationship_type(rel_type)

        if norm_type == RelationshipType.SUPPORTED_BY.value:
            return await self.link_fact_to_proof(
                fact_id=source_id,
                proof_id=target_id,
                polarity=ProofPolarity.SUPPORTS,
                description=description,
                **properties,
            )
        elif norm_type == RelationshipType.CONTRADICTED_BY.value:
            return await self.link_fact_to_proof(
                fact_id=source_id,
                proof_id=target_id,
                polarity=ProofPolarity.CONTRADICTS,
                description=description,
                **properties,
            )
        elif norm_type == RelationshipType.USES_METHOD.value:
            return await self.link_proof_to_methodology(
                proof_id=source_id,
                methodology_id=target_id,
                description=description,
                role=properties.get("role", "primary"),
            )
        elif norm_type == RelationshipType.EVALUATED_ON.value:
            return await self.link_proof_to_dataset(
                proof_id=source_id,
                dataset_id=target_id,
                description=description,
                split=properties.get("split", "test"),
                metric_value=properties.get("metric_value"),
                sample_size=properties.get("sample_size"),
            )
        elif norm_type == RelationshipType.EXTRACTED_FROM.value:
            return await self.link_to_source(
                source_id=source_id,
                target_source_id=target_id,
                description=description,
                section=properties.get("section"),
                page_number=properties.get("page_number"),
                table_figure=properties.get("table_figure"),
            )
        elif norm_type == RelationshipType.ADDRESSES.value:
            return await self.link_fact_to_question(
                fact_id=source_id,
                question_id=target_id,
                description=description,
                relevance_score=properties.get("relevance_score", 1.0),
                is_direct_answer=properties.get("is_direct_answer", True),
            )
        elif norm_type == RelationshipType.RELATES_TO_CONCEPT.value:
            return await self.link_to_concept(
                source_id=source_id,
                concept_id=target_id,
                description=description,
                relation_type=properties.get("relation_type", "applies"),
                prominence=properties.get("prominence", 1.0),
            )
        elif norm_type == RelationshipType.HAS_LIMITATION.value:
            return await self.link_to_limitation(
                source_id=source_id,
                limitation_id=target_id,
                description=description,
                impact_severity=properties.get("impact_severity", "moderate"),
            )
        elif norm_type == RelationshipType.BELONGS_TO_COMMUNITY.value:
            return await self.link_fact_to_community(
                fact_id=source_id,
                community_id=target_id,
                description=description,
                membership_weight=properties.get("membership_weight", 1.0),
            )

        raise ValueError(f"Unsupported relationship type: {norm_type}")

    # ========================================================================
    # Atomic Composite Epistemic Claim Ingestion
    # ========================================================================

    async def append_epistemic_claim(
        self,
        fact: Fact,
        proof: Proof,
        relationship_type: str,
        edge_description: str,
        methodology: Methodology | None = None,
        method_description: str | None = None,
        dataset: Dataset | None = None,
        dataset_description: str | None = None,
        source: Source | None = None,
        source_description: str | None = None,
    ) -> EpistemicClaimResult:
        """Atomically persist Fact, Proof, Methodology, Dataset, and Rich Edges in one Cypher transaction.

        Enforces 100% append-only immutability: attempting to mutate an existing
        fact's propositional statement raises EpistemicIntegrityError.
        """
        validate_rich_description(edge_description)
        norm_rel = validate_relationship_type(relationship_type)
        if norm_rel not in (RelationshipType.SUPPORTED_BY.value, RelationshipType.CONTRADICTED_BY.value):
            raise ValueError(f"Atomic claim relationship must be SUPPORTED_BY or CONTRADICTED_BY. Got: {norm_rel}")

        existing = await self.get_fact(fact.fact_id)
        if existing is not None:
            verify_append_only_transition(existing.statement, fact.statement)

        has_method = methodology is not None
        has_dataset = dataset is not None
        has_source = source is not None

        if has_method and not method_description:
            method_description = f"Employed methodology '{methodology.name}' during evaluation"
        if has_dataset and not dataset_description:
            dataset_description = f"Evaluated on benchmark dataset '{dataset.name}'"
        if has_source and not source_description:
            source_description = f"Extracted from literature source '{source.title}'"

        if method_description:
            validate_rich_description(method_description)
        if dataset_description:
            validate_rich_description(dataset_description)
        if source_description:
            validate_rich_description(source_description)

        params: dict[str, Any] = {
            "fact": {
                "fact_id": fact.fact_id,
                "statement": fact.statement,
                "status": fact.status.value if isinstance(fact.status, FactStatus) else str(fact.status),
                "confidence_score": float(fact.confidence_score),
                "domain": fact.domain,
                "project_id": fact.project_id,
            },
            "proof": {
                "proof_id": proof.proof_id,
                "summary": proof.summary,
                "polarity": proof.polarity.value if isinstance(proof.polarity, ProofPolarity) else str(proof.polarity),
                "proof_type": proof.proof_type.value if hasattr(proof.proof_type, "value") else str(proof.proof_type),
                "confidence": float(proof.confidence),
                "extracted_quote": proof.extracted_quote,
                "metrics": json.dumps(proof.metrics) if isinstance(proof.metrics, dict) else (proof.metrics or "{}"),
                "location": proof.location,
                "source_paper_id": proof.source_paper_id,
                "agent_id": proof.agent_id,
            },
            "rel_type": norm_rel,
            "edge_description": edge_description,
            "has_method": has_method,
            "method": {
                "methodology_id": methodology.methodology_id if methodology else "",
                "name": methodology.name if methodology else "",
                "description": methodology.description if methodology else "",
                "category": (methodology.category.value if hasattr(methodology.category, "value") else str(methodology.category)) if methodology else "",
                "hyperparameters": json.dumps(methodology.hyperparameters) if (methodology and isinstance(methodology.hyperparameters, dict)) else "{}",
            },
            "method_rel_description": method_description or "",
            "has_dataset": has_dataset,
            "dataset": {
                "dataset_id": dataset.dataset_id if dataset else "",
                "name": dataset.name if dataset else "",
                "version": dataset.version if dataset else "1.0",
                "description": dataset.description if dataset else "",
            },
            "dataset_rel_description": dataset_description or "",
            "has_source": has_source,
            "source": {
                "source_id": source.source_id if source else "",
                "title": source.title if source else "",
                "doi": source.doi if source else "",
            },
            "source_rel_description": source_description or "",
        }

        await self._neo4j.execute_write(ATOMIC_COMPOSITE_CLAIM, params)

        # Recalculate status
        new_status, new_conf = await self.resolve_fact_status(fact.fact_id)
        updated_fact = await self.get_fact(fact.fact_id) or fact
        updated_fact.status = new_status
        updated_fact.confidence_score = new_conf

        return EpistemicClaimResult(
            fact=updated_fact,
            proof=proof,
            methodology=methodology,
            dataset=dataset,
            source=source,
            relationship_type=norm_rel,
            edge_description=edge_description,
            status=new_status,
        )

    # ========================================================================
    # Epistemic Conflict Resolution & State Calculation
    # ========================================================================

    async def resolve_fact_status(self, fact_id: str) -> tuple[FactStatus, float]:
        """Recalculate and update the epistemic status of a Fact without destructive overwriting."""
        records = await self._neo4j.execute_read(GET_CONNECTED_PROOFS_FOR_FACT, {"fact_id": fact_id})
        new_status, new_confidence = calculate_epistemic_status(records)

        await self._neo4j.execute_write(
            UPDATE_FACT_STATUS,
            {
                "fact_id": fact_id,
                "status": new_status.value,
                "confidence_score": new_confidence,
            },
        )
        logger.info("Fact %s status resolved: %s (confidence: %.2f)", fact_id, new_status.value, new_confidence)
        return new_status, new_confidence

    async def recompute_fact_epistemic_status(self, fact_id: str) -> FactStatus:
        """Alias returning only the FactStatus enum."""
        status, _ = await self.resolve_fact_status(fact_id)
        return status

    # ========================================================================
    # Graph Traversal & Subgraph Queries
    # ========================================================================

    async def get_fact(self, fact_id: str) -> Fact | None:
        """Fetch a single Fact node by its ID."""
        records = await self._neo4j.execute_read(GET_FACT, {"fact_id": fact_id})
        if not records or not records[0].get("properties"):
            return None
        props = _sanitize_neo4j_dict(records[0]["properties"])
        return Fact(**props)

    async def get_node_by_id(self, node_id: str) -> dict[str, Any] | None:
        """Lookup any node in the epistemic graph by its identifier."""
        records = await self._neo4j.execute_read(GET_NODE_BY_ID, {"id": node_id})
        if not records:
            return None
        return {
            "labels": records[0].get("labels", []),
            "properties": _sanitize_neo4j_dict(records[0].get("properties", {})),
        }

    async def get_debate_subgraph(self, fact_id: str, depth: int = 2) -> DebateSubgraph:
        """Retrieve the central Fact and either depth-1 or depth-2 neighborhood.

        Args:
            fact_id: Identifier of the central Fact.
            depth: Traversal depth (1 or 2).
                - depth=1: Fact, immediate proofs (supporting/contradicting), and 1-hop edges.
                - depth=2: Fact, proofs, plus 2-hop methodologies, datasets, sources, limitations.

        Returns:
            DebateSubgraph model representing the dialectical graph.

        Raises:
            ValueError: If fact_id does not exist or depth is not 1 or 2.
        """
        if depth not in (1, 2):
            raise ValueError(f"Invalid subgraph depth: {depth}. Supported depths are 1 and 2.")

        query = GET_DEBATE_SUBGRAPH_DEPTH1 if depth == 1 else GET_DEBATE_SUBGRAPH_DEPTH2
        records = await self._neo4j.execute_read(query, {"fact_id": fact_id})
        if not records or not records[0].get("fact"):
            raise ValueError(f"Fact with ID '{fact_id}' does not exist.")

        fact_dict = _sanitize_neo4j_dict(records[0]["fact"])
        central_fact = Fact(**fact_dict)

        supporting_proofs: dict[str, Proof] = {}
        contradicting_proofs: dict[str, Proof] = {}
        methodologies: dict[str, Methodology] = {}
        datasets: dict[str, Dataset] = {}
        sources: dict[str, Source] = {}
        limitations: dict[str, Limitation] = {}

        unique_nodes: dict[str, SubgraphNode] = {
            central_fact.fact_id: SubgraphNode(
                id=central_fact.fact_id,
                labels=["Fact"],
                properties=fact_dict,
            )
        }
        unique_relationships: dict[tuple[str, str, str], SubgraphRelationship] = {}

        for row in records:
            p_props = _sanitize_neo4j_dict(row.get("proof"))
            r1_type = row.get("r1_type")
            r1_props = _sanitize_neo4j_dict(row.get("r1_props")) or {}

            # Hop 1: Proof
            if p_props and r1_type:
                pid = p_props.get("proof_id")
                if pid:
                    proof_obj = Proof(**p_props)
                    if r1_type == "SUPPORTED_BY":
                        supporting_proofs[pid] = proof_obj
                    elif r1_type == "CONTRADICTED_BY":
                        contradicting_proofs[pid] = proof_obj

                    unique_nodes[pid] = SubgraphNode(
                        id=pid,
                        labels=["Proof"],
                        properties=p_props,
                    )
                    edge_key = (central_fact.fact_id, pid, r1_type)
                    unique_relationships[edge_key] = SubgraphRelationship(
                        source=central_fact.fact_id,
                        target=pid,
                        type=r1_type,
                        description=r1_props.get("description", ""),
                        properties=r1_props,
                    )

            # Hop 2: Depth-2 Targets (Only processed when depth >= 2)
            if depth >= 2:
                t_props = _sanitize_neo4j_dict(row.get("target"))
                r2_type = row.get("r2_type")
                r2_props = _sanitize_neo4j_dict(row.get("r2_props")) or {}
                t_labels = row.get("target_labels") or []

                if p_props and t_props and r2_type:
                    pid = p_props.get("proof_id")
                    target_id = (
                        t_props.get("methodology_id")
                        or t_props.get("dataset_id")
                        or t_props.get("source_id")
                        or t_props.get("limitation_id")
                        or t_props.get("concept_id")
                    )
                    if target_id and pid:
                        if "Methodology" in t_labels:
                            methodologies[target_id] = Methodology(**t_props)
                        elif "Dataset" in t_labels:
                            datasets[target_id] = Dataset(**t_props)
                        elif "Source" in t_labels:
                            sources[target_id] = Source(**t_props)
                        elif "Limitation" in t_labels:
                            limitations[target_id] = Limitation(**t_props)

                        unique_nodes[target_id] = SubgraphNode(
                            id=target_id,
                            labels=t_labels,
                            properties=t_props,
                        )
                        edge_key = (pid, target_id, r2_type)
                        unique_relationships[edge_key] = SubgraphRelationship(
                            source=pid,
                            target=target_id,
                            type=r2_type,
                            description=r2_props.get("description", ""),
                            properties=r2_props,
                        )

            # Fact contexts (Concept, Question, Community, direct Limitation, direct Source)
            ctx_props = _sanitize_neo4j_dict(row.get("ctx"))
            r3_type = row.get("r3_type")
            r3_props = _sanitize_neo4j_dict(row.get("r3_props")) or {}
            ctx_labels = row.get("ctx_labels") or []

            if ctx_props and r3_type:
                ctx_id = (
                    ctx_props.get("concept_id")
                    or ctx_props.get("question_id")
                    or ctx_props.get("community_id")
                    or ctx_props.get("limitation_id")
                    or ctx_props.get("source_id")
                )
                if ctx_id:
                    if "Limitation" in ctx_labels and ctx_id not in limitations:
                        limitations[ctx_id] = Limitation(**ctx_props)
                    elif "Source" in ctx_labels and ctx_id not in sources:
                        sources[ctx_id] = Source(**ctx_props)

                    unique_nodes[ctx_id] = SubgraphNode(
                        id=ctx_id,
                        labels=ctx_labels,
                        properties=ctx_props,
                    )
                    edge_key = (central_fact.fact_id, ctx_id, r3_type)
                    unique_relationships[edge_key] = SubgraphRelationship(
                        source=central_fact.fact_id,
                        target=ctx_id,
                        type=r3_type,
                        description=r3_props.get("description", ""),
                        properties=r3_props,
                    )

        return DebateSubgraph(
            central_fact=central_fact,
            supporting_proofs=list(supporting_proofs.values()),
            contradicting_proofs=list(contradicting_proofs.values()),
            methodologies=list(methodologies.values()),
            datasets=list(datasets.values()),
            sources=list(sources.values()),
            limitations=list(limitations.values()),
            relationships=list(unique_relationships.values()),
            nodes=list(unique_nodes.values()),
        )

    async def query_epistemic_debate(self, fact_id: str, depth: int = 2) -> DebateSubgraph:
        """Alias for get_debate_subgraph supporting depth configuration."""
        return await self.get_debate_subgraph(fact_id, depth=depth)

    async def list_contested_facts(self, project_id: str | None = None) -> list[dict[str, Any]]:
        """Retrieve all facts characterized by active scientific debate."""
        return await self._neo4j.execute_read(LIST_CONTESTED_FACTS, {"project_id": project_id})

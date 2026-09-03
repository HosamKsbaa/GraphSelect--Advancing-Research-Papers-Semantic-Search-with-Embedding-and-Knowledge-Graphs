"""Comprehensive test suite for EpistemicGraphService API wrapper.

Covers:
1. Node CRUD and merge operations for all 9 node types.
2. Edge linking methods with mandatory rich-text descriptions.
3. Validation errors on invalid edge descriptions or unknown relationship types.
4. Conflict resolution state machine calculations (tentative, supported, consensus, debated, refuted).
5. Append-only integrity verification.
6. ServiceRegistry integration (registry.graphrag).
"""
from __future__ import annotations

import uuid
import pytest
import pytest_asyncio
from pydantic import ValidationError

from agents._service_registry import ServiceRegistry, registry
from core.db.neo4j_service import Neo4jService
from features.graphrag.conflict import (
    EpistemicIntegrityError,
    InvalidRelationshipError,
    calculate_epistemic_status,
    validate_relationship_type,
    validate_rich_description,
    verify_append_only_transition,
)
from features.graphrag.models import (
    Community,
    Concept,
    Dataset,
    Fact,
    FactStatus,
    Limitation,
    LimitationSeverity,
    Methodology,
    MethodologyCategory,
    Proof,
    ProofPolarity,
    ProofType,
    Question,
    Source,
)
from features.graphrag.service import EpistemicGraphService

NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASS = "changeme"


@pytest_asyncio.fixture(scope="function")
async def service() -> EpistemicGraphService:
    """Fixture providing EpistemicGraphService connected to live Neo4j with scoped cleanup."""
    neo4j = Neo4jService(NEO4J_URI, NEO4J_USER, NEO4J_PASS)
    await neo4j.connect()
    graph_service = EpistemicGraphService(neo4j)
    await graph_service.initialize_schema()
    yield graph_service

    # Scoped cleanup for test_srv_ prefixed nodes
    await neo4j.execute_write(
        """
        MATCH (n)
        WHERE (n.fact_id STARTS WITH 'test_srv_'
            OR n.proof_id STARTS WITH 'test_srv_'
            OR n.methodology_id STARTS WITH 'test_srv_'
            OR n.source_id STARTS WITH 'test_srv_'
            OR n.concept_id STARTS WITH 'test_srv_'
            OR n.dataset_id STARTS WITH 'test_srv_'
            OR n.question_id STARTS WITH 'test_srv_'
            OR n.limitation_id STARTS WITH 'test_srv_'
            OR n.community_id STARTS WITH 'test_srv_')
        DETACH DELETE n
        """
    )
    await neo4j.close()


class TestEpistemicGraphServiceNodeCRUD:
    """Tests for all 9 node type creation and append operations."""

    @pytest.mark.asyncio
    async def test_all_9_nodes_creation(self, service: EpistemicGraphService) -> None:
        tag = uuid.uuid4().hex[:8]

        # 1. Fact
        fid = f"test_srv_fact_{tag}"
        f = Fact(fact_id=fid, statement="FlashAttention reduces memory footprint from quadratic to linear in sequence length.")
        f_res = await service.append_fact(f)
        assert f_res == fid
        fact_node = await service.get_fact(fid)
        assert fact_node is not None
        assert fact_node.fact_id == fid
        assert fact_node.status == FactStatus.TENTATIVE

        # 2. Proof
        pid = f"test_srv_proof_{tag}"
        p = Proof(proof_id=pid, summary="IO-awareness enables tiling attention blocks into SRAM.", polarity=ProofPolarity.SUPPORTS)
        p_res = await service.append_proof(p)
        assert p_res == pid

        # 3. Methodology
        mid = f"test_srv_method_{tag}"
        m = Methodology(methodology_id=mid, name="Tiled-SRAM-Kernel", description="Custom CUDA kernel tiling Q, K, V.")
        m_res = await service.append_methodology(m)
        assert m_res == mid

        # 4. Source
        sid = f"test_srv_source_{tag}"
        s = Source(source_id=sid, title="FlashAttention: Fast and Memory-Efficient Exact Attention with IO-Awareness", year=2022)
        s_res = await service.append_source(s)
        assert s_res == sid

        # 5. Concept
        cid = f"test_srv_concept_{tag}"
        c = Concept(concept_id=cid, name=f"IO-Complexity-{tag}", definition="Analysis of memory reads and writes across hierarchies.")
        c_res = await service.append_concept(c)
        assert c_res == cid

        # 6. Dataset
        did = f"test_srv_dataset_{tag}"
        d = Dataset(dataset_id=did, name=f"LongRangeArena-{tag}", description="Benchmark for evaluating long context sequences.")
        d_res = await service.append_dataset(d)
        assert d_res == did

        # 7. Question
        qid = f"test_srv_question_{tag}"
        q = Question(question_id=qid, text="Can exact attention scale to 64k tokens without approximation?", project_id=f"proj_{tag}")
        q_res = await service.append_question(q)
        assert q_res == qid

        # 8. Limitation
        lid = f"test_srv_limitation_{tag}"
        lim = Limitation(limitation_id=lid, statement="Requires compute capability >= 8.0 for tensor core acceleration.", severity=LimitationSeverity.MODERATE)
        l_res = await service.append_limitation(lim)
        assert l_res == lid

        # 9. Community
        cmid = f"test_srv_community_{tag}"
        cm = Community(community_id=cmid, title="Efficient Attention Architectures", summary="Cluster of papers optimizing self-attention IO.")
        cm_res = await service.append_community(cm)
        assert cm_res == cmid

        # Check lookup of any node
        node_lookup = await service.get_node_by_id(fid)
        assert node_lookup is not None
        assert "Fact" in node_lookup["labels"]
        assert node_lookup["properties"]["statement"] == f.statement


class TestEpistemicGraphServiceRelationships:
    """Tests for edge creation with rich-text descriptions and validation."""

    @pytest.mark.asyncio
    async def test_link_nodes_generic_and_specific(self, service: EpistemicGraphService) -> None:
        tag = uuid.uuid4().hex[:8]
        fid = f"test_srv_fact_edge_{tag}"
        pid = f"test_srv_proof_edge_{tag}"
        mid = f"test_srv_method_edge_{tag}"
        did = f"test_srv_dataset_edge_{tag}"
        sid = f"test_srv_source_edge_{tag}"
        cid = f"test_srv_concept_edge_{tag}"
        qid = f"test_srv_question_edge_{tag}"
        lid = f"test_srv_limitation_edge_{tag}"
        cmid = f"test_srv_community_edge_{tag}"

        # Create all nodes
        await service.append_fact(Fact(fact_id=fid, statement="Speculative decoding delivers accelerated token generation."))
        await service.append_proof(Proof(proof_id=pid, summary="2.5x throughput gain on LLaMA-70B.", polarity=ProofPolarity.SUPPORTS))
        await service.append_methodology(Methodology(methodology_id=mid, name="SpecDec-Draft-K", description="Draft proposals of K tokens."))
        await service.append_dataset(Dataset(dataset_id=did, name=f"MT-Bench-{tag}", description="Multi-turn benchmark."))
        await service.append_source(Source(source_id=sid, title="Fast Inference via Speculative Decoding"))
        await service.append_concept(Concept(concept_id=cid, name=f"Speculative-Execution-{tag}"))
        await service.append_question(Question(question_id=qid, text="What is the optimal draft length K?"))
        await service.append_limitation(Limitation(limitation_id=lid, statement="Draft model vocabulary mismatch degrades speedup."))
        await service.append_community(Community(community_id=cmid, title="LLM Acceleration Strategies"))

        # Link Fact -> Proof
        res1 = await service.link_nodes(
            source_id=fid,
            target_id=pid,
            rel_type="SUPPORTED_BY",
            description="Empirical confirmation shows 2.5x wall-clock speedup across standard chat prompts.",
        )
        assert res1 is True

        # Link Proof -> Methodology
        res2 = await service.link_nodes(
            source_id=pid,
            target_id=mid,
            rel_type="USES_METHOD",
            description="Implemented with K=4 proposal window and speculative rejection sampling.",
        )
        assert res2 is True

        # Link Proof -> Dataset
        res3 = await service.link_nodes(
            source_id=pid,
            target_id=did,
            rel_type="EVALUATED_ON",
            description="Evaluated on MT-bench multi-turn conversations testing general instruction following.",
        )
        assert res3 is True

        # Link Proof -> Source
        res4 = await service.link_nodes(
            source_id=pid,
            target_id=sid,
            rel_type="EXTRACTED_FROM",
            description="Findings reported in Section 4.2, Table 3 of the conference publication.",
        )
        assert res4 is True

        # Link Fact -> Question
        res5 = await service.link_nodes(
            source_id=fid,
            target_id=qid,
            rel_type="ADDRESSES",
            description="Directly provides an answer showing K=4 minimizes target verification overhead.",
        )
        assert res5 is True

        # Link Fact -> Concept
        res6 = await service.link_nodes(
            source_id=fid,
            target_id=cid,
            rel_type="RELATES_TO_CONCEPT",
            description="Extends speculative execution from hardware microarchitecture to autoregressive transformers.",
        )
        assert res6 is True

        # Link Proof -> Limitation
        res7 = await service.link_nodes(
            source_id=pid,
            target_id=lid,
            rel_type="HAS_LIMITATION",
            description="Demonstrates throughput collapses if draft and target tokenizers differ in token mapping.",
        )
        assert res7 is True

        # Link Fact -> Community
        res8 = await service.link_nodes(
            source_id=fid,
            target_id=cmid,
            rel_type="BELONGS_TO_COMMUNITY",
            description="Belongs to cluster of hardware-aware latency optimization techniques for large models.",
        )
        assert res8 is True

    @pytest.mark.asyncio
    async def test_relationship_description_validation_rejects_empty(self, service: EpistemicGraphService) -> None:
        """Verify that relationship creation is rejected when description is missing or < 5 characters."""
        with pytest.raises(InvalidRelationshipError, match="at least 5 characters"):
            await service.link_nodes(
                source_id="f1",
                target_id="p1",
                rel_type="SUPPORTED_BY",
                description="bad",
            )

        with pytest.raises(InvalidRelationshipError, match="non-empty string"):
            await service.link_nodes(
                source_id="f1",
                target_id="p1",
                rel_type="SUPPORTED_BY",
                description="",
            )

    @pytest.mark.asyncio
    async def test_relationship_type_validation_rejects_unknown(self, service: EpistemicGraphService) -> None:
        """Verify that unsupported relationship types trigger an InvalidRelationshipError."""
        with pytest.raises(InvalidRelationshipError, match="Unknown relationship type"):
            await service.link_nodes(
                source_id="f1",
                target_id="p1",
                rel_type="RANDOM_EDGE",
                description="Valid rich text description explaining the edge.",
            )


class TestConflictResolutionStateMachine:
    """Pure unit tests for epistemic conflict state transitions and append-only preservation."""

    def test_status_transitions(self) -> None:
        # Empty -> TENTATIVE
        status, conf = calculate_epistemic_status([])
        assert status == FactStatus.TENTATIVE
        assert conf == 0.5

        # Single support -> SUPPORTED
        status, conf = calculate_epistemic_status([{"rel_type": "SUPPORTED_BY", "confidence": 0.9}])
        assert status == FactStatus.SUPPORTED
        assert conf >= 0.60

        # Three strong supports -> CONSENSUS
        status, conf = calculate_epistemic_status([
            {"rel_type": "SUPPORTED_BY", "confidence": 0.9},
            {"rel_type": "SUPPORTED_BY", "confidence": 0.85},
            {"rel_type": "SUPPORTED_BY", "confidence": 0.95},
        ])
        assert status == FactStatus.CONSENSUS
        assert conf >= 0.85

        # Support + Contradiction -> DEBATED
        status, conf = calculate_epistemic_status([
            {"rel_type": "SUPPORTED_BY", "confidence": 0.9},
            {"rel_type": "CONTRADICTED_BY", "confidence": 0.8},
        ])
        assert status == FactStatus.DEBATED
        assert 0.40 <= conf <= 0.60

        # Only Contradiction -> REFUTED
        status, conf = calculate_epistemic_status([
            {"rel_type": "CONTRADICTED_BY", "confidence": 0.9},
        ])
        assert status == FactStatus.REFUTED
        assert conf <= 0.35

    def test_append_only_integrity_preservation(self) -> None:
        # Identical statement is allowed
        verify_append_only_transition(
            "LoRA matches full fine-tuning.",
            "LoRA matches full fine-tuning.",
        )

        # Attempt to mutate statement text raises EpistemicIntegrityError
        with pytest.raises(EpistemicIntegrityError, match="Destructive fact overwrite detected"):
            verify_append_only_transition(
                "LoRA matches full fine-tuning.",
                "LoRA does NOT match full fine-tuning.",
            )


class TestServiceRegistryIntegration:
    """Test that EpistemicGraphService is correctly registered in ServiceRegistry."""

    def test_service_registry_has_graphrag(self) -> None:
        assert hasattr(registry, "graphrag")
        assert hasattr(ServiceRegistry, "graphrag")
        # Ensure it is an EpistemicGraphService instance
        assert isinstance(registry.graphrag, EpistemicGraphService)

"""Adversarial stress-test suite by Challenger 2 for ALRS GraphRAG Backend.

Validates edge cases and boundary boundaries:
1. Malformed inputs and extreme payloads (10,000+ char LaTeX, multi-lingual UTF-8, type errors).
2. Boundary values for confidence scores (0.0, 1.0, -0.1, 1.1, NaN, Inf).
3. Duplicate ID injection attempts, missing entity references, and orphan edge attempts.
4. Depth-2 traversal on isolated nodes, shared methodologies, dual-stance proofs, and cyclic edges.
5. Strict database safety verification: ensures existing 16,083 paper nodes remain untouched.
"""
from __future__ import annotations

import math
import uuid
import pytest
import pytest_asyncio
from pydantic import ValidationError

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
    AddressesRel,
    BelongsToCommunityRel,
    Community,
    Concept,
    ContradictedByRel,
    Dataset,
    DebateSubgraph,
    EvaluatedOnRel,
    ExtractedFromRel,
    Fact,
    FactStatus,
    HasLimitationRel,
    Limitation,
    LimitationSeverity,
    Methodology,
    MethodologyCategory,
    Proof,
    ProofPolarity,
    ProofType,
    Question,
    RelatesToConceptRel,
    RelationshipEdge,
    RelationshipType,
    Source,
    SupportedByRel,
    UsesMethodRel,
)
from features.graphrag.service import EpistemicGraphService

NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASS = "changeme"
EXPECTED_BASELINE_PAPERS = 16083


@pytest_asyncio.fixture(scope="function")
async def neo4j_service() -> Neo4jService:
    """Provides an active Neo4j connection with scoped cleanup of test_challenger2_* nodes."""
    service = Neo4jService(NEO4J_URI, NEO4J_USER, NEO4J_PASS)
    await service.connect()
    yield service
    # Targeted teardown restricted to test_challenger2_* namespace
    cleanup_query = """
    MATCH (n)
    WHERE (n.fact_id STARTS WITH 'test_challenger2_'
        OR n.proof_id STARTS WITH 'test_challenger2_'
        OR n.methodology_id STARTS WITH 'test_challenger2_'
        OR n.source_id STARTS WITH 'test_challenger2_'
        OR n.concept_id STARTS WITH 'test_challenger2_'
        OR n.dataset_id STARTS WITH 'test_challenger2_'
        OR n.question_id STARTS WITH 'test_challenger2_'
        OR n.limitation_id STARTS WITH 'test_challenger2_'
        OR n.community_id STARTS WITH 'test_challenger2_')
    DETACH DELETE n
    """
    try:
        await service.execute_write(cleanup_query)
    finally:
        await service.close()


@pytest_asyncio.fixture(scope="function")
async def graphrag_service(neo4j_service: Neo4jService) -> EpistemicGraphService:
    """Provides the EpistemicGraphService wrapper for agent interactions."""
    return EpistemicGraphService(neo4j_service)


# ============================================================================
# Category 1: Malformed Inputs and Extreme Payloads
# ============================================================================

class TestExtremePayloadsAndMalformedInputs:
    """Stress tests extreme character sizes, complex mathematical notation, and multi-lingual UTF-8."""

    @pytest.mark.asyncio
    async def test_10k_latex_payload_in_relationship_description(
        self, graphrag_service: EpistemicGraphService
    ) -> None:
        """Verify persistence and bit-for-bit retrieval of 10,000+ character complex LaTeX equations."""
        run_tag = uuid.uuid4().hex[:8]
        fact_id = f"test_challenger2_latex_fact_{run_tag}"
        proof_id = f"test_challenger2_latex_proof_{run_tag}"

        latex_snippet = (
            r"\begin{equation}"
            r"\mathcal{L}_{\text{epistemic}}(\theta) = \sum_{i=1}^N \alpha_i \left( "
            r"\frac{\partial^2 \Psi}{\partial x_i^2} + \oint_{\Gamma} \vec{B} \cdot d\vec{\ell} \right) "
            r"+ \lim_{k \to \infty} \prod_{j=1}^k \left(1 - \frac{\lambda_j}{j^{\gamma}}\right) "
            r"\int_{-\infty}^{\infty} e^{-\frac{(t - \mu)^2}{2\sigma^2}} \sqrt{2\pi \sigma^2} dt "
            r"\end{equation}"
            " Parameters $\\theta \\in \\mathbb{R}^{d \\times k}$ optimized via SGD with momentum $\\beta = 0.999$, "
            "special chars: \"quotes\", 'single', {braces}, [brackets], \\\\slashes, %percent, &ampersand, #hash. "
        )
        extreme_latex = (latex_snippet * 25)[:10500]
        assert len(extreme_latex) >= 10000

        await graphrag_service.append_fact(Fact(fact_id=fact_id, statement="Testing 10k LaTeX edge payload."))
        await graphrag_service.append_proof(Proof(proof_id=proof_id, summary="Proof testing extreme LaTeX description."))
        await graphrag_service.link_fact_to_proof(fact_id, proof_id, "SUPPORTED_BY", extreme_latex)

        subgraph = await graphrag_service.get_debate_subgraph(fact_id)
        assert len(subgraph.relationships) == 1
        retrieved_desc = subgraph.relationships[0].description
        assert len(retrieved_desc) == len(extreme_latex)
        assert retrieved_desc == extreme_latex

    @pytest.mark.asyncio
    async def test_10k_multilingual_utf8_payload_in_relationship_description(
        self, graphrag_service: EpistemicGraphService
    ) -> None:
        """Verify persistence and retrieval of 10,000+ character UTF-8 strings (Chinese, Arabic RTL, Emojis)."""
        run_tag = uuid.uuid4().hex[:8]
        fact_id = f"test_challenger2_utf8_fact_{run_tag}"
        proof_id = f"test_challenger2_utf8_proof_{run_tag}"

        multilingual_snippet = (
            "【中文】深度学习推理与事实冲突分析：通过图神经网络实现非破坏性知识库更新。"
            "【العربية】نموذج لغوي متقدم وتحليل التناقض المعرفي مع الحفاظ على سجل البحث الأكاديمي كاملاً بدون حذف. "
            "【Русский】Анализ противоречивых утверждений в научном дискурсе на основе графовых представлений знаний. "
            "【日本語】知識グラフにおける対立仮説の動的統合とエピステミック信頼度スコアの自動計算。 "
            "【Math & Symbols】∀x ∈ X, ∃y ∈ Y: f(x) ↦ g(y) ⊕ ∇²ϕ(z) ⊗ ℏ/2π. "
            "【Emojis】🧠⚡️🔥📊🔍💡🔬📌🛡️✨ "
        )
        extreme_utf8 = (multilingual_snippet * 30)[:10500]
        assert len(extreme_utf8) >= 10000

        await graphrag_service.append_fact(Fact(fact_id=fact_id, statement="Testing 10k multilingual UTF-8 payload."))
        await graphrag_service.append_proof(Proof(proof_id=proof_id, summary="Proof testing multilingual UTF-8 description."))
        await graphrag_service.link_fact_to_proof(fact_id, proof_id, "SUPPORTED_BY", extreme_utf8)

        subgraph = await graphrag_service.get_debate_subgraph(fact_id)
        assert len(subgraph.relationships) == 1
        retrieved_desc = subgraph.relationships[0].description
        assert retrieved_desc == extreme_utf8

    def test_malformed_description_types_rejected(self) -> None:
        """Verify that non-string and whitespace-only descriptions are strictly rejected."""
        with pytest.raises(InvalidRelationshipError):
            validate_rich_description("")

        with pytest.raises(InvalidRelationshipError):
            validate_rich_description("   \n\t  ")

        with pytest.raises(InvalidRelationshipError):
            validate_rich_description("four")  # < 5 characters

        with pytest.raises(InvalidRelationshipError):
            validate_rich_description(None)  # type: ignore

        with pytest.raises(InvalidRelationshipError):
            validate_rich_description(12345)  # type: ignore

        with pytest.raises(InvalidRelationshipError):
            validate_rich_description(["rich", "description"])  # type: ignore

    @pytest.mark.asyncio
    async def test_complex_nested_metrics_and_hyperparameters_roundtrip(
        self, graphrag_service: EpistemicGraphService
    ) -> None:
        """Verify deep nested dictionary serialization in Proof.metrics and Methodology.hyperparameters."""
        run_tag = uuid.uuid4().hex[:8]
        proof_id = f"test_challenger2_metrics_proof_{run_tag}"
        method_id = f"test_challenger2_metrics_method_{run_tag}"

        complex_metrics = {
            "eval": {"acc": 0.965, "ci": [0.94, 0.98]},
            "ablation": [{"layer": 1, "score": 0.5}, {"layer": 2, "score": 0.8}],
            "unicode_key_μ": "verified",
        }
        complex_params = {
            "lr_schedule": {"type": "cosine", "warmup": 2000, "eta_min": 1e-6},
            "regularization": {"weight_decay": 0.05, "dropout": 0.1},
        }

        proof = Proof(proof_id=proof_id, summary="Proof with complex metrics", metrics=complex_metrics)
        method = Methodology(methodology_id=method_id, name="Nested Param Method", hyperparameters=complex_params)

        await graphrag_service.append_proof(proof)
        await graphrag_service.append_methodology(method)

        p_node = await graphrag_service.get_node_by_id(proof_id)
        m_node = await graphrag_service.get_node_by_id(method_id)

        hydrated_proof = Proof(**p_node["properties"])
        hydrated_method = Methodology(**m_node["properties"])

        assert hydrated_proof.metrics == complex_metrics
        assert hydrated_method.hyperparameters == complex_params


# ============================================================================
# Category 2: Boundary Values for Confidence Scores
# ============================================================================

class TestConfidenceScoreBoundaries:
    """Stress tests boundary conditions: 0.0, 1.0, -0.1, 1.1, NaN, and Inf."""

    def test_pydantic_fact_and_proof_reject_negative_and_excessive_confidence(self) -> None:
        """Verify Pydantic rejects confidence outside [0.0, 1.0] for Fact and Proof."""
        with pytest.raises(ValidationError):
            Fact(statement="Valid statement here", confidence_score=-0.0001)

        with pytest.raises(ValidationError):
            Fact(statement="Valid statement here", confidence_score=1.0001)

        with pytest.raises(ValidationError):
            Proof(summary="Valid summary here", confidence=-0.1)

        with pytest.raises(ValidationError):
            Proof(summary="Valid summary here", confidence=1.1)

    def test_pydantic_fact_and_proof_reject_nan_and_inf(self) -> None:
        """Verify Pydantic rejects NaN and Inf for confidence scores."""
        with pytest.raises(ValidationError):
            Fact(statement="Valid statement here", confidence_score=float("nan"))

        with pytest.raises(ValidationError):
            Fact(statement="Valid statement here", confidence_score=float("inf"))

        with pytest.raises(ValidationError):
            Proof(summary="Valid summary here", confidence=float("nan"))

        with pytest.raises(ValidationError):
            Proof(summary="Valid summary here", confidence=float("inf"))

    def test_pydantic_relationships_reject_out_of_bounds_confidence(self) -> None:
        """Verify SupportedByRel and ContradictedByRel reject out-of-bound confidences."""
        with pytest.raises(ValidationError):
            SupportedByRel(source_id="f1", target_id="p1", description="Valid edge desc", confidence=-0.1)

        with pytest.raises(ValidationError):
            SupportedByRel(source_id="f1", target_id="p1", description="Valid edge desc", confidence=1.1)

        with pytest.raises(ValidationError):
            ContradictedByRel(source_id="f1", target_id="p1", description="Valid edge desc", confidence=float("nan"))

    def test_calculate_epistemic_status_boundaries_0_and_1(self) -> None:
        """Verify calculate_epistemic_status handles exact boundary values 0.0 and 1.0 correctly."""
        # 0.0 confidence supporting proof
        status_zero, conf_zero = calculate_epistemic_status([{"rel_type": "SUPPORTED_BY", "confidence": 0.0}])
        assert status_zero == FactStatus.SUPPORTED
        assert conf_zero == 0.70

        # 1.0 confidence supporting proof
        status_one, conf_one = calculate_epistemic_status([{"rel_type": "SUPPORTED_BY", "confidence": 1.0}])
        assert status_one == FactStatus.SUPPORTED
        assert conf_one == 0.70

        # High consensus threshold with 3 proofs of 0.85
        status_cons, conf_cons = calculate_epistemic_status([
            {"rel_type": "SUPPORTED_BY", "confidence": 0.85},
            {"rel_type": "SUPPORTED_BY", "confidence": 0.85},
            {"rel_type": "SUPPORTED_BY", "confidence": 0.85},
        ])
        assert status_cons == FactStatus.CONSENSUS
        assert conf_cons >= 0.85

        # Empty proof set defaults
        status_empty, conf_empty = calculate_epistemic_status([])
        assert status_empty == FactStatus.TENTATIVE
        assert conf_empty == 0.5


# ============================================================================
# Category 3: Duplicate ID Injection & Missing References
# ============================================================================

class TestDuplicateIdAndMissingEntityReferences:
    """Stress tests duplicate entity injection and missing reference failure modes."""

    @pytest.mark.asyncio
    async def test_neo4j_uniqueness_constraint_rejects_duplicate_create(
        self, neo4j_service: Neo4jService
    ) -> None:
        """Verify Neo4j uniqueness constraint blocks raw duplicate CREATE operations."""
        from neo4j.exceptions import ClientError

        run_tag = uuid.uuid4().hex[:8]
        fid = f"test_challenger2_dup_constraint_{run_tag}"

        # 1st creation succeeds
        await neo4j_service.execute_write("CREATE (f:Fact {fact_id: $fid, statement: 'Initial Fact'})", {"fid": fid})

        # 2nd creation with exact same ID fails constraint
        with pytest.raises(ClientError):
            await neo4j_service.execute_write("CREATE (f:Fact {fact_id: $fid, statement: 'Duplicate Fact'})", {"fid": fid})

    @pytest.mark.asyncio
    async def test_audit_append_fact_duplicate_statement_overwrite(
        self, graphrag_service: EpistemicGraphService
    ) -> None:
        """Adversarial check: verifies whether append_fact allows statement overwrites.
        
        NOTE: Per append-only integrity rules, conflicting statement updates should NOT
        silently overwrite existing propositions. This test records the observed behavior.
        """
        run_tag = uuid.uuid4().hex[:8]
        fact_id = f"test_challenger2_stmt_audit_{run_tag}"

        initial_statement = "Proposition Alpha: Model loss scales inversely with parameter count."
        mutated_statement = "Proposition Beta: Model loss does not scale with parameter count."

        # Step 1: Initial Fact
        await graphrag_service.append_fact(Fact(fact_id=fact_id, statement=initial_statement))
        f1 = await graphrag_service.get_fact(fact_id)
        assert f1.statement == initial_statement

        # Step 2: Attempt duplicate ID injection with conflicting statement is rejected
        with pytest.raises(EpistemicIntegrityError, match="Destructive fact overwrite detected"):
            await graphrag_service.append_fact(Fact(fact_id=fact_id, statement=mutated_statement))

        # Confirm database statement remained unchanged
        f2 = await graphrag_service.get_fact(fact_id)
        assert f2.statement == initial_statement

        # Standalone validator strictly rejects this transition:
        with pytest.raises(EpistemicIntegrityError):
            verify_append_only_transition(f1.statement, mutated_statement)

    @pytest.mark.asyncio
    async def test_audit_missing_entity_references_in_linking(
        self, graphrag_service: EpistemicGraphService, neo4j_service: Neo4jService
    ) -> None:
        """Adversarial check: checks behavior when linking to non-existent nodes.
        
        If a target or source node does not exist in the database, Cypher MATCH returns
        0 records. We verify that no orphan relationship is created in Neo4j.
        """
        run_tag = uuid.uuid4().hex[:8]
        existing_fact_id = f"test_challenger2_exist_fact_{run_tag}"
        nonexistent_proof_id = f"test_challenger2_missing_proof_{run_tag}"

        await graphrag_service.append_fact(Fact(fact_id=existing_fact_id, statement="Existing fact node."))

        # Link to missing proof
        result = await graphrag_service.link_fact_to_proof(
            fact_id=existing_fact_id,
            proof_id=nonexistent_proof_id,
            polarity="SUPPORTED_BY",
            description="Attempted link to missing proof.",
        )
        assert result is False, "Expected link_fact_to_proof to return False on missing target proof"

        # Verify no orphan relationship exists in Neo4j
        records = await neo4j_service.execute_read(
            "MATCH (f:Fact {fact_id: $fid})-[r:SUPPORTED_BY]->() RETURN r",
            {"fid": existing_fact_id},
        )
        assert len(records) == 0, "Orphan edge was unexpectedly created in database!"


# ============================================================================
# Category 4: Graph Topology & Depth-2 Traversal Stress
# ============================================================================

class TestGraphTopologyAndTraversalStress:
    """Stress tests isolated nodes, shared methodologies, dual-stance proofs, and full subgraphs."""

    @pytest.mark.asyncio
    async def test_depth2_traversal_on_isolated_fact_returns_empty_collections(
        self, graphrag_service: EpistemicGraphService
    ) -> None:
        """Verify that get_debate_subgraph on an isolated fact returns a valid structure with empty lists."""
        run_tag = uuid.uuid4().hex[:8]
        fact_id = f"test_challenger2_isolated_{run_tag}"

        await graphrag_service.append_fact(Fact(fact_id=fact_id, statement="Isolated claim with zero proofs."))

        subgraph = await graphrag_service.get_debate_subgraph(fact_id)
        assert subgraph.central_fact.fact_id == fact_id
        assert len(subgraph.supporting_proofs) == 0
        assert len(subgraph.contradicting_proofs) == 0
        assert len(subgraph.methodologies) == 0
        assert len(subgraph.datasets) == 0
        assert len(subgraph.sources) == 0
        assert len(subgraph.limitations) == 0
        assert len(subgraph.relationships) == 0
        assert len(subgraph.nodes) == 1
        assert subgraph.nodes[0].id == fact_id

    @pytest.mark.asyncio
    async def test_non_existent_fact_traversal_raises_value_error(
        self, graphrag_service: EpistemicGraphService
    ) -> None:
        """Verify that querying debate subgraph for non-existent fact raises ValueError."""
        with pytest.raises(ValueError, match="does not exist"):
            await graphrag_service.get_debate_subgraph("test_challenger2_completely_fake_id")

    @pytest.mark.asyncio
    async def test_shared_methodology_and_dataset_deduplication_in_subgraph(
        self, graphrag_service: EpistemicGraphService
    ) -> None:
        """Verify that opposing proofs sharing the same Methodology and Dataset are deduplicated in subgraph."""
        run_tag = uuid.uuid4().hex[:8]
        fact_id = f"test_challenger2_dedup_fact_{run_tag}"
        p_sup_id = f"test_challenger2_dedup_p_sup_{run_tag}"
        p_con_id = f"test_challenger2_dedup_p_con_{run_tag}"
        method_id = f"test_challenger2_dedup_method_{run_tag}"
        dataset_id = f"test_challenger2_dedup_dataset_{run_tag}"

        await graphrag_service.append_fact(Fact(fact_id=fact_id, statement="Shared methodology debate claim."))
        await graphrag_service.append_proof(Proof(proof_id=p_sup_id, summary="Proof 1 supporting with method M."))
        await graphrag_service.append_proof(Proof(proof_id=p_con_id, summary="Proof 2 contradicting with method M."))
        await graphrag_service.append_methodology(Methodology(methodology_id=method_id, name="Shared Benchmark Protocol"))
        await graphrag_service.append_dataset(Dataset(dataset_id=dataset_id, name="Shared Evaluation Benchmark"))

        # Link both proofs to the same methodology and dataset
        await graphrag_service.link_fact_to_proof(fact_id, p_sup_id, "SUPPORTED_BY", "Proponent confirms scaling.")
        await graphrag_service.link_fact_to_proof(fact_id, p_con_id, "CONTRADICTED_BY", "Skeptic observes saturation.")
        await graphrag_service.link_proof_to_methodology(p_sup_id, method_id, "P1 employs evaluation protocol.")
        await graphrag_service.link_proof_to_methodology(p_con_id, method_id, "P2 employs identical protocol.")
        await graphrag_service.link_proof_to_dataset(p_sup_id, dataset_id, "Evaluated on shared benchmark.")
        await graphrag_service.link_proof_to_dataset(p_con_id, dataset_id, "Evaluated on shared benchmark.")

        subgraph = await graphrag_service.get_debate_subgraph(fact_id)

        # Deduplication assertions: exactly 1 methodology and 1 dataset in respective lists
        assert len(subgraph.methodologies) == 1
        assert subgraph.methodologies[0].methodology_id == method_id
        assert len(subgraph.datasets) == 1
        assert subgraph.datasets[0].dataset_id == dataset_id

        # Unique nodes in subgraph should be: Central Fact (1) + Proofs (2) + Method (1) + Dataset (1) = 5
        assert len(subgraph.nodes) == 5
        # Relationships: 2 to Fact + 4 from Proofs (2 methods + 2 datasets) = 6
        assert len(subgraph.relationships) == 6

    @pytest.mark.asyncio
    async def test_dual_stance_proof_handling(
        self, graphrag_service: EpistemicGraphService
    ) -> None:
        """Verify handling when a single Proof is linked as both SUPPORTED_BY and CONTRADICTED_BY."""
        run_tag = uuid.uuid4().hex[:8]
        fact_id = f"test_challenger2_dual_fact_{run_tag}"
        proof_id = f"test_challenger2_dual_proof_{run_tag}"

        await graphrag_service.append_fact(Fact(fact_id=fact_id, statement="Dual interpretation claim."))
        await graphrag_service.append_proof(Proof(proof_id=proof_id, summary="Ambiguous statistical evidence."))

        # Link 1: Support
        await graphrag_service.link_fact_to_proof(fact_id, proof_id, "SUPPORTED_BY", "Agent Alpha claims positive effect.")
        f_alpha = await graphrag_service.get_fact(fact_id)
        assert f_alpha.status == FactStatus.SUPPORTED

        # Link 2: Contradict
        await graphrag_service.link_fact_to_proof(fact_id, proof_id, "CONTRADICTED_BY", "Agent Beta claims artifact effect.")
        f_beta = await graphrag_service.get_fact(fact_id)
        assert f_beta.status == FactStatus.DEBATED

        subgraph = await graphrag_service.get_debate_subgraph(fact_id)
        assert len(subgraph.supporting_proofs) == 1
        assert len(subgraph.contradicting_proofs) == 1
        assert len(subgraph.nodes) == 2  # Fact and Proof
        assert len(subgraph.relationships) == 2  # 2 edges between them

    @pytest.mark.asyncio
    async def test_full_depth2_graph_with_all_9_node_types(
        self, graphrag_service: EpistemicGraphService
    ) -> None:
        """Stress-test a complete dialectical graph containing all 9 node types simultaneously."""
        run_tag = uuid.uuid4().hex[:8]
        fid = f"test_challenger2_all9_fact_{run_tag}"
        pid = f"test_challenger2_all9_proof_{run_tag}"
        mid = f"test_challenger2_all9_method_{run_tag}"
        did = f"test_challenger2_all9_dataset_{run_tag}"
        sid = f"test_challenger2_all9_source_{run_tag}"
        lid = f"test_challenger2_all9_limitation_{run_tag}"
        cid = f"test_challenger2_all9_concept_{run_tag}"
        qid = f"test_challenger2_all9_question_{run_tag}"
        cmid = f"test_challenger2_all9_community_{run_tag}"

        # 1. Append all 9 nodes
        await graphrag_service.append_fact(Fact(fact_id=fid, statement="Comprehensive full graph integration claim."))
        await graphrag_service.append_proof(Proof(proof_id=pid, summary="Comprehensive empirical evidence proof."))
        await graphrag_service.append_methodology(Methodology(methodology_id=mid, name="Analytical Protocol"))
        await graphrag_service.append_dataset(Dataset(dataset_id=did, name="Benchmark Corpus"))
        await graphrag_service.append_source(Source(source_id=sid, title="Foundational Paper Title"))
        await graphrag_service.append_limitation(Limitation(limitation_id=lid, statement="Evaluation bounded to English text."))
        await graphrag_service.append_concept(Concept(concept_id=cid, name="Epistemic Closure"))
        await graphrag_service.append_question(Question(question_id=qid, text="Does scale overcome fundamental architectural bounds?"))
        await graphrag_service.append_community(Community(community_id=cmid, title="Foundation Model Scaling Laws"))

        # 2. Link all edges with mandatory rich descriptions
        await graphrag_service.link_fact_to_proof(fid, pid, "SUPPORTED_BY", "Proof provides empirical evidence.")
        await graphrag_service.link_proof_to_methodology(pid, mid, "Uses rigorous analytical protocol.")
        await graphrag_service.link_proof_to_dataset(pid, did, "Evaluated on benchmark corpus.")
        await graphrag_service.link_to_source(pid, sid, "Extracted from foundational paper.")
        await graphrag_service.link_to_limitation(pid, lid, "Identifies evaluation boundary condition.")
        await graphrag_service.link_to_concept(fid, cid, "Grounds claim in epistemic closure concept.")
        await graphrag_service.link_fact_to_question(fid, qid, "Directly answers the research question.")
        await graphrag_service.link_fact_to_community(fid, cmid, "Cluster member of scaling laws community.")

        # 3. Traversal query
        subgraph = await graphrag_service.get_debate_subgraph(fid)

        assert subgraph.central_fact.fact_id == fid
        assert len(subgraph.supporting_proofs) == 1
        assert len(subgraph.methodologies) == 1
        assert len(subgraph.datasets) == 1
        assert len(subgraph.sources) == 1
        assert len(subgraph.limitations) == 1

        # Check total nodes collected (1 fact + 1 proof + 1 method + 1 dataset + 1 source + 1 limit + 1 concept + 1 question + 1 comm = 9)
        node_ids = {n.id for n in subgraph.nodes}
        assert fid in node_ids
        assert pid in node_ids
        assert mid in node_ids
        assert did in node_ids
        assert sid in node_ids
        assert lid in node_ids
        assert cid in node_ids
        assert qid in node_ids
        assert cmid in node_ids
        assert len(subgraph.nodes) == 9

        # Verify all 8 edges carry rich-text description >= 5 chars
        assert len(subgraph.relationships) == 8
        for edge in subgraph.relationships:
            assert len(edge.description.strip()) >= 5, f"Edge {edge.type} has inadequate description"

    @pytest.mark.asyncio
    async def test_depth1_vs_depth2_structural_difference(
        self, graphrag_service: EpistemicGraphService
    ) -> None:
        """Verify structural differences between depth=1 and depth=2 traversals."""
        run_tag = uuid.uuid4().hex[:8]
        fact_id = f"test_challenger2_depth_{run_tag}"
        fact = Fact(fact_id=fact_id, statement="Verification of depth difference.")
        await graphrag_service.append_fact(fact)

        proof = Proof(
            proof_id=f"test_challenger2_p_{run_tag}",
            summary="Proof 1 for depth test",
            polarity=ProofPolarity.SUPPORTS,
            confidence=0.85,
        )
        method = Methodology(
            methodology_id=f"test_challenger2_m_{run_tag}",
            name="Methodology Alpha",
        )
        dataset = Dataset(
            dataset_id=f"test_challenger2_d_{run_tag}",
            name="Dataset Beta",
        )

        await graphrag_service.append_epistemic_claim(
            fact=fact,
            proof=proof,
            relationship_type="SUPPORTED_BY",
            edge_description="Supporting edge description",
            methodology=method,
            dataset=dataset,
        )

        # 1. Depth=1 verification: immediate proofs only, no hop-2 entities
        subgraph_d1 = await graphrag_service.get_debate_subgraph(fact_id, depth=1)
        assert len(subgraph_d1.supporting_proofs) == 1
        assert len(subgraph_d1.methodologies) == 0
        assert len(subgraph_d1.datasets) == 0
        assert len(subgraph_d1.relationships) == 1
        assert len(subgraph_d1.nodes) == 2

        # 2. Depth=2 verification: proofs and 2-hop methodologies + datasets
        subgraph_d2 = await graphrag_service.get_debate_subgraph(fact_id, depth=2)
        assert len(subgraph_d2.supporting_proofs) == 1
        assert len(subgraph_d2.methodologies) == 1
        assert len(subgraph_d2.datasets) == 1
        assert len(subgraph_d2.relationships) == 3
        assert len(subgraph_d2.nodes) == 4

        # 3. Invalid depth validation
        with pytest.raises(ValueError, match="Invalid subgraph depth"):
            await graphrag_service.get_debate_subgraph(fact_id, depth=0)
        with pytest.raises(ValueError, match="Invalid subgraph depth"):
            await graphrag_service.get_debate_subgraph(fact_id, depth=3)


# ============================================================================
# Category 5: Database Safety Verification
# ============================================================================

class TestDatabaseSafetyGuarantee:
    """Verifies that the live Neo4j database (16,083 existing production nodes) is completely preserved."""

    @pytest.mark.asyncio
    async def test_existing_database_records_untouched(
        self, neo4j_service: Neo4jService
    ) -> None:
        """Confirm that all 16,083 existing production nodes (14,118 Papers, 1,445 Authors, etc.) remain untouched."""
        records = await neo4j_service.execute_read(
            "MATCH (n) RETURN count(n) as total_nodes, count(CASE WHEN n:Paper THEN 1 END) as paper_count"
        )
        assert len(records) > 0
        total_nodes = records[0]["total_nodes"]
        paper_count = records[0]["paper_count"]
        assert total_nodes == 16083, f"Total nodes breached! Expected 16,083, found {total_nodes}."
        assert paper_count == 14118, f"Paper count breached! Expected 14,118, found {paper_count}."


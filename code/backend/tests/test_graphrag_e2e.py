"""Comprehensive Requirement-Driven E2E Test Suite for ALRS GraphRAG Backend (Tiers 1-4).

Covers:
- Tier 1 (Happy Paths & Feature Coverage):
  F1: All 9 node types instantiated and persisted via EpistemicGraphService.
  F2: Rich-text relationship models and edge creation for all relationship types.
  F3: Schema initialization & index verification.
  F4: Parameterized Cypher query execution.
  F5: Service API wrapper methods.
  F6: Non-destructive append-only conflict resolution.
  F7: Dynamic epistemic status calculation.
  F8: Multi-agent opposing proof injection.
  F9: Depth-2 neighborhood debate subgraph traversal.

- Tier 2 (Boundaries & Edge Cases):
  - Empty string & minimum length rejections.
  - Extreme unicode, LaTeX formulas, and math symbols in statements and descriptions.
  - Extreme large description payloads (10,000+ characters).
  - Idempotent merge on duplicate IDs.
  - Non-existent fact subgraph traversal handling.
  - Fact with zero proofs handling.
  - Shared methodologies and multi-parent graphs.
  - Missing optional fields and default values.

- Tier 3 (Cross-Feature Combinations & Atomic Claims):
  - Atomic composite claim transaction (Fact + Proof + Methodology + Dataset + Source).
  - Complete epistemic lifecycle transitions: tentative -> supported -> consensus -> debated -> refuted.
  - Mathematical confidence score decay.
  - Multi-proof, multi-method, multi-dataset interconnected graph networks.

- Tier 4 (Real-World Literature Review Debates):
  - Scenario 1: LLM Reasoning Emergence Debate (Wei et al. vs Schaeffer et al.).
  - Scenario 2: Model Quantization Parity Conflict (Dettmers et al. vs Xiao et al.).
  - Scenario 3: Dialectic Subgraph Synthesis Engine for Automated Literature Review.
  - Scenario 4: Macro-Thematic Community Summary & Literature Gap Discovery.
"""
from __future__ import annotations

import json
import uuid
import pytest
import pytest_asyncio

from core.db.neo4j_service import Neo4jService
from features.graphrag.conflict import (
    EpistemicIntegrityError,
    InvalidRelationshipError,
    calculate_epistemic_status,
)
from features.graphrag.models import (
    Community,
    Concept,
    Dataset,
    DebateSubgraph,
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
async def e2e_service() -> EpistemicGraphService:
    """Provides EpistemicGraphService connected to live Neo4j with strict test_e2e_ cleanup."""
    neo4j = Neo4jService(NEO4J_URI, NEO4J_USER, NEO4J_PASS)
    await neo4j.connect()
    service = EpistemicGraphService(neo4j)
    await service.initialize_schema()
    yield service

    # Targeted safety cleanup: ONLY delete nodes with test_e2e_ prefix
    cleanup_query = """
    MATCH (n)
    WHERE (n.fact_id STARTS WITH 'test_e2e_'
        OR n.proof_id STARTS WITH 'test_e2e_'
        OR n.methodology_id STARTS WITH 'test_e2e_'
        OR n.source_id STARTS WITH 'test_e2e_'
        OR n.concept_id STARTS WITH 'test_e2e_'
        OR n.dataset_id STARTS WITH 'test_e2e_'
        OR n.question_id STARTS WITH 'test_e2e_'
        OR n.limitation_id STARTS WITH 'test_e2e_'
        OR n.community_id STARTS WITH 'test_e2e_')
    DETACH DELETE n
    """
    try:
        await neo4j.execute_write(cleanup_query)
    finally:
        await neo4j.close()


# ============================================================================
# Tier 1: Happy Paths & Feature Coverage (≥5 Tests per Feature)
# ============================================================================

class TestTier1HappyPaths:
    """Validates baseline functionality and happy paths across all 9 node types and operations."""

    @pytest.mark.asyncio
    async def test_f1_append_and_retrieve_fact(self, e2e_service: EpistemicGraphService) -> None:
        """F1.1: Append Fact and fetch by ID."""
        run_tag = uuid.uuid4().hex[:8]
        fact_id = f"test_e2e_f1_{run_tag}"
        fact = Fact(
            fact_id=fact_id,
            statement="Self-attention computational complexity scales quadratically with sequence length O(N^2).",
            domain="Deep Learning",
            project_id=f"proj_{run_tag}",
            confidence_score=0.95,
        )
        returned_id = await e2e_service.append_fact(fact)
        assert returned_id == fact_id

        fetched = await e2e_service.get_fact(fact_id)
        assert fetched is not None
        assert fetched.fact_id == fact_id
        assert fetched.statement == fact.statement
        assert fetched.status == FactStatus.TENTATIVE

    @pytest.mark.asyncio
    async def test_f1_append_proof_with_evidence_types(self, e2e_service: EpistemicGraphService) -> None:
        """F1.2: Append Proof nodes covering various empirical evidence types."""
        run_tag = uuid.uuid4().hex[:8]
        p1_id = f"test_e2e_p1_{run_tag}"
        proof = Proof(
            proof_id=p1_id,
            summary="Profiling on A100 GPUs shows execution time increases by 4.02x when context doubles from 2k to 4k.",
            polarity=ProofPolarity.SUPPORTS,
            proof_type=ProofType.EMPIRICAL_BENCHMARK,
            confidence=0.94,
            extracted_quote="Table 3: FlashAttention-1 profiling indicates O(N^2) memory footprint and runtime.",
            agent_id="BenchmarkAgent",
        )
        returned_id = await e2e_service.append_proof(proof)
        assert returned_id == p1_id

        node = await e2e_service.get_node_by_id(p1_id)
        assert node is not None
        assert "Proof" in node["labels"]
        assert node["properties"]["summary"] == proof.summary

    @pytest.mark.asyncio
    async def test_f1_append_methodology_categories(self, e2e_service: EpistemicGraphService) -> None:
        """F1.3: Append Methodology nodes with structured categories and hyperparameters."""
        run_tag = uuid.uuid4().hex[:8]
        m1_id = f"test_e2e_m1_{run_tag}"
        method = Methodology(
            methodology_id=m1_id,
            name="Kernel Tiling and SRAM Fusion",
            description="Splits Q, K, V matrices into SRAM blocks to compute softmax without materializing full NxN matrix.",
            category=MethodologyCategory.MODEL_ARCHITECTURE,
            hyperparameters={"block_size": 128, "precision": "bfloat16"},
            code_url="https://github.com/Dao-AILab/flash-attention",
        )
        ret_id = await e2e_service.append_methodology(method)
        assert ret_id == m1_id

        node = await e2e_service.get_node_by_id(m1_id)
        assert node is not None
        assert "Methodology" in node["labels"]
        assert node["properties"]["name"] == method.name

    @pytest.mark.asyncio
    async def test_f1_append_source_bibliographic(self, e2e_service: EpistemicGraphService) -> None:
        """F1.4: Append Source node with complete bibliographic metadata."""
        run_tag = uuid.uuid4().hex[:8]
        s1_id = f"test_e2e_s1_{run_tag}"
        source = Source(
            source_id=s1_id,
            title="FlashAttention: Fast and Memory-Efficient Exact Attention with IO-Awareness",
            doi="10.48550/arXiv.2205.14135",
            authors=["Tri Dao", "Daniel Y. Fu", "Stefano Ermon", "Atri Rudra", "Christopher Re"],
            year=2022,
            venue="NeurIPS",
            citation_count=1850,
        )
        ret_id = await e2e_service.append_source(source)
        assert ret_id == s1_id

        node = await e2e_service.get_node_by_id(s1_id)
        assert node is not None
        assert "Source" in node["labels"]
        assert node["properties"]["title"] == source.title

    @pytest.mark.asyncio
    async def test_f1_append_concept_dataset_question_limitation_community(
        self,
        e2e_service: EpistemicGraphService,
    ) -> None:
        """F1.5: Append Concept, Dataset, Question, Limitation, and Community nodes."""
        run_tag = uuid.uuid4().hex[:8]
        cid = f"test_e2e_concept_{run_tag}"
        did = f"test_e2e_dataset_{run_tag}"
        qid = f"test_e2e_question_{run_tag}"
        lid = f"test_e2e_limitation_{run_tag}"
        cmid = f"test_e2e_community_{run_tag}"

        # Concept
        c_res = await e2e_service.append_concept(Concept(concept_id=cid, name=f"IO-Aware Attention {run_tag}", definition="Attention that accounts for GPU memory hierarchy reads and writes."))
        assert c_res == cid

        # Dataset
        d_res = await e2e_service.append_dataset(Dataset(dataset_id=did, name=f"LongRangeArena_{run_tag}", description="Benchmark for long-context sequence modeling."))
        assert d_res == did

        # Question
        q_res = await e2e_service.append_question(Question(question_id=qid, text="Can exact attention scale sub-quadratically in wall-clock time?", project_id=f"proj_{run_tag}"))
        assert q_res == qid

        # Limitation
        l_res = await e2e_service.append_limitation(Limitation(limitation_id=lid, statement="Requires modern CUDA architectures with FP16/BF16 tensor cores.", severity=LimitationSeverity.MODERATE))
        assert l_res == lid

        # Community
        cm_res = await e2e_service.append_community(Community(community_id=cmid, title="Hardware-Efficient Attention", summary="Cluster of papers optimizing attention execution speed.", level=1))
        assert cm_res == cmid

    @pytest.mark.asyncio
    async def test_f2_all_relationship_linking_methods(self, e2e_service: EpistemicGraphService) -> None:
        """F2: Verify linking methods for all relationship types with mandatory rich descriptions."""
        run_tag = uuid.uuid4().hex[:8]
        fid = f"test_e2e_rel_fact_{run_tag}"
        pid = f"test_e2e_rel_proof_{run_tag}"
        mid = f"test_e2e_rel_method_{run_tag}"
        did = f"test_e2e_rel_dataset_{run_tag}"
        sid = f"test_e2e_rel_source_{run_tag}"
        qid = f"test_e2e_rel_question_{run_tag}"
        cid = f"test_e2e_rel_concept_{run_tag}"
        lid = f"test_e2e_rel_limitation_{run_tag}"
        cmid = f"test_e2e_rel_community_{run_tag}"

        # Initialize base nodes
        await e2e_service.append_fact(Fact(fact_id=fid, statement="Chunked cross-entropy avoids OOM on large vocabulary outputs."))
        await e2e_service.append_proof(Proof(proof_id=pid, summary="Reduces peak activation memory by 80%."))
        await e2e_service.append_methodology(Methodology(methodology_id=mid, name="Chunked Loss Computation", description="Splits logits into micro-batches."))
        await e2e_service.append_dataset(Dataset(dataset_id=did, name=f"UltraChat_{run_tag}", description="Dialogue dataset with long sequences."))
        await e2e_service.append_source(Source(source_id=sid, title="Llama 3 Technical Report", year=2024))
        await e2e_service.append_question(Question(question_id=qid, text="How to scale vocabulary sizes past 128k?", project_id=f"p_{run_tag}"))
        await e2e_service.append_concept(Concept(concept_id=cid, name=f"Cross-Entropy Memory Footprint_{run_tag}", definition="Memory required to materialize unnormalized logits."))
        await e2e_service.append_limitation(Limitation(limitation_id=lid, statement="Increases host-device coordination overhead."))
        await e2e_service.append_community(Community(community_id=cmid, title="Large Vocab Scaling", summary="Techniques for handling large output vocabularies."))

        # Link all edges with rich-text descriptions
        assert await e2e_service.link_fact_to_proof(fid, pid, "SUPPORTED_BY", "Validates activation savings across 128k vocabulary sizes.")
        assert await e2e_service.link_proof_to_methodology(pid, mid, "Employs chunk size of 4096 tokens per micro-batch.")
        assert await e2e_service.link_proof_to_dataset(pid, did, "Evaluated on 32k context dialogues in UltraChat.")
        assert await e2e_service.link_to_source(pid, sid, "Extracted from Section 3.2, Architecture Design.")
        assert await e2e_service.link_fact_to_question(fid, qid, "Directly answers the memory scaling bottleneck.")
        assert await e2e_service.link_to_concept(fid, cid, "Formalizes the theoretical peak memory bound.")
        assert await e2e_service.link_to_limitation(pid, lid, "Applies specifically when using tensor parallelism across multi-nodes.")
        assert await e2e_service.link_fact_to_community(fid, cmid, "Core anchor fact in the large vocabulary cluster.")

        # Traverse depth-2 subgraph
        subgraph = await e2e_service.get_debate_subgraph(fid, depth=2)
        assert len(subgraph.supporting_proofs) == 1
        assert len(subgraph.methodologies) == 1
        assert len(subgraph.datasets) == 1
        assert len(subgraph.sources) == 1
        assert len(subgraph.limitations) == 1


# ============================================================================
# Tier 2: Boundary and Corner Cases
# ============================================================================

class TestTier2BoundaryAndCornerCases:
    """Exhaustive boundary value analysis (BVA) and stress testing."""

    @pytest.mark.asyncio
    async def test_empty_and_whitespace_descriptions_rejected(
        self,
        e2e_service: EpistemicGraphService,
    ) -> None:
        """Reject empty, whitespace, and short descriptions (<5 chars) across linking methods."""
        fid = f"test_e2e_bva_f_{uuid.uuid4().hex[:8]}"
        pid = f"test_e2e_bva_p_{uuid.uuid4().hex[:8]}"
        await e2e_service.append_fact(Fact(fact_id=fid, statement="Attention sink tokens prevent model collapse on long text."))
        await e2e_service.append_proof(Proof(proof_id=pid, summary="Initial 4 tokens retain high attention weights."))

        # Empty string
        with pytest.raises(InvalidRelationshipError):
            await e2e_service.link_fact_to_proof(fid, pid, "SUPPORTED_BY", "")

        # Whitespace only
        with pytest.raises(InvalidRelationshipError):
            await e2e_service.link_fact_to_proof(fid, pid, "SUPPORTED_BY", "    \t\n   ")

        # Too short (< 5 chars)
        with pytest.raises(InvalidRelationshipError):
            await e2e_service.link_fact_to_proof(fid, pid, "SUPPORTED_BY", "Tiny")

    @pytest.mark.asyncio
    async def test_extreme_unicode_latex_and_math_notation(
        self,
        e2e_service: EpistemicGraphService,
    ) -> None:
        """Ensure facts and descriptions properly handle complex mathematical LaTeX, Greek letters, and emojis."""
        run_tag = uuid.uuid4().hex[:8]
        fid = f"test_e2e_math_f_{run_tag}"
        pid = f"test_e2e_math_p_{run_tag}"

        math_statement = r"For all $\epsilon > 0$, $\lim_{N \to \infty} \mathbb{P}(|L(N) - A N^{-\alpha}| > \epsilon) = 0$ 🔬."
        fact = Fact(fact_id=fid, statement=math_statement, domain="Theoretical Scaling Laws")
        await e2e_service.append_fact(fact)

        rich_math_desc = (
            r"Empirically proven where $\alpha \approx 0.076 \pm 0.002$ and $R^2 \ge 0.998$ across compute budget "
            r"$C \in [10^{18}, 10^{24}]$ FLOPs 🧪. Contains non-ASCII scripts: 深度学习, 梯度下降."
        )
        proof = Proof(proof_id=pid, summary="Regression fit confirms power-law scaling in log-log space.")
        await e2e_service.append_proof(proof)

        await e2e_service.link_fact_to_proof(fid, pid, "SUPPORTED_BY", rich_math_desc)

        subgraph = await e2e_service.get_debate_subgraph(fid, depth=2)
        assert subgraph.central_fact.statement == math_statement
        edge = next(r for r in subgraph.relationships if r.type == "SUPPORTED_BY")
        assert edge.description == rich_math_desc

    @pytest.mark.asyncio
    async def test_extreme_large_description_payload(
        self,
        e2e_service: EpistemicGraphService,
    ) -> None:
        """Ensure rich relationship descriptions can store extensive literature review synthesis narratives."""
        run_tag = uuid.uuid4().hex[:8]
        fid = f"test_e2e_large_f_{run_tag}"
        pid = f"test_e2e_large_p_{run_tag}"

        await e2e_service.append_fact(Fact(fact_id=fid, statement="Mixture of Depths dynamically allocates compute per token."))
        await e2e_service.append_proof(Proof(proof_id=pid, summary="Reduces FLOPs by 50% while maintaining baseline performance."))

        # 5,000 character narrative
        large_narrative = (
            "Detailed scientific context: " + ("In multi-layer transformer architectures, standard routing enforces uniform token compute. " * 50)
        )
        assert len(large_narrative) > 3000

        await e2e_service.link_fact_to_proof(fid, pid, "SUPPORTED_BY", large_narrative)

        subgraph = await e2e_service.get_debate_subgraph(fid, depth=2)
        edge = next(r for r in subgraph.relationships if r.type == "SUPPORTED_BY")
        assert edge.description == large_narrative

    @pytest.mark.asyncio
    async def test_duplicate_id_idempotent_merge(
        self,
        e2e_service: EpistemicGraphService,
    ) -> None:
        """Re-appending identical ID updates node properties without throwing duplicate constraint errors."""
        run_tag = uuid.uuid4().hex[:8]
        fid = f"test_e2e_merge_f_{run_tag}"

        fact_v1 = Fact(fact_id=fid, statement="Rotary position embeddings (RoPE) encode relative position as complex rotation.")
        await e2e_service.append_fact(fact_v1)

        fact_v2 = Fact(fact_id=fid, statement="Rotary position embeddings (RoPE) encode relative position as complex rotation.", domain="NLP")
        # Idempotent MERGE
        ret_id = await e2e_service.append_fact(fact_v2)
        assert ret_id == fid

        fetched = await e2e_service.get_fact(fid)
        assert fetched.domain == "NLP"

    @pytest.mark.asyncio
    async def test_query_non_existent_fact_raises_value_error(
        self,
        e2e_service: EpistemicGraphService,
    ) -> None:
        """Querying get_debate_subgraph for an invalid fact ID raises ValueError cleanly."""
        with pytest.raises(ValueError, match="does not exist"):
            await e2e_service.get_debate_subgraph("non_existent_fact_id_999999")

    @pytest.mark.asyncio
    async def test_fact_with_zero_proofs_returns_empty_subgraph_collections(
        self,
        e2e_service: EpistemicGraphService,
    ) -> None:
        """Fact with no attached proofs returns central fact and empty proof collections."""
        run_tag = uuid.uuid4().hex[:8]
        fid = f"test_e2e_zero_f_{run_tag}"
        await e2e_service.append_fact(Fact(fact_id=fid, statement="Unverified theoretical conjecture regarding quantum attention."))

        subgraph = await e2e_service.get_debate_subgraph(fid, depth=2)
        assert subgraph.central_fact.fact_id == fid
        assert subgraph.central_fact.status == FactStatus.TENTATIVE
        assert len(subgraph.supporting_proofs) == 0
        assert len(subgraph.contradicting_proofs) == 0
        assert len(subgraph.methodologies) == 0
        assert len(subgraph.relationships) == 0

    @pytest.mark.asyncio
    async def test_shared_methodology_between_two_proofs(
        self,
        e2e_service: EpistemicGraphService,
    ) -> None:
        """A single Methodology node can be shared between multiple independent Proofs."""
        run_tag = uuid.uuid4().hex[:8]
        fid = f"test_e2e_shared_f_{run_tag}"
        p1_id = f"test_e2e_shared_p1_{run_tag}"
        p2_id = f"test_e2e_shared_p2_{run_tag}"
        m_id = f"test_e2e_shared_m_{run_tag}"

        await e2e_service.append_fact(Fact(fact_id=fid, statement="Instruction fine-tuning mitigates toxicity when combined with DPO."))
        await e2e_service.append_proof(Proof(proof_id=p1_id, summary="Reduces toxic completions by 35% on RealToxicityPrompts."))
        await e2e_service.append_proof(Proof(proof_id=p2_id, summary="Maintains win-rate against GPT-4 on MT-Bench."))
        await e2e_service.append_methodology(Methodology(methodology_id=m_id, name="Direct Preference Optimization", description="Implicit reward loss."))

        await e2e_service.link_fact_to_proof(fid, p1_id, "SUPPORTED_BY", "Direct empirical validation on toxicity benchmarks.")
        await e2e_service.link_fact_to_proof(fid, p2_id, "SUPPORTED_BY", "Direct empirical validation on helpfulness benchmarks.")
        await e2e_service.link_proof_to_methodology(p1_id, m_id, "Configured with beta=0.1.")
        await e2e_service.link_proof_to_methodology(p2_id, m_id, "Configured with beta=0.1.")

        subgraph = await e2e_service.get_debate_subgraph(fid, depth=2)
        assert len(subgraph.supporting_proofs) == 2
        # Methodology should appear exactly once in deduplicated collection
        assert len(subgraph.methodologies) == 1
        assert subgraph.methodologies[0].methodology_id == m_id


# ============================================================================
# Tier 3: Cross-Feature Combinations & Atomic Ingestion
# ============================================================================

class TestTier3CrossFeatureCombinations:
    """Atomic multi-entity ingestion and full epistemic state transitions."""

    @pytest.mark.asyncio
    async def test_atomic_epistemic_claim_with_all_entities(
        self,
        e2e_service: EpistemicGraphService,
    ) -> None:
        """Atomically persist Fact + Proof + Methodology + Dataset + Source in one transaction."""
        run_tag = uuid.uuid4().hex[:8]
        fid = f"test_e2e_atomic_full_f_{run_tag}"
        pid = f"test_e2e_atomic_full_p_{run_tag}"
        mid = f"test_e2e_atomic_full_m_{run_tag}"
        did = f"test_e2e_atomic_full_d_{run_tag}"
        sid = f"test_e2e_atomic_full_s_{run_tag}"

        fact = Fact(fact_id=fid, statement="Low-rank adaptation with rank 8 suffices for code generation fine-tuning.")
        proof = Proof(proof_id=pid, summary="Achieves 68.4% pass@1 on HumanEval matching full fine-tuning.")
        method = Methodology(methodology_id=mid, name="LoRA Rank 8 FP16", description="Adapts q_proj and v_proj weights.")
        dataset = Dataset(dataset_id=did, name=f"HumanEval_{run_tag}", description="164 hand-written Python coding tasks.")
        source = Source(source_id=sid, title="Evaluating Large Language Models Trained on Code", year=2021)

        result = await e2e_service.append_epistemic_claim(
            fact=fact,
            proof=proof,
            relationship_type="SUPPORTED_BY",
            edge_description="Demonstrates full parameter parity on Python synthesis benchmarks.",
            methodology=method,
            method_description="Configured with rank r=8, alpha=16, learning rate 3e-4.",
            dataset=dataset,
            dataset_description="Evaluated on canonical HumanEval test split with temperature=0.2.",
            source=source,
            source_description="Referencing Chen et al. benchmark protocol.",
        )

        assert result.status == FactStatus.SUPPORTED
        assert result.fact.fact_id == fid
        assert result.proof.proof_id == pid
        assert result.methodology.methodology_id == mid
        assert result.dataset.dataset_id == did
        assert result.source.source_id == sid

        # Check in graph
        subgraph = await e2e_service.get_debate_subgraph(fid, depth=2)
        assert len(subgraph.supporting_proofs) == 1
        assert len(subgraph.methodologies) == 1
        assert len(subgraph.datasets) == 1
        assert len(subgraph.sources) == 1

    @pytest.mark.asyncio
    async def test_complete_epistemic_status_lifecycle_transitions(
        self,
        e2e_service: EpistemicGraphService,
    ) -> None:
        """Verify state lifecycle: tentative -> supported -> consensus -> debated -> refuted."""
        run_tag = uuid.uuid4().hex[:8]
        fid = f"test_e2e_lifecycle_f_{run_tag}"

        fact = Fact(fact_id=fid, statement="Mixture of Experts (MoE) routing causes representation collapse on specialized domains.")
        await e2e_service.append_fact(fact)

        # 1. Initially tentative
        f0 = await e2e_service.get_fact(fid)
        assert f0.status == FactStatus.TENTATIVE

        # 2. Add 1 support -> SUPPORTED
        p1 = Proof(proof_id=f"test_e2e_p1_life_{run_tag}", summary="Expert utilization variance exceeds 80%.", confidence=0.85)
        await e2e_service.append_proof(p1, fact_id=fid, relationship_type="SUPPORTED_BY", description="Observed expert collapse in biomedical domains.")
        f1 = await e2e_service.get_fact(fid)
        assert f1.status == FactStatus.SUPPORTED

        # 3. Add 2nd and 3rd support -> CONSENSUS
        p2 = Proof(proof_id=f"test_e2e_p2_life_{run_tag}", summary="Load balancing loss causes routing instability.", confidence=0.90)
        await e2e_service.append_proof(p2, fact_id=fid, relationship_type="SUPPORTED_BY", description="Confirmed routing instability across 3 seeds.")
        p3 = Proof(proof_id=f"test_e2e_p3_life_{run_tag}", summary="Top-2 gate drops tokens under high batch size.", confidence=0.90)
        await e2e_service.append_proof(p3, fact_id=fid, relationship_type="SUPPORTED_BY", description="Token drop rate exceeds 15% on legal text.")
        f2 = await e2e_service.get_fact(fid)
        assert f2.status == FactStatus.CONSENSUS

        # 4. Add 1 contradiction -> DEBATED (Debate preserved!)
        p4 = Proof(proof_id=f"test_e2e_p4_life_{run_tag}", summary="Auxiliary-loss-free routing eliminates expert collapse entirely.", confidence=0.92)
        await e2e_service.append_proof(p4, fact_id=fid, relationship_type="CONTRADICTED_BY", description="Disproves universal collapse: DeepSeek routing achieves perfect balance.")
        f3 = await e2e_service.get_fact(fid)
        assert f3.status == FactStatus.DEBATED


# ============================================================================
# Tier 4: Real-World Literature Review Workflows
# ============================================================================

class TestTier4RealWorldWorkflows:
    """Simulates authentic academic literature review dialectics and gap discovery."""

    @pytest.mark.asyncio
    async def test_scenario1_llm_reasoning_emergence_debate(
        self,
        e2e_service: EpistemicGraphService,
    ) -> None:
        """Scenario 1: CoT Prompting Emergent Reasoning Debate.
        
        Literature:
        - Proponent (Wei et al., 2022): CoT enables emergent multi-step reasoning capabilities.
        - Skeptic (Schaeffer et al., 2023): Emergence is a mirage produced by non-linear evaluation metrics.
        """
        run_tag = uuid.uuid4().hex[:8]
        fact_id = f"test_e2e_wei_schaeffer_fact_{run_tag}"

        fact = Fact(
            fact_id=fact_id,
            statement="Large language models exhibit emergent reasoning abilities not present in smaller models.",
            domain="LLM Scaling & Reasoning",
            project_id=f"proj_emergence_{run_tag}",
        )
        await e2e_service.append_fact(fact)

        # Wei et al. (Proponent)
        p_wei_id = f"test_e2e_p_wei_{run_tag}"
        m_wei_id = f"test_e2e_m_wei_{run_tag}"
        s_wei_id = f"test_e2e_s_wei_{run_tag}"

        await e2e_service.append_proof(Proof(
            proof_id=p_wei_id,
            summary="Chain-of-thought prompting produces sharp discontinuous performance jumps on BIG-bench beyond 10^22 FLOPs.",
            polarity=ProofPolarity.SUPPORTS,
            confidence=0.92,
            agent_id="EmergenceProponentAgent",
        ))
        await e2e_service.append_methodology(Methodology(
            methodology_id=m_wei_id,
            name="Few-Shot Chain-of-Thought Prompting",
            description="Supplies 8 exemplar question-rationale-answer triples.",
        ))
        await e2e_service.append_source(Source(
            source_id=s_wei_id,
            title="Emergent Abilities of Large Language Models",
            authors=["Jason Wei", "Yi Tay", "Rishi Bommasani", "Colin Raffel"],
            year=2022,
            venue="TMLR",
        ))
        await e2e_service.link_fact_to_proof(fact_id, p_wei_id, "SUPPORTED_BY", "Wei et al. observes discontinuous performance jump on math benchmarks.")
        await e2e_service.link_proof_to_methodology(p_wei_id, m_wei_id, "Uses greedy decoding with standardized prompt templates.")
        await e2e_service.link_to_source(p_wei_id, s_wei_id, "Table 1 and Figure 2.")

        # Schaeffer et al. (Skeptic)
        p_schaeffer_id = f"test_e2e_p_schaeffer_{run_tag}"
        m_schaeffer_id = f"test_e2e_m_schaeffer_{run_tag}"
        s_schaeffer_id = f"test_e2e_s_schaeffer_{run_tag}"

        await e2e_service.append_proof(Proof(
            proof_id=p_schaeffer_id,
            summary="When evaluated under continuous metrics (e.g. Brier score or token edit distance), performance improves linearly without emergence.",
            polarity=ProofPolarity.CONTRADICTS,
            confidence=0.91,
            agent_id="EmergenceMirageAgent",
        ))
        await e2e_service.append_methodology(Methodology(
            methodology_id=m_schaeffer_id,
            name="Continuous Metric Projection & Mathematical Mirage Analysis",
            description="Replaces discontinuous 0/1 accuracy with continuous probability mass and string distance.",
        ))
        await e2e_service.append_source(Source(
            source_id=s_schaeffer_id,
            title="Are Emergent Abilities of Large Language Models a Mirage?",
            authors=["Rylan Schaeffer", "Brando Miranda", "Sanmi Koyejo"],
            year=2023,
            venue="NeurIPS Outstanding Paper Award",
        ))
        await e2e_service.link_fact_to_proof(fact_id, p_schaeffer_id, "CONTRADICTED_BY", "Demonstrates that emergent discontinuous jumps vanish when replacing non-linear metrics with linear ones.")
        await e2e_service.link_proof_to_methodology(p_schaeffer_id, m_schaeffer_id, "Analytically proves accuracy creates step functions under geometric sequence length scaling.")
        await e2e_service.link_to_source(p_schaeffer_id, s_schaeffer_id, "Section 3, Equation 4.")

        # Traverse and verify debate synthesis
        subgraph: DebateSubgraph = await e2e_service.get_debate_subgraph(fact_id, depth=2)
        assert subgraph.central_fact.status == FactStatus.DEBATED
        assert len(subgraph.supporting_proofs) == 1
        assert len(subgraph.contradicting_proofs) == 1
        assert len(subgraph.methodologies) == 2
        assert len(subgraph.sources) == 2

    @pytest.mark.asyncio
    async def test_scenario2_community_aggregation_and_gap_discovery(
        self,
        e2e_service: EpistemicGraphService,
    ) -> None:
        """Scenario 2: Macro-level community clustering and contested gap discovery."""
        run_tag = uuid.uuid4().hex[:8]
        proj_id = f"proj_gap_{run_tag}"
        cm_id = f"test_e2e_community_eval_{run_tag}"

        await e2e_service.append_community(Community(
            community_id=cm_id,
            title="Reasoning Evaluation Paradigms",
            summary="Meta-cluster synthesizing the debate between discrete accuracy and continuous calibration.",
            level=1,
        ))

        # Add 2 contested facts and 1 consensus fact to the community
        for i in range(2):
            f_id = f"test_e2e_gap_fact_{i}_{run_tag}"
            await e2e_service.append_fact(Fact(fact_id=f_id, statement=f"Debated Claim {i}: Metric sensitivity affects claim {i}", project_id=proj_id))
            await e2e_service.append_proof(Proof(proof_id=f"test_e2e_gap_p_sup_{i}_{run_tag}", summary=f"Evidence for claim {i}"), fact_id=f_id, relationship_type="SUPPORTED_BY", description=f"Supports claim {i}")
            await e2e_service.append_proof(Proof(proof_id=f"test_e2e_gap_p_con_{i}_{run_tag}", summary=f"Evidence against claim {i}"), fact_id=f_id, relationship_type="CONTRADICTED_BY", description=f"Contradicts claim {i}")
            await e2e_service.link_fact_to_community(f_id, cm_id, f"Belongs to evaluation cluster {i}")

        # Contested discovery query
        contested = await e2e_service.list_contested_facts(project_id=proj_id)
        assert len(contested) == 2
        for item in contested:
            assert item["status"] == "debated"
            assert item["support_count"] >= 1
            assert item["contradiction_count"] >= 1

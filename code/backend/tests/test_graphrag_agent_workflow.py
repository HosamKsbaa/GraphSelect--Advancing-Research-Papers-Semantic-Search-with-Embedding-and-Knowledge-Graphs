"""Acceptance criteria verification for ALRS GraphRAG multi-agent debate workflow.

Verifies:
1. Two autonomous agents acting on the graph:
   - Agent 1 (ProponentAgent) injects a Fact with a Proof linked via SUPPORTED_BY and a Methodology via USES_METHOD.
   - Agent 2 (SkepticAgent) injects an opposing Proof for the EXACT SAME Fact linked via CONTRADICTED_BY and another Methodology via USES_METHOD.
2. Depth-2 sub-graph query against the central Fact:
   - Retrieves central Fact (statement is invariant, NOT overwritten).
   - Epistemic status reflects DEBATED.
   - Subgraph contains BOTH opposing Proof nodes (SUPPORTED_BY and CONTRADICTED_BY).
   - Subgraph contains BOTH associated Methodology nodes.
   - Rich-text relationship descriptions are preserved on both opposing edges and method edges.
3. Multi-agent debate extension with Datasets, Limitations, and Contested Facts listing.
"""
from __future__ import annotations

import uuid
import pytest
import pytest_asyncio

from core.db.neo4j_service import Neo4jService
from features.graphrag.models import (
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
)
from features.graphrag.service import EpistemicGraphService

NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASS = "changeme"


@pytest_asyncio.fixture(scope="function")
async def graphrag_service() -> EpistemicGraphService:
    """Provides an EpistemicGraphService connected to live Neo4j with scoped targeted teardown."""
    neo4j = Neo4jService(NEO4J_URI, NEO4J_USER, NEO4J_PASS)
    await neo4j.connect()
    service = EpistemicGraphService(neo4j)
    await service.initialize_schema()
    yield service

    # Targeted safety cleanup: ONLY delete nodes with test_workflow_ prefix
    cleanup_query = """
    MATCH (n)
    WHERE (n.fact_id STARTS WITH 'test_workflow_'
        OR n.proof_id STARTS WITH 'test_workflow_'
        OR n.methodology_id STARTS WITH 'test_workflow_'
        OR n.source_id STARTS WITH 'test_workflow_'
        OR n.concept_id STARTS WITH 'test_workflow_'
        OR n.dataset_id STARTS WITH 'test_workflow_'
        OR n.question_id STARTS WITH 'test_workflow_'
        OR n.limitation_id STARTS WITH 'test_workflow_'
        OR n.community_id STARTS WITH 'test_workflow_')
    DETACH DELETE n
    """
    try:
        await neo4j.execute_write(cleanup_query)
    finally:
        await neo4j.close()


class TestMultiAgentDebateWorkflow:
    """Core Acceptance Criteria verification tests for multi-agent dialectical GraphRAG."""

    @pytest.mark.asyncio
    async def test_two_agents_opposing_proofs_and_depth2_subgraph_retrieval(
        self,
        graphrag_service: EpistemicGraphService,
    ) -> None:
        """Simulate two autonomous agents injecting opposing proofs for the exact same Fact.
        
        Direct Acceptance Criteria verification:
        1. Agent 1 (ProponentAgent) injects Fact + Proof (SUPPORTED_BY) + Methodology (USES_METHOD).
        2. Agent 2 (SkepticAgent) injects Proof (CONTRADICTED_BY) + Methodology (USES_METHOD) for the exact same Fact.
        3. Depth-2 subgraph query retrieves central Fact, both opposing Proofs, both Methodologies, and rich descriptions.
        4. Central Fact is NOT overwritten and epistemic status reflects 'debated'.
        """
        run_tag = uuid.uuid4().hex[:8]
        fact_id = f"test_workflow_fact_{run_tag}"
        proof_1_id = f"test_workflow_proof_alpha_{run_tag}"
        method_1_id = f"test_workflow_method_alpha_{run_tag}"
        proof_2_id = f"test_workflow_proof_beta_{run_tag}"
        method_2_id = f"test_workflow_method_beta_{run_tag}"

        original_statement = "Speculative decoding achieves 2.5x speedup across all LLM inference workloads."

        # ====================================================================
        # Step 1: Agent 1 (ProponentAgent) injects Fact, Supporting Proof, and Method
        # ====================================================================
        fact = Fact(
            fact_id=fact_id,
            statement=original_statement,
            domain="Systems & LLM Inference",
            project_id=f"proj_{run_tag}",
            created_by_agent="ProponentAgent_Alpha",
        )
        await graphrag_service.append_fact(fact)

        proof_1 = Proof(
            proof_id=proof_1_id,
            summary="Draft model speculative verification demonstrates 2.6x wall-clock speedup on chat generation.",
            polarity=ProofPolarity.SUPPORTS,
            proof_type=ProofType.EMPIRICAL_BENCHMARK,
            confidence=0.90,
            agent_id="ProponentAgent_Alpha",
        )
        await graphrag_service.append_proof(proof_1)

        method_1 = Methodology(
            methodology_id=method_1_id,
            name="Greedy Speculative Verification (K=5)",
            description="Small draft model (LLaMA-68M) proposes K=5 lookahead tokens; 70B target verifies in parallel.",
            category=MethodologyCategory.EVALUATION_PROTOCOL,
            hyperparameters={"K": 5, "draft_model": "LLaMA-68M", "target_model": "LLaMA-70B"},
        )
        await graphrag_service.append_methodology(method_1)

        # Agent 1 links Fact to Proof via SUPPORTED_BY with rich description
        rel_desc_1 = (
            "Empirical verification confirms 2.6x speedup on low-entropy autoregressive dialogue generation "
            "where draft model acceptance rate exceeds 82%."
        )
        await graphrag_service.link_fact_to_proof(
            fact_id=fact_id,
            proof_id=proof_1_id,
            polarity="SUPPORTED_BY",
            description=rel_desc_1,
            confidence=0.90,
            agent_id="ProponentAgent_Alpha",
        )

        # Agent 1 links Proof to Methodology via USES_METHOD with rich description
        method_desc_1 = "Applied greedy decoding with K=5 lookahead verification across standard conversation prompts."
        await graphrag_service.link_proof_to_methodology(
            proof_id=proof_1_id,
            methodology_id=method_1_id,
            description=method_desc_1,
            role="primary",
        )

        # Verify state after Agent 1: Fact should be SUPPORTED
        fact_after_agent_1 = await graphrag_service.get_fact(fact_id)
        assert fact_after_agent_1 is not None
        assert fact_after_agent_1.status == FactStatus.SUPPORTED
        assert fact_after_agent_1.confidence_score >= 0.60

        # ====================================================================
        # Step 2: Agent 2 (SkepticAgent) injects Opposing Proof & Method for SAME Fact
        # ====================================================================
        proof_2 = Proof(
            proof_id=proof_2_id,
            summary="Evaluation on high-temperature code generation yields acceptance rates below 20%, resulting in 0.85x slowdown.",
            polarity=ProofPolarity.CONTRADICTS,
            proof_type=ProofType.EMPIRICAL_BENCHMARK,
            confidence=0.88,
            agent_id="SkepticAgent_Beta",
        )
        await graphrag_service.append_proof(proof_2)

        method_2 = Methodology(
            methodology_id=method_2_id,
            name="Stochastic Code Benchmark with Temperature 0.8",
            description="Evaluates speculative acceptance rates when target token distribution entropy is high.",
            category=MethodologyCategory.EVALUATION_PROTOCOL,
            hyperparameters={"temperature": 0.8, "top_p": 0.95, "benchmark": "HumanEval"},
        )
        await graphrag_service.append_methodology(method_2)

        # Agent 2 links Fact to Proof via CONTRADICTED_BY with rich description
        rel_desc_2 = (
            "Directly refutes universal speedup claim: speculative decoding introduces memory overhead "
            "and draft rejection cascades on high-entropy coding tasks, producing net wall-clock slowdown."
        )
        await graphrag_service.link_fact_to_proof(
            fact_id=fact_id,
            proof_id=proof_2_id,
            polarity="CONTRADICTED_BY",
            description=rel_desc_2,
            confidence=0.88,
            agent_id="SkepticAgent_Beta",
        )

        # Agent 2 links Proof to Methodology via USES_METHOD with rich description
        method_desc_2 = "Evaluated on 500 Python programs using stochastic sampling at temperature 0.8 and top-p 0.95."
        await graphrag_service.link_proof_to_methodology(
            proof_id=proof_2_id,
            methodology_id=method_2_id,
            description=method_desc_2,
            role="primary",
        )

        # ====================================================================
        # Step 3: Verify Fact Invariance & Status Transition to DEBATED
        # ====================================================================
        fact_after_agent_2 = await graphrag_service.get_fact(fact_id)
        assert fact_after_agent_2 is not None

        # Critical: Fact statement was NOT overwritten or corrupted
        assert fact_after_agent_2.statement == original_statement
        assert fact_after_agent_2.fact_id == fact_id

        # Critical: Epistemic status reflects DEBATED
        assert fact_after_agent_2.status == FactStatus.DEBATED
        # Confidence reflects balanced debate (~0.5)
        assert 0.40 <= fact_after_agent_2.confidence_score <= 0.60

        # ====================================================================
        # Step 4: Execute Depth-2 Subgraph Traversal & Assert Debate Structure
        # ====================================================================
        subgraph: DebateSubgraph = await graphrag_service.get_debate_subgraph(fact_id, depth=2)

        # Assert Central Fact
        assert subgraph.central_fact.fact_id == fact_id
        assert subgraph.central_fact.statement == original_statement
        assert subgraph.central_fact.status == FactStatus.DEBATED

        # Assert Both Opposing Proof Nodes
        proof_ids_in_subgraph = {p.proof_id for p in subgraph.supporting_proofs + subgraph.contradicting_proofs}
        assert proof_1_id in proof_ids_in_subgraph
        assert proof_2_id in proof_ids_in_subgraph

        assert len(subgraph.supporting_proofs) == 1
        assert subgraph.supporting_proofs[0].proof_id == proof_1_id
        assert subgraph.supporting_proofs[0].polarity == ProofPolarity.SUPPORTS

        assert len(subgraph.contradicting_proofs) == 1
        assert subgraph.contradicting_proofs[0].proof_id == proof_2_id
        assert subgraph.contradicting_proofs[0].polarity == ProofPolarity.CONTRADICTS

        # Assert Both Associated Methodology Nodes
        method_ids_in_subgraph = {m.methodology_id for m in subgraph.methodologies}
        assert method_1_id in method_ids_in_subgraph
        assert method_2_id in method_ids_in_subgraph

        # Assert Rich-Text Relationship Descriptions on All Edges
        rel_types = {r.type for r in subgraph.relationships}
        assert "SUPPORTED_BY" in rel_types
        assert "CONTRADICTED_BY" in rel_types
        assert "USES_METHOD" in rel_types

        # Verify descriptions on SUPPORTED_BY and CONTRADICTED_BY
        sup_rel = next(r for r in subgraph.relationships if r.type == "SUPPORTED_BY")
        assert sup_rel.source == fact_id
        assert sup_rel.target == proof_1_id
        assert sup_rel.description == rel_desc_1

        con_rel = next(r for r in subgraph.relationships if r.type == "CONTRADICTED_BY")
        assert con_rel.source == fact_id
        assert con_rel.target == proof_2_id
        assert con_rel.description == rel_desc_2

        # Verify descriptions on USES_METHOD edges
        method_rels = [r for r in subgraph.relationships if r.type == "USES_METHOD"]
        assert len(method_rels) == 2
        method_desc_map = {r.source: r.description for r in method_rels}
        assert method_desc_map[proof_1_id] == method_desc_1
        assert method_desc_map[proof_2_id] == method_desc_2

    @pytest.mark.asyncio
    async def test_atomic_multi_agent_composite_claims(
        self,
        graphrag_service: EpistemicGraphService,
    ) -> None:
        """Test atomic composite claim ingestion by opposing agents using append_epistemic_claim."""
        run_tag = uuid.uuid4().hex[:8]
        fact_id = f"test_workflow_fact_atomic_{run_tag}"

        fact = Fact(
            fact_id=fact_id,
            statement="Quantized 4-bit weights preserve reasoning capacity on competition math.",
            domain="Model Compression",
            project_id=f"proj_{run_tag}",
        )

        # Agent 1 atomically appends Fact + Supporting Proof + Methodology + Dataset
        proof_1 = Proof(
            proof_id=f"test_workflow_p1_atomic_{run_tag}",
            summary="NF4 quantization achieves 98.5% accuracy retention on GSM8K.",
            polarity=ProofPolarity.SUPPORTS,
            confidence=0.92,
            agent_id="QuantizationProponent",
        )
        method_1 = Methodology(
            methodology_id=f"test_workflow_m1_atomic_{run_tag}",
            name="NormalFloat4 (NF4) Quantization with Double Quantization",
            description="Quantizes weights to 4-bit normal float representation.",
        )
        dataset_1 = Dataset(
            dataset_id=f"test_workflow_d1_atomic_{run_tag}",
            name="GSM8K",
            description="Grade school math word problems.",
        )

        res1 = await graphrag_service.append_epistemic_claim(
            fact=fact,
            proof=proof_1,
            relationship_type="SUPPORTED_BY",
            edge_description="NF4 shows virtually lossless accuracy retention on elementary math word problems.",
            methodology=method_1,
            method_description="Employed standard NF4 block size of 64 with FP16 compute type.",
            dataset=dataset_1,
            dataset_description="Evaluated on full 1,319 test split of GSM8K.",
        )
        assert res1.status == FactStatus.SUPPORTED

        # Agent 2 atomically appends Contradicting Proof + Methodology + Dataset to SAME Fact
        proof_2 = Proof(
            proof_id=f"test_workflow_p2_atomic_{run_tag}",
            summary="MATH benchmark accuracy drops by 24.1% under 4-bit quantization.",
            polarity=ProofPolarity.CONTRADICTS,
            confidence=0.89,
            agent_id="QuantizationSkeptic",
        )
        method_2 = Methodology(
            methodology_id=f"test_workflow_m2_atomic_{run_tag}",
            name="16-Shot Competition Math Evaluation",
            description="Tests multi-step proof reasoning on challenging competition mathematics.",
        )
        dataset_2 = Dataset(
            dataset_id=f"test_workflow_d2_atomic_{run_tag}",
            name="MATH",
            description="Competition math dataset with step-by-step LaTeX solutions.",
        )

        res2 = await graphrag_service.append_epistemic_claim(
            fact=fact,
            proof=proof_2,
            relationship_type="CONTRADICTED_BY",
            edge_description="Demonstrates severe degradation on complex multi-step theorem proving and competition math.",
            methodology=method_2,
            method_description="Tested across 5,000 competition problems spanning 7 subjects.",
            dataset=dataset_2,
            dataset_description="Evaluated on the full test split of Hendrycks MATH.",
        )
        assert res2.status == FactStatus.DEBATED

        # Subgraph inspection
        subgraph = await graphrag_service.get_debate_subgraph(fact_id, depth=2)
        assert subgraph.central_fact.status == FactStatus.DEBATED
        assert len(subgraph.supporting_proofs) == 1
        assert len(subgraph.contradicting_proofs) == 1
        assert len(subgraph.methodologies) == 2
        assert len(subgraph.datasets) == 2

    @pytest.mark.asyncio
    async def test_contested_facts_discovery_across_agents(
        self,
        graphrag_service: EpistemicGraphService,
    ) -> None:
        """Verify that list_contested_facts accurately returns facts debated by opposing agents."""
        run_tag = uuid.uuid4().hex[:8]
        proj_id = f"proj_contested_{run_tag}"
        fact_id = f"test_workflow_fact_disc_{run_tag}"

        # Inject contested debate
        fact = Fact(
            fact_id=fact_id,
            statement="Chain-of-thought prompting universally increases model calibration.",
            project_id=proj_id,
        )
        await graphrag_service.append_fact(fact)

        p1_id = f"test_workflow_p1_disc_{run_tag}"
        await graphrag_service.append_proof(
            Proof(proof_id=p1_id, summary="ECE drops on factual QA.", polarity=ProofPolarity.SUPPORTS, agent_id="AgentA"),
            fact_id=fact_id,
            relationship_type="SUPPORTED_BY",
            description="Shows calibration error decreases when reasoning steps are explicitly spelled out.",
        )

        p2_id = f"test_workflow_p2_disc_{run_tag}"
        await graphrag_service.append_proof(
            Proof(proof_id=p2_id, summary="ECE increases on symbolic reasoning.", polarity=ProofPolarity.CONTRADICTS, agent_id="AgentB"),
            fact_id=fact_id,
            relationship_type="CONTRADICTED_BY",
            description="Shows models express overconfidence when rationalizing incorrect intermediate deduction steps.",
        )

        # Retrieve contested facts for this project
        contested = await graphrag_service.list_contested_facts(project_id=proj_id)
        assert len(contested) >= 1
        found = next((item for item in contested if item["fact_id"] == fact_id), None)
        assert found is not None
        assert found["status"] == "debated"
        assert found["support_count"] >= 1
        assert found["contradiction_count"] >= 1

    @pytest.mark.asyncio
    async def test_consensus_formation_and_subsequent_reopening_of_debate(
        self,
        graphrag_service: EpistemicGraphService,
    ) -> None:
        """Test consensus formation (3 supporting proofs) and subsequent transition to DEBATED upon contradiction."""
        run_tag = uuid.uuid4().hex[:8]
        fact_id = f"test_workflow_fact_consensus_{run_tag}"

        fact = Fact(
            fact_id=fact_id,
            statement="Scaling attention window to 128k tokens requires positional interpolation.",
            project_id=f"proj_{run_tag}",
        )
        await graphrag_service.append_fact(fact)

        # Agent 1 injects Proof 1
        p1 = Proof(proof_id=f"test_workflow_p1_cons_{run_tag}", summary="PI preserves perplexity up to 32k.", polarity=ProofPolarity.SUPPORTS, confidence=0.85, agent_id="Agent1")
        await graphrag_service.append_proof(p1, fact_id=fact_id, relationship_type="SUPPORTED_BY", description="Confirms PI maintains low perplexity on 32k context.")
        f_state1 = await graphrag_service.get_fact(fact_id)
        assert f_state1.status == FactStatus.SUPPORTED

        # Agent 2 injects Proof 2
        p2 = Proof(proof_id=f"test_workflow_p2_cons_{run_tag}", summary="YaRN extends context to 64k without fine-tuning loss.", polarity=ProofPolarity.SUPPORTS, confidence=0.90, agent_id="Agent2")
        await graphrag_service.append_proof(p2, fact_id=fact_id, relationship_type="SUPPORTED_BY", description="Replicates PI advantages using temperature-scaled interpolation.")
        f_state2 = await graphrag_service.get_fact(fact_id)
        assert f_state2.status == FactStatus.SUPPORTED

        # Agent 3 injects Proof 3 -> High consensus threshold reached (>=3 supports, w_sup >= 2.4)
        p3 = Proof(proof_id=f"test_workflow_p3_cons_{run_tag}", summary="LongRoPE verifies 128k retrieval accuracy.", polarity=ProofPolarity.SUPPORTS, confidence=0.95, agent_id="Agent3")
        await graphrag_service.append_proof(p3, fact_id=fact_id, relationship_type="SUPPORTED_BY", description="Extends verification to full 128k tokens with high retrieval accuracy.")
        f_state3 = await graphrag_service.get_fact(fact_id)
        assert f_state3.status == FactStatus.CONSENSUS
        assert f_state3.confidence_score >= 0.90

        # Agent 4 (Challenger) discovers failure mode and injects CONTRADICTED_BY proof
        p4 = Proof(proof_id=f"test_workflow_p4_cons_{run_tag}", summary="Linear attention without RoPE exhibits no degradation at 128k.", polarity=ProofPolarity.CONTRADICTS, confidence=0.88, agent_id="AgentChallenger")
        await graphrag_service.append_proof(p4, fact_id=fact_id, relationship_type="CONTRADICTED_BY", description="Disproves necessity of positional interpolation for non-softmax linear architectures.")
        f_state4 = await graphrag_service.get_fact(fact_id)
        assert f_state4.status == FactStatus.DEBATED

    @pytest.mark.asyncio
    async def test_full_epistemic_depth2_graph_with_datasets_sources_and_limitations(
        self,
        graphrag_service: EpistemicGraphService,
    ) -> None:
        """Verify depth-2 subgraph with Fact, 2 opposing Proofs, Methodologies, Datasets, Sources, and Limitations."""
        run_tag = uuid.uuid4().hex[:8]
        fact_id = f"test_workflow_fact_full_{run_tag}"

        fact = Fact(
            fact_id=fact_id,
            statement="Chain-of-thought distillation into 1B student models matches teacher reasoning performance.",
            project_id=f"proj_{run_tag}",
        )
        await graphrag_service.append_fact(fact)

        # 1. Proponent side: Proof + Methodology + Dataset + Limitation
        p_sup_id = f"test_workflow_p_sup_{run_tag}"
        m_sup_id = f"test_workflow_m_sup_{run_tag}"
        d_sup_id = f"test_workflow_d_sup_{run_tag}"
        l_sup_id = f"test_workflow_l_sup_{run_tag}"

        await graphrag_service.append_proof(Proof(proof_id=p_sup_id, summary="Matches 70B teacher on SVAMP math.", polarity=ProofPolarity.SUPPORTS, agent_id="DistillProponent"))
        await graphrag_service.append_methodology(Methodology(methodology_id=m_sup_id, name="Step-by-Step CoT Distillation", description="KL-divergence loss over teacher rationales."))
        await graphrag_service.append_dataset(Dataset(dataset_id=d_sup_id, name="SVAMP", description="Elementary word problems."))
        await graphrag_service.append_limitation(Limitation(limitation_id=l_sup_id, statement="Limited to short word problems.", severity=LimitationSeverity.MODERATE))

        await graphrag_service.link_fact_to_proof(fact_id, p_sup_id, "SUPPORTED_BY", "Validates distillation parity on elementary math word problems.")
        await graphrag_service.link_proof_to_methodology(p_sup_id, m_sup_id, "Uses cross-entropy and rationale weighting.")
        await graphrag_service.link_proof_to_dataset(p_sup_id, d_sup_id, "Evaluated on the full SVAMP dataset.")
        await graphrag_service.link_to_limitation(p_sup_id, l_sup_id, "Student performance degrades as word problem complexity increases.")

        # 2. Opposing side: Proof + Methodology + Dataset + Limitation
        p_con_id = f"test_workflow_p_con_{run_tag}"
        m_con_id = f"test_workflow_m_con_{run_tag}"
        d_con_id = f"test_workflow_d_con_{run_tag}"
        l_con_id = f"test_workflow_l_con_{run_tag}"

        await graphrag_service.append_proof(Proof(proof_id=p_con_id, summary="Suffers 48% accuracy drop on OlympiadBench.", polarity=ProofPolarity.CONTRADICTS, agent_id="DistillSkeptic"))
        await graphrag_service.append_methodology(Methodology(methodology_id=m_con_id, name="Hard Multi-Step Theorem Proof", description="Formal verification benchmark."))
        await graphrag_service.append_dataset(Dataset(dataset_id=d_con_id, name="OlympiadBench", description="Olympiad level math."))
        await graphrag_service.append_limitation(Limitation(limitation_id=l_con_id, statement="Requires formal Lean/Isabelle verification.", severity=LimitationSeverity.CRITICAL))

        await graphrag_service.link_fact_to_proof(fact_id, p_con_id, "CONTRADICTED_BY", "Demonstrates catastrophic reasoning collapse on Olympiad benchmarks.")
        await graphrag_service.link_proof_to_methodology(p_con_id, m_con_id, "Evaluates step-by-step logic against ground-truth formal proofs.")
        await graphrag_service.link_proof_to_dataset(p_con_id, d_con_id, "Benchmarked on OlympiadBench bilingual test suite.")
        await graphrag_service.link_to_limitation(p_con_id, l_con_id, "Evaluator restricted to formal math problems.")

        # Query depth-2 debate subgraph
        subgraph = await graphrag_service.get_debate_subgraph(fact_id, depth=2)
        assert subgraph.central_fact.status == FactStatus.DEBATED

        # Verify all depth-2 entities are collected
        assert len(subgraph.supporting_proofs) == 1
        assert len(subgraph.contradicting_proofs) == 1
        assert len(subgraph.methodologies) == 2
        assert len(subgraph.datasets) == 2
        assert len(subgraph.limitations) == 2

        # Verify relationships
        rel_types = {r.type for r in subgraph.relationships}
        assert "SUPPORTED_BY" in rel_types
        assert "CONTRADICTED_BY" in rel_types
        assert "USES_METHOD" in rel_types
        assert "EVALUATED_ON" in rel_types
        assert "HAS_LIMITATION" in rel_types

        # Verify all relationships carry rich-text descriptions
        for r in subgraph.relationships:
            assert len(r.description.strip()) >= 5, f"Edge {r.type} missing rich-text description"

    @pytest.mark.asyncio
    async def test_fact_statement_immutability_and_append_only_integrity(
        self,
        graphrag_service: EpistemicGraphService,
    ) -> None:
        """Verify that attempting to destructively mutate a Fact statement triggers EpistemicIntegrityError."""
        from features.graphrag.conflict import verify_append_only_transition, EpistemicIntegrityError

        tag = uuid.uuid4().hex[:8]
        fact_id = f"test_workflow_immut_{tag}"
        original = "FlashAttention-2 provides 2x speedup over FlashAttention-1."
        mutated = "FlashAttention-2 is slower than FlashAttention-1."

        # 1. In-memory standalone verification
        with pytest.raises(EpistemicIntegrityError):
            verify_append_only_transition(original, mutated)

        verify_append_only_transition(original, original)
        verify_append_only_transition(original, "  FlashAttention-2 provides 2x speedup over FlashAttention-1.  ")

        # 2. Database service verification: append_fact rejects overwrite
        f1 = Fact(fact_id=fact_id, statement=original, domain="Systems")
        await graphrag_service.append_fact(f1)

        f_mutated = Fact(fact_id=fact_id, statement=mutated, domain="Systems")
        with pytest.raises(EpistemicIntegrityError, match="Destructive fact overwrite detected"):
            await graphrag_service.append_fact(f_mutated)

        # Verify fact statement in database was NOT altered
        persisted = await graphrag_service.get_fact(fact_id)
        assert persisted is not None
        assert persisted.statement == original

        # 3. Database service verification: append_epistemic_claim rejects overwrite
        p_claim = Proof(
            proof_id=f"test_workflow_proof_immut_{tag}",
            summary="Benchmarking attention throughput on H100 SXM5",
            polarity=ProofPolarity.SUPPORTS,
        )
        with pytest.raises(EpistemicIntegrityError, match="Destructive fact overwrite detected"):
            await graphrag_service.append_epistemic_claim(
                fact=f_mutated,
                proof=p_claim,
                relationship_type="SUPPORTED_BY",
                edge_description="Hardware throughput benchmarks across diverse head dimensions",
            )

        # Confirm DB still has immutable original statement
        persisted_after_claim = await graphrag_service.get_fact(fact_id)
        assert persisted_after_claim is not None
        assert persisted_after_claim.statement == original

        # 4. Idempotent re-append with identical statement succeeds cleanly
        f_idempotent = Fact(fact_id=fact_id, statement=f"  {original}  ", domain="Hardware Optimization")
        res_id = await graphrag_service.append_fact(f_idempotent)
        assert res_id == fact_id
        persisted_idemp = await graphrag_service.get_fact(fact_id)
        assert persisted_idemp is not None
        assert persisted_idemp.statement == original
        assert persisted_idemp.domain == "Hardware Optimization"


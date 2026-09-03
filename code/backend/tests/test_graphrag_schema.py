"""Test suite for GraphRAG schema: 9 node models, rich relationships, and Neo4j DDL constraints.

Tests:
1. Pydantic v2 instantiation, defaults, constraints, and alias handling for all 9 node types:
   Fact, Proof, Methodology, Source, Concept, Dataset, Question, Limitation, Community.
2. Edge models and mandatory rich-text description validation across all relationship types:
   SupportedByRel, ContradictedByRel, UsesMethodRel, EvaluatedOnRel, ExtractedFromRel,
   AddressesRel, RelatesToConceptRel, HasLimitationRel, BelongsToCommunityRel.
3. Neo4j schema constraint initialization and uniqueness enforcement against live Neo4j database.
"""
from __future__ import annotations

from datetime import datetime, timezone
import uuid
import pytest
import pytest_asyncio
from pydantic import ValidationError

from core.db.neo4j_service import Neo4jService
from features.graphrag.conflict import (
    EpistemicIntegrityError,
    InvalidRelationshipError,
    validate_relationship_type,
    validate_rich_description,
)
from features.graphrag.models import (
    AddressesRel,
    BelongsToCommunityRel,
    Community,
    CommunityCreate,
    Concept,
    ConceptCreate,
    ContradictedByRel,
    Dataset,
    DatasetCreate,
    DebateSubgraph,
    EvaluatedOnRel,
    ExtractedFromRel,
    Fact,
    FactCreate,
    FactStatus,
    HasLimitationRel,
    Limitation,
    LimitationCreate,
    LimitationSeverity,
    Methodology,
    MethodologyCategory,
    MethodologyCreate,
    Proof,
    ProofCreate,
    ProofPolarity,
    ProofType,
    Question,
    QuestionCreate,
    RelatesToConceptRel,
    RelationshipEdge,
    RelationshipType,
    Source,
    SourceCreate,
    SubgraphNode,
    SubgraphRelationship,
    SupportedByRel,
    UsesMethodRel,
)
from features.graphrag.schema import (
    GRAPHRAG_CONSTRAINTS,
    GRAPHRAG_INDEXES,
    init_graphrag_schema,
)

# Neo4j connection parameters for test environment
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASS = "changeme"

TEST_TAG = f"test_schema_{uuid.uuid4().hex[:8]}"


# ============================================================================
# Fixtures
# ============================================================================

@pytest_asyncio.fixture(scope="function")
async def neo4j_service() -> Neo4jService:
    """Provides an active Neo4j service for schema validation with targeted teardown."""
    service = Neo4jService(NEO4J_URI, NEO4J_USER, NEO4J_PASS)
    await service.connect()
    yield service
    # Targeted safety cleanup: ONLY delete nodes created with test_schema_ prefix
    cleanup_query = """
    MATCH (n)
    WHERE (n.fact_id STARTS WITH 'test_schema_'
        OR n.proof_id STARTS WITH 'test_schema_'
        OR n.methodology_id STARTS WITH 'test_schema_'
        OR n.source_id STARTS WITH 'test_schema_'
        OR n.concept_id STARTS WITH 'test_schema_'
        OR n.dataset_id STARTS WITH 'test_schema_'
        OR n.question_id STARTS WITH 'test_schema_'
        OR n.limitation_id STARTS WITH 'test_schema_'
        OR n.community_id STARTS WITH 'test_schema_')
    DETACH DELETE n
    """
    try:
        await service.execute_write(cleanup_query)
    finally:
        await service.close()


# ============================================================================
# 1. 9 Node Models Validation & Instantiation Tests
# ============================================================================

class TestNodeModelInstantiation:
    """Validates instantiation, default values, and aliases of all 9 node models."""

    def test_fact_model_instantiation(self) -> None:
        """Validate Fact model default values and aliases."""
        fact = Fact(
            statement="Transformer architectures scale loss as a power law with compute.",
            project_id="proj_123",
        )
        assert fact.statement == "Transformer architectures scale loss as a power law with compute."
        assert fact.status == FactStatus.TENTATIVE
        assert fact.confidence_score == 0.5
        assert fact.domain == "general"
        assert fact.id == fact.fact_id
        assert fact.epistemic_status == FactStatus.TENTATIVE
        assert isinstance(fact.created_at, datetime)

    def test_fact_model_alias_id_and_status(self) -> None:
        """Validate Fact alias resolution for 'id' and 'epistemic_status'."""
        fact = Fact.model_validate({
            "id": "fact_custom_uuid",
            "statement": "Low-rank adaptation reduces trainable parameters by 99%.",
            "epistemic_status": "supported",
            "confidence_score": 0.95,
        })
        assert fact.fact_id == "fact_custom_uuid"
        assert fact.status == FactStatus.SUPPORTED
        assert fact.confidence_score == 0.95

    def test_proof_model_instantiation(self) -> None:
        """Validate Proof model default values, enums, and properties."""
        proof = Proof(
            summary="Empirical evaluation on GSM8K demonstrates 92% accuracy.",
            polarity=ProofPolarity.SUPPORTS,
            proof_type=ProofType.EMPIRICAL_BENCHMARK,
            confidence=0.88,
            agent_id="ResearchAgent_Alpha",
        )
        assert proof.summary.startswith("Empirical evaluation")
        assert proof.polarity == ProofPolarity.SUPPORTS
        assert proof.proof_type == ProofType.EMPIRICAL_BENCHMARK
        assert proof.confidence == 0.88
        assert proof.id == proof.proof_id
        assert proof.extracted_quote is None

    def test_proof_model_aliases(self) -> None:
        """Validate Proof alias resolution for 'id', 'quote', and 'created_by_agent'."""
        proof = Proof.model_validate({
            "id": "proof_custom_uuid",
            "summary": "Mathematical derivation proves convergence in O(1/epsilon^2) steps.",
            "quote": "Theorem 3.1: The stochastic gradient bound holds for all epsilon > 0.",
            "created_by_agent": "TheoryAgent_Beta",
            "polarity": "contradicts",
        })
        assert proof.proof_id == "proof_custom_uuid"
        assert proof.extracted_quote.startswith("Theorem 3.1")
        assert proof.quote == proof.extracted_quote
        assert proof.agent_id == "TheoryAgent_Beta"
        assert proof.polarity == ProofPolarity.CONTRADICTS

    def test_methodology_model_instantiation(self) -> None:
        """Validate Methodology model instantiation and defaults."""
        method = Methodology(
            name="Rank-4 LoRA with FP16 Precision",
            description="Fine-tunes query and value projection weights using rank r=4 and alpha=8.",
            category=MethodologyCategory.MODEL_ARCHITECTURE,
            hyperparameters={"rank": 4, "alpha": 8, "lr": 1e-4},
        )
        assert method.name == "Rank-4 LoRA with FP16 Precision"
        assert method.id == method.methodology_id
        assert method.hyperparameters["rank"] == 4
        assert method.category == MethodologyCategory.MODEL_ARCHITECTURE

    def test_source_model_instantiation(self) -> None:
        """Validate Source model instantiation and properties."""
        source = Source(
            title="LoRA: Low-Rank Adaptation of Large Language Models",
            doi="10.48550/arXiv.2106.09685",
            authors=["Edward J. Hu", "Yelong Shen", "Phillip Wallis"],
            year=2021,
            venue="ICLR",
            citation_count=5400,
        )
        assert source.title.startswith("LoRA:")
        assert source.year == 2021
        assert len(source.authors) == 3
        assert source.id == source.source_id

    def test_concept_model_instantiation(self) -> None:
        """Validate Concept model instantiation and aliases."""
        concept = Concept(
            name="Parameter-Efficient Fine-Tuning",
            definition="Techniques that adapt pre-trained language models by updating a small subset of parameters.",
            domain="Natural Language Processing",
            aliases=["PEFT", "Parameter-Efficient Tuning"],
        )
        assert concept.name == "Parameter-Efficient Fine-Tuning"
        assert "PEFT" in concept.aliases
        assert concept.id == concept.concept_id

    def test_dataset_model_instantiation(self) -> None:
        """Validate Dataset model instantiation and properties."""
        dataset = Dataset(
            name="GSM8K",
            version="1.0",
            description="Grade School Math 8K benchmark consisting of 8,500 grade school math word problems.",
            modality="text",
            size="8500 questions",
            license="MIT",
        )
        assert dataset.name == "GSM8K"
        assert dataset.version == "1.0"
        assert dataset.id == dataset.dataset_id

    def test_question_model_instantiation(self) -> None:
        """Validate Question model instantiation and defaults."""
        question = Question(
            text="Does 4-bit weight quantization preserve chain-of-thought mathematical reasoning?",
            project_id="proj_research_2026",
        )
        assert question.text.startswith("Does 4-bit weight")
        assert question.status == "open"
        assert question.project_id == "proj_research_2026"
        assert question.id == question.question_id

    def test_limitation_model_instantiation(self) -> None:
        """Validate Limitation model instantiation and severity enums."""
        limitation = Limitation(
            statement="Evaluations were conducted solely on English language corpora.",
            severity=LimitationSeverity.CRITICAL,
            category="generalization",
        )
        assert limitation.statement.startswith("Evaluations were conducted")
        assert limitation.severity == LimitationSeverity.CRITICAL
        assert limitation.id == limitation.limitation_id

    def test_community_model_instantiation(self) -> None:
        """Validate Community model instantiation, level, and title/name aliases."""
        comm1 = Community(
            title="Efficient Attention & Quantization",
            summary="Synthesized cluster of findings regarding low-bit quantization and linear attention.",
            level=1,
            keywords=["Quantization", "FlashAttention", "LoRA"],
        )
        assert comm1.title == "Efficient Attention & Quantization"
        assert comm1.level == 1
        assert comm1.id == comm1.community_id

        # Name alias test
        comm2 = Community.model_validate({
            "name": "Reasoning & Epistemic Graphs",
            "summary": "Macro-level synthesis of agentic reasoning benchmarks.",
            "level": 2,
        })
        assert comm2.title == "Reasoning & Epistemic Graphs"
        assert comm2.name == "Reasoning & Epistemic Graphs"


# ============================================================================
# 2. Node Model Validation & Boundary Rejection Tests
# ============================================================================

class TestNodeModelValidationRules:
    """Validates boundary conditions and constraint rejections on node models."""

    def test_fact_statement_too_short_rejected(self) -> None:
        """Fact statement must be at least 5 characters."""
        with pytest.raises(ValidationError):
            Fact(statement="ABC")

    def test_fact_confidence_out_of_bounds_rejected(self) -> None:
        """Fact confidence score must be between 0.0 and 1.0."""
        with pytest.raises(ValidationError):
            Fact(statement="Valid statement text", confidence_score=1.5)
        with pytest.raises(ValidationError):
            Fact(statement="Valid statement text", confidence_score=-0.1)

    def test_proof_summary_too_short_rejected(self) -> None:
        """Proof summary must be at least 5 characters."""
        with pytest.raises(ValidationError):
            Proof(summary="Nope")

    def test_proof_confidence_out_of_bounds_rejected(self) -> None:
        """Proof confidence must be between 0.0 and 1.0."""
        with pytest.raises(ValidationError):
            Proof(summary="Valid summary text", confidence=2.0)

    def test_methodology_name_too_short_rejected(self) -> None:
        """Methodology name must be at least 2 characters."""
        with pytest.raises(ValidationError):
            Methodology(name="M", description="Valid description of methodology")

    def test_concept_name_too_short_rejected(self) -> None:
        """Concept name must be at least 2 characters."""
        with pytest.raises(ValidationError):
            Concept(name="C")

    def test_dataset_name_empty_rejected(self) -> None:
        """Dataset name cannot be empty."""
        with pytest.raises(ValidationError):
            Dataset(name="")

    def test_question_text_too_short_rejected(self) -> None:
        """Question text must be at least 5 characters."""
        with pytest.raises(ValidationError):
            Question(text="Why?")

    def test_limitation_statement_too_short_rejected(self) -> None:
        """Limitation statement must be at least 5 characters."""
        with pytest.raises(ValidationError):
            Limitation(statement="Bad")

    def test_community_level_negative_rejected(self) -> None:
        """Community level cannot be negative."""
        with pytest.raises(ValidationError):
            Community(title="Valid Cluster Title", level=-1, summary="Cluster summary")


# ============================================================================
# 3. Relationship Models & Mandatory Rich-Text Description Tests
# ============================================================================

class TestRelationshipEdgeValidation:
    """Validates relationship models and enforces mandatory rich-text description."""

    def test_base_relationship_edge_valid(self) -> None:
        """Base RelationshipEdge instantiates cleanly when rich description is provided."""
        edge = RelationshipEdge(
            source_id="node_a",
            target_id="node_b",
            rel_type="SUPPORTED_BY",
            description="Empirical benchmark results demonstrate 2.5x speedup across 100 trials.",
        )
        assert edge.source_id == "node_a"
        assert edge.target_id == "node_b"
        assert len(edge.description) >= 5

    def test_empty_description_rejected(self) -> None:
        """Empty string description must be rejected with ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            RelationshipEdge(
                source_id="node_a",
                target_id="node_b",
                rel_type="SUPPORTED_BY",
                description="",
            )
        assert "at least 5 characters" in str(exc_info.value) or "min_length" in str(exc_info.value)

    def test_whitespace_description_rejected(self) -> None:
        """Whitespace-only description must be rejected with ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            RelationshipEdge(
                source_id="node_a",
                target_id="node_b",
                rel_type="SUPPORTED_BY",
                description="       ",
            )
        assert "Edge description must be a non-empty rich-text explanation" in str(exc_info.value)

    def test_too_short_description_rejected(self) -> None:
        """Short description (<5 characters) must be rejected."""
        with pytest.raises(ValidationError):
            RelationshipEdge(
                source_id="node_a",
                target_id="node_b",
                rel_type="SUPPORTED_BY",
                description="Good",
            )

    def test_all_typed_relationship_subclasses(self) -> None:
        """Verify instantiation and defaults for all 9 specialized relationship types."""
        desc = "Rich context explaining the empirical setup and observed outcomes."

        r1 = SupportedByRel(source_id="f1", target_id="p1", description=desc, confidence=0.9)
        assert r1.rel_type == RelationshipType.SUPPORTED_BY.value
        assert r1.confidence == 0.9

        r2 = ContradictedByRel(source_id="f1", target_id="p2", description=desc, contradiction_type="boundary_failure")
        assert r2.rel_type == RelationshipType.CONTRADICTED_BY.value
        assert r2.contradiction_type == "boundary_failure"

        r3 = UsesMethodRel(source_id="p1", target_id="m1", description=desc, role="primary")
        assert r3.rel_type == RelationshipType.USES_METHOD.value
        assert r3.role == "primary"

        r4 = EvaluatedOnRel(source_id="p1", target_id="d1", description=desc, split="test_hard")
        assert r4.rel_type == RelationshipType.EVALUATED_ON.value
        assert r4.split == "test_hard"

        r5 = ExtractedFromRel(source_id="p1", target_id="s1", description=desc, section="Section 4.2")
        assert r5.rel_type == RelationshipType.EXTRACTED_FROM.value
        assert r5.section == "Section 4.2"

        r6 = AddressesRel(source_id="f1", target_id="q1", description=desc, relevance_score=0.95)
        assert r6.rel_type == RelationshipType.ADDRESSES.value
        assert r6.relevance_score == 0.95

        r7 = RelatesToConceptRel(source_id="f1", target_id="c1", description=desc, relation_type="applies")
        assert r7.rel_type == RelationshipType.RELATES_TO_CONCEPT.value

        r8 = HasLimitationRel(source_id="p1", target_id="l1", description=desc, impact_severity="critical")
        assert r8.rel_type == RelationshipType.HAS_LIMITATION.value
        assert r8.impact_severity == "critical"

        r9 = BelongsToCommunityRel(source_id="f1", target_id="cm1", description=desc, membership_weight=0.85)
        assert r9.rel_type == RelationshipType.BELONGS_TO_COMMUNITY.value
        assert r9.membership_weight == 0.85

    def test_validate_rich_description_helper(self) -> None:
        """Test the standalone validate_rich_description helper function."""
        # Valid descriptions pass without error
        validate_rich_description("Detailed methodological context")
        validate_rich_description("Valid 5 chars.")

        # Invalid descriptions raise InvalidRelationshipError
        with pytest.raises(InvalidRelationshipError):
            validate_rich_description("")
        with pytest.raises(InvalidRelationshipError):
            validate_rich_description("   ")
        with pytest.raises(InvalidRelationshipError):
            validate_rich_description("tiny")

    def test_validate_relationship_type_helper(self) -> None:
        """Test the standalone validate_relationship_type helper function."""
        assert validate_relationship_type("supported_by") == "SUPPORTED_BY"
        assert validate_relationship_type("CONTRADICTED_BY") == "CONTRADICTED_BY"
        assert validate_relationship_type("uses_method") == "USES_METHOD"

        with pytest.raises(InvalidRelationshipError):
            validate_relationship_type("INVALID_REL_TYPE")


# ============================================================================
# 4. Neo4j Schema Constraint Initialization & Enforcement Tests
# ============================================================================

class TestNeo4jSchemaConstraints:
    """Validates Neo4j schema constraint initialization and uniqueness enforcement."""

    @pytest.mark.asyncio
    async def test_init_graphrag_schema_idempotency(self, neo4j_service: Neo4jService) -> None:
        """Calling init_graphrag_schema multiple times should execute idempotently without failure."""
        await init_graphrag_schema(neo4j_service, embedding_dimensions=768)
        # Second call to ensure idempotency
        await init_graphrag_schema(neo4j_service, embedding_dimensions=768)

        # Verify that constraints exist
        constraints = await neo4j_service.execute_read("SHOW CONSTRAINTS")
        constraint_names = {c.get("name") for c in constraints if c.get("name")}

        expected_constraints = {
            "fact_id_unique",
            "proof_id_unique",
            "methodology_id_unique",
            "source_id_unique",
            "concept_id_unique",
            "concept_name_unique",
            "dataset_id_unique",
            "epistemic_question_id_unique",
            "limitation_id_unique",
            "community_id_unique",
        }
        for name in expected_constraints:
            assert name in constraint_names, f"Expected constraint '{name}' not found in Neo4j constraints"

    @pytest.mark.asyncio
    async def test_fact_id_uniqueness_enforcement(self, neo4j_service: Neo4jService) -> None:
        """Enforces that inserting duplicate fact_id triggers a Neo4j constraint error."""
        dup_fact_id = f"{TEST_TAG}_fact_dup"

        # First insertion should succeed
        await neo4j_service.execute_write(
            "CREATE (f:Fact {fact_id: $id, statement: 'Claim A', status: 'tentative', created_at: datetime()})",
            {"id": dup_fact_id},
        )

        # Second insertion with the exact same fact_id must fail uniqueness constraint
        from neo4j.exceptions import ClientError
        with pytest.raises(ClientError) as exc_info:
            await neo4j_service.execute_write(
                "CREATE (f:Fact {fact_id: $id, statement: 'Claim B', status: 'tentative', created_at: datetime()})",
                {"id": dup_fact_id},
            )
        assert "ConstraintValidationFailed" in str(exc_info.value) or "already exists" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_proof_id_uniqueness_enforcement(self, neo4j_service: Neo4jService) -> None:
        """Enforces that inserting duplicate proof_id triggers a Neo4j constraint error."""
        dup_proof_id = f"{TEST_TAG}_proof_dup"

        await neo4j_service.execute_write(
            "CREATE (p:Proof {proof_id: $id, summary: 'Proof Summary A', polarity: 'supports', created_at: datetime()})",
            {"id": dup_proof_id},
        )

        from neo4j.exceptions import ClientError
        with pytest.raises(ClientError) as exc_info:
            await neo4j_service.execute_write(
                "CREATE (p:Proof {proof_id: $id, summary: 'Proof Summary B', polarity: 'contradicts', created_at: datetime()})",
                {"id": dup_proof_id},
            )
        assert "ConstraintValidationFailed" in str(exc_info.value) or "already exists" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_concept_name_uniqueness_enforcement(self, neo4j_service: Neo4jService) -> None:
        """Enforces that inserting duplicate concept name triggers a Neo4j constraint error."""
        dup_concept_name = f"{TEST_TAG}_ConceptName"
        id1 = f"{TEST_TAG}_c1"
        id2 = f"{TEST_TAG}_c2"

        await neo4j_service.execute_write(
            "CREATE (c:Concept {concept_id: $id, name: $name, created_at: datetime()})",
            {"id": id1, "name": dup_concept_name},
        )

        from neo4j.exceptions import ClientError
        with pytest.raises(ClientError) as exc_info:
            await neo4j_service.execute_write(
                "CREATE (c:Concept {concept_id: $id, name: $name, created_at: datetime()})",
                {"id": id2, "name": dup_concept_name},
            )
        assert "ConstraintValidationFailed" in str(exc_info.value) or "already exists" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_dataset_id_uniqueness_enforcement(self, neo4j_service: Neo4jService) -> None:
        """Enforces that inserting duplicate dataset_id triggers a Neo4j constraint error."""
        dup_dataset_id = f"{TEST_TAG}_dataset_dup"

        await neo4j_service.execute_write(
            "CREATE (d:Dataset {dataset_id: $id, name: 'Dataset A', created_at: datetime()})",
            {"id": dup_dataset_id},
        )

        from neo4j.exceptions import ClientError
        with pytest.raises(ClientError) as exc_info:
            await neo4j_service.execute_write(
                "CREATE (d:Dataset {dataset_id: $id, name: 'Dataset B', created_at: datetime()})",
                {"id": dup_dataset_id},
            )
        assert "ConstraintValidationFailed" in str(exc_info.value) or "already exists" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_question_id_uniqueness_enforcement(self, neo4j_service: Neo4jService) -> None:
        """Enforces that inserting duplicate question_id triggers a Neo4j constraint error."""
        dup_question_id = f"{TEST_TAG}_question_dup"

        await neo4j_service.execute_write(
            "CREATE (q:Question {question_id: $id, text: 'Inquiry A?', status: 'open', created_at: datetime()})",
            {"id": dup_question_id},
        )

        from neo4j.exceptions import ClientError
        with pytest.raises(ClientError) as exc_info:
            await neo4j_service.execute_write(
                "CREATE (q:Question {question_id: $id, text: 'Inquiry B?', status: 'open', created_at: datetime()})",
                {"id": dup_question_id},
            )
        assert "ConstraintValidationFailed" in str(exc_info.value) or "already exists" in str(exc_info.value)

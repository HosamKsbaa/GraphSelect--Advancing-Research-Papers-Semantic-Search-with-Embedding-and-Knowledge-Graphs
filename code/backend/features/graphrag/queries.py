"""Parameterized Cypher queries for the Epistemic Fact Graph (GraphRAG).

Ensures safe execution without string interpolation to eliminate Cypher injection risks.
Covers node persistence, rich-text edge linking, composite claim ingestion,
conflict status evaluation, and depth-1 / depth-2 debate subgraph traversals.
"""
from __future__ import annotations

# ============================================================================
# Node CRUD & Merge Queries
# ============================================================================

MERGE_FACT = """
MERGE (f:Fact {fact_id: $fact_id})
ON CREATE SET f.statement        = $statement,
              f.status           = $status,
              f.confidence_score = $confidence_score,
              f.domain           = $domain,
              f.project_id       = $project_id,
              f.embedding        = $embedding,
              f.embedding_model  = $embedding_model,
              f.created_by_agent = $created_by_agent,
              f.created_at       = datetime(),
              f.updated_at       = datetime()
ON MATCH SET  f.domain           = coalesce($domain, f.domain),
              f.updated_at       = datetime()
RETURN f.fact_id AS fact_id, f.statement AS statement, f.status AS status, f.confidence_score AS confidence_score;
"""

MERGE_PROOF = """
MERGE (p:Proof {proof_id: $proof_id})
ON CREATE SET p.summary         = $summary,
              p.polarity        = $polarity,
              p.proof_type      = $proof_type,
              p.confidence      = $confidence,
              p.extracted_quote = $extracted_quote,
              p.metrics         = $metrics,
              p.location        = $location,
              p.source_paper_id = $source_paper_id,
              p.agent_id        = $agent_id,
              p.created_at      = datetime()
ON MATCH SET  p.summary         = coalesce($summary, p.summary),
              p.confidence      = coalesce($confidence, p.confidence)
RETURN p.proof_id AS proof_id, p.summary AS summary, p.polarity AS polarity;
"""

MERGE_METHODOLOGY = """
MERGE (m:Methodology {methodology_id: $methodology_id})
ON CREATE SET m.name            = $name,
              m.description     = $description,
              m.category        = $category,
              m.hyperparameters = $hyperparameters,
              m.code_url        = $code_url,
              m.created_at      = datetime()
ON MATCH SET  m.description     = coalesce($description, m.description)
RETURN m.methodology_id AS methodology_id, m.name AS name;
"""

MERGE_SOURCE = """
MERGE (s:Source {source_id: $source_id})
ON CREATE SET s.title          = $title,
              s.doi            = $doi,
              s.openalex_id    = $openalex_id,
              s.authors        = $authors,
              s.year           = $year,
              s.venue          = $venue,
              s.url            = $url,
              s.citation_count = $citation_count,
              s.created_at     = datetime()
ON MATCH SET  s.title          = coalesce($title, s.title),
              s.citation_count = coalesce($citation_count, s.citation_count)
RETURN s.source_id AS source_id, s.title AS title;
"""

MERGE_CONCEPT = """
MERGE (c:Concept {concept_id: $concept_id})
ON CREATE SET c.name       = $name,
              c.definition = $definition,
              c.domain     = $domain,
              c.aliases    = $aliases,
              c.created_at = datetime()
ON MATCH SET  c.definition = coalesce($definition, c.definition)
RETURN c.concept_id AS concept_id, c.name AS name;
"""

MERGE_DATASET = """
MERGE (d:Dataset {dataset_id: $dataset_id})
ON CREATE SET d.name        = $name,
              d.version     = $version,
              d.description = $description,
              d.modality    = $modality,
              d.modalities  = $modalities,
              d.size        = $size,
              d.task_type   = $task_type,
              d.url         = $url,
              d.license     = $license,
              d.created_at  = datetime()
ON MATCH SET  d.description = coalesce($description, d.description)
RETURN d.dataset_id AS dataset_id, d.name AS name;
"""

MERGE_QUESTION = """
MERGE (q:Question {question_id: $question_id})
ON CREATE SET q.text       = $text,
              q.status     = $status,
              q.project_id = $project_id,
              q.session_id = $session_id,
              q.embedding  = $embedding,
              q.created_at = datetime()
ON MATCH SET  q.status     = coalesce($status, q.status)
RETURN q.question_id AS question_id, q.text AS text;
"""

MERGE_LIMITATION = """
MERGE (l:Limitation {limitation_id: $limitation_id})
ON CREATE SET l.statement  = $statement,
              l.severity   = $severity,
              l.category   = $category,
              l.created_at = datetime()
ON MATCH SET  l.severity   = coalesce($severity, l.severity)
RETURN l.limitation_id AS limitation_id, l.statement AS statement;
"""

MERGE_COMMUNITY = """
MERGE (cm:Community {community_id: $community_id})
ON CREATE SET cm.title       = $title,
              cm.name        = $name,
              cm.summary     = $summary,
              cm.level       = $level,
              cm.keywords    = $keywords,
              cm.findings    = $findings,
              cm.rating      = $rating,
              cm.fact_count  = $fact_count,
              cm.proof_count = $proof_count,
              cm.created_at  = datetime()
ON MATCH SET  cm.summary     = coalesce($summary, cm.summary),
              cm.fact_count  = coalesce($fact_count, cm.fact_count),
              cm.proof_count = coalesce($proof_count, cm.proof_count)
RETURN cm.community_id AS community_id, cm.title AS title;
"""

GET_NODE_BY_ID = """
MATCH (n)
WHERE n.fact_id = $id
   OR n.proof_id = $id
   OR n.methodology_id = $id
   OR n.source_id = $id
   OR n.concept_id = $id
   OR n.dataset_id = $id
   OR n.question_id = $id
   OR n.limitation_id = $id
   OR n.community_id = $id
RETURN labels(n) AS labels, properties(n) AS properties;
"""

GET_FACT = """
MATCH (f:Fact {fact_id: $fact_id})
RETURN properties(f) AS properties;
"""

# ============================================================================
# Rich-Text Relationship Linking Queries
# ============================================================================

LINK_FACT_TO_SUPPORTING_PROOF = """
MATCH (f:Fact {fact_id: $fact_id})
MATCH (p:Proof {proof_id: $proof_id})
MERGE (f)-[r:SUPPORTED_BY]->(p)
ON CREATE SET r.description = $description,
              r.confidence  = $confidence,
              r.strength    = $strength,
              r.agent_id    = $agent_id,
              r.created_at  = datetime()
ON MATCH SET  r.description = $description,
              r.confidence  = coalesce($confidence, r.confidence),
              r.updated_at  = datetime()
RETURN type(r) AS rel_type, r.description AS description;
"""

LINK_FACT_TO_CONTRADICTING_PROOF = """
MATCH (f:Fact {fact_id: $fact_id})
MATCH (p:Proof {proof_id: $proof_id})
MERGE (f)-[r:CONTRADICTED_BY]->(p)
ON CREATE SET r.description        = $description,
              r.confidence         = $confidence,
              r.contradiction_type = $contradiction_type,
              r.agent_id           = $agent_id,
              r.created_at         = datetime()
ON MATCH SET  r.description        = $description,
              r.confidence         = coalesce($confidence, r.confidence),
              r.updated_at         = datetime()
RETURN type(r) AS rel_type, r.description AS description;
"""

LINK_PROOF_TO_METHODOLOGY = """
MATCH (p:Proof {proof_id: $proof_id})
MATCH (m:Methodology {methodology_id: $methodology_id})
MERGE (p)-[r:USES_METHOD]->(m)
ON CREATE SET r.description = $description,
              r.role        = $role,
              r.created_at  = datetime()
ON MATCH SET  r.description = $description,
              r.updated_at  = datetime()
RETURN type(r) AS rel_type, r.description AS description;
"""

LINK_PROOF_TO_DATASET = """
MATCH (p:Proof {proof_id: $proof_id})
MATCH (d:Dataset {dataset_id: $dataset_id})
MERGE (p)-[r:EVALUATED_ON]->(d)
ON CREATE SET r.description  = $description,
              r.split        = $split,
              r.metric_value = $metric_value,
              r.sample_size  = $sample_size,
              r.created_at   = datetime()
ON MATCH SET  r.description  = $description,
              r.updated_at   = datetime()
RETURN type(r) AS rel_type, r.description AS description;
"""

LINK_TO_SOURCE = """
MATCH (src) WHERE (src:Proof AND src.proof_id = $source_id) OR (src:Fact AND src.fact_id = $source_id)
MATCH (s:Source {source_id: $target_id})
MERGE (src)-[r:EXTRACTED_FROM]->(s)
ON CREATE SET r.description  = $description,
              r.section      = $section,
              r.page_number  = $page_number,
              r.table_figure = $table_figure,
              r.created_at   = datetime()
ON MATCH SET  r.description  = $description,
              r.updated_at   = datetime()
RETURN type(r) AS rel_type, r.description AS description;
"""

LINK_FACT_TO_QUESTION = """
MATCH (f:Fact {fact_id: $fact_id})
MATCH (q:Question {question_id: $question_id})
MERGE (f)-[r:ADDRESSES]->(q)
ON CREATE SET r.description      = $description,
              r.relevance_score  = $relevance_score,
              r.is_direct_answer = $is_direct_answer,
              r.created_at       = datetime()
ON MATCH SET  r.description      = $description,
              r.updated_at       = datetime()
RETURN type(r) AS rel_type, r.description AS description;
"""

LINK_TO_CONCEPT = """
MATCH (src) WHERE (src:Fact AND src.fact_id = $source_id) OR (src:Methodology AND src.methodology_id = $source_id) OR (src:Proof AND src.proof_id = $source_id)
MATCH (c:Concept {concept_id: $concept_id})
MERGE (src)-[r:RELATES_TO_CONCEPT]->(c)
ON CREATE SET r.description   = $description,
              r.relation_type = $relation_type,
              r.prominence    = $prominence,
              r.created_at    = datetime()
ON MATCH SET  r.description   = $description,
              r.updated_at    = datetime()
RETURN type(r) AS rel_type, r.description AS description;
"""

LINK_TO_LIMITATION = """
MATCH (src) WHERE (src:Proof AND src.proof_id = $source_id) OR (src:Fact AND src.fact_id = $source_id) OR (src:Methodology AND src.methodology_id = $source_id)
MATCH (l:Limitation {limitation_id: $limitation_id})
MERGE (src)-[r:HAS_LIMITATION]->(l)
ON CREATE SET r.description     = $description,
              r.impact_severity = $impact_severity,
              r.created_at      = datetime()
ON MATCH SET  r.description     = $description,
              r.updated_at      = datetime()
RETURN type(r) AS rel_type, r.description AS description;
"""

LINK_FACT_TO_COMMUNITY = """
MATCH (f:Fact {fact_id: $fact_id})
MATCH (cm:Community {community_id: $community_id})
MERGE (f)-[r:BELONGS_TO_COMMUNITY]->(cm)
ON CREATE SET r.description       = $description,
              r.membership_weight = $membership_weight,
              r.created_at        = datetime()
ON MATCH SET  r.description       = $description,
              r.updated_at        = datetime()
RETURN type(r) AS rel_type, r.description AS description;
"""

# ============================================================================
# Atomic Composite Ingestion Query
# ============================================================================

ATOMIC_COMPOSITE_CLAIM = """
MERGE (f:Fact {fact_id: $fact.fact_id})
ON CREATE SET f.statement        = $fact.statement,
              f.status           = $fact.status,
              f.confidence_score = $fact.confidence_score,
              f.domain           = $fact.domain,
              f.project_id       = $fact.project_id,
              f.created_at       = datetime(),
              f.updated_at       = datetime()
ON MATCH SET  f.updated_at       = datetime()

CREATE (p:Proof {
    proof_id:        $proof.proof_id,
    summary:         $proof.summary,
    polarity:        $proof.polarity,
    proof_type:      $proof.proof_type,
    confidence:      $proof.confidence,
    extracted_quote: $proof.extracted_quote,
    metrics:         $proof.metrics,
    location:        $proof.location,
    source_paper_id: $proof.source_paper_id,
    agent_id:        $proof.agent_id,
    created_at:      datetime()
})

FOREACH (_ IN CASE WHEN $rel_type = 'SUPPORTED_BY' THEN [1] ELSE [] END |
    CREATE (f)-[:SUPPORTED_BY {
        description: $edge_description,
        confidence:  $proof.confidence,
        strength:    'conclusive',
        agent_id:    $proof.agent_id,
        created_at:  datetime()
    }]->(p)
)

FOREACH (_ IN CASE WHEN $rel_type = 'CONTRADICTED_BY' THEN [1] ELSE [] END |
    CREATE (f)-[:CONTRADICTED_BY {
        description:        $edge_description,
        confidence:         $proof.confidence,
        contradiction_type: 'empirical_divergence',
        agent_id:           $proof.agent_id,
        created_at:         datetime()
    }]->(p)
)

FOREACH (_ IN CASE WHEN $has_method THEN [1] ELSE [] END |
    MERGE (m:Methodology {methodology_id: $method.methodology_id})
    ON CREATE SET m.name            = $method.name,
                  m.description     = $method.description,
                  m.category        = $method.category,
                  m.hyperparameters = $method.hyperparameters,
                  m.created_at      = datetime()
    CREATE (p)-[:USES_METHOD {
        description: $method_rel_description,
        role:        'primary',
        created_at:  datetime()
    }]->(m)
)

FOREACH (_ IN CASE WHEN $has_dataset THEN [1] ELSE [] END |
    MERGE (d:Dataset {dataset_id: $dataset.dataset_id})
    ON CREATE SET d.name        = $dataset.name,
                  d.version     = $dataset.version,
                  d.description = $dataset.description,
                  d.created_at  = datetime()
    CREATE (p)-[:EVALUATED_ON {
        description: $dataset_rel_description,
        split:       'test',
        created_at:  datetime()
    }]->(d)
)

FOREACH (_ IN CASE WHEN $has_source THEN [1] ELSE [] END |
    MERGE (s:Source {source_id: $source.source_id})
    ON CREATE SET s.title      = $source.title,
                  s.doi        = $source.doi,
                  s.created_at = datetime()
    CREATE (p)-[:EXTRACTED_FROM {
        description: $source_rel_description,
        created_at:  datetime()
    }]->(s)
)

RETURN f.fact_id AS fact_id, p.proof_id AS proof_id;
"""

# ============================================================================
# Status Resolution & Debate Subgraph Traversal Queries
# ============================================================================

GET_CONNECTED_PROOFS_FOR_FACT = """
MATCH (f:Fact {fact_id: $fact_id})
OPTIONAL MATCH (f)-[r:SUPPORTED_BY|CONTRADICTED_BY]->(p:Proof)
WHERE p IS NOT NULL
RETURN type(r) AS rel_type,
       r.description AS description,
       properties(r) AS rel_properties,
       p.proof_id AS proof_id,
       p.summary AS summary,
       p.polarity AS polarity,
       p.confidence AS confidence,
       p.agent_id AS agent_id,
       p.created_at AS created_at;
"""

UPDATE_FACT_STATUS = """
MATCH (f:Fact {fact_id: $fact_id})
SET f.status           = $status,
    f.confidence_score = $confidence_score,
    f.updated_at       = datetime()
RETURN f.fact_id AS fact_id, f.status AS status, f.confidence_score AS confidence_score;
"""

GET_DEBATE_SUBGRAPH_DEPTH1 = """
MATCH (f:Fact {fact_id: $fact_id})
OPTIONAL MATCH (f)-[r1:SUPPORTED_BY|CONTRADICTED_BY]->(p:Proof)
OPTIONAL MATCH (f)-[r3:RELATES_TO_CONCEPT|ADDRESSES|BELONGS_TO_COMMUNITY|HAS_LIMITATION|EXTRACTED_FROM]->(ctx)
RETURN properties(f) AS fact,
       type(r1) AS r1_type,
       properties(r1) AS r1_props,
       properties(p) AS proof,
       type(r3) AS r3_type,
       properties(r3) AS r3_props,
       labels(ctx) AS ctx_labels,
       properties(ctx) AS ctx;
"""

GET_DEBATE_SUBGRAPH_DEPTH2 = """
MATCH (f:Fact {fact_id: $fact_id})
OPTIONAL MATCH (f)-[r1:SUPPORTED_BY|CONTRADICTED_BY]->(p:Proof)
OPTIONAL MATCH (p)-[r2:USES_METHOD|EVALUATED_ON|EXTRACTED_FROM|HAS_LIMITATION|RELATES_TO_CONCEPT]->(target)
OPTIONAL MATCH (f)-[r3:RELATES_TO_CONCEPT|ADDRESSES|BELONGS_TO_COMMUNITY|HAS_LIMITATION|EXTRACTED_FROM]->(ctx)
RETURN properties(f) AS fact,
       type(r1) AS r1_type,
       properties(r1) AS r1_props,
       properties(p) AS proof,
       type(r2) AS r2_type,
       properties(r2) AS r2_props,
       labels(target) AS target_labels,
       properties(target) AS target,
       type(r3) AS r3_type,
       properties(r3) AS r3_props,
       labels(ctx) AS ctx_labels,
       properties(ctx) AS ctx;
"""

LIST_CONTESTED_FACTS = """
MATCH (f:Fact)
WHERE f.status = 'debated'
   OR (EXISTS((f)-[:SUPPORTED_BY]->(:Proof)) AND EXISTS((f)-[:CONTRADICTED_BY]->(:Proof)))
OPTIONAL MATCH (f)-[r_sup:SUPPORTED_BY]->(p_sup:Proof)
OPTIONAL MATCH (f)-[r_con:CONTRADICTED_BY]->(p_con:Proof)
WITH f, r_sup, p_sup, r_con, p_con
WHERE $project_id IS NULL OR $project_id = '' OR f.project_id = $project_id
RETURN f.fact_id AS fact_id,
       f.statement AS statement,
       f.status AS status,
       f.confidence_score AS confidence_score,
       count(DISTINCT p_sup) AS support_count,
       count(DISTINCT p_con) AS contradiction_count,
       collect(DISTINCT {
           proof_id: p_sup.proof_id,
           summary: p_sup.summary,
           description: r_sup.description
       }) AS supporting_evidence,
       collect(DISTINCT {
           proof_id: p_con.proof_id,
           summary: p_con.summary,
           description: r_con.description
       }) AS contradicting_evidence
ORDER BY contradiction_count DESC, support_count DESC;
"""

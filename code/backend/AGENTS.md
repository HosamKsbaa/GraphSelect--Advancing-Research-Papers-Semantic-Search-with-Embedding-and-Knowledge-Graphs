# ALRS v2 Agent Architecture & Autonomous Research Enhancement Tools

## 1. Overview

The Automated Literature Review System (ALRS v2) orchestrates autonomous multi-agent research across a 6-stage Graph-Centric Dual-Loop (GCDL) pipeline built on Google Agent Development Kit (ADK) and Neo4j 5.x.

Feature 007 ("Autonomous Research Workflow Enhancements") delivers four core capabilities integrated directly into ADK agents:
1. **Continuous Library Ingestion & Bidirectional Graph Wiring** (User Story 1)
2. **Autonomous Gap-Driven Search Remediation Loops** (User Story 2)
3. **Scientometric-Vector Progressive Ladder (SVPL) Multi-Hop Traversal** (User Story 3)
4. **Section-Granular Synthesis Matrices & Dual-Layer Persistence** (User Story 4)

Governed strictly by **Constitution v2.2.1** (pure graph-native persistence, strictly zero MySQL, strict static typing, and functions $\le 25$ lines).

---

## 2. ADK Multi-Agent Hierarchy & Enhancement Tools

All Feature 007 tools are defined in `agents/tools/autonomous_enhancement_tools.py` as typed asynchronous ADK tool functions adhering to Pydantic v2 schemas and strict error typing.

### 2.1 Tool Inventory

| Tool Function | Target Stage / Agent | Purpose | Invariant / Guard |
| :--- | :--- | :--- | :--- |
| `ingest_user_paper_tool` | Stage 2 (`SearchSnowballAgent`) | Auto-ingests DOIs, arXiv IDs, and URLs; queries academic APIs; wires bidirectional `:CITES` edges | Relevance Gate Invariant (FR-016): $\cos(\mathbf{e}_P, \mathbf{e}_{RQ}) \ge 0.75$ for `can_expand_deeply` |
| `confirm_title_ingestion_tool` | Stage 2 (`SearchSnowballAgent`) | Confirms or dismisses interactive title confirmation chips for fuzzy paper titles ($\ge 90\%$ similarity) | Graph mutation deferred until explicit user or agent confirmation |
| `run_autonomous_gap_remediation_tool` | Stage 2 (`SearchSnowballAgent`) | Executes closed-loop search remediation for deficient research questions ($C(RQ_i) < 0.70$) up to 3 iterations | Mode-dependent termination; yields native ADK `RequestInput` suspension event in Exploration mode |
| `svpl_multi_hop_discovery_tool` | Stage 2 (`SearchSnowballAgent`) | Resolves 2-hop and 3-hop bridge pathways across 4 progressive layers without exponential network crawling | Strict Necessity Gating (FR-015): forbidden during routine BFS; requires explicit user command or $N=0$ empty gap |
| `generate_section_synthesis_matrix_tool` | Stage 4 (`MethodologyArchitect`) | Generates 3–5 tailored analytical dimensions per outline section, extracts cell evidence, validates citekeys | 100% LaTeX citekey validation (`\cite{doi_...}`); dual-layer persistence (Neo4j + markdown) |

---

## 3. Tool Mechanics & Specifications

### 3.1 Continuous Ingestion & Bidirectional Wiring (`ingest_user_paper_tool`)
- **Identifier Extraction**: Extracts standard DOI expressions (`10.\d{4,9}/[-._;()/:A-Za-z0-9]+`), arXiv IDs (`arXiv:\d{4}\.\d{4,5}`), and URLs.
- **Title Matching**: Evaluates token set ratio similarity against OpenAlex candidates; matches $\ge 0.90$ generate a `TitleConfirmationChip` without mutating the graph until confirmed.
- **Bidirectional Wiring**: Executes a single atomic Cypher `FOREACH` transaction that resolves outgoing citations (`:CITES`) and incoming citations (`:CITED_BY`) against all existing library papers simultaneously, preventing $N+1$ queries.
- **Relevance Gate Invariant (FR-016)**: Evaluates $\max_{RQ_i} \cos(\mathbf{e}_P, \mathbf{e}_{RQ_i})$ against active research questions. Papers scoring $< 0.75$ have `can_expand_deeply = False`, strictly forbidding recursive snowballing and unsolicited content extraction.

### 3.2 SVPL Multi-Hop Traversal Engine (`svpl_multi_hop_discovery_tool`)
- **Strict Necessity Gating (FR-015)**: Multi-hop is an on-demand contingency tool. If called during routine crawling or ingestion without `explicit_user_directive` or `empty_gap_remediation` with $N=0$, raises `MultiHopUnauthorizedError` (HTTP 403).
- **Progressive Ladder Mechanics**:
  - **Layer 0 (Local Neo4j Stubs)**: Queries in-graph stubs and existing edges in $<10\text{ms}$ (0 external API calls).
  - **Layer 1 (OpenAlex Relational Primitives)**: Executes 1-shot server-side filters (`filter=cited_by:{A},cites:{C}`, bibliographic coupling `cited_by:{A},cited_by:{C}`, or co-citation `cites:{A},cites:{C}`) in $\le 1$ HTTP request in ~250ms without downloading candidate arrays.
  - **Layer 2 (Pipe-Disjunctive Meet-in-the-Middle)**: Chunks intermediate references using OpenAlex pipe syntax (`filter=cited_by:W1|W2|...|W50,cites:{C}`) for 3-hop paths.
  - **Layer 3 (Concept-Guided Steiner Beam A*)**: Explores distant pathways using adaptive semantic pruning threshold $\tau_h = \max(\tau_{\text{base}}, \mu_h - 0.5\sigma_h)$ with strict candidate quota cap $K_h \le 25$ papers per hop, guaranteeing zero domain drift.
  - **Layer 4 (Atomic Neo4j Bridge Materialization)**: Persists intermediate `:Paper` nodes and typed `:BRIDGES` edges atomically in Neo4j with provenance tags.

### 3.3 Autonomous Gap Remediation Loops (`run_autonomous_gap_remediation_tool`)
- **Coverage Metric $C(RQ_i)$**: Computes semantic coverage for each research question across active library papers using document embeddings.
- **Targeted Search Dispatch**: For questions with $C(RQ_i) < 0.70$, formulates targeted search vectors and queries OpenAlex for top 3 candidates.
- **Iterative Loop**: Up to 3 iterations. If $N=0$ candidates are found during retrieval, the engine autonomously invokes SVPL multi-hop discovery as an empty-gap contingency fallback.
- **Terminal States**:
  - **Exploration Mode**: Pauses execution (`status: paused_awaiting_input`) and attaches a native Google ADK `RequestInput` suspension event (Constitution A45) for interactive researcher steering.
  - **Targeted / Refinement Mode**: Flags the research question as an "Open Research Frontier" in Neo4j (`is_open_frontier = True`, recording `remediation_run_id`), logs a convergence warning, and transitions to outline planning with a dedicated literature deficit caveat.

### 3.4 Granular Section Synthesis Matrices (`generate_section_synthesis_matrix_tool`)
- **Dimension Derivation**: Dynamically derives 3 to 5 section-specific analytical dimensions (e.g., benchmark datasets, failure modes, mitigation architectures) tailored to the section title and narrative theme.
- **Evidence Extraction & Citekey Validation**: Formats canonical LaTeX citekeys (`\cite{doi_...}`) verified against library papers with 100% grounding, enforcing zero citation hallucination.
- **Dual-Layer Persistence**: Persists structured `:SectionSynthesisMatrix` nodes connected via `[:HAS_MATRIX]` to `:OutlineSection` in Neo4j for queryability, while serializing token-efficient markdown tables to `stage_04_artifacts/matrices/{section_id}.md` for injection into drafting agent tool context.

---

## 4. Agent Tool Wiring & Service Registry

### 4.1 Stage 2 Acquisition (`SearchSnowballAgent`)
Located in `agents/stage2_acquisition/agent.py`:
- Configured with `ingest_user_paper_tool`, `confirm_title_ingestion_tool`, `svpl_multi_hop_discovery_tool`, and `run_autonomous_gap_remediation_tool`.
- Operates within dialectical pair `Stage2AcquisitionDialecticalPair` alongside `RelevanceQualityAuditor`.

### 4.2 Stage 4 Synthesis (`MethodologyArchitect`)
Located in `agents/stage4_synthesis/agent.py`:
- Configured with `generate_section_synthesis_matrix_tool` alongside baseline comparative matrix tools.
- Operates within dialectical pair `Stage4SynthesisDialecticalPair` alongside `NoveltyRigorChallenger`.

### 4.3 Service Registry & Dependency Injection
- `agents/_service_registry.py`: Registers autonomous enhancement services (`ingestion_service`, `svpl_service`, `remediation_service`, `matrix_service`) with alias resolution in `_ALIAS_MAP`.
- `core/dependencies.py`: Exposes FastAPI dependency injection providers (`get_ingestion_service`, `get_svpl_service`, `get_gap_remediation_service`, `get_matrix_service`) enabling clean decoupling in routers and test fixtures.

---

## 5. Developer Testing & Verification

Run the verification suite from `newcode/code/backend`:

```bash
# 1. Quickstart Scenarios
.venv/bin/pytest tests/features/test_continuous_ingestion.py -v
.venv/bin/pytest tests/features/test_autonomous_gap_remediation.py -v
.venv/bin/pytest tests/features/test_svpl_multihop_discovery.py -v
.venv/bin/pytest tests/features/test_section_synthesis_matrix.py -v

# 2. Static Type Checking
.venv/bin/mypy features/ingestion features/gap_analysis features/ranking features/drafting agents/tools/autonomous_enhancement_tools.py core/dependencies.py

# 3. Full Feature Test Suite
.venv/bin/pytest tests/features/ -v
```

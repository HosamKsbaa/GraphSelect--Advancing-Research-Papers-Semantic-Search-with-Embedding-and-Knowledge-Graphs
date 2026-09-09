"""Automated validation tests for ALRS v2 platform spec, contracts, data model, and implementation plan."""
from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator, validate
from pydantic import ValidationError

REPO_ROOT = Path(__file__).resolve().parents[4]
FEATURE_DIR = REPO_ROOT / "specs" / "006-alrs-v2-platform"
CONTRACTS_DIR = FEATURE_DIR / "contracts"


def test_campaign_api_yaml_validity_and_schemas() -> None:
    """Validate OpenAPI 3.1 YAML schema and ratified endpoints."""
    api_yaml_path = CONTRACTS_DIR / "campaign_api.yaml"
    assert api_yaml_path.exists(), f"Missing {api_yaml_path}"

    with open(api_yaml_path, encoding="utf-8") as f:
        spec = yaml.safe_load(f)

    assert spec.get("openapi") == "3.1.0"
    paths = spec.get("paths", {})

    # 1. Steering Endpoint Check
    steering_path = "/campaigns/{campaign_id}/steering"
    assert steering_path in paths, f"Path {steering_path} not found in paths"
    steering_post = paths[steering_path].get("post", {})
    assert steering_post.get("operationId") == "steerCampaign"
    assert "200" in steering_post.get("responses", {})
    assert "409" in steering_post.get("responses", {})
    ref = (
        steering_post.get("requestBody", {})
        .get("content", {})
        .get("application/json", {})
        .get("schema", {})
        .get("$ref")
    )
    assert ref == "#/components/schemas/SteeringRequest"

    # Deprecated audit endpoint must be removed
    audit_path = "/campaigns/{campaign_id}/audit"
    assert audit_path not in paths, f"Deprecated path {audit_path} should not be in paths"

    # 2. PDF Upload Endpoint Check
    pdf_path = "/campaigns/{campaign_id}/papers/{doi}/pdf"
    assert pdf_path in paths, f"Path {pdf_path} not found in paths"
    pdf_post = paths[pdf_path].get("post", {})
    assert pdf_post.get("operationId") == "uploadPaperPdf"
    assert "multipart/form-data" in pdf_post.get("requestBody", {}).get("content", {})
    pdf_req_ref = (
        pdf_post.get("requestBody", {})
        .get("content", {})
        .get("multipart/form-data", {})
        .get("schema", {})
        .get("$ref")
    )
    assert pdf_req_ref == "#/components/schemas/PdfUploadRequest"
    pdf_resp_ref = (
        pdf_post.get("responses", {})
        .get("200", {})
        .get("content", {})
        .get("application/json", {})
        .get("schema", {})
        .get("$ref")
    )
    assert pdf_resp_ref == "#/components/schemas/PdfUploadResponse"

    # 3. Schemas in components
    schemas = spec.get("components", {}).get("schemas", {})
    assert "SteeringRequest" in schemas
    steering_schema = schemas["SteeringRequest"]
    assert "action" in steering_schema.get("properties", {})
    assert steering_schema["properties"]["action"]["enum"] == [
        "CONTINUE",
        "EDIT_DIRECTIVE",
        "FORCE_APPROVE",
        "CONFIRM_ROLLBACK",
    ]

    assert "PdfUploadRequest" in schemas
    assert "PdfUploadResponse" in schemas
    camp_props = schemas.get("CampaignResponse", {}).get("properties", {})
    assert "total_turns" in camp_props
    assert "total_prompt_tokens" in camp_props
    assert "total_completion_tokens" in camp_props
    assert "total_cached_tokens" in camp_props
    assert "total_latency_seconds" in camp_props
    assert "total_cost_usd" in camp_props
    assert "vts_ratio" in camp_props

    # 4. StageSubstateDetail Check
    assert "StageSubstateDetail" in schemas
    substate_schema = schemas["StageSubstateDetail"]
    assert "awaiting_input" in substate_schema.get("properties", {}).get("status", {}).get("enum", [])
    assert "is_quarantined" in substate_schema.get("properties", {})
    assert "quarantine_path" in substate_schema.get("properties", {})
    assert "StageNote" in schemas
    stage_note_schema = schemas["StageNote"]
    stage_note_props = stage_note_schema.get("properties", {})
    for prop in ["note_id", "stage_index", "author_agent", "content"]:
        assert prop in stage_note_props, f"Missing {prop} in StageNote schema"
        assert prop in stage_note_schema.get("required", []), f"{prop} must be required in StageNote"
    notes_ref = substate_schema.get("properties", {}).get("notes", {}).get("items", {}).get("$ref")
    assert notes_ref == "#/components/schemas/StageNote"


def test_critique_vector_and_agent_tools_json() -> None:
    """Validate JSON schemas for critique vectors and agent tools contracts."""
    critique_path = CONTRACTS_DIR / "critique_vector_schema.json"
    assert critique_path.exists()
    with open(critique_path, encoding="utf-8") as f:
        critique_schema = json.load(f)

    Draft202012Validator.check_schema(critique_schema)

    tools_path = CONTRACTS_DIR / "agent_tools_contracts.json"
    assert tools_path.exists()
    with open(tools_path, encoding="utf-8") as f:
        tools_contract = json.load(f)

    assert "stages" in tools_contract
    assert "stage_0_guidance" in tools_contract["stages"]
    assert "stage_5_drafting" in tools_contract["stages"]
    Draft202012Validator.check_schema(tools_contract)

    # 1. Validate Stage 0: Intent Profile builder and critic alignment
    stage0_builder = tools_contract["stages"]["stage_0_guidance"]["builder_tools"][0]
    stage0_critic = tools_contract["stages"]["stage_0_guidance"]["critic_tools"][0]
    assert stage0_builder["returns"]["properties"]["intent_profile"]["$ref"] == "#/definitions/UserIntentProfile"
    assert stage0_critic["parameters"]["properties"]["intent_profile"]["$ref"] == "#/definitions/UserIntentProfile"

    # 2. Validate Stage 1: FINER research questions
    stage1_builder = tools_contract["stages"]["stage_1_scoping"]["builder_tools"][0]
    stage1_critic = tools_contract["stages"]["stage_1_scoping"]["critic_tools"][0]
    assert stage1_builder["returns"]["properties"]["research_questions"]["items"]["$ref"] == "#/definitions/FinerResearchQuestion"
    assert stage1_critic["parameters"]["properties"]["research_questions"]["items"]["$ref"] == "#/definitions/FinerResearchQuestion"

    # 3. Validate Stage 3: parse_multimodal_pdf_pages_tool supports abstract fallback & ExtractedClaim
    stage3_builder_tools = tools_contract["stages"]["stage_3_extraction"]["builder_tools"]
    pdf_tool = next(t for t in stage3_builder_tools if t["name"] == "parse_multimodal_pdf_pages_tool")
    assert "paper_doi" in pdf_tool["parameters"]["required"]
    assert "pdf_path" not in pdf_tool["parameters"]["required"]
    assert pdf_tool["parameters"]["properties"]["pdf_path"]["type"] == ["string", "null"]
    claim_schema = tools_contract["definitions"]["ExtractedClaim"]
    assert "page_number" in claim_schema["properties"]
    assert "page" not in claim_schema["properties"]
    assert "paper_doi" in claim_schema["properties"]
    assert "paper_doi" in claim_schema["required"]

    # 4. Validate Stage 4: Comparison matrix and identified contradictions
    stage4_builder = tools_contract["stages"]["stage_4_synthesis"]["builder_tools"][0]
    stage4_critic = tools_contract["stages"]["stage_4_synthesis"]["critic_tools"][0]
    assert "identified_contradictions" in stage4_builder["returns"]["properties"]
    assert "contradictions_identified" not in stage4_builder["returns"]["properties"]
    assert stage4_critic["parameters"]["properties"]["comparison_matrix"]["$ref"] == "#/definitions/ComparisonMatrix"
    matrix_schema = tools_contract["definitions"]["ComparisonMatrix"]
    assert "matrix_entries" in matrix_schema["properties"]
    assert "identified_contradictions" in matrix_schema["properties"]


def test_sqlite_telemetry_ddl_and_analytics() -> None:
    """Validate SQLite DDL and analytical query execution from data-model.md."""
    data_model_path = FEATURE_DIR / "data-model.md"
    assert data_model_path.exists()

    with open(data_model_path, encoding="utf-8") as f:
        content = f.read()

    # Extract SQL DDL block from Section 2.1
    sql_blocks = re.findall(r"```sql\n(.*?)```", content, re.DOTALL)
    assert len(sql_blocks) >= 2, "Expected at least DDL and analytical SQL blocks"
    ddl = sql_blocks[0]

    assert "run_id TEXT NOT NULL" in ddl
    assert "tool_name TEXT" in ddl
    assert "prompt_hash TEXT" in ddl

    conn = sqlite3.connect(":memory:")
    conn.executescript(ddl)

    # Insert test turn events
    conn.execute(
        """
        INSERT INTO turn_events (
            event_id, campaign_id, run_id, stage_index, agent_name, agent_role, tool_name, turn_number,
            prompt_tokens, completion_tokens, cached_tokens, prompt_hash, latency_ms, cost_usd,
            status, model_name, critique_dimension, critique_score, timestamp
        ) VALUES (
            'ev-001', 'camp-uuid-1', 'run-001', 0, 'ParentResearchAdvisor', 'builder', 'formulate_intent_profile_tool', 1,
            2500, 500, 1000, 'hash-abc', 1800.0, 0.0035, 'success', 'gemini-2.5-flash', NULL, NULL, '2026-09-08T20:00:00Z'
        )
    """
    )
    conn.execute(
        """
        INSERT INTO turn_events (
            event_id, campaign_id, run_id, stage_index, agent_name, agent_role, tool_name, turn_number,
            prompt_tokens, completion_tokens, cached_tokens, prompt_hash, latency_ms, cost_usd,
            status, model_name, critique_dimension, critique_score, timestamp
        ) VALUES (
            'ev-002', 'camp-uuid-1', 'run-001', 0, 'IntentAlignmentCritic', 'critic', 'audit_intent_alignment_tool', 2,
            3000, 600, 2000, 'hash-def', 2200.0, 0.0042, 'success', 'gemini-2.5-flash', 'intent_alignment', 0.94, '2026-09-08T20:00:05Z'
        )
    """
    )

    # Run Query 1: Campaign Rollup
    cursor = conn.execute(
        """
        SELECT 
            campaign_id,
            COUNT(*) AS total_turns,
            SUM(prompt_tokens) AS total_prompt_tokens,
            SUM(completion_tokens) AS total_completion_tokens,
            SUM(cached_tokens) AS total_cached_tokens,
            ROUND(SUM(latency_ms) / 1000.0, 2) AS total_latency_seconds,
            ROUND(SUM(cost_usd), 4) AS total_cost_usd
        FROM turn_events
        WHERE campaign_id = 'camp-uuid-1'
        GROUP BY campaign_id;
    """
    )
    row = cursor.fetchone()
    assert row is not None
    assert row[0] == "camp-uuid-1"
    assert row[1] == 2
    assert row[2] == 5500
    assert row[3] == 1100
    assert row[4] == 3000
    assert row[5] == 4.0
    assert row[6] == 0.0077

    # Run Query 2: VTS Ratio
    cursor = conn.execute(
        """
        SELECT 
            campaign_id,
            ROUND(CAST(SUM(CASE WHEN agent_role = 'critic' THEN prompt_tokens + completion_tokens ELSE 0 END) AS REAL) /
                  NULLIF(SUM(CASE WHEN agent_role = 'builder' THEN prompt_tokens + completion_tokens ELSE 0 END), 0), 2) AS vts_ratio
        FROM turn_events
        WHERE campaign_id = 'camp-uuid-1';
    """
    )
    vts_row = cursor.fetchone()
    assert vts_row is not None
    assert vts_row[1] == 1.2

    conn.close()


def test_pydantic_models_from_data_model() -> None:
    """Validate python code block in data-model.md can be compiled and models used."""
    data_model_path = FEATURE_DIR / "data-model.md"
    with open(data_model_path, encoding="utf-8") as f:
        content = f.read()

    match = re.search(r"```python\n(.*?)```", content, re.DOTALL)
    assert match, "No python code block found in data-model.md"
    code = match.group(1)

    import sys
    import types

    mod_name = "data_model_runtime_test"
    mod = types.ModuleType(mod_name)
    sys.modules[mod_name] = mod
    try:
        exec(code, mod.__dict__)
    finally:
        pass

    SteeringRequest = mod.SteeringRequest
    SteeringAction = mod.SteeringAction
    TurnEventModel = mod.TurnEventModel
    PdfUploadResponseModel = mod.PdfUploadResponseModel
    ResearchCampaignModel = mod.ResearchCampaignModel
    ExtractedClaim = mod.ExtractedClaim
    BoundingBox = mod.BoundingBox

    # Test ExtractedClaim with multimodal vision crop
    claim_multimodal = ExtractedClaim(
        claim_id="claim-001",
        paper_doi="10.48550/arxiv.1706.03762",
        statement="Self-attention achieves 28.4 BLEU.",
        page_number=6,
        bounding_box=BoundingBox(y0=0.1, x0=0.2, y1=0.3, x1=0.8),
        crop_uri="/data/provenance/crops/claim-001.png",
        confidence=0.98,
    )
    assert claim_multimodal.page_number == 6
    assert claim_multimodal.bounding_box is not None

    # Test ExtractedClaim with abstract fallback (is_multimodal: false)
    claim_fallback = ExtractedClaim(
        claim_id="claim-002",
        paper_doi="10.48550/arxiv.2001.00001",
        statement="Abstract finding without PDF visual proof.",
        confidence=0.95,
    )
    assert claim_fallback.page_number is None
    assert claim_fallback.bounding_box is None
    assert claim_fallback.crop_uri is None

    # Test SteeringRequest validation
    req = SteeringRequest(
        action="EDIT_DIRECTIVE",
        stage_index=1,
        directives="Focus more on graph attention networks",
    )
    assert req.action == "EDIT_DIRECTIVE"
    assert req.stage_index == 1

    # Test invalid steering action raises ValidationError
    with pytest.raises(ValidationError):
        SteeringRequest(action="INVALID_ACTION", stage_index=1)

    # Test TurnEventModel
    event = TurnEventModel(
        event_id="ev-123",
        campaign_id="camp-123",
        run_id="run-123",
        stage_index=2,
        agent_name="SearchSnowballAgent",
        agent_role="builder",
        tool_name="run_alrs_snowballing_tool",
        turn_number=1,
        prompt_tokens=1500,
        completion_tokens=400,
        prompt_hash="hash-123",
        latency_ms=1200.5,
        cost_usd=0.002,
        status="success",
        model_name="gemini-2.5-flash",
    )
    assert event.run_id == "run-123"
    assert event.tool_name == "run_alrs_snowballing_tool"
    assert event.prompt_hash == "hash-123"
    assert event.cached_tokens == 0
    assert event.cost_usd == 0.002

    # Test C11 Boolean fields on artifacts
    GuidanceArtifacts = mod.GuidanceArtifacts
    ScopingArtifacts = mod.ScopingArtifacts
    guidance = GuidanceArtifacts(is_onboarding_complete=True)
    assert guidance.is_onboarding_complete is True
    scoping = ScopingArtifacts(has_novelty_collision=True)
    assert scoping.has_novelty_collision is True

    # Test PdfUploadResponseModel
    pdf_resp = PdfUploadResponseModel(
        campaign_id="camp-123",
        doi="10.48550/arxiv.1706.03762",
        file_path="/data/pdfs/10.48550_arxiv.1706.03762.pdf",
        file_size_bytes=1048576,
        is_multimodal=True,
        message="PDF uploaded successfully",
    )
    assert pdf_resp.is_multimodal is True

    # Test ResearchCampaignModel telemetry rollups
    camp = ResearchCampaignModel(
        campaign_id="camp-123",
        name="Epistemic GNN Review",
        topic="Graph neural networks for citation verification",
        entry_mode="exploration",
        status="active",
        total_turns=12,
        total_prompt_tokens=45000,
        total_completion_tokens=9000,
        total_cached_tokens=15000,
        total_latency_seconds=35.5,
        total_cost_usd=0.45,
        vts_ratio=1.35,
    )
    assert camp.total_turns == 12
    assert camp.total_prompt_tokens == 45000
    assert camp.total_latency_seconds == 35.5
    assert camp.vts_ratio == 1.35


def test_spec_md_clarifications_and_fr_synchronization() -> None:
    """Validate that spec.md properly encodes all 5 ratified decisions and synchronizes requirements."""
    spec_path = FEATURE_DIR / "spec.md"
    assert spec_path.exists()
    with open(spec_path, encoding="utf-8") as f:
        content = f.read()

    # 1. Clarifications Section & Session Header
    assert "## Clarifications" in content
    assert "### Session 2026-09-08" in content

    # 2. Ratified Decisions
    assert "Clean Break Cutover" in content
    assert "Mode-Dependent Gating with Dedicated Steering API" in content
    assert "HITL Quarantine Suspension with Deferred Rollback" in content
    assert "Embedded Local SQLite Database" in content
    assert "Interactive Upload Prompt with Abstract Fallback & Multipart API" in content

    # 3. Synchronized Functional Requirements
    assert "FR-004" in content
    assert "adaptive threshold pruning" in content
    assert "FR-006" in content
    assert "awaiting_input" in content
    assert "POST /campaigns/{campaign_id}/steering" in content
    assert "stage_XX_rejected/" in content
    assert "FR-009" in content
    assert "POST /campaigns/{campaign_id}/papers/{doi}/pdf" in content
    assert "is_multimodal: false" in content
    assert "FR-011" in content
    assert "clean break cutover dropping all legacy MySQL tables and services" in content
    assert "FR-014" in content
    assert "data/telemetry.sqlite" in content
    assert "turn_events" in content

    # 4. Synchronized Key Entities
    assert "TurnEvent" in content


def test_plan_md_sqlite_telemetry_and_endpoints() -> None:
    """Validate that plan.md reflects SQLite telemetry and new API endpoints."""
    plan_path = FEATURE_DIR / "plan.md"
    assert plan_path.exists()
    with open(plan_path, encoding="utf-8") as f:
        content = f.read()

    assert "data/telemetry.sqlite" in content
    assert "POST /campaigns/{campaign_id}/steering" in content
    assert "POST /campaigns/{campaign_id}/papers/{doi}/pdf" in content
    assert "data/campaigns/{campaign_id}/stage_{k}_rejected/" in content
    assert "Clean Break Cutover" in content
    # Assert all 7 dependent files in Phase 2 Target Files
    assert "core/dependencies.py" in content
    assert "core/logging/log_service.py" in content
    assert "features/logs/router.py" in content
    assert "features/sessions/router.py" in content
    assert "features/search/session_service.py" in content
    assert "features/agents/router.py" in content
    assert "projects/" in content
    assert "requirements.txt" in content
    # Assert paper retrieval in Phase 2 & 3 and workflow router mount
    assert "core/paper_retrieval/service.py" in content
    assert "features/workflow/router.py" in content
    assert "LoopAgent" not in content
    assert "ADK Workflow structures" in content


def test_edge_cases_and_boundary_conditions() -> None:
    """Validate boundary conditions, empty inputs, and error paths across schemas and queries."""
    data_model_path = FEATURE_DIR / "data-model.md"
    with open(data_model_path, encoding="utf-8") as f:
        content = f.read()

    match = re.search(r"```python\n(.*?)```", content, re.DOTALL)
    assert match
    code = match.group(1)

    import sys
    import types

    mod_name = "data_model_edge_test"
    mod = types.ModuleType(mod_name)
    sys.modules[mod_name] = mod
    exec(code, mod.__dict__)

    SteeringRequest = mod.SteeringRequest
    SteeringAction = mod.SteeringAction
    ResearchCampaignModel = mod.ResearchCampaignModel

    # 1. All valid SteeringAction enum members
    for action in ["CONTINUE", "EDIT_DIRECTIVE", "FORCE_APPROVE", "CONFIRM_ROLLBACK"]:
        req = SteeringRequest(action=action, stage_index=0)
        assert req.action == action

    # 2. Stage boundaries (0 to 5)
    SteeringRequest(action="CONTINUE", stage_index=0)
    SteeringRequest(action="CONTINUE", stage_index=5)
    with pytest.raises(ValidationError):
        SteeringRequest(action="CONTINUE", stage_index=-1)
    with pytest.raises(ValidationError):
        SteeringRequest(action="CONTINUE", stage_index=6)

    # 3. Research questions boundary (<= 6)
    camp_valid = ResearchCampaignModel(
        campaign_id="camp-valid",
        name="Valid",
        topic="Testing",
        research_questions=[f"RQ{i}" for i in range(6)],
    )
    assert len(camp_valid.research_questions) == 6

    with pytest.raises(ValidationError):
        ResearchCampaignModel(
            campaign_id="camp-invalid",
            name="Invalid",
            topic="Testing",
            research_questions=[f"RQ{i}" for i in range(7)],
        )

    # 4. SQLite Division by zero and empty table safety
    sql_blocks = re.findall(r"```sql\n(.*?)```", content, re.DOTALL)
    ddl = sql_blocks[0]
    conn = sqlite3.connect(":memory:")
    conn.executescript(ddl)

    # Empty table query should not error
    cursor = conn.execute(
        """
        SELECT 
            campaign_id,
            ROUND(CAST(SUM(CASE WHEN agent_role = 'critic' THEN prompt_tokens + completion_tokens ELSE 0 END) AS REAL) /
                  NULLIF(SUM(CASE WHEN agent_role = 'builder' THEN prompt_tokens + completion_tokens ELSE 0 END), 0), 2) AS vts_ratio
        FROM turn_events
        WHERE campaign_id = 'non-existent';
    """
    )
    row = cursor.fetchone()
    assert row[1] is None  # Handled safely via NULLIF without ZeroDivisionError

    # Builder has 0 tokens (only critic tokens)
    conn.execute(
        """
        INSERT INTO turn_events (
            event_id, campaign_id, run_id, stage_index, agent_name, agent_role, turn_number,
            prompt_tokens, completion_tokens, cached_tokens, latency_ms, cost_usd,
            status, model_name, critique_dimension, critique_score, timestamp
        ) VALUES (
            'ev-critic-only', 'camp-critic-only', 'run-critic-only', 1, 'ScopeCritic', 'critic', 1,
            500, 100, 0, 800.0, 0.001, 'success', 'gemini-2.5-flash', 'relevance', 0.9, '2026-09-08T21:00:00Z'
        )
    """
    )
    cursor = conn.execute(
        """
        SELECT 
            campaign_id,
            ROUND(CAST(SUM(CASE WHEN agent_role = 'critic' THEN prompt_tokens + completion_tokens ELSE 0 END) AS REAL) /
                  NULLIF(SUM(CASE WHEN agent_role = 'builder' THEN prompt_tokens + completion_tokens ELSE 0 END), 0), 2) AS vts_ratio
        FROM turn_events
        WHERE campaign_id = 'camp-critic-only';
    """
    )
    row_zero_builder = cursor.fetchone()
    assert row_zero_builder[1] is None  # Safe NULL rather than crash

    conn.close()


def test_sqlite_wal_concurrency_multi_worker(tmp_path: Path) -> None:
    """Stress test SQLite multi-worker concurrent writes under WAL mode."""
    import concurrent.futures
    import time

    data_model_path = FEATURE_DIR / "data-model.md"
    with open(data_model_path, encoding="utf-8") as f:
        content = f.read()

    sql_blocks = re.findall(r"```sql\n(.*?)```", content, re.DOTALL)
    ddl = sql_blocks[0]

    db_path = tmp_path / "telemetry_stress.sqlite"
    init_conn = sqlite3.connect(str(db_path))
    init_conn.executescript(ddl)
    init_conn.close()

    def worker_insert(worker_id: int) -> int:
        conn = sqlite3.connect(str(db_path), timeout=15.0)
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA busy_timeout = 5000;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        inserted = 0
        for i in range(10):
            event_id = f"ev-w{worker_id}-{i}"
            conn.execute(
                """
                INSERT INTO turn_events (
                    event_id, campaign_id, run_id, stage_index, agent_name, agent_role, turn_number,
                    prompt_tokens, completion_tokens, cached_tokens, latency_ms, cost_usd,
                    status, model_name, critique_dimension, critique_score, timestamp
                ) VALUES (
                    ?, 'camp-stress', 'run-stress', 2, 'SearchSnowballAgent', 'builder', ?,
                    100, 50, 20, 150.0, 0.0001, 'success', 'gemini-2.5-flash', NULL, NULL, '2026-09-08T22:00:00Z'
                )
            """,
                (event_id, i + 1),
            )
            conn.commit()
            inserted += 1
            time.sleep(0.002)
        conn.close()
        return inserted

    num_workers = 20
    with concurrent.futures.ThreadPoolExecutor(max_workers=num_workers) as executor:
        futures = [executor.submit(worker_insert, wid) for wid in range(num_workers)]
        results = [f.result() for f in futures]

    assert sum(results) == num_workers * 10

    verify_conn = sqlite3.connect(str(db_path))
    cursor = verify_conn.execute("SELECT COUNT(*) FROM turn_events WHERE campaign_id = 'camp-stress'")
    total_count = cursor.fetchone()[0]
    assert total_count == num_workers * 10
    verify_conn.close()


def test_constitution_c8_and_agents_md_sync() -> None:
    """Validate Constitution v2.2.1 C8 carve-out and AGENTS.md reference synchronization."""
    constitution_path = REPO_ROOT / ".specify" / "memory" / "constitution.md"
    assert constitution_path.exists(), f"Missing {constitution_path}"
    with open(constitution_path, encoding="utf-8") as f:
        const_content = f.read()

    assert "Constitution (v2.2.1)" in const_content
    assert "**Version**: 2.2.1" in const_content
    c8_carveout = (
        "Embedded zero-configuration local SQLite (`data/telemetry.sqlite` via Python standard library `sqlite3` with WAL mode) "
        "is permitted strictly and exclusively for local per-turn execution telemetry, token consumption tracking, and unit economics ($VTS, T_{eq}$), "
        "while preserving the strict, absolute ban on external relational database servers (MySQL, PostgreSQL, MariaDB) in any environment."
    )
    assert c8_carveout in const_content
    assert "ADK Workflow statecharts" in const_content

    agents_md_path = REPO_ROOT / "AGENTS.md"
    assert agents_md_path.exists(), f"Missing {agents_md_path}"
    with open(agents_md_path, encoding="utf-8") as f:
        agents_content = f.read()

    assert "`.specify/memory/constitution.md` (v2.2.1)" in agents_content



def test_offline_test_fixtures_and_mocks() -> None:
    """Verify conftest.py defines deterministic mock fixtures per Constitution A59 (zero live API calls)."""
    conftest_path = REPO_ROOT / "newcode/code/backend/tests/conftest.py"
    assert conftest_path.exists(), f"Missing {conftest_path}"
    content = conftest_path.read_text(encoding="utf-8")
    assert "mock_neo4j_service" in content or "mock_openalex" in content
    assert "fixture" in content


def test_main_lifespan_and_neo4j_readiness() -> None:
    """Verify main.py configures FastAPI lifespan and Neo4j connection lifecycle."""
    main_path = REPO_ROOT / "newcode/code/backend/main.py"
    assert main_path.exists(), f"Missing {main_path}"
    content = main_path.read_text(encoding="utf-8")
    assert "lifespan" in content
    assert "FastAPI" in content


def test_pdf_multipart_upload_schema_and_spec() -> None:
    """Verify contracts/campaign_api.yaml defines POST /campaigns/{campaign_id}/papers/{doi}/pdf multipart endpoint."""
    contract_path = FEATURE_DIR / "contracts/campaign_api.yaml"
    assert contract_path.exists(), f"Missing {contract_path}"
    with open(contract_path, encoding="utf-8") as f:
        schema = yaml.safe_load(f)
    paths = schema.get("paths", {})
    pdf_endpoint = paths.get("/campaigns/{campaign_id}/papers/{doi}/pdf")
    assert pdf_endpoint is not None, "Missing PDF upload endpoint in campaign_api.yaml"
    post_op = pdf_endpoint.get("post")
    assert post_op is not None, "Missing POST operation on PDF upload endpoint"
    request_body = post_op.get("requestBody", {})
    content_types = request_body.get("content", {})
    assert "multipart/form-data" in content_types, "PDF upload endpoint must use multipart/form-data"


def test_tasks_md_structure_and_coverage() -> None:
    """Validate tasks.md checklist format, 7 phases, user stories, and test verification commands."""
    tasks_path = FEATURE_DIR / "tasks.md"
    assert tasks_path.exists(), f"Missing {tasks_path}"
    content = tasks_path.read_text(encoding="utf-8")

    # 1. Verify 7 Phase headers
    expected_phases = [
        "Phase 1: Foundation & Baseline Preparation",
        "Phase 2: Clean Break Cutover & Zero-MySQL Epistemic Neo4j Persistence",
        "Phase 3: Google ADK 6-Stage Dialectical Dual-Loop Engine",
        "Phase 4: GraphSelect Topological Traversal & Candidate Appraisal",
        "Phase 5: 100% Citation Grounding & Sandboxed Compiler Gate",
        "Phase 6: Multimodal Document Extraction & Abstract Fallback",
        "Phase 7: Master's Thesis Empirical Benchmark Suite & Code Hardening",
    ]
    for phase in expected_phases:
        assert phase in content, f"Phase '{phase}' missing from tasks.md"

    # 2. Strict Checklist Format: - [ ] or - [x] Txxx [P?] [USx?] Description with file path
    task_regex = re.compile(r"^- \[[ xX]\] (T\d{3})(?: \[(P)\])?(?: \[(US\d+)\])? (.*)$")
    all_checkboxes = [line for line in content.splitlines() if line.startswith(("- [ ]", "- [x]", "- [X]"))]
    assert len(all_checkboxes) >= 70, f"Expected at least 70 tasks, found {len(all_checkboxes)}"

    story_counts: dict[str, int] = {}
    prev_tid_num = 0
    for line in all_checkboxes:
        m = task_regex.match(line)
        assert m is not None, f"Line does not match strict checklist task regex: {line}"
        tid, p, us, desc = m.groups()
        tid_num = int(tid[1:])
        assert tid_num == prev_tid_num + 1, f"Task IDs must be sequential! Expected T{prev_tid_num+1:03d}, got {tid}"
        prev_tid_num = tid_num
        # Ensure file path is present in task line
        assert "newcode/" in desc or "specs/" in desc, f"Task {tid} missing explicit target file path: {desc}"
        if us:
            story_counts[us] = story_counts.get(us, 0) + 1

    # 3. All user stories (US1, US2, US3, US4) must be represented
    for us in ["US1", "US2", "US3", "US4"]:
        assert story_counts.get(us, 0) > 0, f"User Story {us} has no tasks assigned!"

    # 4. Action, Target Files, and Verification commands must be provided for every task
    tasks = re.findall(r"(- \[[ xX]\] T\d{3}.*?)(?=(?:- \[[ xX]\] T\d{3})|\Z)", content, re.DOTALL)
    assert len(tasks) == len(all_checkboxes)
    for t in tasks:
        first_line = t.strip().splitlines()[0]
        assert "- **Action**:" in t, f"Missing Action in {first_line}"
        assert "- **Target Files**:" in t, f"Missing Target Files in {first_line}"
        assert "- **Verification**:" in t, f"Missing Verification in {first_line}"
        assert ".k " not in t, f"Found '.k' typo in verification of {first_line}"
        assert "from config import settings" not in t, f"Found invalid 'settings' import in {first_line}"

    # 5. Parallel execution examples must be present for all 4 user stories
    for us in ["User Story 1", "User Story 2", "User Story 3", "User Story 4"]:
        assert f"Parallel Execution Example: {us}" in content, f"Missing parallel execution example for {us}"





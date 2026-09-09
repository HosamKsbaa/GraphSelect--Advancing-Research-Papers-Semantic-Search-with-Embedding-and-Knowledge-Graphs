"""Contract and schema validation test suite for Feature 008 (Presentation Agent).

Validates OpenAPI 3.1 specification, Google ADK tool JSON schemas,
and Pydantic v2 domain model invariants per ADR-001 and Constitution A9, A28, A37.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
import pytest
import yaml
from pydantic import ValidationError

from features.export.presentation_models import (
    AuditSlideGroundingRequest,
    PresentationAudienceProfile,
    PresentationDeckArtifact,
    PresentationDeckRequest,
    PresentationDeckResponse,
    PresentationErrorDetail,
    PresentationErrorCode,
    PresentationSlide,
    PresentationTheme,
    PresenterNotes,
    ProjectEpistemicFacts,
    SlideGroundingCriticReport,
    SlideLayoutType,
)

CONTRACTS_DIR = Path(__file__).resolve().parents[5] / "specs/008-interactive-presentation-agent/contracts"


def test_conftest_fixtures(
    mock_presentation_project_facts: dict[str, Any],
    mock_empty_campaign_facts: dict[str, Any],
) -> None:
    """Verify conftest fixtures match ProjectEpistemicFacts schema without error."""
    facts_seeded = ProjectEpistemicFacts.model_validate(mock_presentation_project_facts)
    assert facts_seeded.project_id == "test-campaign-001"
    assert facts_seeded.scientometrics.total_papers == 42
    assert facts_seeded.empty_library_warning is False

    facts_empty = ProjectEpistemicFacts.model_validate(mock_empty_campaign_facts)
    assert facts_empty.project_id == "empty-campaign-002"
    assert facts_empty.scientometrics.total_papers == 0
    assert facts_empty.empty_library_warning is True


@pytest.mark.asyncio
async def test_conftest_neo4j_mock(mock_presentation_neo4j_service: Any) -> None:
    """Verify mock Neo4j service dispatches query responses accurately."""
    res_seeded = await mock_presentation_neo4j_service.execute_read(
        "MATCH (p:Project {project_id: $project_id})-[:HAS_RESEARCH_QUESTION]->(rq) RETURN p",
        {"project_id": "test-campaign-001"},
    )
    assert len(res_seeded) == 1
    assert res_seeded[0]["project_name"] == "Graph-Centric Dual-Loop Architecture"

    audit_res = await mock_presentation_neo4j_service.execute_read(
        "UNWIND $candidate_dois AS candidate_doi MATCH (p:Paper)",
        {"candidate_dois": ["10.1145/3292500.3330919", "10.9999/fake-paper"]},
    )
    assert len(audit_res) == 2
    assert audit_res[0]["is_grounded"] is True
    assert audit_res[1]["is_grounded"] is False


def test_openapi_schema_matches_pydantic_models() -> None:
    """Verify OpenAPI YAML schema definitions align with Pydantic domain models."""
    yaml_path = CONTRACTS_DIR / "presentation_api.yaml"
    assert yaml_path.exists(), f"Missing {yaml_path}"

    with open(yaml_path, "r", encoding="utf-8") as f:
        spec = yaml.safe_load(f)

    # Check path existence
    paths = spec["paths"]
    assert "/api/export/{project_id}/presentation" in paths
    assert "/api/export/{project_id}/presentation/latest" in paths
    assert "/api/export/{project_id}/presentations" in paths
    assert "/api/export/{project_id}/presentation/{artifact_id}/download" in paths
    assert "/api/export/{project_id}/presentation/{artifact_id}/pdf" in paths

    # Check request fields
    req_schema = spec["components"]["schemas"]["PresentationDeckRequest"]
    pydantic_req_fields = set(PresentationDeckRequest.model_fields.keys())
    openapi_req_fields = set(req_schema["properties"].keys())
    assert openapi_req_fields.issubset(pydantic_req_fields)

    # Check response fields
    resp_schema = spec["components"]["schemas"]["PresentationDeckResponse"]
    pydantic_resp_fields = set(PresentationDeckResponse.model_fields.keys())
    openapi_resp_fields = set(resp_schema["properties"].keys())
    assert openapi_resp_fields.issubset(pydantic_resp_fields)


def test_adk_tools_json_schema_matches_pydantic_models() -> None:
    """Verify Google ADK tools JSON schema contract matches Pydantic definitions."""
    json_path = CONTRACTS_DIR / "agent_tools_contracts.json"
    assert json_path.exists(), f"Missing {json_path}"

    with open(json_path, "r", encoding="utf-8") as f:
        contract_data = json.load(f)

    tools = {t["name"]: t for t in contract_data["tools"]}
    assert "generate_presentation_deck_tool" in tools
    assert "audit_slide_grounding_tool" in tools

    gen_tool = tools["generate_presentation_deck_tool"]
    gen_props = set(gen_tool["parameters"]["properties"].keys())
    assert gen_props.issubset(set(PresentationDeckRequest.model_fields.keys()))

    audit_tool = tools["audit_slide_grounding_tool"]
    audit_params = set(audit_tool["parameters"]["properties"].keys())
    assert audit_params.issubset(set(AuditSlideGroundingRequest.model_fields.keys()))

    critic_report_fields = set(SlideGroundingCriticReport.model_fields.keys())
    audit_returns = set(audit_tool["returns"]["properties"].keys())
    assert audit_returns.issubset(critic_report_fields)


def test_pydantic_invariants_and_validators() -> None:
    """Verify boundary validators enforce Constitution C7 and A37 invariants."""
    # 1. Slide count boundary enforcement (8 <= N <= 20)
    with pytest.raises(ValidationError):
        PresentationDeckRequest(project_id="p-1", target_slide_count=5)
    with pytest.raises(ValidationError):
        PresentationDeckRequest(project_id="p-1", target_slide_count=25)

    valid_req = PresentationDeckRequest(project_id="p-1", target_slide_count=12)
    assert valid_req.target_slide_count == 12

    # 2. CHR == 0.0% validation invariant
    with pytest.raises(ValueError, match="Zero Hallucination Invariant Violated"):
        SlideGroundingCriticReport(
            is_grounded=True,
            measured_chr=15.5,
            composite_score=0.85,
            dimension_scores={"accuracy": 0.8},
            violations=["Ungrounded DOI 10.9999/fake"],
            actionable_directives=["Replace DOI"],
        )

    # Valid grounding report when CHR == 0.0%
    valid_report = SlideGroundingCriticReport(
        is_grounded=True,
        measured_chr=0.0,
        composite_score=1.0,
        dimension_scores={"accuracy": 1.0},
        violations=[],
        actionable_directives=[],
    )
    assert valid_report.is_grounded is True

"""Tests verifying Tiered Multi-Agent Model Architecture configuration and runtime propagation."""
import os
import pytest
from unittest.mock import patch
from starlette.testclient import TestClient

from config import Settings, get_settings
from main import app
from features.settings import router as settings_router
from agents.orchestrator.agent import create_orchestrator_agent
from agents.planner.agent import create_planner_agent
from agents.writing.reviewer_agent import create_reviewer_agent
from agents.debugger.agent import create_debugger_agent
from agents.research.alrs_agent import create_alrs_agent
from agents.research.gap_finder import create_gap_finder_agent
from agents.research.evidence_synthesizer import create_evidence_synthesizer_agent
from agents.writing.drafting_agent import create_drafting_agent


def test_agent_tier_model_inheritance():
    """Verify Tier 1 and Tier 2 agents inherit the configured tier models."""
    settings = get_settings()

    # Tier 1: Orchestration & Reasoning
    proj_agent = create_orchestrator_agent()
    plan_agent = create_planner_agent()
    rev_agent = create_reviewer_agent()
    deb_agent = create_debugger_agent()

    assert proj_agent.model == settings.adk_tier1_model
    assert plan_agent.model == settings.adk_tier1_model
    assert rev_agent.model == settings.adk_tier1_model
    assert deb_agent.model == settings.adk_tier1_model

    # Tier 2: Specialized Workers
    alrs_agent = create_alrs_agent()
    gap_agent = create_gap_finder_agent()
    synth_agent = create_evidence_synthesizer_agent()
    draft_agent = create_drafting_agent()

    assert alrs_agent.model == settings.adk_tier2_model
    assert gap_agent.model == settings.adk_tier2_model
    assert synth_agent.model == settings.adk_tier2_model
    assert draft_agent.model == settings.adk_tier2_model


def test_settings_api_tiered_models_get_and_put(tmp_path):
    """Verify settings REST API returns and updates tiered models."""
    temp_env = tmp_path / ".env"
    temp_env.write_text(
        "OPENALEX_API_KEY=test-alex-key\n"
        "NEO4J_PASSWORD=test-neo-pass\n"
        "MYSQL_PASSWORD=test-sql-pass\n"
        "ADK_TIER1_MODEL=gemini-2.5-flash\n"
        "ADK_TIER2_MODEL=gemini-3.5-flash-lite\n"
    )

    with patch.object(settings_router, "ENV_FILE", temp_env):
        client = TestClient(app)
        # 1. GET /api/settings
        res = client.get("/api/settings")
        assert res.status_code == 200
        data = res.json()
        assert data["adk_tier1_model"] == "gemini-2.5-flash"
        assert data["adk_tier2_model"] == "gemini-3.5-flash-lite"
        assert "gemini-2.5-pro" in data["available_models"]

        # 2. PUT /api/settings to switch to Maximum Rigor preset (Tier 1: gemini-2.5-pro, Tier 2: gemini-2.5-flash)
        update_res = client.put(
            "/api/settings",
            json={
                "adk_tier1_model": "gemini-2.5-pro",
                "adk_tier2_model": "gemini-2.5-flash",
            },
        )
        assert update_res.status_code == 200
        assert update_res.json()["success"] is True

        # 3. Verify changes persisted
        env_content = temp_env.read_text()
        assert "ADK_TIER1_MODEL=gemini-2.5-pro" in env_content
        assert "ADK_TIER2_MODEL=gemini-2.5-flash" in env_content


def test_settings_api_get_available_models(tmp_path):
    """Verify GET /api/settings/models returns live or fallback Gemini models."""
    temp_env = tmp_path / ".env"
    temp_env.write_text(
        "OPENALEX_API_KEY=test-alex-key\n"
        "NEO4J_PASSWORD=test-neo-pass\n"
        "MYSQL_PASSWORD=test-sql-pass\n"
    )

    with patch.object(settings_router, "ENV_FILE", temp_env):
        client = TestClient(app)
        res = client.get("/api/settings/models")
        assert res.status_code == 200
        data = res.json()
        assert "models" in data
        assert len(data["models"]) > 0
        assert data["total"] == len(data["models"])
        assert data["source"] in ("google_api", "fallback")
        assert "gemini-2.5-flash" in data["models"]

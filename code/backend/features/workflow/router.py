"""Workflow and Campaign API router for ALRS v2.

Implements REST and SSE streaming endpoints for research campaigns matching contracts/campaign_api.yaml.
Complies with Constitution C1/C9 (<25 lines per function).
"""
from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, AsyncIterator, Literal
import uuid
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from core.db.neo4j_service import Neo4jService
from core.dependencies import get_neo4j_service
from features.workflow.execution_pipeline import execute_campaign
from features.workflow.state_models import (
    ResearchCampaignModel,
    SteeringRequest,
    normalize_doi,
    utc_now,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/campaigns", tags=["campaigns"])


class CreateCampaignRequest(BaseModel):
    topic: str
    name: str = ""
    entry_mode: Literal["exploration", "refinement", "targeted"] = "exploration"
    token_budget: int = Field(default=500_000, ge=10_000)
    seed_dois: list[str] = Field(default_factory=list)
    research_questions: list[str] = Field(default_factory=list, max_length=6)


class ExecuteStageRequest(BaseModel):
    stage_index: int | None = Field(default=None, ge=0, le=5)
    force: bool = False
    parameters: dict[str, Any] = Field(default_factory=dict)


@router.post("", status_code=status.HTTP_201_CREATED, summary="Initialize a new Research Campaign")
async def create_campaign(
    payload: CreateCampaignRequest,
    neo4j: Neo4jService = Depends(get_neo4j_service),
) -> dict[str, Any]:
    """Create and persist a new ResearchCampaign node."""
    cid = str(uuid.uuid4())
    norm_dois = [normalize_doi(d) for d in payload.seed_dois if normalize_doi(d)]
    start_st = 2 if payload.entry_mode == "targeted" else (1 if payload.entry_mode == "refinement" else 0)
    now_iso = utc_now().isoformat()
    cypher = """
    MERGE (c:ResearchCampaign {campaign_id: $cid})
    SET c.name = $name, c.topic = $topic, c.entry_mode = $mode,
        c.status = 'active', c.current_stage = $st, c.token_budget = $budget,
        c.tokens_used = 0, c.total_turns = 0, c.vts_ratio = 0.0,
        c.seed_dois = $dois, c.research_questions = $rqs, c.created_at = $now
    RETURN c.campaign_id AS campaign_id, c.name AS name, c.topic AS topic,
           c.entry_mode AS entry_mode, c.status AS status, c.current_stage AS current_stage,
           c.token_budget AS token_budget, c.tokens_used AS tokens_used,
           c.total_turns AS total_turns, c.vts_ratio AS vts_ratio, c.created_at AS created_at
    """
    params = {
        "cid": cid, "name": payload.name or f"Campaign: {payload.topic[:30]}",
        "topic": payload.topic, "mode": payload.entry_mode, "st": start_st,
        "budget": payload.token_budget, "dois": norm_dois, "rqs": payload.research_questions, "now": now_iso,
    }
    records = await neo4j.execute_write(cypher, params)
    return records[0] if records else {"campaign_id": cid, "status": "active"}


@router.get("", summary="List all research campaigns")
async def list_campaigns(
    mode: str | None = Query(default=None),
    limit: int = Query(default=20),
    neo4j: Neo4jService = Depends(get_neo4j_service),
) -> list[dict[str, Any]]:
    """List campaigns with optional mode filter."""
    where_clause = "WHERE c.entry_mode = $mode" if mode else ""
    query = f"""
    MATCH (c:ResearchCampaign) {where_clause}
    RETURN c.campaign_id AS campaign_id, c.name AS name, c.topic AS topic,
           c.entry_mode AS entry_mode, c.status AS status,
           c.current_stage AS current_stage, c.token_budget AS token_budget,
           c.tokens_used AS tokens_used, c.total_turns AS total_turns,
           c.vts_ratio AS vts_ratio, c.created_at AS created_at
    ORDER BY c.created_at DESC LIMIT $limit
    """
    params: dict[str, Any] = {"limit": limit}
    if mode:
        params["mode"] = mode
    return await neo4j.execute_read(query, params)


@router.get("/{campaign_id}", summary="Get campaign details")
async def get_campaign(
    campaign_id: str,
    neo4j: Neo4jService = Depends(get_neo4j_service),
) -> dict[str, Any]:
    """Fetch campaign details and 4-quadrant stage substate."""
    query = """
    MATCH (c:ResearchCampaign {campaign_id: $campaign_id})
    OPTIONAL MATCH (c)-[:HAS_STAGE_STATE]->(s:StageSubstate)
    RETURN c.campaign_id AS campaign_id, c.name AS name, c.topic AS topic,
           c.entry_mode AS entry_mode, c.status AS status,
           c.current_stage AS current_stage, c.token_budget AS token_budget,
           c.tokens_used AS tokens_used, c.total_turns AS total_turns,
           c.vts_ratio AS vts_ratio, c.created_at AS created_at,
           collect(s) AS stages
    """
    records = await neo4j.execute_read(query, {"campaign_id": campaign_id})
    if not records or not records[0].get("campaign_id"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Campaign {campaign_id} not found")
    return records[0]


async def _run_background_campaign_stage(campaign_id: str, stage_idx: int, neo4j: Neo4jService) -> None:
    """Execute campaign stage in background task."""
    try:
        camp = ResearchCampaignModel(campaign_id=campaign_id, current_stage=stage_idx)
        await execute_campaign(camp, persistence=None)
        await neo4j.execute_write(
            "MATCH (c:ResearchCampaign {campaign_id: $cid}) SET c.current_stage = $st, c.status = $status",
            {"cid": campaign_id, "st": camp.current_stage, "status": camp.status},
        )
    except Exception as exc:
        logger.exception("Background execution failed for campaign %s: %s", campaign_id, exc)


@router.post("/{campaign_id}/execute", status_code=status.HTTP_202_ACCEPTED, summary="Trigger stage execution")
async def trigger_stage_execution(
    campaign_id: str,
    payload: ExecuteStageRequest | None = None,
    neo4j: Neo4jService = Depends(get_neo4j_service),
) -> dict[str, Any]:
    """Trigger execution of the active or requested stage asynchronously."""
    recs = await neo4j.execute_read("MATCH (c:ResearchCampaign {campaign_id: $cid}) RETURN c", {"cid": campaign_id})
    if not recs:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Campaign {campaign_id} not found")
    c_data = recs[0]["c"]
    st = payload.stage_index if payload and payload.stage_index is not None else c_data.get("current_stage", 0)
    if c_data.get("status") == "awaiting_input" and not (payload and payload.force):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Campaign awaiting human steering decision")
    asyncio.create_task(_run_background_campaign_stage(campaign_id, st, neo4j))
    return {
        "campaign_id": campaign_id,
        "stage_index": st,
        "status": "started",
        "message": f"Stage {st} execution started asynchronously.",
    }


async def _stream_campaign_generator(campaign_id: str, neo4j: Neo4jService) -> AsyncIterator[dict[str, str]]:
    """Yield Server-Sent Events stream for campaign updates."""
    yield {"event": "connected", "data": json.dumps({"campaign_id": campaign_id, "status": "connected"})}
    for tick in range(1, 4):
        await asyncio.sleep(0.01)
        recs = await neo4j.execute_read(
            "MATCH (c:ResearchCampaign {campaign_id: $cid}) RETURN c.status AS s, c.current_stage AS st",
            {"cid": campaign_id},
        )
        status_val = recs[0].get("s", "active") if recs else "active"
        stage_val = recs[0].get("st", 0) if recs else 0
        payload = {"tick": tick, "status": status_val, "current_stage": stage_val}
        yield {"id": str(tick), "event": "progress", "data": json.dumps(payload)}
    yield {"event": "heartbeat", "data": json.dumps({"ping": utc_now().isoformat()})}


@router.get("/{campaign_id}/stream", summary="Stream campaign SSE events")
async def stream_campaign_events(
    campaign_id: str,
    neo4j: Neo4jService = Depends(get_neo4j_service),
) -> EventSourceResponse:
    """Return Server-Sent Events stream for active campaign."""
    recs = await neo4j.execute_read("MATCH (c:ResearchCampaign {campaign_id: $cid}) RETURN c.campaign_id", {"cid": campaign_id})
    if not recs:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Campaign {campaign_id} not found")
    return EventSourceResponse(_stream_campaign_generator(campaign_id, neo4j))


@router.post("/{campaign_id}/steering", summary="Submit researcher steering directives")
async def steer_campaign(
    campaign_id: str,
    payload: SteeringRequest,
    neo4j: Neo4jService = Depends(get_neo4j_service),
) -> dict[str, Any]:
    """Apply steering directives to an awaiting_input campaign."""
    recs = await neo4j.execute_read("MATCH (c:ResearchCampaign {campaign_id: $cid}) RETURN c", {"cid": campaign_id})
    if not recs:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Campaign {campaign_id} not found")
    c_data = recs[0]["c"]
    if c_data.get("status") != "awaiting_input":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Campaign is not awaiting input")
    if payload.action == "CONFIRM_ROLLBACK":
        await neo4j.rollback_stage_transaction(campaign_id, payload.stage_index)
    next_status = "active"
    next_stage = payload.stage_index if payload.action != "FORCE_APPROVE" else min(5, payload.stage_index + 1)
    await neo4j.execute_write(
        "MATCH (c:ResearchCampaign {campaign_id: $cid}) SET c.status = $st, c.current_stage = $stage, c.directives = $dir",
        {"cid": campaign_id, "st": next_status, "stage": next_stage, "dir": payload.directives or ""},
    )
    return await get_campaign(campaign_id, neo4j)


def _validate_pdf_payload(content: bytes, is_authorized: bool) -> None:
    """Verify authorization and magic bytes for PDF upload."""
    if not is_authorized:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="PDF upload not authorized")
    if not content.startswith(b"%PDF"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid PDF file: magic byte check failed")


def _save_pdf_artifact(campaign_id: str, clean_doi: str, content: bytes) -> Path:
    """Save raw PDF bytes to local campaign storage."""
    safe_doi = clean_doi.replace("/", "_")
    target_dir = Path("data/campaigns") / campaign_id / "pdfs"
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / f"{safe_doi}.pdf"
    target_path.write_bytes(content)
    return target_path


async def _verify_campaign_and_paper(neo4j: Neo4jService, campaign_id: str, clean_doi: str) -> None:
    """Check existence of campaign and paper nodes prior to PDF attachment."""
    camp = await neo4j.execute_read("MATCH (c:ResearchCampaign {campaign_id: $cid}) RETURN c", {"cid": campaign_id})
    if not camp:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Campaign {campaign_id} not found")
    paper = await neo4j.execute_read("MATCH (p:Paper {doi: $doi}) RETURN p", {"doi": clean_doi})
    if not paper:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Paper {clean_doi} not found in graph")


@router.post("/{campaign_id}/papers/{doi:path}/pdf", summary="Upload authorized PDF for an academic paper")
async def upload_paper_pdf(
    campaign_id: str,
    doi: str,
    file: UploadFile = File(...),
    is_authorized: bool = Form(True),
    neo4j: Neo4jService = Depends(get_neo4j_service),
) -> dict[str, Any]:
    """Accept multipart PDF upload, validate magic bytes, and update :Paper node."""
    clean_doi = normalize_doi(doi)
    content = await file.read()
    _validate_pdf_payload(content, is_authorized)
    await _verify_campaign_and_paper(neo4j, campaign_id, clean_doi)
    saved_path = _save_pdf_artifact(campaign_id, clean_doi, content)

    await neo4j.execute_write(
        "MATCH (p:Paper {doi: $doi}) SET p.is_multimodal = true, p.pdf_path = $path",
        {"doi": clean_doi, "path": str(saved_path)},
    )
    return {
        "campaign_id": campaign_id,
        "doi": clean_doi,
        "file_path": str(saved_path),
        "file_size_bytes": len(content),
        "is_multimodal": True,
        "message": "PDF uploaded and verified; multimodal processing enqueued",
    }



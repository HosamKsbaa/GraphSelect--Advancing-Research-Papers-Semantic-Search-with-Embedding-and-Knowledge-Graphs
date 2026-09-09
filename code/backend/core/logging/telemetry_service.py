"""Embedded SQLite WAL Telemetry Service for ALRS v2.

Complies with Constitution C8, C9 (sub-25 line functions), C11, and data-model.md §2.
"""
from __future__ import annotations

import math
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import get_settings


TURN_EVENTS_DDL = """
PRAGMA journal_mode = WAL;
PRAGMA busy_timeout = 5000;
PRAGMA synchronous = NORMAL;

CREATE TABLE IF NOT EXISTS turn_events (
    event_id TEXT PRIMARY KEY,
    campaign_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    stage_index INTEGER NOT NULL,
    agent_name TEXT NOT NULL,
    agent_role TEXT NOT NULL,
    tool_name TEXT,
    turn_number INTEGER NOT NULL,
    prompt_tokens INTEGER NOT NULL,
    completion_tokens INTEGER NOT NULL,
    cached_tokens INTEGER NOT NULL DEFAULT 0,
    prompt_hash TEXT,
    latency_ms REAL NOT NULL,
    cost_usd REAL NOT NULL,
    status TEXT NOT NULL,
    model_name TEXT NOT NULL,
    critique_dimension TEXT,
    critique_score REAL,
    timestamp TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_turn_events_campaign ON turn_events (campaign_id, stage_index);
CREATE INDEX IF NOT EXISTS idx_turn_events_timestamp ON turn_events (timestamp);
"""


class TelemetryService:
    """Embedded SQLite WAL telemetry service for per-turn metrics and rollups."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        if db_path is None:
            db_path = get_settings().sqlite_telemetry_path
        self._db_path = Path(db_path) if str(db_path) != ":memory:" else ":memory:"
        self._mem_conn: sqlite3.Connection | None = None
        self._ensure_db_dir()
        self._init_db()

    def _ensure_db_dir(self) -> None:
        """Ensure parent directory exists for SQLite database."""
        if str(self._db_path) != ":memory:":
            Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)

    def _get_connection(self) -> sqlite3.Connection:
        """Create and configure a SQLite connection in WAL mode."""
        if str(self._db_path) == ":memory:":
            if self._mem_conn is None:
                self._mem_conn = sqlite3.connect(":memory:")
                self._mem_conn.row_factory = sqlite3.Row
            return self._mem_conn
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA busy_timeout = 5000;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        return conn

    def _init_db(self) -> None:
        """Execute DDL initialization script."""
        conn = self._get_connection()
        conn.executescript(TURN_EVENTS_DDL)
        conn.commit()
        if str(self._db_path) != ":memory:":
            conn.close()

    def record_turn_event(self, event_data: dict[str, Any] | Any) -> str:
        """Insert a turn execution event into the SQLite store."""
        data = self._coerce_event_dict(event_data)
        query = (
            "INSERT INTO turn_events ("
            "event_id, campaign_id, run_id, stage_index, agent_name, agent_role, "
            "tool_name, turn_number, prompt_tokens, completion_tokens, cached_tokens, "
            "prompt_hash, latency_ms, cost_usd, status, model_name, "
            "critique_dimension, critique_score, timestamp) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
        )
        values = self._build_event_tuple(data)
        conn = self._get_connection()
        try:
            conn.execute(query, values)
            conn.commit()
        finally:
            if str(self._db_path) != ":memory:":
                conn.close()
        return str(data["event_id"])

    def _coerce_event_dict(self, event: dict[str, Any] | Any) -> dict[str, Any]:
        """Normalize event object or Pydantic model to dictionary."""
        if hasattr(event, "model_dump"):
            res = dict(event.model_dump())
        elif isinstance(event, dict):
            res = dict(event)
        else:
            res = dict(vars(event))
        if "event_id" not in res or not res["event_id"]:
            res["event_id"] = f"ev-{uuid.uuid4().hex[:12]}"
        if "timestamp" not in res or not res["timestamp"]:
            res["timestamp"] = datetime.now(timezone.utc).isoformat()
        elif isinstance(res["timestamp"], datetime):
            res["timestamp"] = res["timestamp"].isoformat()
        return res

    def _build_event_tuple(self, d: dict[str, Any]) -> tuple[Any, ...]:
        """Construct parameter tuple for turn event insertion."""
        return (
            d.get("event_id"),
            d.get("campaign_id"),
            d.get("run_id", "default_run"),
            int(d.get("stage_index", 0)),
            d.get("agent_name", "unknown"),
            d.get("agent_role", "builder"),
            d.get("tool_name"),
            int(d.get("turn_number", 1)),
            int(d.get("prompt_tokens", 0)),
            int(d.get("completion_tokens", 0)),
            int(d.get("cached_tokens", 0)),
            d.get("prompt_hash"),
            float(d.get("latency_ms", 0.0)),
            float(d.get("cost_usd", 0.0)),
            d.get("status", "success"),
            d.get("model_name", "gemini-2.5-flash"),
            d.get("critique_dimension"),
            d.get("critique_score"),
            str(d.get("timestamp")),
        )

    def get_campaign_rollup(self, campaign_id: str) -> dict[str, Any]:
        """Compute aggregate cost, token usage, and latency for a campaign."""
        query = (
            "SELECT campaign_id, COUNT(*) AS total_turns, "
            "SUM(prompt_tokens) AS total_prompt_tokens, "
            "SUM(completion_tokens) AS total_completion_tokens, "
            "SUM(cached_tokens) AS total_cached_tokens, "
            "ROUND(SUM(latency_ms) / 1000.0, 2) AS total_latency_seconds, "
            "ROUND(SUM(cost_usd), 4) AS total_cost_usd "
            "FROM turn_events WHERE campaign_id = ? GROUP BY campaign_id"
        )
        conn = self._get_connection()
        try:
            row = conn.execute(query, (campaign_id,)).fetchone()
        finally:
            if str(self._db_path) != ":memory:":
                conn.close()
        return self._format_rollup_row(campaign_id, row)

    def _format_rollup_row(self, campaign_id: str, row: sqlite3.Row | None) -> dict[str, Any]:
        """Format rollup database row into typed dictionary."""
        if not row:
            return {
                "campaign_id": campaign_id,
                "total_turns": 0,
                "total_prompt_tokens": 0,
                "total_completion_tokens": 0,
                "total_cached_tokens": 0,
                "total_latency_seconds": 0.0,
                "total_cost_usd": 0.0,
            }
        return {
            "campaign_id": row["campaign_id"],
            "total_turns": int(row["total_turns"]),
            "total_prompt_tokens": int(row["total_prompt_tokens"] or 0),
            "total_completion_tokens": int(row["total_completion_tokens"] or 0),
            "total_cached_tokens": int(row["total_cached_tokens"] or 0),
            "total_latency_seconds": float(row["total_latency_seconds"] or 0.0),
            "total_cost_usd": float(row["total_cost_usd"] or 0.0),
        }

    def get_vts_ratio(self, campaign_id: str) -> float:
        """Calculate Verification-to-Synthesis (VTS) token expenditure ratio."""
        query = (
            "SELECT ROUND(CAST(SUM(CASE WHEN agent_role = 'critic' "
            "THEN prompt_tokens + completion_tokens ELSE 0 END) AS REAL) / "
            "NULLIF(SUM(CASE WHEN agent_role = 'builder' "
            "THEN prompt_tokens + completion_tokens ELSE 0 END), 0), 2) AS vts_ratio "
            "FROM turn_events WHERE campaign_id = ?"
        )
        conn = self._get_connection()
        try:
            row = conn.execute(query, (campaign_id,)).fetchone()
        finally:
            if str(self._db_path) != ":memory:":
                conn.close()
        return float(row["vts_ratio"]) if row and row["vts_ratio"] is not None else 0.0

    def get_stage_triage(self, campaign_id: str) -> list[dict[str, Any]]:
        """Retrieve stage-by-stage iterations, retries, and average critic scores."""
        query = (
            "SELECT stage_index, COUNT(*) AS turns, "
            "SUM(CASE WHEN status = 'retry' THEN 1 ELSE 0 END) AS retries, "
            "SUM(CASE WHEN status = 'rejected' THEN 1 ELSE 0 END) AS rejections, "
            "ROUND(AVG(critique_score), 3) AS avg_critic_score, "
            "ROUND(SUM(cost_usd), 4) AS stage_cost_usd "
            "FROM turn_events WHERE campaign_id = ? "
            "GROUP BY stage_index ORDER BY stage_index ASC"
        )
        conn = self._get_connection()
        try:
            rows = conn.execute(query, (campaign_id,)).fetchall()
        finally:
            if str(self._db_path) != ":memory:":
                conn.close()
        return [dict(r) for r in rows]

    def compute_equivalent_token_time(self, campaign_id: str) -> float:
        """Compute Equivalent Token Time (T_eq = total_latency_seconds / max(1, total_completion_tokens))."""
        rollup = self.get_campaign_rollup(campaign_id)
        tokens = max(1, rollup["total_completion_tokens"])
        return float(round(rollup["total_latency_seconds"] / tokens, 4))

    def compute_verification_to_synthesis_ratio(self, campaign_id: str) -> float:
        """Compute VTS ratio (A50 requirement: VTS >= 1.2)."""
        return self.get_vts_ratio(campaign_id)

    def compute_total_cost_usd(self, campaign_id: str) -> float:
        """Compute total monetary cost for campaign turns."""
        rollup = self.get_campaign_rollup(campaign_id)
        return float(rollup["total_cost_usd"])

    def compute_pomdp_cumulative_reward(
        self,
        campaign_id: str,
        beta_1: float = 1.0,
        beta_2: float = 1.5,
        beta_3: float = 1.2,
        beta_4: float = 0.5,
        r_compile: float = 1.0,
        r_citation: float = 1.0,
        r_novelty: float = 0.8,
    ) -> float:
        """Calculate POMDP cumulative reward per Constitution A48."""
        cost = self.compute_total_cost_usd(campaign_id)
        reward = (beta_1 * r_compile) + (beta_2 * r_citation) + (beta_3 * r_novelty) - (beta_4 * cost)
        return float(round(reward, 4))

    async def sync_campaign_rollups_to_neo4j(self, campaign_id: str, neo4j_service: Any) -> None:
        """Synchronize SQLite analytical rollup to :ResearchCampaign in Neo4j."""
        rollup = self.get_campaign_rollup(campaign_id)
        vts = self.get_vts_ratio(campaign_id)
        cypher = (
            "MATCH (c:ResearchCampaign {campaign_id: $campaign_id}) "
            "SET c.total_turns = $total_turns, "
            "c.total_prompt_tokens = $total_prompt_tokens, "
            "c.total_completion_tokens = $total_completion_tokens, "
            "c.total_cached_tokens = $total_cached_tokens, "
            "c.total_latency_seconds = $total_latency_seconds, "
            "c.total_cost_usd = $total_cost_usd, "
            "c.vts_ratio = $vts_ratio, "
            "c.updated_at = datetime()"
        )
        params = {**rollup, "vts_ratio": vts}
        if hasattr(neo4j_service, "execute_write"):
            await neo4j_service.execute_write(cypher, params)

    def get_turn_events(self, campaign_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        """Query turn events filtered by campaign with analytical limit."""
        args: tuple[Any, ...]
        if campaign_id:
            query = "SELECT * FROM turn_events WHERE campaign_id = ? ORDER BY timestamp DESC LIMIT ?"
            args = (campaign_id, limit)
        else:
            query = "SELECT * FROM turn_events ORDER BY timestamp DESC LIMIT ?"
            args = (limit,)
        conn = self._get_connection()
        try:
            rows = conn.execute(query, args).fetchall()
        finally:
            if str(self._db_path) != ":memory:":
                conn.close()
        return [dict(r) for r in rows]

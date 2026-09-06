"""Scoped navigation, public message board, and state mutation tools for ALRS agents.

Implements Requirement R4:
- get_project_state: Dot-path query, summary mode, stage isolation to prevent LLM context exhaustion.
- post_to_message_board: Publish cross-cutting discoveries across 6 typed classifications with DOI normalization.
- read_message_board: Filter public message board by message type, stage, tag, DOI, or unacknowledged status.
- update_stage_substate: Scoped mutation for an agent's stage quadrant with deep-merging and validation.
"""
from __future__ import annotations

import copy
import json
import logging
from pathlib import Path
from typing import Any, Literal
from pydantic import BaseModel, ValidationError

try:
    from google.adk.tools.tool_context import ToolContext
except ImportError:
    ToolContext = Any  # type: ignore[misc, assignment]

from features.workflow.state_models import (
    BoardClassification,
    BoardMessage,
    ProjectState,
    StageNote,
    WorkflowStageName,
    deep_merge,
    normalize_doi,
    normalize_stage_name,
    utc_now,
)

logger = logging.getLogger(__name__)

# Valid board message types
VALID_MESSAGE_TYPES = {
    "insight",
    "serendipity",
    "gap",
    "warning",
    "decision",
    "hypothesis",
}

# Valid workflow stages
VALID_STAGES = {
    "stage_1_research",
    "stage_2_analysis",
    "stage_3_planning",
    "stage_4_writing",
    "stage_5_export",
}

# Valid quadrants
VALID_QUADRANTS = {"meta", "inputs", "artifacts", "notes"}

# Module-level active project state fallback (for testing/standalone usage without ToolContext)
_active_project_state: ProjectState | None = None


def set_active_project_state(state: ProjectState | None) -> None:
    """Set the module-level active project state."""
    global _active_project_state
    _active_project_state = state


def get_active_project_state() -> ProjectState | None:
    """Get the module-level active project state."""
    global _active_project_state
    return _active_project_state


async def _resolve_project_state(
    tool_context: ToolContext | None = None,
) -> tuple[ProjectState | None, str | None, bool]:
    """Resolve ProjectState, agent_name, and whether the original was a raw dict (asynchronous).

    Returns:
        tuple of (state: ProjectState | None, agent_name: str | None, original_was_raw_dict: bool)
    """
    global _active_project_state

    agent_name: str | None = None
    if tool_context is not None:
        agent_obj = getattr(tool_context, "agent", None)
        if agent_obj is not None:
            agent_name = getattr(agent_obj, "name", None)
        if not agent_name:
            agent_name = getattr(tool_context, "agent_name", None)
        if not agent_name:
            agent_name = getattr(tool_context, "author", None)

    state_container: Any = None
    if tool_context is not None:
        if hasattr(tool_context, "state"):
            state_container = getattr(tool_context, "state", None)
        elif isinstance(tool_context, dict):
            state_container = tool_context
        elif isinstance(tool_context, ProjectState):
            return tool_context, agent_name or "system", False

    raw_state = None
    project_id = None
    original_was_dict = False

    if isinstance(state_container, dict):
        raw_state = state_container.get("project_state")
        project_id = state_container.get("project_id") or state_container.get("active_project_id")
        if not agent_name:
            agent_name = state_container.get("agent_name") or state_container.get("current_agent")
    elif state_container is not None and hasattr(state_container, "get"):
        raw_state = state_container.get("project_state")
        project_id = state_container.get("project_id") or state_container.get("active_project_id")
    elif isinstance(state_container, ProjectState):
        raw_state = state_container

    if raw_state is not None:
        if isinstance(raw_state, ProjectState):
            return raw_state, agent_name or "system", False
        if isinstance(raw_state, dict):
            try:
                state_obj = ProjectState.model_validate(raw_state)
                return state_obj, agent_name or "system", True
            except Exception as e:
                logger.warning("Failed to validate raw project_state dict: %s", e)
                return None, agent_name, True

    # If project_id exists, load asynchronously via persistence service or disk
    if project_id:
        pid_str = str(project_id)
        try:
            from features.workflow.persistence_service import ProjectPersistenceService

            svc = ProjectPersistenceService.get_instance()
            loaded = await svc.load_state(pid_str, tool_context)
            if loaded is not None:
                if state_container is not None and hasattr(state_container, "__setitem__"):
                    try:
                        dumped = loaded.model_dump(mode="json")
                        state_container["project_state"] = dumped if original_was_dict else loaded
                        state_container["project_id"] = pid_str
                    except Exception:
                        pass
                return loaded, agent_name or "system", False
        except Exception as exc:
            logger.debug("Async state load via persistence service skipped/failed for %s: %s", pid_str, exc)

        candidate_bases = (
            Path(__file__).resolve().parent.parent.parent / "data" / "projects",
            Path("backend/data/projects"),
            Path("data/projects"),
        )
        for base in candidate_bases:
            try:
                state_file = base / pid_str / "project_state.json"
                if state_file.exists():
                    with open(state_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    state_obj = ProjectState.model_validate(data)
                    if state_container is not None and hasattr(state_container, "__setitem__"):
                        try:
                            dumped = state_obj.model_dump(mode="json")
                            state_container["project_state"] = dumped if original_was_dict else state_obj
                            state_container["project_id"] = pid_str
                        except Exception:
                            pass
                    return state_obj, agent_name or "system", False
            except Exception as e:
                logger.debug("Failed to load project state from disk %s: %s", base, e)

    # Fallback to module-level active project state
    if _active_project_state is not None:
        return _active_project_state, agent_name or "system", False

    return None, agent_name, False


def _sync_project_state(
    state: ProjectState,
    tool_context: ToolContext | None = None,
    original_was_dict: bool = False,
) -> None:
    """Synchronize mutated ProjectState back to tool_context, disk, and MySQL."""
    global _active_project_state
    if _active_project_state is not None and _active_project_state.project_id == state.project_id:
        _active_project_state = state

    if tool_context is not None:
        state_container: Any = getattr(tool_context, "state", None)
        if state_container is None and isinstance(tool_context, dict):
            state_container = tool_context

        dumped = state.model_dump(mode="json")
        if state_container is not None and hasattr(state_container, "__setitem__"):
            state_dict: Any = state_container
            if original_was_dict:
                state_dict["project_state"] = dumped
            else:
                state_dict["project_state"] = state
            try:
                state_dict["project_id"] = str(state.project_id)
            except Exception:
                pass

    # Invoke ProjectPersistenceService to persist to both disk and MySQL
    try:
        from features.workflow.persistence_service import ProjectPersistenceService

        ProjectPersistenceService.save_state(state, tool_context)
    except Exception as e:
        logger.debug("Persistence via ProjectPersistenceService skipped or failed: %s", e)


def _dump_json_safe(val: Any) -> Any:
    """Recursively convert Pydantic models and data structures to JSON-safe primitives."""
    if isinstance(val, BaseModel):
        return val.model_dump(mode="json")
    if isinstance(val, (list, tuple, set)):
        return [_dump_json_safe(x) for x in val]
    if isinstance(val, dict):
        return {k: _dump_json_safe(v) for k, v in val.items()}
    return val


# ---------------------------------------------------------------------------
# Tool 1: get_project_state (R4 Scoped Dot-Path Querying)
# ---------------------------------------------------------------------------

async def get_project_state(
    scope: str = "summary",
    stage: str | None = None,
    path: str | None = None,
    tool_context: ToolContext | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Retrieve all or part of the unified ProjectState with scoped dot-path navigation.

    Prevents LLM context overflow by returning targeted summaries or subtrees.

    Args:
        scope: Navigation scope:
            - 'summary': Compact metadata, tokens, stages progress, unacknowledged board messages count (default).
            - 'stage': Returns the specified stage's substate or quadrant.
            - 'path': Resolves a dot-delimited path into the state.
            - 'all' / 'full': Full serialized project state.
        stage: Specific workflow stage (e.g. 'stage_1_research', 'research', 'stage_2_analysis').
        path: Dot-delimited query path (e.g. 'stage_1_research.artifacts.papers.10.1145/3292500.title').
        tool_context: ADK ToolContext (auto-injected).

    Returns:
        dict: {"status": "success", "scope": scope, "path": path, "data": ...}
              or {"status": "error", "message": ...}
    """
    state, _, _ = await _resolve_project_state(tool_context)
    if state is None:
        return {
            "status": "error",
            "message": "No active project state found in context or storage.",
        }

    # Case 1: stage is provided
    if stage is not None or scope == "stage":
        target_stage_raw = stage or kwargs.get("target_stage")
        if not target_stage_raw:
            return {
                "status": "error",
                "message": "Parameter 'stage' must be provided when scope='stage'.",
            }
        try:
            norm_stage = normalize_stage_name(target_stage_raw)
        except Exception:
            return {
                "status": "error",
                "message": f"Invalid stage '{target_stage_raw}'. Must be one of: {sorted(list(VALID_STAGES))}",
            }
        if norm_stage not in VALID_STAGES or not hasattr(state, norm_stage):
            return {
                "status": "error",
                "message": f"Invalid stage '{target_stage_raw}'. Must be one of: {sorted(list(VALID_STAGES))}",
            }

        substate = getattr(state, norm_stage)
        if path:
            # If path doesn't start with stage name, prefix it
            if path.startswith(norm_stage + "."):
                query_path = path
            elif path.startswith("stage_"):
                query_path = path
            else:
                query_path = f"{norm_stage}.{path}"
            try:
                val = state.get_by_dot_path(query_path)
                val_dump = _dump_json_safe(val)
                return {
                    "status": "success",
                    "scope": scope,
                    "stage": norm_stage,
                    "path": path,
                    "data": val_dump,
                }
            except Exception as e:
                return {
                    "status": "error",
                    "message": f"Dot-path resolution failed for path '{query_path}': {e}",
                    "path": path,
                }
        else:
            return {
                "status": "success",
                "scope": scope if scope != "summary" else "stage",
                "stage": norm_stage,
                "path": path,
                "data": substate.model_dump(mode="json"),
            }

    # Case 2: path is provided (without stage)
    if path is not None or scope == "path":
        if not path:
            return {
                "status": "error",
                "message": "Parameter 'path' is required when scope='path'.",
            }
        try:
            val = state.get_by_dot_path(path)
            val_dump = _dump_json_safe(val)
            return {
                "status": "success",
                "scope": scope if scope != "summary" else "path",
                "path": path,
                "data": val_dump,
            }
        except Exception as e:
            return {
                "status": "error",
                "message": f"Dot-path resolution failed for path '{path}': {e}",
                "path": path,
            }

    # Case 3: scope == "all" or "full"
    if scope in ("all", "full"):
        return {
            "status": "success",
            "scope": scope,
            "path": None,
            "data": state.model_dump(mode="json"),
        }

    # Case 4: scope == "summary" (default)
    if scope == "summary":
        summary = state.get_summary()
        summary["unacknowledged_messages_count"] = sum(
            1 for m in state.message_board if not m.acknowledged_by
        )
        return {
            "status": "success",
            "scope": "summary",
            "path": None,
            "data": summary,
        }

    return {
        "status": "error",
        "message": f"Unknown scope '{scope}'. Supported scopes: 'summary', 'stage', 'path', 'all'.",
    }


# ---------------------------------------------------------------------------
# Tool 2: post_to_message_board (R4 Public Message Board Publishing)
# ---------------------------------------------------------------------------

async def post_to_message_board(
    message_type: str,
    title: str,
    content: str,
    stage: str | None = None,
    tags: list[str] | None = None,
    related_paper_dois: list[str] | None = None,
    author: str | None = None,
    author_agent: str | None = None,
    relevant_dois: list[str] | None = None,
    classification: str | None = None,
    metadata: dict[str, Any] | None = None,
    tool_context: ToolContext | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Publish a cross-cutting discovery or decision to the shared public message board.

    Args:
        message_type: Message classification: 'insight', 'serendipity', 'gap', 'warning', 'decision', 'hypothesis'.
        title: Short descriptive headline.
        content: Detailed markdown explanation of discovery.
        stage: Workflow stage identifier or 'global'.
        tags: Optional categorical keywords.
        related_paper_dois: Optional academic DOIs (will be canonically normalized).
        author: Optional author agent name.
        author_agent: Alias for author.
        relevant_dois: Alias for related_paper_dois.
        classification: Alias for message_type.
        metadata: Optional metadata dictionary.
        tool_context: ADK ToolContext (auto-injected).

    Returns:
        dict: {"status": "success", "message_id": ..., "message": ...}
              or {"status": "error", "message": ...}
    """
    effective_msg_type = message_type or classification or kwargs.get("classification")
    msg_type_clean = str(effective_msg_type).strip().lower() if effective_msg_type else ""
    if msg_type_clean not in VALID_MESSAGE_TYPES:
        return {
            "status": "error",
            "message": (
                f"Invalid message_type '{effective_msg_type}'. Must be one of: "
                f"{sorted(list(VALID_MESSAGE_TYPES))}"
            ),
        }

    state, detected_agent, original_was_dict = await _resolve_project_state(tool_context)
    if state is None:
        return {
            "status": "error",
            "message": "No active project state found in context or storage.",
        }

    post_author = author or author_agent or kwargs.get("author") or kwargs.get("author_agent") or detected_agent or "system"
    effective_stage = stage.strip() if stage and stage.strip() else "global"

    cleaned_dois: list[str] = []
    raw_dois = related_paper_dois or relevant_dois or kwargs.get("relevant_dois")
    if raw_dois:
        for d in raw_dois:
            n = normalize_doi(str(d))
            if n:
                cleaned_dois.append(n)

    post_metadata = metadata if metadata is not None else kwargs.get("metadata", {})

    try:
        msg = state.post_message(
            author_agent=post_author,
            message_type=msg_type_clean,
            title=title.strip(),
            content=content.strip(),
            stage=effective_stage,
            tags=tags or [],
            related_paper_dois=cleaned_dois,
            metadata=post_metadata,
        )
        _sync_project_state(state, tool_context, original_was_dict)
        return {
            "status": "success",
            "message_id": msg.id,
            "message": msg.model_dump(mode="json"),
        }
    except Exception as e:
        logger.error("post_to_message_board failed: %s", e, exc_info=True)
        return {"status": "error", "message": f"Failed to post to message board: {str(e)}"}


# ---------------------------------------------------------------------------
# Tool 3: read_message_board (R4 Public Message Board Filtering)
# ---------------------------------------------------------------------------

async def read_message_board(
    message_type: str | None = None,
    stage: str | None = None,
    tag: str | None = None,
    paper_doi: str | None = None,
    unacknowledged_only: bool = False,
    limit: int = 50,
    mark_as_acknowledged: bool = False,
    unacknowledged_by: str | None = None,
    classification: str | None = None,
    doi: str | None = None,
    tool_context: ToolContext | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Query and filter public message board entries across multiple facets.

    Args:
        message_type: Filter by classification: 'insight', 'serendipity', 'gap', 'warning', 'decision', 'hypothesis'.
        stage: Filter by originating workflow stage name.
        tag: Filter by keyword tag.
        paper_doi: Filter by referenced academic DOI (normalized).
        unacknowledged_only: If True, only returns messages not yet acknowledged.
        limit: Maximum number of messages to return (default: 50).
        mark_as_acknowledged: If True, marks returned messages as acknowledged by calling agent.
        unacknowledged_by: Specific agent to check acknowledgment for.
        classification: Alias for message_type.
        doi: Alias for paper_doi.
        tool_context: ADK ToolContext (auto-injected).

    Returns:
        dict: {"status": "success", "count": ..., "messages": [...]}
              or {"status": "error", "message": ...}
    """
    state, detected_agent, original_was_dict = await _resolve_project_state(tool_context)
    if state is None:
        return {
            "status": "error",
            "message": "No active project state found in context or storage.",
        }

    # Handle aliases
    filter_type = message_type or classification or kwargs.get("classification")
    filter_doi = paper_doi or doi or kwargs.get("doi")

    # Normalize tag / tags filter (both string and list/tuple inputs accepted)
    raw_tags: list[str] = []
    if tag is not None:
        if isinstance(tag, (list, tuple, set)):
            raw_tags.extend(str(t).strip() for t in tag if str(t).strip())
        elif isinstance(tag, str) and tag.strip():
            raw_tags.append(tag.strip())
        elif tag:
            raw_tags.append(str(tag).strip())

    tags_kwarg = kwargs.get("tags")
    if tags_kwarg is not None:
        if isinstance(tags_kwarg, (list, tuple, set)):
            raw_tags.extend(str(t).strip() for t in tags_kwarg if str(t).strip())
        elif isinstance(tags_kwarg, str) and tags_kwarg.strip():
            raw_tags.append(tags_kwarg.strip())
        elif tags_kwarg:
            raw_tags.append(str(tags_kwarg).strip())

    filtered = list(state.message_board)

    if filter_type:
        ft_clean = str(filter_type).strip().lower()
        filtered = [m for m in filtered if m.message_type == ft_clean]

    if stage:
        st_clean = str(stage).strip().lower()
        try:
            norm_st = normalize_stage_name(st_clean)
        except Exception:
            norm_st = st_clean
        filtered = [
            m for m in filtered
            if m.stage.lower() == st_clean or m.stage.lower() == norm_st
        ]

    if raw_tags:
        clean_tags = [t.lower() for t in raw_tags]
        filtered = [
            m for m in filtered
            if any(
                ct == t.lower() or ct in t.lower()
                for t in m.tags
                for ct in clean_tags
            )
        ]

    if filter_doi:
        norm_doi = normalize_doi(str(filter_doi))
        filtered = [
            m for m in filtered
            if norm_doi in m.related_paper_dois
        ]

    if unacknowledged_only:
        effective_unack_by = unacknowledged_by or kwargs.get("unacknowledged_by")
        if effective_unack_by:
            filtered = [m for m in filtered if not m.is_acknowledged_by(effective_unack_by)]
        elif detected_agent and detected_agent not in ("system", "agent"):
            filtered = [m for m in filtered if not m.is_acknowledged_by(detected_agent)]
        else:
            filtered = [m for m in filtered if len(m.acknowledged_by) == 0]

    # Apply limit slicing BEFORE acknowledgment loop so only returned messages are marked
    if limit is not None and limit > 0:
        results = filtered[-limit:]
    else:
        results = filtered

    # Handle mark_as_acknowledged if requested (scoped strictly to returned results)
    mark_as_ack = mark_as_acknowledged or kwargs.get("mark_as_acknowledged", False)
    if mark_as_ack and detected_agent:
        mutated = False
        for m in results:
            if not m.is_acknowledged_by(detected_agent):
                m.acknowledge(detected_agent)
                mutated = True
        if mutated:
            state.touch()
            _sync_project_state(state, tool_context, original_was_dict)

    return {
        "status": "success",
        "count": len(results),
        "messages": [m.model_dump(mode="json") for m in results],
    }


# ---------------------------------------------------------------------------
# Tool 4: update_stage_substate (R4 Scoped Mutation with Deep Merge & Validation)
# ---------------------------------------------------------------------------

async def update_stage_substate(
    stage: str,
    quadrant: str,
    data: dict[str, Any],
    tool_context: ToolContext | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Scoped mutation for an agent's stage substate quadrant with deep-merging and validation.

    Args:
        stage: Workflow stage ('stage_1_research' through 'stage_5_export').
        quadrant: Quadrant to update: 'meta', 'inputs', 'artifacts', or 'notes'.
        data: Dictionary of fields to update/merge into the quadrant.
        tool_context: ADK ToolContext (auto-injected).

    Returns:
        dict: {"status": "success", "stage": stage, "quadrant": quadrant, "data": ...}
              or {"status": "error", "message": ...}
    """
    try:
        norm_stage = normalize_stage_name(stage)
    except Exception:
        return {
            "status": "error",
            "message": (
                f"Invalid stage '{stage}'. Must be one of: "
                f"{sorted(list(VALID_STAGES))}"
            ),
        }
    if norm_stage not in VALID_STAGES:
        return {
            "status": "error",
            "message": (
                f"Invalid stage '{stage}'. Must be one of: "
                f"{sorted(list(VALID_STAGES))}"
            ),
        }

    q_clean = str(quadrant).strip().lower() if quadrant else ""
    if q_clean not in VALID_QUADRANTS:
        return {
            "status": "error",
            "message": (
                f"Invalid quadrant '{quadrant}'. Must be one of: "
                f"{sorted(list(VALID_QUADRANTS))}"
            ),
        }

    state, detected_agent, original_was_dict = await _resolve_project_state(tool_context)
    if state is None:
        return {
            "status": "error",
            "message": "No active project state found in context or storage.",
        }

    if q_clean == "notes":
        if not isinstance(data, (dict, list, str)):
            return {
                "status": "error",
                "message": f"Data for notes quadrant must be a dict, list, or str, got {type(data).__name__}",
            }
    else:
        if not isinstance(data, (dict, list)):
            return {
                "status": "error",
                "message": f"Data for quadrant mutation must be a dict (or list for notes), got {type(data).__name__}",
            }

    substate = getattr(state, norm_stage)

    # 1. Notes quadrant mutation
    if q_clean == "notes":
        if isinstance(data, str):
            items = [{"content": data, "author": detected_agent or "system"}]
        elif isinstance(data, list):
            items = data
        elif isinstance(data, dict):
            if "notes" in data and isinstance(data["notes"], list):
                items = data["notes"]
            elif "content" in data:
                items = [data]
            elif "note" in data:
                items = [{"content": str(data["note"]), "author": detected_agent or "system"}]
            else:
                items = [{"author": k, "content": str(v)} for k, v in data.items()]
        else:
            return {
                "status": "error",
                "message": f"Invalid data for notes quadrant: {type(data).__name__}",
            }

        try:
            for item in items:
                if isinstance(item, StageNote):
                    substate.notes.append(item)
                elif isinstance(item, dict):
                    item_dict = dict(item)
                    if "content" not in item_dict and "note" in item_dict:
                        item_dict["content"] = str(item_dict.pop("note"))
                    if "author" not in item_dict:
                        item_dict["author"] = detected_agent or "system"
                    substate.notes.append(StageNote.model_validate(item_dict))
                elif isinstance(item, str):
                    substate.notes.append(
                        StageNote(author=detected_agent or "system", content=item)
                    )
                else:
                    return {
                        "status": "error",
                        "message": f"Cannot parse note item of type {type(item).__name__}",
                    }
        except ValidationError as val_err:
            return {
                "status": "error",
                "message": f"Validation failed for {norm_stage}.notes: {val_err}",
            }
        except Exception as err:
            return {
                "status": "error",
                "message": f"Error updating {norm_stage}.notes: {err}",
            }

        substate.meta.updated_at = utc_now()
        state.touch()
        _sync_project_state(state, tool_context, original_was_dict)

        return {
            "status": "success",
            "stage": norm_stage,
            "quadrant": q_clean,
            "data": [n.model_dump(mode="json") for n in substate.notes],
        }

    # 2. Meta, Inputs, Artifacts quadrant mutation with deep-merge and validation
    if not isinstance(data, dict):
        return {
            "status": "error",
            "message": f"Data for quadrant '{q_clean}' must be a dict, got {type(data).__name__}",
        }

    target_quadrant = getattr(substate, q_clean)
    current_dict = target_quadrant.model_dump(mode="python")
    deep_merge(current_dict, data)

    model_cls = type(target_quadrant)
    try:
        validated_quadrant = model_cls.model_validate(current_dict)
    except ValidationError as val_err:
        return {
            "status": "error",
            "message": f"Validation failed for {norm_stage}.{q_clean}: {val_err}",
        }
    except Exception as err:
        return {
            "status": "error",
            "message": f"Error validating {norm_stage}.{q_clean}: {err}",
        }

    setattr(substate, q_clean, validated_quadrant)
    substate.meta.updated_at = utc_now()
    state.touch()
    _sync_project_state(state, tool_context, original_was_dict)

    return {
        "status": "success",
        "stage": norm_stage,
        "quadrant": q_clean,
        "data": validated_quadrant.model_dump(mode="json"),
    }

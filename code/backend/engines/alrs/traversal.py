"""Multi-seed fair frontier scheduling and E-UCB task selection for GraphSelect.

Ported from archive commit 865cd08 (`code/backend/alrs_tool/search/multi_frontier.py`
and `code/backend/alrs_tool/search/epistemic_pagerank.py`).
"""

from __future__ import annotations

import json
from typing import Literal
from uuid import UUID, uuid4, uuid5

from pydantic import BaseModel, ConfigDict, Field, field_validator

from engines.openalex import OpenAlexWork, normalize_doi

from .epistemic_pagerank import is_expansion_blocked
from .ranking import PaperRanking

MULTI_PAGE_SIZE = 5


class DiscoveryStartingPaper(BaseModel):
    model_config = ConfigDict(extra="forbid")

    doi: str = Field(min_length=6, max_length=512)
    candidate_id: str = Field(default="seed", min_length=1)
    title: str = Field(default="Seed Paper", min_length=1)

    @field_validator("doi")
    @classmethod
    def validate_doi(cls, value: str) -> str:
        return normalize_doi(value)


class TraversalTask(BaseModel):
    task_id: str = ""
    origin_doi: str = ""
    lane_index: int = 0
    parent_doi: str
    parent_work_id: str
    depth: int
    direction: Literal["references", "citations"]
    reference_ids: list[str] = Field(default_factory=list)
    cursor: str = "*"


class DiscoveryFrontierState(BaseModel):
    run_id: UUID = Field(default_factory=uuid4)
    seed_doi: str = ""
    starting_papers: list[DiscoveryStartingPaper] = Field(default_factory=list)
    traversal_tasks: list[TraversalTask] = Field(default_factory=list)
    expanded_dois: list[str] = Field(default_factory=list)
    completed_task_ids: list[str] = Field(default_factory=list)
    last_lane_index: int = -1


def task_identity(run_id: UUID, task: TraversalTask) -> str:
    contents = [
        task.origin_doi,
        task.parent_doi,
        task.direction,
        task.depth,
        task.cursor,
        task.reference_ids,
    ]
    identity = uuid5(run_id, json.dumps(contents, separators=(",", ":")))
    return f"multi-task-{identity}"


def root_receipt_id(run_id: UUID, doi: str) -> str:
    return f"multi-root-{uuid5(run_id, doi)}"


def expansion_tasks(
    run_id: UUID,
    work: OpenAlexWork,
    origin_doi: str,
    depth: int,
    roots: list[str],
) -> list[TraversalTask]:
    if work.id is None or work.doi is None:
        return []
    lane_index = roots.index(origin_doi)
    references = list(dict.fromkeys(work.referenced_works))
    tasks = [
        TraversalTask(
            origin_doi=origin_doi,
            lane_index=lane_index,
            parent_doi=work.doi,
            parent_work_id=work.id,
            depth=depth,
            direction="references",
            reference_ids=references[index : index + MULTI_PAGE_SIZE],
        )
        for index in range(0, len(references), MULTI_PAGE_SIZE)
    ]
    tasks.append(
        TraversalTask(
            origin_doi=origin_doi,
            lane_index=lane_index + len(roots),
            parent_doi=work.doi,
            parent_work_id=work.id,
            depth=depth,
            direction="citations",
        )
    )
    return [task.model_copy(update={"task_id": task_identity(run_id, task)}) for task in tasks]


def select_fair_task(
    state: DiscoveryFrontierState,
    eligible: set[str],
) -> tuple[TraversalTask | None, list[str]]:
    completed = set(state.completed_task_ids)
    roots = {paper.doi for paper in state.starting_papers}
    if not roots and state.seed_doi:
        roots = {state.seed_doi}
    pending: list[TraversalTask] = []
    for task in state.traversal_tasks:
        if task.task_id in completed:
            continue
        if task.parent_doi not in roots and task.parent_doi not in eligible:
            completed.add(task.task_id)
        else:
            pending.append(task)
    if not pending:
        return None, sorted(completed)
    depth = min(task.depth for task in pending)
    at_depth = [task for task in pending if task.depth == depth]
    lanes = sorted({task.lane_index for task in at_depth})
    following = [lane for lane in lanes if lane > state.last_lane_index]
    lane = following[0] if following else lanes[0]
    return next(task for task in at_depth if task.lane_index == lane), sorted(completed)


def select_epistemic_frontier_task(
    state: DiscoveryFrontierState,
    eligible: set[str],
    rankings: list[PaperRanking] | None = None,
) -> tuple[TraversalTask | None, list[str]]:
    """Select the next frontier task using BFS depth fairness and E-UCB priority."""
    completed = set(state.completed_task_ids)
    roots = {paper.doi for paper in state.starting_papers}
    if not roots and state.seed_doi:
        roots = {state.seed_doi}
    ranking_map = {item.paper_key: item for item in (rankings or [])}
    pruned_dois = {
        item.paper_key
        for item in (rankings or [])
        if is_expansion_blocked(item, item.researcher_steering)
    }
    pending: list[TraversalTask] = []
    for task in state.traversal_tasks:
        if task.task_id in completed:
            continue
        if task.parent_doi in pruned_dois or (
            task.parent_doi not in roots and task.parent_doi not in eligible
        ):
            completed.add(task.task_id)
        else:
            pending.append(task)
    if not pending:
        return None, sorted(completed)
    min_depth = min(task.depth for task in pending)
    at_depth = [task for task in pending if task.depth == min_depth]
    prioritized = sorted(
        at_depth,
        key=lambda item: (
            -(ranking_map[item.parent_doi].ucb_frontier_priority or 0.0)
            * (0.85 ** max(0, item.depth - 1))
            if item.parent_doi in ranking_map
            else 0.0,
            item.lane_index,
        ),
    )
    return prioritized[0], sorted(completed)


def append_cursor_task(
    state: DiscoveryFrontierState,
    task: TraversalTask,
    next_cursor: str | None,
) -> tuple[list[TraversalTask], list[str]]:
    tasks = list(state.traversal_tasks)
    if task.direction != "citations" or not next_cursor:
        return tasks, []
    continuation = task.model_copy(update={"cursor": next_cursor})
    continuation.task_id = task_identity(state.run_id, continuation)
    if any(item.task_id == continuation.task_id for item in tasks):
        return tasks, ["citation_cursor_cycle"]
    tasks.append(continuation)
    return tasks, []


def extend_multi_frontier(
    state: DiscoveryFrontierState,
    task: TraversalTask,
    works: list[OpenAlexWork],
    saved_dois: set[str],
    eligible: set[str],
    next_cursor: str | None,
    max_depth: int,
) -> tuple[list[TraversalTask], list[str], list[str]]:
    tasks, reasons = append_cursor_task(state, task, next_cursor)
    expanded = list(state.expanded_dois)
    if task.depth >= max_depth:
        return tasks, expanded, reasons
    roots = [paper.doi for paper in state.starting_papers] or ([state.seed_doi] if state.seed_doi else [])
    for work in works:
        doi = work.doi
        if doi is None or doi not in saved_dois or doi in expanded:
            continue
        if doi not in eligible and doi not in roots:
            continue
        tasks.extend(expansion_tasks(state.run_id, work, task.origin_doi, task.depth + 1, roots))
        expanded.append(doi)
    return tasks, expanded, reasons

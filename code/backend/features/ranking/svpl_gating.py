"""Strict Necessity Gating for SVPL Multi-Hop Bridge Traversal (FR-015).

Complies with Constitution v2.2.1:
- C7: Strict static typing without bare signatures.
- C9: Granular functions under 25 lines with Single Responsibility.
- C10: Early return guard clauses over nested logic.
- C11: Domain abstraction and predicate booleans.
"""
from __future__ import annotations

import logging
from typing import Union

from core.errors.enhancement_errors import MultiHopUnauthorizedError
from features.ranking.svpl_models import MultiHopAuthorization, MultiHopTriggerReason

logger = logging.getLogger(__name__)

AUTHORIZED_TRIGGERS: frozenset[MultiHopTriggerReason] = frozenset({
    MultiHopTriggerReason.EXPLICIT_USER_DIRECTIVE,
    MultiHopTriggerReason.EMPTY_GAP_REMEDIATION,
})


def parse_trigger_reason(
    trigger_input: Union[MultiHopAuthorization, MultiHopTriggerReason, str],
) -> MultiHopTriggerReason:
    """Extract and validate MultiHopTriggerReason enum from input."""
    if isinstance(trigger_input, MultiHopAuthorization):
        return trigger_input.trigger_reason
    if isinstance(trigger_input, MultiHopTriggerReason):
        return trigger_input
    if isinstance(trigger_input, str):
        try:
            return MultiHopTriggerReason(trigger_input.strip().lower())
        except ValueError:
            raise MultiHopUnauthorizedError(
                f"MULTIHOP_UNAUTHORIZED: Unrecognized trigger reason '{trigger_input}'."
            )
    raise MultiHopUnauthorizedError("MULTIHOP_UNAUTHORIZED: Invalid trigger payload.")


def is_multihop_authorized(
    trigger_input: Union[MultiHopAuthorization, MultiHopTriggerReason, str],
    candidate_count: int = 0,
) -> bool:
    """Evaluate whether multi-hop discovery is authorized under FR-015."""
    if isinstance(trigger_input, MultiHopAuthorization) and not trigger_input.is_authorized:
        return False
    try:
        reason = parse_trigger_reason(trigger_input)
    except MultiHopUnauthorizedError:
        return False

    if reason == MultiHopTriggerReason.EXPLICIT_USER_DIRECTIVE:
        return True
    if reason == MultiHopTriggerReason.EMPTY_GAP_REMEDIATION:
        return candidate_count == 0
    return False


def validate_gap_remediation_candidate_count(
    reason: MultiHopTriggerReason,
    candidate_count: int,
) -> None:
    """Assert that empty_gap_remediation triggers only execute when candidates are 0."""
    if reason == MultiHopTriggerReason.EMPTY_GAP_REMEDIATION and candidate_count > 0:
        raise MultiHopUnauthorizedError(
            "MULTIHOP_UNAUTHORIZED: Multi-hop discovery during gap remediation "
            f"is permitted strictly when candidates are exhausted (N=0, got N={candidate_count})."
        )


def check_multihop_authorization(
    auth: Union[MultiHopAuthorization, MultiHopTriggerReason, str],
    candidate_count: int = 0,
) -> None:
    """Enforce FR-015: raises MultiHopUnauthorizedError if unauthorized.

    Only permitted for:
    1. MultiHopTriggerReason.EXPLICIT_USER_DIRECTIVE
    2. MultiHopTriggerReason.EMPTY_GAP_REMEDIATION (with candidate_count == 0)
    """
    if isinstance(auth, MultiHopAuthorization) and not auth.is_authorized:
        raise MultiHopUnauthorizedError(
            "MULTIHOP_UNAUTHORIZED: Authorization denied or explicit token revoked."
        )

    reason = parse_trigger_reason(auth)
    if reason not in AUTHORIZED_TRIGGERS:
        raise MultiHopUnauthorizedError(
            f"MULTIHOP_UNAUTHORIZED: Multi-hop discovery is forbidden for trigger '{reason.value}'. "
            "Routine crawler or general discovery calls are blocked per FR-015."
        )

    validate_gap_remediation_candidate_count(reason, candidate_count)
    logger.info("Multi-hop authorization verified: trigger=%s, candidate_count=%d", reason.value, candidate_count)

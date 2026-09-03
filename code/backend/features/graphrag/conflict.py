"""Append-only conflict resolution state machine and epistemic status calculator.

Preserves academic debate: contradictory empirical findings do not overwrite
the central Fact, but are linked via Proof nodes with CONTRADICTED_BY edges.
The epistemic status of the Fact is dynamically computed based on cumulative
evidentiary weights.
"""
from __future__ import annotations

import logging
import math
from typing import Any
from features.graphrag.models import FactStatus, RelationshipType

logger = logging.getLogger(__name__)

# Minimum length for mandatory rich-text relationship descriptions
MIN_DESCRIPTION_LENGTH = 5

ALLOWED_RELATIONSHIP_TYPES = {rel.value for rel in RelationshipType}


class EpistemicIntegrityError(ValueError):
    """Raised when an operation attempts to destructively mutate fact history."""
    pass


class InvalidRelationshipError(ValueError):
    """Raised when an invalid relationship type or missing description is provided."""
    pass


def validate_rich_description(description: str, min_length: int = MIN_DESCRIPTION_LENGTH) -> None:
    """Ensure that relationship descriptions provide genuine semantic nuance."""
    if not description or not isinstance(description, str):
        raise InvalidRelationshipError("Relationship description is mandatory and must be a non-empty string.")
    cleaned = description.strip()
    if len(cleaned) < min_length:
        raise InvalidRelationshipError(
            f"Relationship description must have at least {min_length} characters of rich-text explanation. Got: '{cleaned}'"
        )


def validate_relationship_type(rel_type: str) -> str:
    """Normalize and validate that the relationship type belongs to the defined schema."""
    norm = rel_type.strip().upper()
    if norm not in ALLOWED_RELATIONSHIP_TYPES:
        raise InvalidRelationshipError(
            f"Unknown relationship type '{rel_type}'. Allowed types: {sorted(ALLOWED_RELATIONSHIP_TYPES)}"
        )
    return norm


def calculate_epistemic_status(
    connected_proofs: list[dict[str, Any]],
) -> tuple[FactStatus, float]:
    """Calculate dynamic epistemic status and confidence score from connected proofs.
    
    Args:
        connected_proofs: List of dictionaries representing attached proofs and edge types.
            Expected keys: 'rel_type' (SUPPORTED_BY or CONTRADICTED_BY),
                           'confidence' (float), and optional proof metadata.

    Returns:
        tuple[FactStatus, float]: (new_status, confidence_score)
    """
    if not connected_proofs:
        return FactStatus.TENTATIVE, 0.5

    w_sup = 0.0
    w_con = 0.0
    count_sup = 0
    count_con = 0

    for item in connected_proofs:
        rel = item.get("rel_type") or item.get("type") or ""
        conf = float(item.get("confidence") or 0.8)
        conf = max(0.0, min(1.0, conf))

        if rel == RelationshipType.SUPPORTED_BY.value or rel.lower() == "supported_by":
            w_sup += conf
            count_sup += 1
        elif rel == RelationshipType.CONTRADICTED_BY.value or rel.lower() == "contradicted_by":
            w_con += conf
            count_con += 1

    total_weight = w_sup + w_con
    if total_weight <= 0.0:
        return FactStatus.TENTATIVE, 0.5

    # 1. Both supporting and contradicting evidence exist -> DEBATED
    if count_sup > 0 and count_con > 0:
        # Confidence reflects the ratio of support to total debate weight
        conf_score = round(w_sup / total_weight, 3)
        return FactStatus.DEBATED, conf_score

    # 2. Only supporting evidence exists -> SUPPORTED or CONSENSUS
    if count_sup > 0 and count_con == 0:
        # High consensus threshold: at least 3 independent proofs and strong cumulative weight
        if count_sup >= 3 and w_sup >= 2.4:
            conf_score = min(0.99, round(0.85 + 0.03 * count_sup, 3))
            return FactStatus.CONSENSUS, conf_score
        conf_score = min(0.95, round(0.60 + 0.10 * count_sup, 3))
        return FactStatus.SUPPORTED, conf_score

    # 3. Only contradicting evidence exists -> REFUTED
    if count_con > 0 and count_sup == 0:
        # Confidence in the original statement drops towards 0.0
        conf_score = max(0.05, round(0.5 / (1.0 + w_con), 3))
        return FactStatus.REFUTED, conf_score

    return FactStatus.TENTATIVE, 0.5


def verify_append_only_transition(
    previous_statement: str,
    incoming_statement: str,
) -> None:
    """Verify that an update to a Fact does not destructively overwrite its statement."""
    if previous_statement and incoming_statement:
        if previous_statement.strip().lower() != incoming_statement.strip().lower():
            raise EpistemicIntegrityError(
                f"Destructive fact overwrite detected. Previous statement: '{previous_statement}'. "
                f"Attempted overwrite: '{incoming_statement}'. Contradictory claims must be added as "
                f"Proof nodes with CONTRADICTED_BY edges rather than mutating existing facts."
            )


def validate_edge_confidence(confidence: float, clamp: bool = False) -> float:
    """Validate and clamp edge confidence float to [0.0, 1.0].

    Args:
        confidence: Floating point confidence score.
        clamp: If True, clamp finite floats outside [0.0, 1.0] to bounds.
               If False, raise ValueError for floats outside [0.0, 1.0].

    Returns:
        float: Validated (and optionally clamped) confidence score in [0.0, 1.0].

    Raises:
        ValueError: If confidence is NaN, Infinite, or out of range when clamp=False.
    """
    if confidence is None:
        return 0.8
    try:
        val = float(confidence)
    except (TypeError, ValueError) as err:
        raise ValueError(f"Confidence score must be a valid float. Got: {confidence}") from err

    if math.isnan(val) or math.isinf(val):
        raise ValueError(f"Confidence score cannot be NaN or Infinite. Got: {val}")

    if clamp:
        return max(0.0, min(1.0, val))

    if not (0.0 <= val <= 1.0):
        raise ValueError(f"Confidence score must be within [0.0, 1.0]. Got: {val}")

    return val

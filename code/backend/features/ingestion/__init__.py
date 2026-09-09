"""Continuous Ingestion feature module.

Exports Pydantic v2 domain models and contracts for chat-driven paper ingestion.
"""
from __future__ import annotations

from features.ingestion.models import (
    ConfirmTitleIngestionInput,
    ConfirmTitleIngestionOutput,
    IdentifierType,
    IngestUserPaperInput,
    IngestUserPaperOutput,
    IngestionSource,
    TitleConfirmationChip,
    UserIngestedPaper,
)

__all__ = [
    "ConfirmTitleIngestionInput",
    "ConfirmTitleIngestionOutput",
    "IdentifierType",
    "IngestUserPaperInput",
    "IngestUserPaperOutput",
    "IngestionSource",
    "TitleConfirmationChip",
    "UserIngestedPaper",
]

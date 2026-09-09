"""Export package for ALRS v2."""
from __future__ import annotations

from typing import Any

from features.export.presentation_models import (
    PresentationDeckRequest,
    PresentationDeckResponse,
    PresentationErrorCode,
)

__all__ = [
    "PresentationService",
    "PresentationDeckRequest",
    "PresentationDeckResponse",
    "PresentationErrorCode",
]


def __getattr__(name: str) -> Any:
    if name == "PresentationService":
        from features.export.presentation_service import PresentationService
        return PresentationService
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

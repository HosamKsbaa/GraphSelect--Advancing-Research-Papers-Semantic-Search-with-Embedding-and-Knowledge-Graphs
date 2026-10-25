"""OpenAlex engine: bounded, budget-accounted access to OpenAlex works.

Public API. Import from `engines.openalex`, never from its internal modules.
Ported from the audited archive (`alrs_tool/clients/`, commit 865cd08).
"""

from engines.errors import ProviderError
from engines.openalex.budget import ProviderBudget
from engines.openalex.models import OpenAlexWork, OpenAlexWorkPage, normalize_doi, normalize_work_id
from engines.openalex.rate_limiter import AsyncTokenBucketRateLimiter
from engines.openalex.service import (
    MissingDoiError,
    OpenAlexClient,
    reconstruct_abstract,
    to_paper_create,
)

__all__ = [
    "AsyncTokenBucketRateLimiter",
    "MissingDoiError",
    "OpenAlexClient",
    "OpenAlexWork",
    "OpenAlexWorkPage",
    "ProviderBudget",
    "ProviderError",
    "normalize_doi",
    "normalize_work_id",
    "reconstruct_abstract",
    "to_paper_create",
]

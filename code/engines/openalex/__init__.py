"""OpenAlex engine: bounded, budget-accounted access to OpenAlex works.

Public API. Import from `engines.openalex`, never from its internal modules.
Ported from the audited archive (`alrs_tool/clients/`, commit 865cd08).
"""

from engines.openalex.budget import ProviderBudget, ProviderError
from engines.openalex.models import OpenAlexWork, OpenAlexWorkPage, normalize_doi, normalize_work_id
from engines.openalex.rate_limiter import AsyncTokenBucketRateLimiter
from engines.openalex.service import MissingDoiError, OpenAlexClient, reconstruct_abstract

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
]

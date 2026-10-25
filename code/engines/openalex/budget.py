"""Account for provider requests before issuing external work."""

import time
from collections.abc import Awaitable, Callable

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr


UsageCallback = Callable[[int, float], Awaitable[None]]
RetryCallback = Callable[[int], Awaitable[None]]


class ProviderError(RuntimeError):
    """A sanitized provider failure suitable for saved research events."""

    def __init__(self, code: str, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


class ProviderBudget(BaseModel):
    """Cumulative limits; restore usage when resuming a workflow node."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    max_requests: int = Field(default=5, ge=1)
    max_seconds: float = Field(default=30.0, gt=0)
    max_retries: int = Field(default=2, ge=0, le=2)
    requests_used: int = Field(default=0, ge=0)
    retries_used: int = Field(default=0, ge=0)
    active_seconds: float = Field(default=0.0, ge=0)
    on_attempt: UsageCallback | None = Field(default=None, exclude=True, repr=False)
    on_usage: UsageCallback | None = Field(default=None, exclude=True, repr=False)
    on_retry: RetryCallback | None = Field(default=None, exclude=True, repr=False)
    _last_accounted_at: float = PrivateAttr(default_factory=time.monotonic)
    _accounting_active: bool = PrivateAttr(default=True)

    def record_elapsed(self) -> None:
        now = time.monotonic()
        if self._accounting_active:
            self.active_seconds += max(0.0, now - self._last_accounted_at)
        self._last_accounted_at = now

    def pause_accounting(self) -> None:
        """Model reasoning is bounded separately from provider-active execution."""
        self.record_elapsed()
        self._accounting_active = False

    def resume_accounting(self) -> None:
        self._last_accounted_at = time.monotonic()
        self._accounting_active = True

    def remaining_seconds(self) -> float:
        self.record_elapsed()
        remaining = self.max_seconds - self.active_seconds
        if remaining <= 0:
            raise ProviderError("time_limit", "The provider active-time limit was reached.")
        return remaining

    def check_request_available(self) -> None:
        if self.requests_used >= self.max_requests:
            raise ProviderError("request_limit", "The provider request limit was reached.")

    async def reserve_request(self) -> None:
        self.check_request_available()
        self.remaining_seconds()
        self.requests_used += 1
        if self.on_attempt is not None:
            await self.on_attempt(self.requests_used, self.active_seconds)

    async def persist_usage(self) -> None:
        self.record_elapsed()
        if self.on_usage is not None:
            await self.on_usage(self.requests_used, self.active_seconds)

    async def reserve_retry(self) -> None:
        self.retries_used += 1
        if self.on_retry is not None:
            await self.on_retry(self.retries_used)

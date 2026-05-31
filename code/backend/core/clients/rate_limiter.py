from __future__ import annotations
import asyncio
import logging
import time

logger = logging.getLogger(__name__)


class AdaptiveRateLimiter:
    """Adaptive token-bucket rate limiter with 429 backoff."""

    def __init__(
        self,
        initial_rate: float = 9.0,
        min_rate: float = 0.5,
        recovery_increment: float = 0.5,
    ) -> None:
        self._initial_rate = initial_rate
        self._current_rate = initial_rate
        self._min_rate = min_rate
        self._recovery_increment = recovery_increment
        self._lock = asyncio.Lock()
        self._last_request_time: float = 0.0
        self._tokens: float = initial_rate
        self._last_refill: float = time.monotonic()

    @property
    def current_rate(self) -> float:
        return self._current_rate

    async def acquire(self) -> None:
        """Wait until a token is available, then consume it."""
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_refill
            self._tokens = min(
                self._current_rate,
                self._tokens + elapsed * self._current_rate,
            )
            self._last_refill = now

            if self._tokens < 1.0:
                wait_time = (1.0 - self._tokens) / self._current_rate
                await asyncio.sleep(wait_time)
                self._tokens = 0.0
                self._last_refill = time.monotonic()
            else:
                self._tokens -= 1.0

    def on_429(self) -> float:
        """Halve the rate on HTTP 429. Returns the new rate."""
        old_rate = self._current_rate
        self._current_rate = max(self._min_rate, self._current_rate / 2.0)
        logger.warning(
            'Rate limited (429). Rate: %.1f -> %.1f req/s',
            old_rate, self._current_rate,
        )
        return self._current_rate

    def on_success(self) -> float:
        """Slowly recover rate after successful requests. Returns current rate."""
        if self._current_rate < self._initial_rate:
            self._current_rate = min(
                self._initial_rate,
                self._current_rate + self._recovery_increment,
            )
        return self._current_rate

    def reset(self) -> None:
        """Reset rate to initial value."""
        self._current_rate = self._initial_rate
        self._tokens = self._initial_rate
        self._last_refill = time.monotonic()

"""Async Token Bucket Rate Limiter for academic provider APIs."""

import asyncio
import time
from typing import Optional


class AsyncTokenBucketRateLimiter:
    """Thread-safe and async-safe token bucket rate limiter."""

    def __init__(self, rate: float = 10.0, capacity: float = 10.0):
        self.rate = rate
        self.capacity = capacity
        self.tokens = capacity
        self.last_update = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self.last_update
            self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
            self.last_update = now

            if self.tokens < 1.0:
                needed = (1.0 - self.tokens) / self.rate
                await asyncio.sleep(needed)
                self.tokens = 0.0
                self.last_update = time.monotonic()
            else:
                self.tokens -= 1.0

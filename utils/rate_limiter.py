"""
Rate Limiter Module
Implements token bucket rate limiting with exponential backoff for Polymarket API
"""

import asyncio
import time
from typing import Optional, Callable, Any
from dataclasses import dataclass, field
from collections import deque
from loguru import logger


@dataclass
class RateLimitState:
    """Current rate limit state"""
    tokens: float
    last_update: float
    backoff_until: float = 0.0
    consecutive_errors: int = 0


class TokenBucketRateLimiter:
    """
    Token bucket rate limiter with burst support

    Features:
    - Configurable rate and burst limits
    - Exponential backoff on rate limit errors
    - Async-first design
    - Per-endpoint tracking
    """

    def __init__(
        self,
        rate_per_second: float = 10.0,
        burst_limit: int = 20,
        backoff_base: float = 1.0,
        backoff_max: float = 60.0
    ):
        """
        Initialize rate limiter

        Args:
            rate_per_second: Tokens refilled per second
            burst_limit: Maximum tokens in bucket
            backoff_base: Base backoff time in seconds
            backoff_max: Maximum backoff time in seconds
        """
        self.rate = rate_per_second
        self.burst = burst_limit
        self.backoff_base = backoff_base
        self.backoff_max = backoff_max

        self._state = RateLimitState(
            tokens=float(burst_limit),
            last_update=time.monotonic()
        )
        self._lock = asyncio.Lock()

        # Request timing history for monitoring
        self._request_times: deque = deque(maxlen=100)

    def _refill_tokens(self) -> None:
        """Refill tokens based on elapsed time"""
        now = time.monotonic()
        elapsed = now - self._state.last_update
        self._state.tokens = min(
            self.burst,
            self._state.tokens + elapsed * self.rate
        )
        self._state.last_update = now

    async def acquire(self, tokens: int = 1) -> float:
        """
        Acquire tokens, waiting if necessary

        Args:
            tokens: Number of tokens to acquire

        Returns:
            Wait time in seconds (0 if no wait needed)
        """
        async with self._lock:
            # Check if we're in backoff
            now = time.monotonic()
            if self._state.backoff_until > now:
                wait_time = self._state.backoff_until - now
                logger.debug(f"Rate limiter in backoff, waiting {wait_time:.2f}s")
                await asyncio.sleep(wait_time)
                now = time.monotonic()

            # Refill tokens
            self._refill_tokens()

            # Calculate wait time if not enough tokens
            wait_time = 0.0
            if self._state.tokens < tokens:
                tokens_needed = tokens - self._state.tokens
                wait_time = tokens_needed / self.rate
                logger.debug(f"Rate limiter waiting {wait_time:.2f}s for {tokens} tokens")
                await asyncio.sleep(wait_time)
                self._refill_tokens()

            # Consume tokens
            self._state.tokens -= tokens
            self._request_times.append(time.monotonic())

            return wait_time

    async def on_rate_limit_error(self) -> None:
        """Handle rate limit error with exponential backoff"""
        async with self._lock:
            self._state.consecutive_errors += 1
            backoff = min(
                self.backoff_base * (2 ** (self._state.consecutive_errors - 1)),
                self.backoff_max
            )
            self._state.backoff_until = time.monotonic() + backoff
            self._state.tokens = 0  # Drain bucket on error

            logger.warning(
                f"Rate limit hit, backing off for {backoff:.1f}s "
                f"(attempt {self._state.consecutive_errors})"
            )

    async def on_success(self) -> None:
        """Reset error count on successful request"""
        async with self._lock:
            if self._state.consecutive_errors > 0:
                self._state.consecutive_errors = 0
                logger.debug("Rate limiter error count reset")

    @property
    def current_rate(self) -> float:
        """Calculate current request rate over last 100 requests"""
        if len(self._request_times) < 2:
            return 0.0
        elapsed = self._request_times[-1] - self._request_times[0]
        if elapsed == 0:
            return 0.0
        return len(self._request_times) / elapsed

    @property
    def available_tokens(self) -> float:
        """Get currently available tokens"""
        return self._state.tokens

    def is_throttled(self) -> bool:
        """Check if currently in backoff"""
        return time.monotonic() < self._state.backoff_until


class MultiEndpointRateLimiter:
    """
    Rate limiter that tracks multiple endpoints separately

    Polymarket has different rate limits for:
    - Orders: 2400/10s (~240/s)
    - General API: 100/s
    - WebSocket: No explicit limit
    """

    def __init__(self):
        self.limiters = {
            "orders": TokenBucketRateLimiter(
                rate_per_second=200.0,  # Conservative: 200/s vs 240/s limit
                burst_limit=50,
                backoff_base=1.0,
                backoff_max=30.0
            ),
            "api": TokenBucketRateLimiter(
                rate_per_second=50.0,  # Conservative: 50/s vs 100/s limit
                burst_limit=20,
                backoff_base=0.5,
                backoff_max=30.0
            ),
            "gamma": TokenBucketRateLimiter(
                rate_per_second=10.0,  # Gamma API is typically slower
                burst_limit=10,
                backoff_base=1.0,
                backoff_max=60.0
            ),
        }

    async def acquire(self, endpoint: str = "api", tokens: int = 1) -> float:
        """Acquire tokens for specific endpoint"""
        limiter = self.limiters.get(endpoint, self.limiters["api"])
        return await limiter.acquire(tokens)

    async def on_rate_limit_error(self, endpoint: str = "api") -> None:
        """Handle rate limit error for specific endpoint"""
        limiter = self.limiters.get(endpoint, self.limiters["api"])
        await limiter.on_rate_limit_error()

    async def on_success(self, endpoint: str = "api") -> None:
        """Reset error count for specific endpoint"""
        limiter = self.limiters.get(endpoint, self.limiters["api"])
        await limiter.on_success()

    def get_stats(self) -> dict:
        """Get rate limiter statistics"""
        return {
            name: {
                "available_tokens": limiter.available_tokens,
                "current_rate": limiter.current_rate,
                "is_throttled": limiter.is_throttled()
            }
            for name, limiter in self.limiters.items()
        }


def rate_limited(
    endpoint: str = "api",
    tokens: int = 1,
    rate_limiter: Optional[MultiEndpointRateLimiter] = None
):
    """
    Decorator for rate-limited async functions

    Usage:
        @rate_limited("orders")
        async def place_order(...):
            ...
    """
    def decorator(func: Callable) -> Callable:
        async def wrapper(*args, **kwargs) -> Any:
            limiter = rate_limiter or _global_rate_limiter
            await limiter.acquire(endpoint, tokens)

            try:
                result = await func(*args, **kwargs)
                await limiter.on_success(endpoint)
                return result
            except Exception as e:
                # Check if this is a rate limit error
                error_str = str(e).lower()
                if "rate" in error_str or "429" in error_str or "too many" in error_str:
                    await limiter.on_rate_limit_error(endpoint)
                raise

        return wrapper
    return decorator


# Global rate limiter instance
_global_rate_limiter = MultiEndpointRateLimiter()


def get_rate_limiter() -> MultiEndpointRateLimiter:
    """Get global rate limiter instance"""
    return _global_rate_limiter

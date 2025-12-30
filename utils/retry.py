"""
Retry Logic Module
Implements exponential backoff retry for API calls
"""

import asyncio
import functools
from typing import Callable, TypeVar, Any, Tuple, Type
from loguru import logger
import random

T = TypeVar('T')


class RetryError(Exception):
    """Raised when all retry attempts fail"""
    def __init__(self, message: str, last_exception: Exception = None):
        super().__init__(message)
        self.last_exception = last_exception


def exponential_backoff(
    attempt: int,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    jitter: bool = True
) -> float:
    """
    Calculate delay with exponential backoff

    Args:
        attempt: Current attempt number (0-based)
        base_delay: Base delay in seconds
        max_delay: Maximum delay cap
        jitter: Add random jitter

    Returns:
        Delay in seconds
    """
    delay = base_delay * (2 ** attempt)
    delay = min(delay, max_delay)

    if jitter:
        # Add +/- 25% jitter
        jitter_range = delay * 0.25
        delay += random.uniform(-jitter_range, jitter_range)

    return max(0, delay)


def retry(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    on_retry: Callable[[int, Exception], None] = None
):
    """
    Decorator for synchronous retry with exponential backoff

    Args:
        max_attempts: Maximum retry attempts
        base_delay: Base delay between retries
        max_delay: Maximum delay cap
        exceptions: Tuple of exceptions to catch
        on_retry: Callback on retry (attempt, exception)

    Usage:
        @retry(max_attempts=3, base_delay=1.0)
        def api_call():
            ...
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> T:
            last_exception = None

            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    remaining = max_attempts - attempt - 1

                    if remaining > 0:
                        delay = exponential_backoff(attempt, base_delay, max_delay)
                        logger.warning(
                            f"Retry {attempt + 1}/{max_attempts} for {func.__name__}: "
                            f"{e}. Waiting {delay:.1f}s..."
                        )

                        if on_retry:
                            on_retry(attempt + 1, e)

                        import time
                        time.sleep(delay)
                    else:
                        logger.error(
                            f"All {max_attempts} attempts failed for {func.__name__}: {e}"
                        )

            raise RetryError(
                f"Failed after {max_attempts} attempts",
                last_exception
            )

        return wrapper
    return decorator


def async_retry(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    on_retry: Callable[[int, Exception], None] = None
):
    """
    Decorator for async retry with exponential backoff

    Args:
        max_attempts: Maximum retry attempts
        base_delay: Base delay between retries
        max_delay: Maximum delay cap
        exceptions: Tuple of exceptions to catch
        on_retry: Callback on retry (attempt, exception)

    Usage:
        @async_retry(max_attempts=3)
        async def async_api_call():
            ...
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            last_exception = None

            for attempt in range(max_attempts):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    remaining = max_attempts - attempt - 1

                    if remaining > 0:
                        delay = exponential_backoff(attempt, base_delay, max_delay)
                        logger.warning(
                            f"Async retry {attempt + 1}/{max_attempts} for {func.__name__}: "
                            f"{e}. Waiting {delay:.1f}s..."
                        )

                        if on_retry:
                            on_retry(attempt + 1, e)

                        await asyncio.sleep(delay)
                    else:
                        logger.error(
                            f"All {max_attempts} attempts failed for {func.__name__}: {e}"
                        )

            raise RetryError(
                f"Failed after {max_attempts} attempts",
                last_exception
            )

        return wrapper
    return decorator


class RetryContext:
    """
    Context manager for retry logic

    Usage:
        async with RetryContext(max_attempts=3) as ctx:
            while ctx.should_retry():
                try:
                    result = await risky_operation()
                    break
                except Exception as e:
                    await ctx.handle_error(e)
    """

    def __init__(
        self,
        max_attempts: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        exceptions: Tuple[Type[Exception], ...] = (Exception,)
    ):
        self.max_attempts = max_attempts
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exceptions = exceptions
        self.attempt = 0
        self.last_exception = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

    def should_retry(self) -> bool:
        """Check if more retries are available"""
        return self.attempt < self.max_attempts

    async def handle_error(self, error: Exception):
        """
        Handle error and wait before retry

        Args:
            error: Exception that occurred

        Raises:
            RetryError: If max attempts exceeded
        """
        if not isinstance(error, self.exceptions):
            raise error

        self.last_exception = error
        self.attempt += 1

        if self.attempt >= self.max_attempts:
            raise RetryError(
                f"Failed after {self.max_attempts} attempts",
                self.last_exception
            )

        delay = exponential_backoff(self.attempt - 1, self.base_delay, self.max_delay)
        logger.warning(f"Retry {self.attempt}/{self.max_attempts}: {error}. Waiting {delay:.1f}s...")
        await asyncio.sleep(delay)


# Pre-configured retry decorators for common use cases
api_retry = retry(max_attempts=3, base_delay=1.0, max_delay=30.0)
ws_retry = async_retry(max_attempts=5, base_delay=2.0, max_delay=60.0)
order_retry = retry(max_attempts=2, base_delay=0.5, max_delay=5.0)

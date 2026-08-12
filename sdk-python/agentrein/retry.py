"""Retry logic with exponential backoff for HTTP requests."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, TypeVar

import httpx

T = TypeVar("T")


def default_retry_on(error: BaseException) -> bool:
    """Determine whether an error is retryable."""
    if isinstance(error, httpx.HTTPStatusError):
        return error.response.status_code >= 500
    if isinstance(error, httpx.RequestError):
        return True

    err_msg = str(error).lower()
    return any(sub in err_msg for sub in ("refused", "timeout", "failed to fetch", "network"))


@dataclass
class RetryOptions:
    """Configuration options for retrying operations with backoff."""

    max_attempts: int = 3
    base_delay_ms: int = 500
    max_delay_ms: int = 8000
    retry_on: Callable[[BaseException], bool] | None = None


def retry_with_backoff(
    fn: Callable[[], T],
    options: RetryOptions | None = None,
) -> T:
    """Execute a function, retrying with exponential backoff if it fails."""
    opts = options or RetryOptions()
    max_attempts = opts.max_attempts
    base_delay_ms = opts.base_delay_ms
    max_delay_ms = opts.max_delay_ms
    retry_on = opts.retry_on or default_retry_on

    attempt = 0
    while True:
        attempt += 1
        try:
            return fn()
        except BaseException as error:
            if attempt >= max_attempts or not retry_on(error):
                raise
            delay_ms = min(base_delay_ms * (2**attempt), max_delay_ms)
            time.sleep(delay_ms / 1000.0)

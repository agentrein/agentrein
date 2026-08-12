"""Connector retry logic with idempotency key handling."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Callable, Generic, TypeVar

T = TypeVar("T")

NETWORK_ERROR_KEYWORDS = [
    "timeout",
    "econnrefused",
    "econnreset",
    "network",
    "etimedout",
    "enotfound",
    "failed to fetch",
]


def extract_status_code(error: BaseException) -> int | None:
    """Extract HTTP status code from various connector SDK error shapes."""
    # 1. StripeError.http_status
    http_status = getattr(error, "http_status", None)
    if isinstance(http_status, int):
        return http_status

    # 2. GithubException.status, SalesforceError.status
    status = getattr(error, "status", None)
    if isinstance(status, int):
        return status

    # 3. httpx-based custom clients status_code
    status_code = getattr(error, "status_code", None)
    if isinstance(status_code, int):
        return status_code

    # 4. Nested response object (httpx, slack_sdk)
    response = getattr(error, "response", None)
    if response is not None:
        # httpx.Response-like status_code
        resp_status_code = getattr(response, "status_code", None)
        if isinstance(resp_status_code, int):
            return resp_status_code
        # slack_sdk dict-like status
        try:
            resp_status = response["status"]
            if isinstance(resp_status, int):
                return resp_status
            if isinstance(resp_status, str) and resp_status.isdigit():
                return int(resp_status)
        except (TypeError, KeyError, IndexError):
            pass

    # 5. Google API client legacy shape (googleapiclient.errors.HttpError.resp.status)
    resp = getattr(error, "resp", None)
    if resp is not None:
        resp_status = getattr(resp, "status", None)
        if isinstance(resp_status, int):
            return resp_status
        if isinstance(resp_status, str) and resp_status.isdigit():
            return int(resp_status)

    return None


def is_transient_connector_error(error: BaseException) -> bool:
    """Determine if a connector error is transient and should be retried."""
    status = extract_status_code(error)
    if status is not None:
        return status >= 500
    return any(keyword in str(error).lower() for keyword in NETWORK_ERROR_KEYWORDS)


@dataclass(frozen=True)
class ConnectorRetryResult(Generic[T]):
    """Result of a retried connector call."""

    result: T
    retry_count: int
    idempotency_key: str


def retry_connector_call(fn: Callable[[str], T]) -> ConnectorRetryResult[T]:
    """Retry a connector call with a generated idempotency key and exponential delays."""
    idempotency_key = str(uuid.uuid4())
    max_attempts = 3
    delays = [0.5, 1.0, 2.0]

    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            result = fn(idempotency_key)
            return ConnectorRetryResult(
                result=result,
                retry_count=attempt - 1,
                idempotency_key=idempotency_key,
            )
        except Exception as error:
            last_error = error
            if attempt == max_attempts or not is_transient_connector_error(error):
                raise
            time.sleep(delays[attempt - 1])

    if last_error is not None:
        raise last_error
    raise RuntimeError("Unreachable")

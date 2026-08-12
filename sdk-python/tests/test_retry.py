from __future__ import annotations

import httpx
import pytest
from pytest_mock import MockerFixture

from agentrein.retry import RetryOptions, default_retry_on, retry_with_backoff


def test_default_retry_on() -> None:
    request = httpx.Request("GET", "https://example.com")
    response_500 = httpx.Response(500, request=request)
    err_500 = httpx.HTTPStatusError("500 Internal Server Error", request=request, response=response_500)
    assert default_retry_on(err_500) is True

    response_400 = httpx.Response(400, request=request)
    err_400 = httpx.HTTPStatusError("400 Bad Request", request=request, response=response_400)
    assert default_retry_on(err_400) is False

    err_req = httpx.RequestError("Connection failed", request=request)
    assert default_retry_on(err_req) is True

    err_refused = ValueError("connection refused by peer")
    assert default_retry_on(err_refused) is True

    err_timeout = ValueError("read timeout expired")
    assert default_retry_on(err_timeout) is True

    err_other = ValueError("invalid value passed")
    assert default_retry_on(err_other) is False


def test_retry_with_backoff_success() -> None:
    call_count = 0

    def fn() -> str:
        nonlocal call_count
        call_count += 1
        return "success"

    res = retry_with_backoff(fn)
    assert res == "success"
    assert call_count == 1


def test_retry_with_backoff_eventual_success(mocker: MockerFixture) -> None:
    mock_sleep = mocker.patch("time.sleep")
    call_count = 0

    def fn() -> str:
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise httpx.RequestError("Temporary failure", request=httpx.Request("GET", "https://example.com"))
        return "success"

    res = retry_with_backoff(fn, RetryOptions(max_attempts=3, base_delay_ms=100))
    assert res == "success"
    assert call_count == 3

    assert mock_sleep.call_count == 2
    mock_sleep.assert_any_call(0.2)
    mock_sleep.assert_any_call(0.4)


def test_retry_with_backoff_max_attempts_exceeded(mocker: MockerFixture) -> None:
    mock_sleep = mocker.patch("time.sleep")
    call_count = 0

    def fn() -> str:
        nonlocal call_count
        call_count += 1
        raise httpx.RequestError("Persistent failure", request=httpx.Request("GET", "https://example.com"))

    with pytest.raises(httpx.RequestError) as exc_info:
        retry_with_backoff(fn, RetryOptions(max_attempts=3))

    assert "Persistent failure" in str(exc_info.value)
    assert call_count == 3
    assert mock_sleep.call_count == 2


def test_retry_with_backoff_no_retry_on_non_retryable(mocker: MockerFixture) -> None:
    mock_sleep = mocker.patch("time.sleep")
    call_count = 0

    def fn() -> str:
        nonlocal call_count
        call_count += 1
        raise ValueError("Invalid user input")

    with pytest.raises(ValueError) as exc_info:
        retry_with_backoff(fn)

    assert "Invalid user input" in str(exc_info.value)
    assert call_count == 1
    assert mock_sleep.call_count == 0

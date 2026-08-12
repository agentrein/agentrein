from __future__ import annotations

import pytest
from pytest_mock import MockerFixture

from agentrein.connector_retry import (
    ConnectorRetryResult,
    extract_status_code,
    is_transient_connector_error,
    retry_connector_call,
)


class DummyException(Exception):
    pass


def test_extract_status_code_stripe() -> None:
    exc = DummyException()
    exc.http_status = 400  # type: ignore[attr-defined]
    assert extract_status_code(exc) == 400


def test_extract_status_code_github() -> None:
    exc = DummyException()
    exc.status = 403  # type: ignore[attr-defined]
    assert extract_status_code(exc) == 403


def test_extract_status_code_custom() -> None:
    exc = DummyException()
    exc.status_code = 502  # type: ignore[attr-defined]
    assert extract_status_code(exc) == 502


def test_extract_status_code_nested_response_obj() -> None:
    class DummyResponse:
        def __init__(self, status_code: int) -> None:
            self.status_code = status_code

    exc = DummyException()
    exc.response = DummyResponse(500)  # type: ignore[attr-defined]
    assert extract_status_code(exc) == 500


def test_extract_status_code_nested_response_dict() -> None:
    exc = DummyException()
    exc.response = {"status": 404}  # type: ignore[attr-defined]
    assert extract_status_code(exc) == 404

    exc2 = DummyException()
    exc2.response = {"status": "503"}  # type: ignore[attr-defined]
    assert extract_status_code(exc2) == 503


def test_extract_status_code_nested_response_invalid_dict() -> None:
    exc = DummyException()
    # Not dict-like or missing 'status'
    exc.response = [1, 2, 3]  # type: ignore[attr-defined]
    assert extract_status_code(exc) is None


def test_extract_status_code_google_legacy() -> None:
    class DummyResp:
        def __init__(self, status: str | int) -> None:
            self.status = status

    exc = DummyException()
    exc.resp = DummyResp("504")  # type: ignore[attr-defined]
    assert extract_status_code(exc) == 504

    exc2 = DummyException()
    exc2.resp = DummyResp(500)  # type: ignore[attr-defined]
    assert extract_status_code(exc2) == 500


def test_extract_status_code_none() -> None:
    exc = DummyException("Some message")
    assert extract_status_code(exc) is None


def test_is_transient_connector_error() -> None:
    # With status code
    exc_500 = DummyException()
    exc_500.status_code = 500  # type: ignore[attr-defined]
    assert is_transient_connector_error(exc_500) is True

    exc_400 = DummyException()
    exc_400.status_code = 400  # type: ignore[attr-defined]
    assert is_transient_connector_error(exc_400) is False

    # Without status code, with keyword
    exc_timeout = DummyException("Request connection timeout")
    assert is_transient_connector_error(exc_timeout) is True

    # Without status code, without keyword
    exc_normal = DummyException("Invalid parameter value")
    assert is_transient_connector_error(exc_normal) is False


def test_retry_connector_call_success() -> None:
    call_keys: list[str] = []

    def fn(idempotency_key: str) -> str:
        call_keys.append(idempotency_key)
        return "ok"

    res = retry_connector_call(fn)
    assert isinstance(res, ConnectorRetryResult)
    assert res.result == "ok"
    assert res.retry_count == 0
    assert len(res.idempotency_key) > 0
    assert call_keys == [res.idempotency_key]


def test_retry_connector_call_eventual_success(mocker: MockerFixture) -> None:
    mock_sleep = mocker.patch("time.sleep")
    call_keys: list[str] = []

    def fn(idempotency_key: str) -> str:
        call_keys.append(idempotency_key)
        if len(call_keys) < 3:
            exc = DummyException()
            exc.status_code = 503  # type: ignore[attr-defined]
            raise exc
        return "eventual ok"

    res = retry_connector_call(fn)
    assert res.result == "eventual ok"
    assert res.retry_count == 2
    assert len(call_keys) == 3
    # Same idempotency key used across all attempts
    assert len(set(call_keys)) == 1
    assert call_keys[0] == res.idempotency_key

    # Check delays
    assert mock_sleep.call_count == 2
    mock_sleep.assert_any_call(0.5)
    mock_sleep.assert_any_call(1.0)


def test_retry_connector_call_fatal_error(mocker: MockerFixture) -> None:
    mock_sleep = mocker.patch("time.sleep")
    call_count = 0

    def fn(idempotency_key: str) -> str:
        nonlocal call_count
        call_count += 1
        exc = DummyException("Fatal bad request")
        exc.status_code = 400  # type: ignore[attr-defined]
        raise exc

    with pytest.raises(DummyException):
        retry_connector_call(fn)

    assert call_count == 1
    assert mock_sleep.call_count == 0


def test_retry_connector_call_max_attempts_exceeded(mocker: MockerFixture) -> None:
    mock_sleep = mocker.patch("time.sleep")
    call_count = 0

    def fn(idempotency_key: str) -> str:
        nonlocal call_count
        call_count += 1
        exc = DummyException("Transient error")
        exc.status_code = 500  # type: ignore[attr-defined]
        raise exc

    with pytest.raises(DummyException):
        retry_connector_call(fn)

    assert call_count == 3
    assert mock_sleep.call_count == 2

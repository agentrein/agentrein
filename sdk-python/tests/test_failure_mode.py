"""Tests for SDK failureMode Option A behavior across status codes and error paths."""

import httpx
import pytest
from unittest.mock import Mock

from agentrein import AgentRein, Session
from agentrein.errors import AgentReinDeniedError, AgentReinUnavailableError


def make_session(is_sandbox: bool = False) -> Session:
    return Session(
        id="sess_test_123",
        organization_id="org_test_123",
        agent_id="test-agent",
        intent="test intent",
        status="ACTIVE",
        is_sandbox=is_sandbox,
        created_at="2026-10-25T00:00:00Z",
        updated_at="2026-10-25T00:00:00Z",
    )


def make_http_error(status_code: int, type_slug: str = "policy-blocked", detail: str = "Blocked by policy") -> httpx.HTTPStatusError:
    req = httpx.Request("POST", "https://api.agentrein.com/test")
    resp = httpx.Response(
        status_code=status_code,
        request=req,
        json={"error": {"type": f"https://agentrein.com/errors/{type_slug}", "title": "Denied", "status": status_code, "detail": detail}},
    )
    return httpx.HTTPStatusError(message=f"HTTP {status_code}", request=req, response=resp)


@pytest.mark.parametrize("status_code", [401, 403, 409, 429])
@pytest.mark.parametrize("failure_mode", ["open", "closed"])
def test_approval_gated_server_decision_raises_and_never_executes_target(
    status_code: int, failure_mode: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = AgentRein(api_key="ar_test_key", failure_mode=failure_mode)  # type: ignore[arg-type]
    monkeypatch.setattr(client, "_get_token", lambda: "mock_token")

    def mock_post(*args, **kwargs):
        raise make_http_error(status_code, "policy-blocked", "Action denied")

    monkeypatch.setattr(client._http, "post", mock_post)

    target_func = Mock(return_value="executed")
    dummy_vendor = Mock()
    dummy_vendor.delete_item = target_func

    wrapped = client.wrap(
        dummy_vendor,
        make_session(),
        connector="stripe",
        requires_approval=["delete_item"],
    )

    with pytest.raises(AgentReinDeniedError) as exc_info:
        wrapped.delete_item(id="item_1")

    assert exc_info.value.status == status_code
    assert target_func.call_count == 0, "Target vendor function must NEVER execute without approval"


@pytest.mark.parametrize("status_code", [500, 503])
def test_approval_gated_5xx_open_mode_falls_open(
    status_code: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = AgentRein(api_key="ar_test_key", failure_mode="open")
    monkeypatch.setattr(client, "_get_token", lambda: "mock_token")

    def mock_post(*args, **kwargs):
        raise make_http_error(status_code, "internal-error", "Server outage")

    monkeypatch.setattr(client._http, "post", mock_post)

    target_func = Mock(return_value="executed_fall_open")
    dummy_vendor = Mock()
    dummy_vendor.delete_item = target_func

    wrapped = client.wrap(
        dummy_vendor,
        make_session(),
        connector="stripe",
        requires_approval=["delete_item"],
    )

    res = wrapped.delete_item(id="item_1")
    assert res == "executed_fall_open"
    assert target_func.call_count == 1


@pytest.mark.parametrize("status_code", [401, 403, 409, 429])
@pytest.mark.parametrize("failure_mode", ["open", "closed"])
def test_standard_path_server_decision_raises_denied_error(
    status_code: int, failure_mode: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = AgentRein(api_key="ar_test_key", failure_mode=failure_mode)  # type: ignore[arg-type]
    monkeypatch.setattr(client, "_get_token", lambda: "mock_token")

    def mock_post(*args, **kwargs):
        raise make_http_error(status_code, "policy-blocked", "Action post-check denied")

    monkeypatch.setattr(client._http, "post", mock_post)

    dummy_vendor = Mock()
    dummy_vendor.send_message = Mock(return_value="ok")

    wrapped = client.wrap(
        dummy_vendor,
        make_session(),
        connector="slack",
    )

    with pytest.raises(AgentReinDeniedError) as exc_info:
        wrapped.send_message(channel="C123", text="hello")

    assert exc_info.value.status == status_code


@pytest.mark.parametrize("status_code", [401, 403, 409, 429])
@pytest.mark.parametrize("failure_mode", ["open", "closed"])
def test_rollback_session_server_decision_raises(
    status_code: int, failure_mode: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = AgentRein(api_key="ar_test_key", failure_mode=failure_mode)  # type: ignore[arg-type]
    monkeypatch.setattr(client, "_get_token", lambda: "mock_token")

    def mock_post(*args, **kwargs):
        raise make_http_error(status_code, "plan-required", "Plan upgrade needed")

    monkeypatch.setattr(client._http, "post", mock_post)

    with pytest.raises(AgentReinDeniedError) as exc_info:
        client.rollback_session(make_session())

    assert exc_info.value.status == status_code


@pytest.mark.parametrize("status_code", [401, 403, 409, 429])
@pytest.mark.parametrize("failure_mode", ["open", "closed"])
def test_new_session_server_decision_raises(
    status_code: int, failure_mode: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = AgentRein(api_key="ar_test_key", failure_mode=failure_mode)  # type: ignore[arg-type]
    monkeypatch.setattr(client, "_get_token", lambda: "mock_token")

    def mock_post(*args, **kwargs):
        raise make_http_error(status_code, "quota-exceeded", "Monthly quota exceeded")

    monkeypatch.setattr(client._http, "post", mock_post)

    with pytest.raises(AgentReinDeniedError) as exc_info:
        client.new_session(agent_id="test-agent")

    assert exc_info.value.status == status_code


@pytest.mark.parametrize("status_code", [401, 403, 409, 429])
@pytest.mark.parametrize("failure_mode", ["open", "closed"])
def test_complete_session_server_decision_raises(
    status_code: int, failure_mode: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = AgentRein(api_key="ar_test_key", failure_mode=failure_mode)  # type: ignore[arg-type]
    monkeypatch.setattr(client, "_get_token", lambda: "mock_token")

    def mock_patch(*args, **kwargs):
        raise make_http_error(status_code, "session-conflict", "Session in invalid state")

    monkeypatch.setattr(client._http, "patch", mock_patch)

    with pytest.raises(AgentReinDeniedError) as exc_info:
        client.complete_session(make_session())

    assert exc_info.value.status == status_code


def test_complete_session_5xx_open_logs_warning(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    client = AgentRein(api_key="ar_test_key", failure_mode="open")
    monkeypatch.setattr(client, "_get_token", lambda: "mock_token")

    def mock_patch(*args, **kwargs):
        raise make_http_error(500, "internal-error", "Database down")

    monkeypatch.setattr(client._http, "patch", mock_patch)

    with caplog.at_level("WARNING"):
        client.complete_session(make_session())

    assert "Failed to complete session" in caplog.text


def test_rollback_session_5xx_open_logs_warning(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    client = AgentRein(api_key="ar_test_key", failure_mode="open")
    monkeypatch.setattr(client, "_get_token", lambda: "mock_token")

    def mock_post(*args, **kwargs):
        raise make_http_error(503, "unavailable", "Redis down")

    monkeypatch.setattr(client._http, "post", mock_post)

    with caplog.at_level("WARNING"):
        client.rollback_session(make_session())

    assert "Failed to rollback session" in caplog.text


@pytest.mark.parametrize("status_code", [401, 403, 409, 429])
def test_sandbox_server_decision_raises(
    status_code: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = AgentRein(api_key="ar_test_key", failure_mode="open")
    monkeypatch.setattr(client, "_get_token", lambda: "mock_token")

    def mock_post(*args, **kwargs):
        raise make_http_error(status_code, "policy-blocked", "Denied in sandbox")

    monkeypatch.setattr(client._http, "post", mock_post)

    vendor = Mock()
    vendor.query_data = Mock(return_value="data")

    wrapped = client.wrap(
        vendor,
        make_session(is_sandbox=True),
        connector="postgres",
    )

    with pytest.raises(AgentReinDeniedError) as exc_info:
        wrapped.query_data(query="SELECT 1")

    assert exc_info.value.status == status_code


def test_new_session_agent_paused_raises_denied_error(monkeypatch: pytest.MonkeyPatch) -> None:
    client = AgentRein(api_key="ar_test_key", failure_mode="open")
    monkeypatch.setattr(client, "_get_token", lambda: "mock_token")

    def mock_post(url: str, *args, **kwargs):
        if url.endswith("/sessions"):
            raise make_http_error(403, "agent-paused", 'Agent "paused-agent" is paused')
        return httpx.Response(status_code=200, request=httpx.Request("POST", url), json={"data": {}})

    monkeypatch.setattr(client._http, "post", mock_post)

    with pytest.raises(AgentReinDeniedError) as exc_info:
        client.new_session(agent_id="paused-agent")

    assert exc_info.value.status == 403
    assert exc_info.value.error_type == "agent-paused"
    assert exc_info.value.detail == 'Agent "paused-agent" is paused'

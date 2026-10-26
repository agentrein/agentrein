"""Tests for Python SDK registry fetch and action precapture parity (SKI-24)."""

from unittest.mock import Mock
import httpx
import pytest

from agentrein import AgentRein, Session
from agentrein.errors import AgentReinDeniedError


def make_session() -> Session:
    return Session(
        id="sess_prec_123",
        organization_id="org_test_123",
        agent_id="test-agent",
        intent="test precapture",
        status="ACTIVE",
        is_sandbox=False,
        created_at="2026-10-25T00:00:00Z",
        updated_at="2026-10-25T00:00:00Z",
    )


def test_precapture_called_and_passed_to_action_logging(monkeypatch: pytest.MonkeyPatch) -> None:
    client = AgentRein(api_key="ar_test_key")
    monkeypatch.setattr(client, "_get_token", lambda: "mock_token")

    registry_called = False
    precapture_called = False
    log_action_payload = None

    def mock_get(url: str, *args, **kwargs):
        nonlocal registry_called
        if url.endswith("/registry"):
            registry_called = True
            return httpx.Response(
                status_code=200,
                request=httpx.Request("GET", url),
                json={"data": [{"apiName": "stripe.customers.update", "captureBeforeState": True}]},
            )
        return httpx.Response(status_code=200, request=httpx.Request("GET", url), json={"data": {}})

    def mock_post(url: str, *args, **kwargs):
        nonlocal precapture_called, log_action_payload
        if "/actions/precapture" in url:
            precapture_called = True
            return httpx.Response(
                status_code=200,
                request=httpx.Request("POST", url),
                json={"data": {"precaptureId": "snap_pre_abc123", "captureFailed": False}},
            )
        if "/actions" in url:
            log_action_payload = kwargs.get("json", {})
            return httpx.Response(
                status_code=200,
                request=httpx.Request("POST", url),
                json={"data": {"id": "act_123", "status": "SUCCESS"}},
            )
        return httpx.Response(status_code=200, request=httpx.Request("POST", url), json={"data": {}})

    monkeypatch.setattr(client._http, "get", mock_get)
    monkeypatch.setattr(client._http, "post", mock_post)

    vendor = Mock()
    vendor.update = Mock(return_value={"id": "cus_1", "email": "new@example.com"})

    wrapped = client.wrap(
        vendor,
        make_session(),
        connector="stripe.customers",
    )

    result = wrapped.update(id="cus_1", email="new@example.com")
    assert result == {"id": "cus_1", "email": "new@example.com"}

    assert precapture_called, "execute_precapture must be called before mutation"
    assert log_action_payload is not None
    assert log_action_payload.get("precaptureId") == "snap_pre_abc123"
    assert log_action_payload.get("captureFailed") is not True


def test_precapture_skipped_when_registry_specifies_false(monkeypatch: pytest.MonkeyPatch) -> None:
    client = AgentRein(api_key="ar_test_key")
    monkeypatch.setattr(client, "_get_token", lambda: "mock_token")

    precapture_called = False
    log_action_payload = None

    def mock_get(url: str, *args, **kwargs):
        if url.endswith("/registry"):
            return httpx.Response(
                status_code=200,
                request=httpx.Request("GET", url),
                json={"data": [{"apiName": "slack.messages.post", "captureBeforeState": False}]},
            )
        return httpx.Response(status_code=200, request=httpx.Request("GET", url), json={"data": {}})

    def mock_post(url: str, *args, **kwargs):
        nonlocal precapture_called, log_action_payload
        if "/actions/precapture" in url:
            precapture_called = True
            return httpx.Response(
                status_code=200,
                request=httpx.Request("POST", url),
                json={"data": {"precaptureId": "snap_999", "captureFailed": False}},
            )
        if "/actions" in url:
            log_action_payload = kwargs.get("json", {})
            return httpx.Response(
                status_code=200,
                request=httpx.Request("POST", url),
                json={"data": {"id": "act_123", "status": "SUCCESS"}},
            )
        return httpx.Response(status_code=200, request=httpx.Request("POST", url), json={"data": {}})

    monkeypatch.setattr(client._http, "get", mock_get)
    monkeypatch.setattr(client._http, "post", mock_post)

    vendor = Mock()
    vendor.post = Mock(return_value="sent")

    wrapped = client.wrap(
        vendor,
        make_session(),
        connector="slack.messages",
    )

    wrapped.post(text="hello")
    assert not precapture_called, "precapture should NOT be called when captureBeforeState is False"
    assert log_action_payload is not None
    assert "precaptureId" not in log_action_payload


def test_precapture_transient_failure_proceeds_with_capture_failed_true(monkeypatch: pytest.MonkeyPatch) -> None:
    client = AgentRein(api_key="ar_test_key")
    monkeypatch.setattr(client, "_get_token", lambda: "mock_token")

    log_action_payload = None

    def mock_get(url: str, *args, **kwargs):
        if url.endswith("/registry"):
            return httpx.Response(status_code=200, request=httpx.Request("GET", url), json={"data": [{"apiName": "stripe.customers.delete", "captureBeforeState": True}]})
        return httpx.Response(status_code=200, request=httpx.Request("GET", url), json={"data": {}})

    def mock_post(url: str, *args, **kwargs):
        nonlocal log_action_payload
        if "/actions/precapture" in url:
            raise httpx.HTTPError("Precapture service 500")
        if "/actions" in url:
            log_action_payload = kwargs.get("json", {})
            return httpx.Response(status_code=200, request=httpx.Request("POST", url), json={"data": {"id": "act_1", "status": "SUCCESS"}})
        return httpx.Response(status_code=200, request=httpx.Request("POST", url), json={"data": {}})

    monkeypatch.setattr(client._http, "get", mock_get)
    monkeypatch.setattr(client._http, "post", mock_post)

    vendor = Mock()
    vendor.delete = Mock(return_value={"deleted": True})

    wrapped = client.wrap(vendor, make_session(), connector="stripe.customers")
    res = wrapped.delete(id="cus_1")

    assert res == {"deleted": True}
    assert log_action_payload is not None
    assert log_action_payload.get("captureFailed") is True
    assert log_action_payload.get("precaptureId") is None


def test_precapture_server_decision_denied_raises_and_blocks_call(monkeypatch: pytest.MonkeyPatch) -> None:
    client = AgentRein(api_key="ar_test_key")
    monkeypatch.setattr(client, "_get_token", lambda: "mock_token")

    def mock_get(url: str, *args, **kwargs):
        return httpx.Response(status_code=200, request=httpx.Request("GET", url), json={"data": [{"apiName": "stripe.customers.delete", "captureBeforeState": True}]})

    def mock_post(url: str, *args, **kwargs):
        if "/actions/precapture" in url:
            req = httpx.Request("POST", url)
            resp = httpx.Response(status_code=403, request=req, json={"error": {"type": "https://agentrein.com/errors/policy-blocked", "title": "Blocked", "status": 403, "detail": "Precapture forbidden"}})
            raise httpx.HTTPStatusError("HTTP 403", request=req, response=resp)
        return httpx.Response(status_code=200, request=httpx.Request("POST", url), json={"data": {}})

    monkeypatch.setattr(client._http, "get", mock_get)
    monkeypatch.setattr(client._http, "post", mock_post)

    vendor = Mock()
    vendor.delete = Mock()

    wrapped = client.wrap(vendor, make_session(), connector="stripe.customers")

    with pytest.raises(AgentReinDeniedError) as exc_info:
        wrapped.delete(id="cus_1")

    assert exc_info.value.status == 403
    assert vendor.delete.call_count == 0


def test_approval_gate_includes_precapture_in_pending_approval(monkeypatch: pytest.MonkeyPatch) -> None:
    client = AgentRein(api_key="ar_test_key")
    monkeypatch.setattr(client, "_get_token", lambda: "mock_token")

    pending_body = None

    def mock_get(url: str, *args, **kwargs):
        if url.endswith("/registry"):
            return httpx.Response(status_code=200, request=httpx.Request("GET", url), json={"data": [{"apiName": "stripe.customers.delete", "captureBeforeState": True}]})
        if "/approvals/" in url:
            return httpx.Response(status_code=200, request=httpx.Request("GET", url), json={"data": {"status": "APPROVED"}})
        return httpx.Response(status_code=200, request=httpx.Request("GET", url), json={"data": {}})

    def mock_post(url: str, *args, **kwargs):
        nonlocal pending_body
        if "/actions/precapture" in url:
            return httpx.Response(status_code=200, request=httpx.Request("POST", url), json={"data": {"precaptureId": "snap_gate_789", "captureFailed": False}})
        if "/actions" in url:
            pending_body = kwargs.get("json", {})
            return httpx.Response(status_code=200, request=httpx.Request("POST", url), json={"data": {"id": "act_g1", "status": "PENDING_APPROVAL", "approvalRequest": {"id": "appr_1"}}})
        return httpx.Response(status_code=200, request=httpx.Request("POST", url), json={"data": {}})

    def mock_patch(url: str, *args, **kwargs):
        return httpx.Response(status_code=200, request=httpx.Request("PATCH", url), json={"data": {}})

    monkeypatch.setattr(client._http, "get", mock_get)
    monkeypatch.setattr(client._http, "post", mock_post)
    monkeypatch.setattr(client._http, "patch", mock_patch)

    vendor = Mock()
    vendor.delete = Mock(return_value={"deleted": True})

    wrapped = client.wrap(
        vendor,
        make_session(),
        connector="stripe.customers",
        requires_approval=["delete"],
    )

    wrapped.delete(id="cus_1")
    assert pending_body is not None
    assert pending_body.get("status") == "PENDING_APPROVAL"
    assert pending_body.get("precaptureId") == "snap_gate_789"

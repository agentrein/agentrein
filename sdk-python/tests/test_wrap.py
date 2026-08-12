from __future__ import annotations

from typing import Any

import httpx
import pytest
from pytest_mock import MockerFixture

from agentrein.client import AgentRein, Session
from agentrein.errors import (
    ApprovalRejectedError,
    WrapOptionsValidationError,
)
from agentrein.simulate_response import SimulatedResponse


class MockCharges:
    def create(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return {"id": "ch_123", "amount": 100}


class MockClient:
    def __init__(self) -> None:
        self.charges = MockCharges()


@pytest.fixture
def session() -> Session:
    return Session(
        id="session-123",
        organization_id="org-456",
        agent_id="agent-789",
        intent=None,
        status="ACTIVE",
        is_sandbox=False,
        created_at="2026-08-12T12:00:00Z",
        updated_at="2026-08-12T12:00:00Z",
    )


@pytest.fixture
def sandbox_session() -> Session:
    return Session(
        id="session-123",
        organization_id="org-456",
        agent_id="agent-789",
        intent=None,
        status="ACTIVE",
        is_sandbox=True,
        created_at="2026-08-12T12:00:00Z",
        updated_at="2026-08-12T12:00:00Z",
    )


def test_wrap_options_validation() -> None:
    client = AgentRein(api_key="key")
    session = Session(
        id="s-1",
        organization_id="o-1",
        agent_id="a-1",
        intent=None,
        status="ACTIVE",
        is_sandbox=False,
        created_at="now",
        updated_at="now",
    )
    dummy = MockClient()

    with pytest.raises(WrapOptionsValidationError) as exc_info:
        client.wrap(dummy, session, connector="")
    assert "connector must be a non-empty string" in str(exc_info.value)

    with pytest.raises(WrapOptionsValidationError) as exc_info:
        client.wrap(dummy, session, connector="stripe", poll_interval_ms=500)
    assert "poll_interval_ms must be >= 1000ms" in str(exc_info.value)

    with pytest.raises(WrapOptionsValidationError) as exc_info:
        client.wrap(dummy, session, connector="stripe", timeout_ms=4000)
    assert "timeout_ms must be >= 5000ms" in str(exc_info.value)


def test_wrap_proxy_chaining() -> None:
    client = AgentRein(api_key="key")
    session = Session(
        id="s-1",
        organization_id="o-1",
        agent_id="a-1",
        intent=None,
        status="ACTIVE",
        is_sandbox=False,
        created_at="now",
        updated_at="now",
    )
    dummy = MockClient()

    wrapped = client.wrap(dummy, session, connector="stripe")
    # Verify that accessing fields returns a new proxy with nested paths
    proxy_charges = wrapped.charges
    assert proxy_charges._path == ["charges"]  # type: ignore[attr-defined]
    proxy_create = proxy_charges.create
    assert proxy_create._path == ["charges", "create"]  # type: ignore[attr-defined]


def test_wrap_branch_standard_success(
    session: Session, mocker: MockerFixture
) -> None:
    client = AgentRein(api_key="key")
    mocker.patch.object(client, "_get_token", return_value="token")
    mock_log = mocker.patch.object(client, "_log_action")

    dummy = MockClient()
    wrapped = client.wrap(dummy, session, connector="stripe")

    res = wrapped.charges.create(amount=100)
    assert res == {"id": "ch_123", "amount": 100}

    mock_log.assert_called_once_with(
        session_id="session-123",
        api_name="stripe.charges.create",
        operation_type="CREATE",
        payload={"amount": 100},
        response={"id": "ch_123", "amount": 100},
        status="SUCCESS",
        timeout_ms=86400000,
    )


def test_wrap_branch_standard_failure(
    session: Session, mocker: MockerFixture
) -> None:
    client = AgentRein(api_key="key")
    mocker.patch.object(client, "_get_token", return_value="token")
    mock_log = mocker.patch.object(client, "_log_action")

    dummy = MockClient()
    # Stub create to throw exception
    mocker.patch.object(dummy.charges, "create", side_effect=ValueError("Insufficient funds"))

    wrapped = client.wrap(dummy, session, connector="stripe")

    with pytest.raises(ValueError) as exc_info:
        wrapped.charges.create(amount=100)

    assert "Insufficient funds" in str(exc_info.value)
    mock_log.assert_called_once_with(
        session_id="session-123",
        api_name="stripe.charges.create",
        operation_type="CREATE",
        payload={"amount": 100},
        response={},
        status="FAILED",
        timeout_ms=86400000,
    )


def test_wrap_branch_sandbox_simulated(
    sandbox_session: Session, mocker: MockerFixture
) -> None:
    client = AgentRein(api_key="key")
    mocker.patch.object(client, "_get_token", return_value="token")
    mocker.patch("time.sleep")

    mock_resp = mocker.MagicMock(spec=httpx.Response)
    mock_resp.json.return_value = {"data": {"simulated": True}}
    mock_post = mocker.patch.object(client._http, "post", return_value=mock_resp)

    dummy = MockClient()
    wrapped = client.wrap(dummy, sandbox_session, connector="stripe")

    res = wrapped.charges.create(amount=100)
    assert isinstance(res, SimulatedResponse)

    mock_post.assert_called_once_with(
        "/sessions/session-123/actions",
        json={
            "apiName": "stripe.charges.create",
            "operationType": "CREATE",
            "payload": {"amount": 100},
            "response": {},
            "status": "SUCCESS",
        },
        headers={"Authorization": "Bearer token"},
    )


def test_wrap_branch_sandbox_not_simulated(
    sandbox_session: Session, mocker: MockerFixture
) -> None:
    client = AgentRein(api_key="key")
    mocker.patch.object(client, "_get_token", return_value="token")
    mocker.patch("time.sleep")

    mock_resp = mocker.MagicMock(spec=httpx.Response)
    mock_resp.json.return_value = {"data": {"simulated": False}}
    mocker.patch.object(client._http, "post", return_value=mock_resp)

    dummy = MockClient()
    wrapped = client.wrap(dummy, sandbox_session, connector="stripe")

    res = wrapped.charges.create(amount=100)
    assert res == {"id": "ch_123", "amount": 100}


def test_wrap_branch_retryable_success(
    session: Session, mocker: MockerFixture
) -> None:
    client = AgentRein(api_key="key")
    mocker.patch.object(client, "_get_token", return_value="token")
    mock_log = mocker.patch.object(client, "_log_action")

    from agentrein.connector_retry import ConnectorRetryResult
    mocker.patch(
        "agentrein.client.retry_connector_call",
        return_value=ConnectorRetryResult(
            result={"id": "ch_123", "amount": 100},
            retry_count=1,
            idempotency_key="idem-key-123",
        ),
    )

    dummy = MockClient()
    wrapped = client.wrap(dummy, session, connector="stripe", retryable=["charges.create"])

    res = wrapped.charges.create(amount=100)
    assert res == {"id": "ch_123", "amount": 100}

    # Verify standard log includes the _agentrein_meta key in response logged, but return val doesn't have it
    mock_log.assert_called_once_with(
        session_id="session-123",
        api_name="stripe.charges.create",
        operation_type="CREATE",
        payload={"amount": 100},
        response={"id": "ch_123", "amount": 100, "_agentrein_meta": {"retry_count": 1}},
        status="SUCCESS",
        timeout_ms=86400000,
    )


def test_wrap_branch_approval_success(
    session: Session, mocker: MockerFixture
) -> None:
    client = AgentRein(api_key="key")
    mocker.patch.object(client, "_get_token", return_value="token")
    mocker.patch("time.sleep")

    # POST action pending response
    mock_post_resp = mocker.MagicMock(spec=httpx.Response)
    mock_post_resp.json.return_value = {
        "data": {
            "id": "act-123",
            "simulated": False,
            "approval": {"id": "app-456"},
        }
    }
    mocker.patch.object(client._http, "post", return_value=mock_post_resp)

    # Poll approval mock
    mocker.patch.object(client, "_poll_approval", return_value="APPROVED")

    # PATCH success response
    mock_patch_resp = mocker.MagicMock(spec=httpx.Response)
    mock_patch = mocker.patch.object(client._http, "patch", return_value=mock_patch_resp)

    dummy = MockClient()
    wrapped = client.wrap(
        dummy, session, connector="stripe", requires_approval=["charges.create"]
    )

    res = wrapped.charges.create(amount=100)
    assert res == {"id": "ch_123", "amount": 100}

    mock_patch.assert_called_once_with(
        "/sessions/session-123/actions/act-123",
        json={"status": "SUCCESS", "response": {"id": "ch_123", "amount": 100}},
        headers={"Authorization": "Bearer token"},
    )


def test_wrap_branch_approval_rejected(
    session: Session, mocker: MockerFixture
) -> None:
    client = AgentRein(api_key="key")
    mocker.patch.object(client, "_get_token", return_value="token")
    mocker.patch("time.sleep")

    # POST action pending response
    mock_post_resp = mocker.MagicMock(spec=httpx.Response)
    mock_post_resp.json.return_value = {
        "data": {
            "id": "act-123",
            "simulated": False,
            "approval": {"id": "app-456"},
        }
    }
    mocker.patch.object(client._http, "post", return_value=mock_post_resp)

    # Poll approval rejected
    mocker.patch.object(
        client, "_poll_approval", side_effect=ApprovalRejectedError("app-456", "unsafe")
    )
    mock_log = mocker.patch.object(client, "_log_action")

    dummy = MockClient()
    wrapped = client.wrap(
        dummy, session, connector="stripe", requires_approval=["charges.create"]
    )

    with pytest.raises(ApprovalRejectedError) as exc_info:
        wrapped.charges.create(amount=100)

    assert exc_info.value.approval_id == "app-456"
    assert exc_info.value.reason == "unsafe"

    # FAILED action status must be logged
    mock_log.assert_called_once_with(
        session_id="session-123",
        api_name="stripe.charges.create",
        operation_type="CREATE",
        payload={"amount": 100},
        response={},
        status="FAILED",
        timeout_ms=86400000,
    )

from __future__ import annotations

import httpx
import pytest
from pytest_mock import MockerFixture

from agentrein.client import AgentRein, Session
from agentrein.errors import (
    AgentReinUnavailableError,
    ApprovalRejectedError,
    ApprovalTimeoutError,
    ConfigValidationError,
)


@pytest.fixture
def client() -> AgentRein:
    return AgentRein(api_key="test_api_key", server_url="https://api.agentrein.com")


def test_get_token_success(client: AgentRein, mocker: MockerFixture) -> None:
    mock_response = mocker.MagicMock(spec=httpx.Response)
    mock_response.json.return_value = {"data": {"token": "mocked_token"}}
    mock_post = mocker.patch.object(client._http, "post", return_value=mock_response)

    token = client._get_token()
    assert token == "mocked_token"
    mock_post.assert_called_once_with("/auth/token", json={"apiKey": "test_api_key"})
    mock_response.raise_for_status.assert_called_once()

    # Subsequent call should return cached token
    cached_token = client._get_token()
    assert cached_token == "mocked_token"
    assert mock_post.call_count == 1


def test_get_token_failure(client: AgentRein, mocker: MockerFixture) -> None:
    mocker.patch.object(client._http, "post", side_effect=httpx.HTTPError("Network down"))

    with pytest.raises(AgentReinUnavailableError) as exc_info:
        client._get_token()
    assert "Failed to authenticate" in str(exc_info.value)


def test_new_session(client: AgentRein, mocker: MockerFixture) -> None:
    mocker.patch.object(client, "_get_token", return_value="mocked_token")

    mock_response = mocker.MagicMock(spec=httpx.Response)
    mock_response.json.return_value = {
        "data": {
            "id": "session-123",
            "organizationId": "org-456",
            "agentId": "agent-789",
            "intent": "test intent",
            "status": "ACTIVE",
            "isSandbox": False,
            "createdAt": "2026-08-12T12:00:00Z",
            "updatedAt": "2026-08-12T12:00:00Z",
        }
    }
    mock_post = mocker.patch.object(client._http, "post", return_value=mock_response)

    session = client.new_session(agent_id="agent-789", intent="test intent")

    assert isinstance(session, Session)
    assert session.id == "session-123"
    assert session.organization_id == "org-456"
    assert session.agent_id == "agent-789"
    assert session.intent == "test intent"
    assert session.status == "ACTIVE"
    assert session.is_sandbox is False

    mock_post.assert_called_once_with(
        "/sessions",
        json={"agentId": "agent-789", "intent": "test intent"},
        headers={"Authorization": "Bearer mocked_token"},
    )


def test_resume_session(client: AgentRein, mocker: MockerFixture) -> None:
    mocker.patch.object(client, "_get_token", return_value="mocked_token")

    mock_response = mocker.MagicMock(spec=httpx.Response)
    mock_response.json.return_value = {
        "data": {
            "id": "session-123",
            "organizationId": "org-456",
            "agentId": "agent-789",
            "intent": None,
            "status": "ACTIVE",
            "isSandbox": True,
            "createdAt": "2026-08-12T12:00:00Z",
            "updatedAt": "2026-08-12T12:00:00Z",
        }
    }
    mock_get = mocker.patch.object(client._http, "get", return_value=mock_response)

    session = client.resume_session("session-123")
    assert session.id == "session-123"
    assert session.is_sandbox is True

    mock_get.assert_called_once_with(
        "/sessions/session-123",
        headers={"Authorization": "Bearer mocked_token"},
    )

    # Test alias get_session
    mock_get.reset_mock()
    session_alias = client.get_session("session-123")
    assert session_alias.id == "session-123"
    assert mock_get.call_count == 1


def test_complete_session_success(client: AgentRein, mocker: MockerFixture) -> None:
    mocker.patch.object(client, "_get_token", return_value="mocked_token")
    mock_response = mocker.MagicMock(spec=httpx.Response)
    mock_patch = mocker.patch.object(client._http, "patch", return_value=mock_response)

    session = Session(
        id="session-123",
        organization_id="org-456",
        agent_id="agent-789",
        intent=None,
        status="ACTIVE",
        is_sandbox=False,
        created_at="2026-08-12T12:00:00Z",
        updated_at="2026-08-12T12:00:00Z",
    )

    client.complete_session(session)
    mock_patch.assert_called_once_with(
        "/sessions/session-123",
        json={"status": "COMPLETED"},
        headers={"Authorization": "Bearer mocked_token"},
    )


def test_complete_session_failure(mocker: MockerFixture) -> None:
    client_closed = AgentRein(api_key="key", failure_mode="closed")
    mocker.patch.object(client_closed, "_get_token", return_value="mocked_token")
    mocker.patch.object(client_closed._http, "patch", side_effect=httpx.HTTPError("Failed patch"))

    session = Session(
        id="session-123",
        organization_id="org-456",
        agent_id="agent-789",
        intent=None,
        status="ACTIVE",
        is_sandbox=False,
        created_at="2026-08-12T12:00:00Z",
        updated_at="2026-08-12T12:00:00Z",
    )

    # In closed mode, failure must raise
    with pytest.raises(AgentReinUnavailableError):
        client_closed.complete_session(session)

    # In open mode (default), failure should be swallowed
    client_open = AgentRein(api_key="key", failure_mode="open")
    mocker.patch.object(client_open, "_get_token", return_value="mocked_token")
    mocker.patch.object(client_open._http, "patch", side_effect=httpx.HTTPError("Failed patch"))

    client_open.complete_session(session)  # should not raise


def test_rollback_session_failure(mocker: MockerFixture) -> None:
    client_closed = AgentRein(api_key="key", failure_mode="closed")
    mocker.patch.object(client_closed, "_get_token", return_value="mocked_token")
    mocker.patch.object(client_closed._http, "post", side_effect=httpx.HTTPError("Failed rollback"))

    session = Session(
        id="session-123",
        organization_id="org-456",
        agent_id="agent-789",
        intent=None,
        status="ACTIVE",
        is_sandbox=False,
        created_at="2026-08-12T12:00:00Z",
        updated_at="2026-08-12T12:00:00Z",
    )

    with pytest.raises(AgentReinUnavailableError):
        client_closed.rollback_session(session)

    client_open = AgentRein(api_key="key", failure_mode="open")
    mocker.patch.object(client_open, "_get_token", return_value="mocked_token")
    mocker.patch.object(client_open._http, "post", side_effect=httpx.HTTPError("Failed rollback"))

    client_open.rollback_session(session)  # should not raise


def test_validate_config_success(client: AgentRein, mocker: MockerFixture) -> None:
    mocker.patch.object(client, "_get_token", return_value="mocked_token")
    mock_response = mocker.MagicMock(spec=httpx.Response)
    mock_response.json.return_value = {"data": {"valid": True}}
    mock_get = mocker.patch.object(client._http, "get", return_value=mock_response)

    res = client.validate_config(["stripe", "github"])
    assert res == {"valid": True}
    mock_get.assert_called_once_with(
        "/settings/credentials/validate",
        params={"connectors": "stripe,github"},
        headers={"Authorization": "Bearer mocked_token"},
    )


def test_validate_config_failure(client: AgentRein, mocker: MockerFixture) -> None:
    mocker.patch.object(client, "_get_token", return_value="mocked_token")
    mocker.patch.object(client._http, "get", side_effect=httpx.HTTPError("Validation API error"))

    with pytest.raises(ConfigValidationError):
        client.validate_config(["stripe"])


def test_log_action_success(client: AgentRein, mocker: MockerFixture) -> None:
    mocker.patch.object(client, "_get_token", return_value="mocked_token")
    mock_response = mocker.MagicMock(spec=httpx.Response)
    mock_post = mocker.patch.object(client._http, "post", return_value=mock_response)

    client._log_action(
        session_id="session-123",
        api_name="stripe.charges.create",
        operation_type="CREATE",
        payload={"amount": 100},
        response={"id": "ch_123"},
        status="SUCCESS",
        timeout_ms=5000,
    )

    mock_post.assert_called_once_with(
        "/sessions/session-123/actions",
        json={
            "apiName": "stripe.charges.create",
            "operationType": "CREATE",
            "payload": {"amount": 100},
            "response": {"id": "ch_123"},
            "status": "SUCCESS",
            "timeoutMs": 5000,
        },
        headers={"Authorization": "Bearer mocked_token"},
    )


def test_log_action_failure_trigger_rollback(mocker: MockerFixture) -> None:
    # Setup open client
    client = AgentRein(api_key="key", failure_mode="open")
    mocker.patch.object(client, "_get_token", return_value="mocked_token")
    mocker.patch("time.sleep")  # avoid actual sleep in backoff retry

    mock_post = mocker.patch.object(client._http, "post", side_effect=httpx.HTTPError("Network timeout"))
    mock_warn = mocker.patch("logging.Logger.warning")

    client._log_action(
        session_id="session-123",
        api_name="stripe.charges.create",
        operation_type="CREATE",
        payload=None,
        response=None,
        status="FAILED",  # action status is FAILED, so fallback rollback should trigger
    )

    # First calls will be the 3 action log attempts due to retry_with_backoff,
    # followed by the fallback rollback attempt.
    # Total call count should be 4: 3 retries for log + 1 rollback
    assert mock_post.call_count == 4

    # The last call should be the rollback endpoint
    mock_post.assert_called_with(
        "/sessions/session-123/rollback",
        json={},
        headers={"Authorization": "Bearer mocked_token"},
    )
    # Warning should be logged in open mode
    mock_warn.assert_called_once()


def test_log_action_failure_closed_re_raises(mocker: MockerFixture) -> None:
    client = AgentRein(api_key="key", failure_mode="closed")
    mocker.patch.object(client, "_get_token", return_value="mocked_token")
    mocker.patch("time.sleep")

    mocker.patch.object(client._http, "post", side_effect=httpx.HTTPError("Fatal"))

    with pytest.raises(httpx.HTTPError):
        client._log_action(
            session_id="session-123",
            api_name="stripe.charges.create",
            operation_type="CREATE",
            payload=None,
            response=None,
            status="SUCCESS",
        )


def test_poll_approval_approved(client: AgentRein, mocker: MockerFixture) -> None:
    mocker.patch.object(client, "_get_token", return_value="mocked_token")
    mocker.patch("time.sleep")

    mock_resp = mocker.MagicMock(spec=httpx.Response)
    mock_resp.json.return_value = {"data": {"status": "APPROVED"}}
    mocker.patch.object(client._http, "get", return_value=mock_resp)

    res = client._poll_approval(approval_id="app-123", poll_interval_ms=10, timeout_ms=100)
    assert res == "APPROVED"


def test_poll_approval_rejected(client: AgentRein, mocker: MockerFixture) -> None:
    mocker.patch.object(client, "_get_token", return_value="mocked_token")
    mocker.patch("time.sleep")

    mock_resp = mocker.MagicMock(spec=httpx.Response)
    mock_resp.json.return_value = {"data": {"status": "REJECTED", "reason": "unsafe"}}
    mocker.patch.object(client._http, "get", return_value=mock_resp)

    with pytest.raises(ApprovalRejectedError) as exc_info:
        client._poll_approval(approval_id="app-123", poll_interval_ms=10, timeout_ms=100)

    assert exc_info.value.approval_id == "app-123"
    assert exc_info.value.reason == "unsafe"


def test_poll_approval_timeout(client: AgentRein, mocker: MockerFixture) -> None:
    mocker.patch.object(client, "_get_token", return_value="mocked_token")
    mocker.patch("time.sleep")

    mock_resp = mocker.MagicMock(spec=httpx.Response)
    # Keep status as PENDING
    mock_resp.json.return_value = {"data": {"status": "PENDING"}}
    mocker.patch.object(client._http, "get", return_value=mock_resp)

    # Set real time mock to simulate loop expiration immediately
    mocker.patch("time.time", side_effect=[0.0, 0.0, 1.0, 2.0])

    with pytest.raises(ApprovalTimeoutError) as exc_info:
        client._poll_approval(approval_id="app-123", poll_interval_ms=10, timeout_ms=50)

    assert exc_info.value.approval_id == "app-123"
    assert exc_info.value.timeout_ms == 50

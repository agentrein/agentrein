from __future__ import annotations

from agentrein.errors import (
    AgentReinError,
    AgentReinUnavailableError,
    ApprovalRejectedError,
    ApprovalTimeoutError,
    ConfigValidationError,
    WrapOptionsValidationError,
)


def test_agent_rein_error_base() -> None:
    # Verify inheritance
    assert issubclass(AgentReinUnavailableError, AgentReinError)
    assert issubclass(ApprovalRejectedError, AgentReinError)
    assert issubclass(ApprovalTimeoutError, AgentReinError)
    assert issubclass(ConfigValidationError, AgentReinError)
    assert issubclass(WrapOptionsValidationError, AgentReinError)


def test_agent_rein_unavailable_error() -> None:
    # Default message
    err1 = AgentReinUnavailableError()
    assert str(err1) == "AgentRein safety layer is unavailable"

    # Custom message
    err2 = AgentReinUnavailableError("Custom unavailable message")
    assert str(err2) == "Custom unavailable message"


def test_approval_rejected_error() -> None:
    # Without reason
    err1 = ApprovalRejectedError(approval_id="app-123")
    assert err1.approval_id == "app-123"
    assert err1.reason is None
    assert str(err1) == "Approval app-123 was rejected"

    # With reason
    err2 = ApprovalRejectedError(approval_id="app-456", reason="user cancelled")
    assert err2.approval_id == "app-456"
    assert err2.reason == "user cancelled"
    assert str(err2) == "Approval app-456 was rejected: user cancelled"


def test_approval_timeout_error() -> None:
    err = ApprovalTimeoutError(approval_id="app-789", timeout_ms=5000)
    assert err.approval_id == "app-789"
    assert err.timeout_ms == 5000
    assert str(err) == "Approval app-789 timed out after 5000ms"


def test_validation_errors() -> None:
    err1 = ConfigValidationError("config invalid")
    assert str(err1) == "config invalid"

    err2 = WrapOptionsValidationError("options invalid")
    assert str(err2) == "options invalid"

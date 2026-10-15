"""Custom exceptions for the AgentRein SDK."""

from __future__ import annotations


class AgentReinError(Exception):
    """Base exception for all AgentRein SDK errors."""


class AgentReinUnavailableError(AgentReinError):
    """Raised when the AgentRein safety layer is unavailable."""

    def __init__(self, message: str | None = None) -> None:
        super().__init__(message or "AgentRein safety layer is unavailable")


class ApprovalRejectedError(AgentReinError):
    """Raised when an approval is rejected."""

    approval_id: str
    reason: str | None

    def __init__(self, approval_id: str, reason: str | None = None) -> None:
        self.approval_id = approval_id
        self.reason = reason
        message = (
            f"Approval {approval_id} was rejected: {reason}"
            if reason
            else f"Approval {approval_id} was rejected"
        )
        super().__init__(message)


class ApprovalTimeoutError(AgentReinError):
    """Raised when an approval times out."""

    approval_id: str
    timeout_ms: int

    def __init__(self, approval_id: str, timeout_ms: int) -> None:
        self.approval_id = approval_id
        self.timeout_ms = timeout_ms
        super().__init__(f"Approval {approval_id} timed out after {timeout_ms}ms")


class ConfigValidationError(AgentReinError):
    """Raised when configuration validation fails."""

    def __init__(self, message: str) -> None:
        super().__init__(message)


class WrapOptionsValidationError(AgentReinError):
    """Raised when wrap options validation fails."""

    def __init__(self, message: str) -> None:
        super().__init__(message)

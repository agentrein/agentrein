"""Core client implementation for AgentRein."""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass
from typing import Any, Literal, TypeVar, cast

import httpx

from agentrein.connector_retry import retry_connector_call
from agentrein.errors import (
    AgentReinDeniedError,
    AgentReinUnavailableError,
    ApprovalRejectedError,
    ApprovalTimeoutError,
    ConfigValidationError,
    WrapOptionsValidationError,
)
from agentrein.retry import retry_with_backoff
from agentrein.simulate_response import create_simulated_response

T = TypeVar("T")


def is_server_decision(err: Exception) -> bool:
    """Return True if the error is an explicit server decision (HTTP 401, 403, 409, 429)."""
    if isinstance(err, httpx.HTTPStatusError):
        return err.response.status_code in (401, 403, 409, 429)
    return False


def to_server_denied_error(err: Exception) -> AgentReinDeniedError:
    """Transform an HTTP status error into a typed AgentReinDeniedError parsing RFC 7807 problem details."""
    if isinstance(err, httpx.HTTPStatusError):
        status = err.response.status_code
        error_type = "unknown"
        detail = str(err)
        try:
            body = err.response.json()
            err_obj = body.get("error") if isinstance(body, dict) and isinstance(body.get("error"), dict) else body
            if isinstance(err_obj, dict):
                raw_type = err_obj.get("type", "")
                if "/" in str(raw_type):
                    error_type = str(raw_type).rstrip("/").split("/")[-1]
                elif raw_type:
                    error_type = str(raw_type)
                detail = str(err_obj.get("detail") or err_obj.get("title") or err_obj.get("message") or detail)
        except Exception:
            pass
        return AgentReinDeniedError(status=status, error_type=error_type, detail=detail)
    return AgentReinDeniedError(status=500, error_type="unknown", detail=str(err))


@dataclass
class Session:
    """Represents an AgentRein safety session."""

    id: str
    organization_id: str
    agent_id: str
    intent: str | None
    status: str
    is_sandbox: bool
    created_at: str
    updated_at: str

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> Session:
        """Map backend camelCase JSON keys to the python Session dataclass fields."""
        return cls(
            id=data["id"],
            organization_id=data["organizationId"],
            agent_id=data["agentId"],
            intent=data.get("intent"),
            status=data["status"],
            is_sandbox=data.get("isSandbox", False),
            created_at=data["createdAt"],
            updated_at=data["updatedAt"],
        )


@dataclass
class WrapOptions:
    """Configuration options for wrapping connector API calls."""

    connector: str
    requires_approval: list[str] | None = None
    retryable: list[str] | None = None
    poll_interval_ms: int = 2000
    timeout_ms: int = 86_400_000


_OP_MAP: dict[str, Literal["CREATE", "UPDATE", "DELETE"]] = {
    "create": "CREATE",
    "send": "CREATE",
    "post": "CREATE",
    "append": "CREATE",
    "add": "CREATE",
    "update": "UPDATE",
    "patch": "UPDATE",
    "modify": "UPDATE",
    "move": "UPDATE",
    "trash": "UPDATE",
    "upsert": "UPDATE",
    "delete": "DELETE",
    "del": "DELETE",
    "remove": "DELETE",
    "destroy": "DELETE",
}


class _WrapProxy:
    def __init__(
        self,
        client: AgentRein,
        session: Session,
        options: WrapOptions,
        target: Any,
        path: list[str],
    ) -> None:
        self._client = client
        self._session = session
        self._options = options
        self._target = target
        self._path = path

    def __getattr__(self, name: str) -> _WrapProxy:
        return _WrapProxy(
            self._client,
            self._session,
            self._options,
            getattr(self._target, name),
            self._path + [name],
        )

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        api_name = f"{self._options.connector}.{'.'.join(self._path)}"
        last_seg = self._path[-1].lower() if self._path else ""
        operation_type = _OP_MAP.get(last_seg, "CREATE")
        method_path = ".".join(self._path)

        # IMPORTANT Python-specific adaptation (no TS equivalent):
        # In TS, payload = args[0] because JS connector calls take one object literal argument.
        # In Python, connector SDKs typically use kwargs, not a single positional dict.
        payload = kwargs if kwargs else (args[0] if args else {})

        requires_approval = self._options.requires_approval
        needs_approval = requires_approval is not None and (
            method_path in requires_approval or api_name in requires_approval
        )
        retryable = self._options.retryable
        is_retryable = retryable is not None and (
            method_path in retryable or api_name in retryable
        )

        # Branch 1 — approval gate
        if needs_approval:
            action_body = {
                "apiName": api_name,
                "operationType": operation_type,
                "payload": payload if payload is not None else {},
                "response": {},
                "status": "PENDING_APPROVAL",
            }
            if self._options.timeout_ms is not None:
                action_body["timeoutMs"] = self._options.timeout_ms

            action_res = None
            try:
                def _post_action() -> httpx.Response:
                    r = self._client._http.post(
                        f"/sessions/{self._session.id}/actions",
                        json=action_body,
                        headers=self._client._auth_headers(),
                    )
                    r.raise_for_status()
                    return r
                action_res = retry_with_backoff(_post_action)
            except Exception as error:
                if is_server_decision(error):
                    raise to_server_denied_error(error)
                if self._client._failure_mode == "closed":
                    raise
                logging.getLogger("agentrein").warning(
                    "Failed to create pending approval action: %s", error
                )
                action_res = None

            if action_res is None:
                try:
                    result = self._target(*args, **kwargs)
                    self._client._log_action(
                        session_id=self._session.id,
                        api_name=api_name,
                        operation_type=operation_type,
                        payload=payload,
                        response=result,
                        status="SUCCESS",
                        timeout_ms=self._options.timeout_ms,
                    )
                    return result
                except Exception:
                    self._client._log_action(
                        session_id=self._session.id,
                        api_name=api_name,
                        operation_type=operation_type,
                        payload=payload,
                        response={},
                        status="FAILED",
                        timeout_ms=self._options.timeout_ms,
                    )
                    raise

            action = action_res.json()["data"]
            if action.get("simulated") is True:
                return create_simulated_response()

            action_id = action["id"]
            approval_id = (
                action.get("approvalRequest", {}).get("id")
                or action.get("approval", {}).get("id")
                or action_id
            )

            try:
                self._client._poll_approval(
                    approval_id=approval_id,
                    poll_interval_ms=self._options.poll_interval_ms,
                    timeout_ms=self._options.timeout_ms,
                )
            except (ApprovalRejectedError, ApprovalTimeoutError):
                self._client._log_action(
                    session_id=self._session.id,
                    api_name=api_name,
                    operation_type=operation_type,
                    payload=payload,
                    response={},
                    status="FAILED",
                    timeout_ms=self._options.timeout_ms,
                )
                raise

            try:
                result = self._target(*args, **kwargs)
            except Exception:
                self._client._log_action(
                    session_id=self._session.id,
                    api_name=api_name,
                    operation_type=operation_type,
                    payload=payload,
                    response={},
                    status="FAILED",
                    timeout_ms=self._options.timeout_ms,
                )
                raise

            try:
                def _patch_action() -> httpx.Response:
                    r = self._client._http.patch(
                        f"/sessions/{self._session.id}/actions/{action_id}",
                        json={"status": "SUCCESS", "response": result},
                        headers=self._client._auth_headers(),
                    )
                    r.raise_for_status()
                    return r
                retry_with_backoff(_patch_action)
            except Exception as error:
                if is_server_decision(error):
                    raise to_server_denied_error(error)
                if self._client._failure_mode == "closed":
                    raise
                logging.getLogger("agentrein").warning(
                    "Failed to update action to SUCCESS: %s", error
                )

            return result

        # Branch 2 — sandbox
        elif self._session.is_sandbox:
            action_body = {
                "apiName": api_name,
                "operationType": operation_type,
                "payload": payload if payload is not None else {},
                "response": {},
                "status": "SUCCESS",
            }
            action_res = None
            try:
                def _post_sandbox_action() -> httpx.Response:
                    r = self._client._http.post(
                        f"/sessions/{self._session.id}/actions",
                        json=action_body,
                        headers=self._client._auth_headers(),
                    )
                    r.raise_for_status()
                    return r
                action_res = retry_with_backoff(_post_sandbox_action)
            except Exception as error:
                if is_server_decision(error):
                    raise to_server_denied_error(error)
                if self._client._failure_mode == "closed":
                    raise
                logging.getLogger("agentrein").warning(
                    "Failed to log sandbox action: %s", error
                )
                action_res = None

            if action_res is not None:
                action = action_res.json()["data"]
                if action.get("simulated") is True:
                    return create_simulated_response()

            return self._target(*args, **kwargs)

        # Branch 3 — retryable
        elif is_retryable:
            try:
                retry_result = retry_connector_call(
                    lambda idempotency_key: self._target(*args, **kwargs)
                )
                result = retry_result.result
            except Exception:
                self._client._log_action(
                    session_id=self._session.id,
                    api_name=api_name,
                    operation_type=operation_type,
                    payload=payload,
                    response={},
                    status="FAILED",
                    timeout_ms=self._options.timeout_ms,
                )
                raise

            response_with_meta = result
            if isinstance(result, dict):
                try:
                    meta_dict = dict(result)
                    meta_dict["_agentrein_meta"] = {"retry_count": retry_result.retry_count}
                    response_with_meta = meta_dict
                except Exception:  # noqa: BLE001, S110
                    pass

            self._client._log_action(
                session_id=self._session.id,
                api_name=api_name,
                operation_type=operation_type,
                payload=payload,
                response=response_with_meta,
                status="SUCCESS",
                timeout_ms=self._options.timeout_ms,
            )
            return result

        # Branch 4 — standard
        else:
            try:
                result = self._target(*args, **kwargs)
            except Exception:
                self._client._log_action(
                    session_id=self._session.id,
                    api_name=api_name,
                    operation_type=operation_type,
                    payload=payload,
                    response={},
                    status="FAILED",
                    timeout_ms=self._options.timeout_ms,
                )
                raise

            self._client._log_action(
                session_id=self._session.id,
                api_name=api_name,
                operation_type=operation_type,
                payload=payload,
                response=result,
                status="SUCCESS",
                timeout_ms=self._options.timeout_ms,
            )
            return result


class AgentRein:
    """The main client SDK to interact with the AgentRein safety layer."""

    def __init__(
        self,
        api_key: str,
        server_url: str = "https://api.agentrein.com",
        failure_mode: Literal["open", "closed"] = "open",
    ) -> None:
        self._api_key = api_key
        self._server_url = server_url.rstrip("/")
        self._failure_mode = failure_mode
        self._token: str | None = None
        self._token_expires_at: float = 0.0
        self._http = httpx.Client(base_url=self._server_url, timeout=30.0)

    def _get_token(self) -> str:
        """Retrieve a cached authentication token or fetch a new one if expired."""
        if self._token is not None and time.time() < self._token_expires_at - 300:
            return self._token

        try:
            resp = self._http.post("/auth/token", json={"apiKey": self._api_key})
            resp.raise_for_status()
            data = resp.json()["data"]
            self._token = str(data["token"])
            self._token_expires_at = time.time() + 24 * 60 * 60
            return self._token
        except Exception as error:
            if is_server_decision(error):
                raise to_server_denied_error(error)
            raise AgentReinUnavailableError(f"Failed to authenticate: {error}") from error

    def _auth_headers(self) -> dict[str, str]:
        """Generate headers containing the bearer authentication token."""
        return {"Authorization": f"Bearer {self._get_token()}"}

    def new_session(self, agent_id: str | None = None, intent: str | None = None) -> Session:
        """Create a new safety session for an agent and intent."""
        if agent_id is None:
            agent_id = str(uuid.uuid4())

        try:
            resp = self._http.post(
                "/sessions",
                json={"agentId": agent_id, "intent": intent},
                headers=self._auth_headers(),
            )
            resp.raise_for_status()
            return Session.from_api(resp.json()["data"])
        except Exception as error:
            if is_server_decision(error):
                raise to_server_denied_error(error)
            raise AgentReinUnavailableError(f"Failed to create session: {error}") from error

    def resume_session(self, session_id: str) -> Session:
        """Retrieve an existing safety session by ID."""
        try:
            resp = self._http.get(f"/sessions/{session_id}", headers=self._auth_headers())
            resp.raise_for_status()
            return Session.from_api(resp.json()["data"])
        except Exception as error:
            if is_server_decision(error):
                raise to_server_denied_error(error)
            raise AgentReinUnavailableError(f"Failed to resume session: {error}") from error

    def get_session(self, session_id: str) -> Session:
        """Alias for resume_session."""
        return self.resume_session(session_id)

    def complete_session(self, session: Session) -> None:
        """Mark a safety session as COMPLETED."""
        try:
            resp = self._http.patch(
                f"/sessions/{session.id}",
                json={"status": "COMPLETED"},
                headers=self._auth_headers(),
            )
            resp.raise_for_status()
        except Exception as error:
            if is_server_decision(error):
                raise to_server_denied_error(error)
            if self._failure_mode == "closed":
                raise AgentReinUnavailableError(f"Failed to complete session: {error}") from error
            logging.getLogger("agentrein").warning(
                "Failed to complete session (%s): %s", session.id, error
            )

    def rollback_session(self, session: Session) -> None:
        """Initiate rollback process for a session."""
        try:
            resp = self._http.post(
                f"/sessions/{session.id}/rollback",
                json={},
                headers=self._auth_headers(),
            )
            resp.raise_for_status()
        except Exception as error:
            if is_server_decision(error):
                raise to_server_denied_error(error)
            if self._failure_mode == "closed":
                raise AgentReinUnavailableError(f"Failed to rollback session: {error}") from error
            logging.getLogger("agentrein").warning(
                "Failed to rollback session (%s): %s", session.id, error
            )

    def validate_config(self, connectors: list[str]) -> dict[str, Any]:
        """Validate current config settings for a list of connector IDs."""
        try:
            resp = self._http.get(
                "/settings/credentials/validate",
                params={"connectors": ",".join(connectors)},
                headers=self._auth_headers(),
            )
            resp.raise_for_status()
            data = resp.json()["data"]
            if not isinstance(data, dict):
                raise ConfigValidationError("Invalid data format returned from config validation")
            return data
        except Exception as error:
            if is_server_decision(error):
                raise to_server_denied_error(error)
            raise ConfigValidationError(f"Configuration validation failed: {error}") from error

    def _log_action(
        self,
        session_id: str,
        api_name: str,
        operation_type: Literal["CREATE", "UPDATE", "DELETE"],
        payload: Any,
        response: Any,
        status: Literal["SUCCESS", "FAILED", "PENDING_APPROVAL"],
        timeout_ms: int | None = None,
    ) -> None:
        """Log an action call against the active session, retrying on transient errors."""
        body = {
            "apiName": api_name,
            "operationType": operation_type,
            "payload": payload if payload is not None else {},
            "response": response if response is not None else {},
            "status": status,
        }
        if timeout_ms is not None:
            body["timeoutMs"] = timeout_ms

        def make_log_request() -> httpx.Response:
            resp = self._http.post(
                f"/sessions/{session_id}/actions",
                json=body,
                headers=self._auth_headers(),
            )
            resp.raise_for_status()
            return resp

        try:
            retry_with_backoff(make_log_request)
        except Exception as error:
            if is_server_decision(error):
                raise to_server_denied_error(error)

            if status == "FAILED":
                try:
                    self._http.post(
                        f"/sessions/{session_id}/rollback",
                        json={},
                        headers=self._auth_headers(),
                    )
                except Exception:  # noqa: BLE001, S110
                    pass

            if self._failure_mode == "closed":
                raise
            logging.getLogger("agentrein").warning("Failed to log action: %s", error)

    def _poll_approval(
        self,
        approval_id: str,
        poll_interval_ms: int,
        timeout_ms: int,
    ) -> Literal["APPROVED"]:
        """Poll for manual approval status until approved, rejected, or timed out."""
        deadline = time.time() + timeout_ms / 1000.0
        while time.time() < deadline:
            try:
                resp = self._http.get(
                    f"/approvals/{approval_id}",
                    headers=self._auth_headers(),
                )
                resp.raise_for_status()
                data = resp.json()["data"]
                status = data.get("status")
                if status == "APPROVED":
                    return "APPROVED"
                if status == "REJECTED":
                    reason = data.get("reason")
                    raise ApprovalRejectedError(approval_id, reason)
            except httpx.HTTPError:
                # Keep polling if connection fails transiently
                pass
            time.sleep(poll_interval_ms / 1000.0)

        raise ApprovalTimeoutError(approval_id, timeout_ms)

    def wrap(
        self,
        client: T,
        session: Session,
        *,
        connector: str,
        requires_approval: list[str] | None = None,
        retryable: list[str] | None = None,
        poll_interval_ms: int = 2000,
        timeout_ms: int = 86_400_000,
    ) -> T:
        """Wrap a connector client to intercept calls and manage policies.

        Decision branches:
        1. Approval: Check requires_approval policy to queue actions.
        2. Sandbox: If in sandbox session, log actions and optionally simulate response.
        3. Retryable: Apply idempotent backoff retry rules.
        4. Standard: Log action directly to the dashboard.

        This SDK uses a blind-proxy pattern: it has zero knowledge of the wrapped client's
        underlying API methods. All policy decisions and response simulation are managed by
        the AgentRein backend.
        """
        if not connector or not isinstance(connector, str):
            raise WrapOptionsValidationError("connector must be a non-empty string")
        if poll_interval_ms < 1000:
            raise WrapOptionsValidationError("poll_interval_ms must be >= 1000ms")
        if timeout_ms < 5000:
            raise WrapOptionsValidationError("timeout_ms must be >= 5000ms")

        options = WrapOptions(
            connector=connector,
            requires_approval=requires_approval,
            retryable=retryable,
            poll_interval_ms=poll_interval_ms,
            timeout_ms=timeout_ms,
        )
        return cast(T, _WrapProxy(self, session, options, target=client, path=[]))

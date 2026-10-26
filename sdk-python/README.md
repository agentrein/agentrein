# AgentRein Python SDK

[![PyPI Version](https://img.shields.io/pypi/v/agentrein?logo=pypi&logoColor=white&color=3775A9&style=flat-square)](https://pypi.org/project/agentrein/)
[![Python Versions](https://img.shields.io/pypi/pyversions/agentrein?logo=python&logoColor=white&style=flat-square)](https://pypi.org/project/agentrein/)
[![CI Status](https://img.shields.io/github/actions/workflow/status/agentrein/agentrein/ci-python.yml?branch=main&label=CI&logo=github&logoColor=white&style=flat-square)](https://github.com/agentrein/agentrein/actions/workflows/ci-python.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue?style=flat-square)](https://github.com/agentrein/agentrein/blob/main/LICENSE)

Automatic rollback and execution safety for Python AI agents.

[Documentation](https://agentrein.com/docs) | [Quickstart Guide](https://agentrein.com/docs/quickstart) | [Dashboard](https://agentrein.com/dashboard) | [GitHub](https://github.com/agentrein/agentrein)

---

## Overview

When autonomous AI agents make tool calls—charging credit cards, updating CRM records, sending emails, or provisioning cloud infrastructure—any failure, model hallucination, or network timeout can leave external systems corrupted.

AgentRein provides runtime execution safety for AI agents:

- **Automatic Rollback**: Unwinds tool calls in strict reverse order (LIFO) when an agent workflow fails.
- **Approval Gates**: Intercepts high-risk operations and holds execution until approved via dashboard or webhook.
- **Intent Drift Detection**: Evaluates whether individual tool calls align with the session's stated goal.
- **Unified Audit Logging**: Immutable execution timelines capturing complete payloads, responses, and resource URLs.
- **Idempotent Retries**: Automatic exponential backoff for transient connector rate limits and network errors.
- **Zero-Invasive Proxy**: Wrap existing vendor SDK clients without altering method signatures or business logic.

---

## Installation

Install using `pip`:

```bash
pip install agentrein
```

Or using `poetry`:

```bash
poetry add agentrein
```

Or using `uv`:

```bash
uv add agentrein
```

---

## Quickstart

```python
import os
import stripe
from agentrein import AgentRein, ApprovalRejectedError

# Initialize AgentRein client
rein = AgentRein(
    api_key=os.environ["AGENTREIN_API_KEY"],
    server_url="https://api.agentrein.com", # optional
    failure_mode="open",                    # 'open' (default) | 'closed'
)

# Start a tracked safety session
session = rein.new_session(
    agent_id="billing-assistant",
    intent="Refund overcharged customer and update records",
)

try:
    # Initialize standard vendor client
    stripe_client = stripe.StripeClient(os.environ["STRIPE_API_KEY"])

    # Wrap the client with AgentRein safety policies
    safe_stripe = rein.wrap(
        stripe_client,
        session=session,
        connector="stripe",
        requires_approval=["refunds.create"],
        retryable=["charges.retrieve"],
    )

    # Execute operations normally
    charge = safe_stripe.charges.retrieve("ch_3Mtw")
    refund = safe_stripe.refunds.create(charge=charge.id, amount=2500)

    # Mark session as successfully completed
    rein.complete_session(session)

except AgentReinDeniedError as err:
    print(f"Action denied by AgentRein ({err.status} {err.error_type}): {err.detail}")
except ApprovalRejectedError as err:
    print(f"Action rejected by reviewer: {err.reason}")
    rein.rollback_session(session)

except Exception as err:
    print(f"Workflow failed: {err}. Unwinding tool calls...")
    rein.rollback_session(session)
    raise
```

---

## Core Concepts

### Sessions

A session represents the transactional boundary of an agent workflow. All actions intercepted during a session are indexed and rolled back together as a unit. Sessions are created with `rein.new_session()` and finalized with either `complete_session()` or `rollback_session()`.

### Proxy Wrapping

The `wrap()` method returns a dynamic proxy around any third-party SDK client. The proxy intercepts method calls at runtime, logs the action to the control plane, enforces approval rules, and captures the identifiers required for rollback. The underlying client's method signatures and return types remain unchanged.

### LIFO Rollback

When `rein.rollback_session()` is invoked, the platform unwinds executed actions in reverse order of execution using registered connector inverse handlers. For example, if an agent creates a GitHub issue and then sends a Slack notification, rollback first unsends the Slack message, then closes the GitHub issue.

### Failure Modes

- **`failure_mode="open"` (Default)**: If the AgentRein control plane is temporarily unreachable, tool calls execute directly against the vendor API to avoid blocking production agents.
- **`failure_mode="closed"`**: Intercepted calls fail fast with `AgentReinUnavailableError` if the control plane cannot be reached. Recommended for high-compliance or financial workloads.

---

## Usage Guide

### Approval Gates

Hold high-risk operations in a pending state until a human operator confirms the action via the AgentRein dashboard:

```python
safe_github = rein.wrap(
    github_client,
    session=session,
    connector="github",
    requires_approval=["issues.lock", "files.delete"],
    poll_interval_ms=2000,
    timeout_ms=300_000, # 5-minute timeout
)

# Execution blocks here until approved in the dashboard
safe_github.issues.lock(owner="my-org", repo="legacy-repo", issue_number=42)
```

If the operator rejects the action, an `ApprovalRejectedError` is raised. If the timeout expires without review, an `ApprovalTimeoutError` is raised.

### Idempotent Retries

Configure automatic backoff retries for methods subject to rate limits or transient network failures:

```python
safe_hubspot = rein.wrap(
    hubspot_client,
    session=session,
    connector="hubspot",
    retryable=["crm.contacts.basic_api.get_by_id"],
)
```

---

## API Reference

### `AgentRein`

```python
class AgentRein(
    api_key: str,
    server_url: str = "https://api.agentrein.com",
    failure_mode: Literal["open", "closed"] = "open",
)
```

#### Methods

- **`new_session(agent_id: str | None = None, intent: str | None = None) -> Session`**  
  Creates a new safety session. If `agent_id` is omitted, a UUID is generated.
- **`resume_session(session_id: str) -> Session`**  
  Retrieves an active session by ID (alias: `get_session`).
- **`wrap(client: T, session: Session, connector: str, requires_approval: list[str] | None = None, retryable: list[str] | None = None, poll_interval_ms: int = 2000, timeout_ms: int = 86_400_000) -> T`**  
  Wraps a vendor SDK client with the safety proxy.
- **`complete_session(session: Session) -> None`**  
  Marks the session as `COMPLETED`. Locks the timeline against further modifications.
- **`rollback_session(session: Session) -> None`**  
  Triggers server-side LIFO compensation for all recorded actions in the session.
- **`validate_config(connectors: list[str]) -> dict[str, Any]`**  
  Validates API credentials and connector health.

---

## Error Handling

All custom exceptions derive from `AgentReinError`:

```python
from agentrein.errors import (
    AgentReinError,
    AgentReinDeniedError,
    AgentReinUnavailableError,
    ApprovalRejectedError,
    ApprovalTimeoutError,
    ConfigValidationError,
    WrapOptionsValidationError,
)

try:
    safe_client.execute()
except AgentReinDeniedError as err:
    print(f"Action denied by AgentRein ({err.status} {err.error_type}): {err.detail}")
except ApprovalRejectedError as err:
    print(f"Action {err.action_id} rejected: {err.reason}")
except ApprovalTimeoutError as err:
    print(f"Action {err.action_id} timed out after {err.timeout_ms}ms")
except AgentReinUnavailableError as err:
    print(f"Control plane unreachable: {err}")
```

---

## Supported Connectors

| Connector | Actions | Rollback Behavior |
| :--- | :---: | :--- |
| **Stripe** | 10 | Reverses charges & deletes invoices |
| **Slack** | 24 | Unsends messages & deletes posts |
| **GitHub** | 20 | Closes issues, deletes comments & cleans releases |
| **HubSpot** | 17 | Restores contacts & deals |
| **Salesforce** | 28 | Rolls back records & opportunities |
| **Gmail** | 16 | Unsends drafts & deletes threads |
| **Google Drive** | 10 | Restores files & permissions |
| **Google Sheets**| 8 | Reverts cell edits & row changes |
| **Notion** | 9 | Deletes pages & restores blocks |

---

## Framework Compatibility

AgentRein operates at the client proxy layer and works with any Python agent framework:

- LangChain & LangGraph
- OpenAI Assistants API
- Anthropic Tool Use
- Groq & LlamaIndex
- Native Python agent loops

---

## Development

```bash
# 1. Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 2. Install package in editable mode with development dependencies
pip install -e "sdk-python[dev]"

# 3. Run test suite
pytest sdk-python/tests
```

---

## License

Distributed under the [MIT License](https://github.com/agentrein/agentrein/blob/main/LICENSE).

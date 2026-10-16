<div align="center">

# AgentRein Python SDK

**Deploy AI agents. Undo anything.**  
The reliability and safety layer for Python AI agents.

[![PyPI version](https://img.shields.io/pypi/v/agentrein.svg?style=flat-square&color=blue)](https://pypi.org/project/agentrein/)
[![Python Versions](https://img.shields.io/pypi/pyversions/agentrein.svg?style=flat-square)](https://pypi.org/project/agentrein/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=flat-square)](https://opensource.org/licenses/MIT)
[![CI Status](https://img.shields.io/github/actions/workflow/status/agentrein/agentrein/ci-python.yml?branch=main&style=flat-square&label=CI)](https://github.com/agentrein/agentrein/actions)

[Website](https://agentrein.com) • [Documentation](https://agentrein.com/docs) • [Dashboard](https://agentrein.com/dashboard) • [Report Issue](https://github.com/agentrein/agentrein/issues)

</div>

---

## Overview

When autonomous AI agents make tool calls—charging credit cards, updating CRM records, sending emails, or provisioning infrastructure—any failure, model hallucination, or network timeout can leave external systems in an inconsistent state.

**AgentRein** acts as a safety and transaction proxy for your AI agents:
- 🔄 **Automatic LIFO Rollback**: Undoes side effects in reverse order if an agent workflow fails.
- 🚦 **Human-in-the-Loop Approval Gates**: Intercepts high-risk operations and holds execution until approved via dashboard or webhook.
- 🔁 **Idempotent Retry Engine**: Automatically retries transient connector failures with exponential backoff.
- 🧪 **Sandbox Simulation Mode**: Safely test agents against live workflows without mutating production state.
- 🛡️ **Zero-Invasive Blind Proxy**: Wrap your existing Python SDK clients (Stripe, GitHub, HubSpot, Slack, etc.) without rewriting business logic.
- 🌐 **Fail-Open by Default**: Agent execution is never blocked if the safety control plane is temporarily unreachable.

---

## Table of Contents

- [Installation](#installation)
- [Quick Start](#quick-start)
- [Core Concepts](#core-concepts)
- [Usage Guide](#usage-guide)
  - [Human Approval Gates](#human-approval-gates)
  - [Idempotent Retries](#idempotent-retries)
  - [Sandbox Simulation](#sandbox-simulation)
  - [Fail Modes (Open vs. Closed)](#fail-modes-open-vs-closed)
- [API Reference](#api-reference)
- [Error Handling](#error-handling)
- [Supported Connectors](#supported-connectors)
- [Development & Testing](#development--testing)
- [License](#license)

---

## Installation

Install via `pip`:

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

## Quick Start

```python
import os
import stripe
from agentrein import AgentRein, ApprovalRejectedError

# 1. Initialize the AgentRein client
rein = AgentRein(
    api_key=os.environ["AGENTREIN_API_KEY"],
    server_url="https://api.agentrein.com",  # optional, default
    failure_mode="open",                     # optional, "open" | "closed"
)

# 2. Start a safety session for your agent's task
session = rein.new_session(
    agent_id="billing-assistant",
    intent="Refund overcharged customer and update records",
)

try:
    # 3. Initialize your standard 3rd-party client
    stripe_client = stripe.StripeClient(os.environ["STRIPE_API_KEY"])

    # 4. Wrap the client with AgentRein protection
    safe_stripe = rein.wrap(
        stripe_client,
        session=session,
        connector="stripe",
        requires_approval=["refunds.create"],  # pauses for human sign-off
        retryable=["charges.retrieve"],        # automatic retry on network blips
    )

    # 5. Execute operations normally through the wrapped proxy
    charge = safe_stripe.charges.retrieve("ch_3Mtw")
    refund = safe_stripe.refunds.create(charge=charge.id, amount=2500)

    # 6. Mark the session as successfully completed
    rein.complete_session(session)
    print("Workflow completed successfully.")

except ApprovalRejectedError as err:
    print(f"Action rejected by reviewer: {err.reason}")
    rein.rollback_session(session)

except Exception as err:
    print(f"Workflow failed: {err}. Initiating automatic rollback...")
    rein.rollback_session(session)
    raise
```

---

## Core Concepts

| Concept | Description |
| :--- | :--- |
| **`Session`** | The transactional boundary of an agent workflow. All actions intercepted during a session are indexed and rolled back together as a unified unit. |
| **`wrap()`** | A dynamic proxy wrapper that intercepts method calls on any third-party SDK client, logging actions and enforcing configured safety policies. |
| **LIFO Rollback** | Last-In-First-Out compensation: actions are rolled back in strict reverse order of execution using registered connector inverse handlers. |
| **Approval Gates** | High-stakes actions configured in `requires_approval` are queued as `PENDING_APPROVAL` until approved by a team member in the AgentRein dashboard. |
| **Fail Modes** | Configurable resiliency: `failure_mode="open"` (default) allows production agents to proceed if the control plane is offline; `failure_mode="closed"` halts execution for regulated environments. |

---

## Usage Guide

### Human Approval Gates

Prevent catastrophic autonomous mistakes by requiring manual human approval for sensitive method paths:

```python
safe_github = rein.wrap(
    github_client,
    session=session,
    connector="github",
    requires_approval=["repos.delete", "issues.delete"],
    poll_interval_ms=3000,   # Check approval status every 3 seconds
    timeout_ms=300_000,      # Wait up to 5 minutes before timing out
)

# Execution will pause here until approved in the AgentRein dashboard:
safe_github.repos.delete(owner="my-org", repo="legacy-repo")
```

If the reviewer rejects the request, an `ApprovalRejectedError` is raised with the reviewer's reason. If the timeout expires without approval, an `ApprovalTimeoutError` is raised.

### Idempotent Retries

Network hiccups and rate limits shouldn't break long-running agent workflows. Specify methods in `retryable` to automatically apply jittered exponential backoff:

```python
safe_hubspot = rein.wrap(
    hubspot_client,
    session=session,
    connector="hubspot",
    retryable=["crm.contacts.basic_api.get_by_id"],
)
```

### Sandbox Simulation

When running agents in testing or dry-run modes, configure the session as a sandbox:

```python
sandbox_session = rein.new_session(
    agent_id="test-agent",
    intent="Dry-run customer notifications",
)
# If the session is marked as sandbox on the backend, safe calls return
# synthetic responses without touching third-party APIs.
```

### Fail Modes (Open vs. Closed)

```python
# Default: Fail-Open (Recommended for standard web services & AI assistants)
# If AgentRein servers are unreachable, calls proceed directly to the third-party API.
rein = AgentRein(api_key="...", failure_mode="open")

# Fail-Closed (Recommended for financial services, healthcare, security-critical ops)
# If AgentRein servers are unreachable, an AgentReinUnavailableError is raised.
rein = AgentRein(api_key="...", failure_mode="closed")
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
  Creates a new tracked safety session. If `agent_id` is omitted, a UUID is automatically generated.
- **`resume_session(session_id: str) -> Session`**  
  Retrieves an active session by ID (alias: `get_session`).
- **`wrap(client: T, session: Session, connector: str, requires_approval: list[str] | None = None, retryable: list[str] | None = None, poll_interval_ms: int = 2000, timeout_ms: int = 86_400_000) -> T`**  
  Wraps any SDK client with the AgentRein safety proxy. Returns the client cast to its original type `T`.
- **`complete_session(session: Session) -> None`**  
  Marks the session as `COMPLETED`. Locks the session and prevents further mutations.
- **`rollback_session(session: Session) -> None`**  
  Triggers server-side LIFO compensation for all recorded actions in the session.
- **`validate_config(connectors: list[str]) -> dict[str, Any]`**  
  Verifies API credentials and permissions for the specified connector names.

---

## Error Handling

AgentRein exports typed exceptions for granular error handling:

```python
from agentrein.errors import (
    AgentReinError,
    AgentReinUnavailableError,
    ApprovalRejectedError,
    ApprovalTimeoutError,
    ConfigValidationError,
    WrapOptionsValidationError,
)

try:
    safe_client.invoices.create(...)
except ApprovalRejectedError as e:
    print(f"Action {e.action_id} was rejected. Reason: {e.reason}")
except ApprovalTimeoutError as e:
    print(f"Action {e.action_id} timed out after {e.timeout_ms}ms")
except AgentReinUnavailableError as e:
    print(f"Safety control plane is unreachable: {e}")
except AgentReinError as e:
    print(f"General AgentRein error: {e}")
```

---

## Supported Connectors

AgentRein comes with built-in reversible action definitions across major enterprise platforms:

| Connector | Supported Actions | Primary Rollback Strategy |
| :--- | :--- | :--- |
| **GitHub** | 20 actions (Issues, PRs, Comments, Labels, Stars) | Soft-delete, close, or revert state |
| **Slack** | 24 actions (Messages, Threads, Reactions, Pins) | Delete message, correction reply, remove reaction |
| **Stripe** | 10 actions (Customers, Invoices, Refunds, Subscriptions) | Delete customer/draft, cancel subscription |
| **HubSpot** | 17 actions (Contacts, Deals, Companies, Tickets) | Restore `beforeState` snapshot or soft-delete |
| **Salesforce** | 28 actions (Contacts, Accounts, Leads, Opportunities) | Restore pre-execution SObject snapshot |
| **Gmail** | 16 actions (Messages, Drafts, Labels, Threads) | Move to trash, correction reply, restore labels |
| **Google Drive** | 10 actions (Files, Folders, Permissions) | Trash, restore version, undo move/permissions |
| **Google Sheets**| 8 actions (Spreadsheets, Sheets, Rows, Cells) | Clear inserted rows, restore previous cell state |
| **Notion** | 9 actions (Pages, Database Items, Blocks) | Archive page, delete block, restore properties |

---

## Development & Testing

If you are contributing to the Python SDK from inside the [AgentRein monorepo](https://github.com/agentrein/agentrein):

```bash
# 1. Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 2. Install editable package with development dependencies
pip install -e "sdk-python[dev]"

# 3. Run test suite
pytest sdk-python/tests

# 4. Run type checker and linter
mypy sdk-python/agentrein
ruff check sdk-python/agentrein
```

---

## License

Distributed under the [MIT License](https://github.com/agentrein/agentrein/blob/main/LICENSE). See `LICENSE` for more information.

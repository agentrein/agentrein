<div align="center">

# AgentRein Python SDK

### Automatic rollback for AI agents.

*AI agents can act. They shouldn't be irreversible.*

[![PyPI version](https://img.shields.io/pypi/v/agentrein.svg?style=flat-square&color=blue)](https://pypi.org/project/agentrein/)
[![Python Versions](https://img.shields.io/pypi/pyversions/agentrein.svg?style=flat-square)](https://pypi.org/project/agentrein/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=flat-square)](https://opensource.org/licenses/MIT)
[![CI Status](https://img.shields.io/github/actions/workflow/status/agentrein/agentrein/ci-python.yml?branch=main&style=flat-square&label=CI)](https://github.com/agentrein/agentrein/actions)

[Website](https://agentrein.com) • [Documentation](https://agentrein.com/docs) • [Quickstart Guide](https://agentrein.com/docs/quickstart) • [Dashboard](https://agentrein.com/dashboard) • [Report Issue](https://github.com/agentrein/agentrein/issues)

</div>

---

## The Problem

> **AI agents fail silently. And one small mistake can become a big one.**
> - **Stripe:** Invoice generated with the wrong amount.
> - **GitHub:** A record or branch deleted in production.
> - **Slack:** A message sent to the wrong customer.
> 
> *By the time you notice, it's already done. What if you could roll it back?*

**AgentRein** snapshots every action your AI agents take. When a step fails or goes off course, everything before it is rolled back automatically across every connector you use.

---

## One import. Full control.

Add a safety net to the agent you already built. **No rewrite. No new infrastructure.**

```python
from agentrein import AgentRein

rein = AgentRein(api_key="rein_api_key_...")
session = rein.new_session(agent_id="billing-agent", intent="Process monthly customer invoice")

# Wrap your existing SDK client
safe_stripe = rein.wrap(stripe_client, session=session, connector="stripe")
```

---

## Four Protective Layers

AgentRein places four reliable guardrails between your autonomous agent and a bad outcome:

```
Action ──▶ Risk Assessment ──▶ Approval Gate ──▶ Rollback Engine ──▶ Restored
```

1. 🔄 **Automatic Rollback (`Made a mistake? Undo it.`)**  
   Automatically reverse agent actions when things go wrong. AgentRein unwinds external tool calls in strict reverse order (LIFO) with zero manual cleanup.
2. 🚦 **Approval Gates (`High-risk action? Stop and ask.`)**  
   Pause critical actions (like deleting records or charging cards) for human sign-off via the AgentRein dashboard before execution.
3. 🎯 **Intent Drift Detection (`Agent drifting off course? Catch it.`)**  
   Continuous verification ensures an agent's individual tool calls remain aligned with the stated session `intent`.
4. 📋 **Unified Audit Trail (`Need to know what happened? See everything.`)**  
   Searchable, immutable execution timelines displaying full request payloads, responses, and deterministic resource URLs.

---

## Table of Contents

- [Installation](#installation)
- [Quick Start](#quick-start)
- [Framework Compatibility](#framework-compatibility)
- [Usage Guide](#usage-guide)
  - [1. Automatic Rollback](#1-automatic-rollback)
  - [2. Human Approval Gates](#2-human-approval-gates)
  - [3. Idempotent Retries](#3-idempotent-retries)
  - [4. Fail Modes (Open vs. Closed)](#4-fail-modes-open-vs-closed)
- [API Reference](#api-reference)
- [Error Handling](#error-handling)
- [Supported Connectors](#supported-connectors)
- [Development & Testing](#development--testing)
- [License](#license)

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

## Quick Start

```python
import os
import stripe
from agentrein import AgentRein, ApprovalRejectedError

# 1. Initialize AgentRein
rein = AgentRein(
    api_key=os.environ["AGENTREIN_API_KEY"],
    server_url="https://api.agentrein.com", # optional, default
    failure_mode="open",                    # 'open' (resilient) | 'closed' (strict)
)

# 2. Start a safety session with an explicit intent
session = rein.new_session(
    agent_id="finance-agent-4",
    intent="Create invoice and collect pending subscription fees",
)

try:
    # 3. Initialize your standard vendor client
    stripe_client = stripe.StripeClient(os.environ["STRIPE_API_KEY"])

    # 4. Wrap the client — no changes to underlying method calls
    safe_stripe = rein.wrap(
        stripe_client,
        session=session,
        connector="stripe",
        requires_approval=["invoices.del", "subscriptions.cancel"],
        retryable=["charges.retrieve"],
    )

    # 5. Agent executes actions
    invoice = safe_stripe.invoices.create(customer="cus_123", amount=5000)

    # 6. Complete session to lock audit record
    rein.complete_session(session)
    print("Agent workflow finished safely.")

except ApprovalRejectedError as err:
    print(f"Action rejected by dashboard reviewer: {err.reason}")
    rein.rollback_session(session)

except Exception as err:
    print(f"Workflow error: {err}. Unwinding all tool calls...")
    rein.rollback_session(session)
    raise
```

---

## Framework Compatibility

AgentRein works seamlessly across the Python AI agent ecosystem without modifying your prompt engineering or agent loops:

- **LangChain & LangGraph**
- **OpenAI Assistants & Function Calling**
- **Anthropic Tool Use**
- **Groq & LlamaIndex**
- **Mastra & Native Python Runtimes**

---

## Usage Guide

### 1. Automatic Rollback

When a multi-step agent workflow crashes halfway through, calling `rein.rollback_session(session)` triggers LIFO (last-in-first-out) compensation. Every executed tool call is reversed automatically using pre-execution snapshots and inverse handlers.

```python
try:
    # Step 1: Create issue in GitHub
    safe_github.issues.create(title="Bug Report")
    # Step 2: Notify Slack
    safe_slack.chat.post_message(channel="#eng", text="Investigating")
    # Step 3: Fails here!
    raise RuntimeError("Model hallucinated invalid payload")
except Exception:
    # Rolls back Slack (deletes message) then GitHub (closes issue)
    rein.rollback_session(session)
```

### 2. Human Approval Gates

Hold high-risk operations in a `PENDING_APPROVAL` queue until a team member confirms the action in the AgentRein dashboard:

```python
safe_github = rein.wrap(
    github_client,
    session=session,
    connector="github",
    requires_approval=["repos.delete", "issues.delete"],
    poll_interval_ms=2000,
    timeout_ms=300_000, # 5-minute timeout
)

# Execution pauses here until approved
safe_github.repos.delete(owner="my-org", repo="repo-name")
```

### 3. Idempotent Retries

Avoid failing long-running agent execution on transient 429 rate-limits or network blips:

```python
safe_hubspot = rein.wrap(
    hubspot_client,
    session=session,
    connector="hubspot",
    retryable=["crm.contacts.basic_api.get_by_id"],
)
```

### 4. Fail Modes (Open vs. Closed)

- **`failure_mode="open"` (Default)**: Production agent operations continue normally if the AgentRein control plane is temporarily unreachable.
- **`failure_mode="closed"`**: Enforces strict compliance. Intercepted calls fail fast with `AgentReinUnavailableError` if the control plane cannot be reached.

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

- **`new_session(agent_id: str | None = None, intent: str | None = None) -> Session`**  
  Starts a safety session for an agent workflow with optional goal/intent declaration.
- **`resume_session(session_id: str) -> Session`**  
  Retrieves an active session by its ID (alias: `get_session`).
- **`wrap(client: T, session: Session, connector: str, ...) -> T`**  
  Wraps any vendor SDK client with the transparent safety proxy.
- **`complete_session(session: Session) -> None`**  
  Marks the session as `COMPLETED`. Locks the execution timeline.
- **`rollback_session(session: Session) -> None`**  
  Triggers server-side LIFO compensation for all recorded actions in the session.
- **`validate_config(connectors: list[str]) -> dict[str, Any]`**  
  Verifies that configured connector credentials and permissions are healthy.

---

## Error Handling

```python
from agentrein.errors import (
    AgentReinError,
    AgentReinUnavailableError,
    ApprovalRejectedError,
    ApprovalTimeoutError,
    ConfigValidationError,
)

try:
    safe_client.execute()
except ApprovalRejectedError as e:
    print(f"Action {e.action_id} was rejected by operator: {e.reason}")
except ApprovalTimeoutError as e:
    print(f"Approval timed out after {e.timeout_ms}ms")
except AgentReinUnavailableError as e:
    print(f"AgentRein control plane unreachable: {e}")
```

---

## Supported Connectors

Works out of the box with the tools your agents already use:

| Connector | Actions | What AgentRein Does on Rollback |
| :--- | :---: | :--- |
| **Stripe** | 10 | Reverses charges & deletes invoices |
| **Slack** | 24 | Unsends messages & deletes posts |
| **GitHub** | 20 | Closes issues & reverts commits |
| **HubSpot** | 17 | Restores contacts & deals |
| **Salesforce** | 28 | Rolls back records & opportunities |
| **Gmail** | 16 | Unsends drafts & deletes threads |
| **Google Drive** | 10 | Restores files & permissions |
| **Google Sheets**| 8 | Reverts cell edits & row changes |
| **Notion** | 9 | Deletes pages & restores blocks |

---

## Development & Testing

When contributing from within the [AgentRein monorepo](https://github.com/agentrein/agentrein):

```bash
# 1. Setup virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 2. Install editable package with dev dependencies
pip install -e "sdk-python[dev]"

# 3. Run test suite
pytest sdk-python/tests
```

---

## License

Distributed under the [MIT License](https://github.com/agentrein/agentrein/blob/main/LICENSE). See `LICENSE` for more information.

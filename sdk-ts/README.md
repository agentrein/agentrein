<div align="center">

# AgentRein TypeScript SDK

**Deploy AI agents. Undo anything.**  
The reliability, rollback, and safety net for TypeScript AI agents.

[![npm version](https://img.shields.io/npm/v/agentrein.svg?style=flat-square&color=blue)](https://www.npmjs.com/package/agentrein)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.0+-3178C6.svg?style=flat-square&logo=typescript&logoColor=white)](https://www.typescriptlang.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=flat-square)](https://opensource.org/licenses/MIT)
[![CI Status](https://img.shields.io/github/actions/workflow/status/agentrein/agentrein/ci-ts.yml?branch=main&style=flat-square&label=CI)](https://github.com/agentrein/agentrein/actions)

[Website](https://agentrein.com) • [Documentation](https://agentrein.com/docs) • [Dashboard](https://agentrein.com/dashboard) • [Report Issue](https://github.com/agentrein/agentrein/issues)

</div>

---

## Overview

When autonomous AI agents make tool calls—charging credit cards, updating CRM records, sending emails, or provisioning cloud resources—any runtime error, model hallucination, or network timeout can leave external systems corrupted.

**AgentRein** acts as a safety and transaction proxy for your AI agents:
- 🔄 **Automatic LIFO Rollback**: Undoes side effects in reverse order if an agent workflow fails.
- 🚦 **Human-in-the-Loop Approval Gates**: Intercepts high-risk operations and holds execution until approved via dashboard or webhook.
- 🔁 **Idempotent Retry Engine**: Automatically retries transient connector failures with exponential backoff.
- 🧪 **Sandbox Simulation Mode**: Safely test agents against live workflows without mutating production state.
- 🛡️ **Zero-Invasive Blind Proxy**: Wrap any existing TypeScript SDK client (Stripe, Octokit, HubSpot, Slack, etc.) without altering your business logic.
- 🌐 **Fail-Open Resiliency**: Safe by default; mission-critical agent workflows are never blocked if the safety control plane is temporarily unreachable.

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

Install using your preferred package manager:

```bash
# npm
npm install agentrein

# pnpm
pnpm add agentrein

# yarn
yarn add agentrein

# bun
bun add agentrein
```

> **Note:** The SDK ships with dual CommonJS (CJS) and ECMAScript Modules (ESM) builds, fully typed with TypeScript declarations.

---

## Quick Start

```typescript
import { AgentRein, ApprovalRejectedError } from 'agentrein';
import Stripe from 'stripe';

// 1. Initialize the AgentRein client
const agentrein = new AgentRein({
  apiKey: process.env.AGENTREIN_API_KEY!,
  serverUrl: 'https://api.agentrein.com', // optional, default
  failureMode: 'open',                   // optional: 'open' | 'closed'
});

// 2. Start a safety session for your agent's task
const session = await agentrein.newSession({
  agentId: 'billing-agent-01',
  intent: 'Generate monthly invoices and handle customer refunds',
});

try {
  // 3. Initialize your standard 3rd-party client
  const stripe = new Stripe(process.env.STRIPE_SECRET_KEY!, { apiVersion: '2023-10-16' });

  // 4. Wrap the client with AgentRein protection
  const safeStripe = agentrein.wrap(stripe, session, {
    connector: 'stripe',
    requiresApproval: ['invoices.del', 'subscriptions.cancel'], // Human sign-off required
    retryable: ['charges.retrieve'],                            // Automatic backoff retry
  });

  // 5. Execute operations normally through the wrapped proxy
  const invoice = await safeStripe.invoices.create({
    customer: 'cus_12345',
    collection_method: 'send_invoice',
    days_until_due: 30,
  });

  // 6. Complete the session when workflow finishes
  await agentrein.completeSession(session);
  console.log('Session completed successfully:', session.id);

} catch (err) {
  if (err instanceof ApprovalRejectedError) {
    console.error(`Action was rejected by reviewer: ${err.reason}`);
  } else {
    console.error('Workflow error encountered. Initiating rollback...', err);
  }

  // Trigger server-side LIFO rollback for all actions in this session
  await agentrein.rollbackSession(session);
}
```

---

## Core Concepts

| Concept | Description |
| :--- | :--- |
| **`Session`** | The transactional boundary of an agent workflow. All actions intercepted during a session are indexed and rolled back together as a unified unit. |
| **`wrap()`** | A dynamic proxy wrapper that intercepts method calls on any third-party SDK client, logging actions and enforcing configured safety policies. |
| **LIFO Rollback** | Last-In-First-Out compensation: actions are rolled back in strict reverse order of execution using registered connector inverse handlers. |
| **Approval Gates** | High-stakes actions configured in `requiresApproval` are queued as `PENDING_APPROVAL` until approved by a team member in the AgentRein dashboard. |
| **Fail Modes** | Configurable resiliency: `failureMode: 'open'` (default) allows production agents to proceed if the control plane is offline; `failureMode: 'closed'` halts execution for regulated environments. |

---

## Usage Guide

### Human Approval Gates

Flag sensitive method paths with `requiresApproval` to block execution until a human operator approves the action in the AgentRein dashboard:

```typescript
const safeGitHub = agentrein.wrap(octokit, session, {
  connector: 'github',
  requiresApproval: ['repos.delete', 'issues.delete'],
  pollIntervalMs: 2500, // Check approval status every 2.5s (default: 2000ms)
  timeoutMs: 300_000,   // Wait up to 5 minutes before timing out (default: 24h)
});

// Execution pauses here until approved in the dashboard
await safeGitHub.repos.delete({ owner: 'acme-corp', repo: 'sensitive-repo' });
```

### Idempotent Retries

Handle transient HTTP timeouts and 429 rate-limit responses automatically with exponential backoff:

```typescript
const safeSlack = agentrein.wrap(slackClient, session, {
  connector: 'slack',
  retryable: ['chat.postMessage'],
});
```

### Sandbox Simulation

In sandbox sessions, destructive or live operations simulate responses using the backend schema mock engine without touching downstream production systems:

```typescript
// If session.isSandbox is true:
const simulatedResult = await safeClient.charges.create({ ... });
// Action is audited, but real charge is not processed
```

### Fail Modes (Open vs. Closed)

```typescript
// Default: Fail-Open (Recommended for web services and autonomous agents)
// Intercepted calls continue unprotected if AgentRein is unreachable.
const agentrein = new AgentRein({ apiKey: '...', failureMode: 'open' });

// Fail-Closed (Recommended for banking, healthcare, and high-compliance workloads)
// Intercepted calls fail fast with AgentReinUnavailableError if control plane is down.
const agentrein = new AgentRein({ apiKey: '...', failureMode: 'closed' });
```

---

## API Reference

### `new AgentRein(options)`

```typescript
interface AgentReinOptions {
  apiKey: string;
  serverUrl?: string;          // Default: "https://api.agentrein.com"
  failureMode?: 'open' | 'closed'; // Default: 'open'
}
```

### Methods

#### `agentrein.newSession(options?: SessionOptions | string): Promise<Session>`
Creates a new tracked safety session. Accepts either an options object or a string `agentId`.

```typescript
const session = await agentrein.newSession({
  agentId: 'support-agent',
  intent: 'Update customer address and forward ticket',
});
```

#### `agentrein.wrap<T>(client: T, session: Session, options: WrapOptions): T`
Wraps any SDK client with the safety proxy.

```typescript
interface WrapOptions {
  connector: string;
  requiresApproval?: string[];
  retryable?: string[];
  pollIntervalMs?: number; // Minimum 1000ms
  timeoutMs?: number;      // Minimum 5000ms
}
```

#### `agentrein.resumeSession(sessionId: string): Promise<Session>`
Retrieves an existing session by ID (alias: `getSession`).

#### `agentrein.completeSession(session: Session): Promise<void>`
Marks the session as `COMPLETED`. Locks the session and prevents further mutations.

#### `agentrein.rollbackSession(session: Session): Promise<void>`
Triggers server-side LIFO compensation for all recorded actions in the session.

#### `agentrein.validateConfig(connectors: string[]): Promise<Record<string, unknown>>`
Verifies API credentials and connectivity for a list of connector names.

---

## Error Handling

All custom errors extend standard `Error` and contain actionable metadata:

```typescript
import {
  AgentReinUnavailableError,
  ApprovalRejectedError,
  ApprovalTimeoutError,
  ConfigValidationError,
  WrapOptionsValidationError,
} from 'agentrein';

try {
  await safeClient.orders.cancel({ id: 'ord_123' });
} catch (error) {
  if (error instanceof ApprovalRejectedError) {
    console.error(`Approval rejected for action ${error.actionId}: ${error.reason}`);
  } else if (error instanceof ApprovalTimeoutError) {
    console.error(`Approval timed out after ${error.timeoutMs}ms`);
  } else if (error instanceof AgentReinUnavailableError) {
    console.error('AgentRein control plane unreachable:', error.message);
  }
}
```

---

## Supported Connectors

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

When developing within the [AgentRein monorepo](https://github.com/agentrein/agentrein):

```bash
# 1. Install monorepo dependencies from root
npm ci

# 2. Build types dependency
npm run build --workspace types

# 3. Typecheck the TypeScript SDK
(cd sdk-ts && npx tsc --noEmit)

# 4. Build both CommonJS and ESM outputs
npm run build --workspace agentrein
```

---

## License

Distributed under the [MIT License](https://github.com/agentrein/agentrein/blob/main/LICENSE). See `LICENSE` for more information.

# AgentRein TypeScript SDK

[![npm version](https://img.shields.io/npm/v/agentrein?logo=npm&logoColor=white&color=CB3837&style=flat-square)](https://www.npmjs.com/package/agentrein)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.0+-3178C6?logo=typescript&logoColor=white&style=flat-square)](https://www.typescriptlang.org/)
[![CI Status](https://img.shields.io/github/actions/workflow/status/agentrein/agentrein/ci-ts.yml?branch=main&label=CI&logo=github&logoColor=white&style=flat-square)](https://github.com/agentrein/agentrein/actions/workflows/ci-ts.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue?style=flat-square)](https://github.com/agentrein/agentrein/blob/main/LICENSE)

Automatic rollback and execution safety for TypeScript AI agents.

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

The package ships with dual CommonJS (CJS) and ECMAScript Modules (ESM) builds, including full TypeScript declarations.

---

## Quickstart

```typescript
import { AgentRein, ApprovalRejectedError } from 'agentrein';
import Stripe from 'stripe';

// Initialize AgentRein client
const agentrein = new AgentRein({
  apiKey: process.env.AGENTREIN_API_KEY!,
  serverUrl: 'https://api.agentrein.com', // optional
  failureMode: 'open',                   // 'open' (default) | 'closed'
});

// Start a tracked safety session
const session = await agentrein.newSession({
  agentId: 'billing-agent-01',
  intent: 'Send Q4 invoices to active corporate clients',
});

try {
  // Initialize standard vendor client
  const stripe = new Stripe(process.env.STRIPE_SECRET_KEY!, { apiVersion: '2023-10-16' });

  // Wrap the client with AgentRein safety policies
  const safeStripe = agentrein.wrap(stripe, session, {
    connector: 'stripe',
    requiresApproval: ['customers.delete', 'refunds.create'],
    retryable: ['customers.create', 'invoices.create'],
  });

  // Execute operations normally
  const invoice = await safeStripe.invoices.create({
    customer: 'cus_123',
    collection_method: 'send_invoice',
    days_until_due: 30,
  });

  // Complete session to lock the audit record
  await agentrein.completeSession(session);

} catch (err) {
  if (err instanceof ApprovalRejectedError) {
    console.error(`Action rejected by reviewer: ${err.reason}`);
  } else {
    console.error('Workflow error encountered. Unwinding tool calls...', err);
  }

  // Trigger server-side LIFO rollback for all actions in this session
  await agentrein.rollbackSession(session);
}
```

---

## Core Concepts

### Sessions

A session represents the transactional boundary of an agent workflow. All actions intercepted during a session are indexed and rolled back together as a unit. Sessions are created with `agentrein.newSession()` and finalized with either `completeSession()` or `rollbackSession()`.

### Proxy Wrapping

The `wrap()` method returns a typed proxy around any third-party SDK client. The proxy intercepts method calls at runtime, logs the action to the control plane, enforces approval rules, and captures the identifiers required for rollback. The underlying client's method signatures and return types remain unchanged.

### LIFO Rollback

When `agentrein.rollbackSession()` is invoked, the platform unwinds executed actions in reverse order of execution using registered connector inverse handlers. For example, if an agent creates a GitHub issue and then sends a Slack notification, rollback first unsends the Slack message, then closes the GitHub issue.

### Failure Modes

- **`failureMode: 'open'` (Default)**: If the AgentRein control plane is temporarily unreachable, tool calls execute directly against the vendor API to avoid blocking production agents.
- **`failureMode: 'closed'`**: Intercepted calls fail fast with `AgentReinUnavailableError` if the control plane cannot be reached. Recommended for high-compliance or financial workloads.

---

## Usage Guide

### Approval Gates

Hold high-risk operations in a pending state until a human operator confirms the action via the AgentRein dashboard:

```typescript
const safeGitHub = agentrein.wrap(octokit, session, {
  connector: 'github',
  requiresApproval: ['issues.lock', 'files.delete'],
  pollIntervalMs: 2000,
  timeoutMs: 300_000, // 5-minute timeout
});

// Execution blocks here until approved in the dashboard
await safeGitHub.issues.lock({ owner: 'acme-corp', repo: 'critical-repo', issue_number: 42, lock_reason: 'resolved' });
```

If the operator rejects the action, an `ApprovalRejectedError` is thrown. If the timeout expires without review, an `ApprovalTimeoutError` is thrown.

### Idempotent Retries

Configure automatic backoff retries for methods subject to rate limits or transient network failures:

```typescript
const safeSlack = agentrein.wrap(slackClient, session, {
  connector: 'slack',
  retryable: ['chat.postMessage'],
});
```

---

## API Reference

### `new AgentRein(options)`

```typescript
interface AgentReinOptions {
  apiKey: string;
  serverUrl?: string;              // Default: "https://api.agentrein.com"
  failureMode?: 'open' | 'closed'; // Default: 'open'
}
```

### Core Methods

- **`agentrein.newSession(options?: SessionOptions | string): Promise<Session>`**  
  Creates a new safety session. Accepts either an options object or a string `agentId`.
- **`agentrein.wrap<T>(client: T, session: Session, options: WrapOptions): T`**  
  Wraps a vendor SDK client with the safety proxy.
- **`agentrein.resumeSession(sessionId: string): Promise<Session>`**  
  Retrieves an active session by ID (alias: `getSession`).
- **`agentrein.completeSession(session: Session): Promise<void>`**  
  Marks the session as `COMPLETED`. Locks the timeline against further modifications.
- **`agentrein.rollbackSession(session: Session): Promise<void>`**  
  Triggers server-side LIFO compensation for all recorded actions in the session.
- **`agentrein.validateConfig(connectors: string[]): Promise<Record<string, unknown>>`**  
  Validates API credentials and connector health.

---

## Error Handling

All custom exceptions extend standard `Error`:

```typescript
import {
  AgentReinUnavailableError,
  ApprovalRejectedError,
  ApprovalTimeoutError,
  ConfigValidationError,
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

AgentRein operates at the client proxy layer and works with any TypeScript agent framework:

- Vercel AI SDK
- LangChain & LangGraph (JS/TS)
- Mastra
- OpenAI Assistants & Function Calling
- Native TypeScript agent loops

---

## Development & Testing

```bash
# 1. Install dependencies from monorepo root
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

Distributed under the [MIT License](https://github.com/agentrein/agentrein/blob/main/LICENSE).

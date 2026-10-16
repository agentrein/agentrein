<div align="center">

# AgentRein TypeScript SDK

### Automatic rollback for AI agents.

*AI agents can act. They shouldn't be irreversible.*

[![npm version](https://img.shields.io/npm/v/agentrein.svg?style=flat-square&color=blue)](https://www.npmjs.com/package/agentrein)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.0+-3178C6.svg?style=flat-square&logo=typescript&logoColor=white)](https://www.typescriptlang.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=flat-square)](https://opensource.org/licenses/MIT)
[![CI Status](https://img.shields.io/github/actions/workflow/status/agentrein/agentrein/ci-ts.yml?branch=main&style=flat-square&label=CI)](https://github.com/agentrein/agentrein/actions)

[Website](https://agentrein.com) • [Documentation](https://agentrein.com/docs) • [Quickstart Guide](https://agentrein.com/docs/quickstart) • [Dashboard](https://agentrein.com/dashboard) • [Report Issue](https://github.com/agentrein/agentrein/issues)

</div>

---

## The Problem

> **AI agents fail silently. And one small mistake can become a big one.**
> - **Stripe:** Invoice generated with the wrong amount.
> - **GitHub:** A record deleted in production.
> - **Slack:** A message sent to the wrong customer.
> 
> *By the time you notice, it's already done. What if you could roll it back?*

**AgentRein** snapshots every action your AI agents take. When a step fails or goes off course, everything before it is rolled back automatically across every connector you use.

---

## One import. Full control.

Add a safety net to the agent you already built. **No rewrite. No new infrastructure.**

```typescript
import { AgentRein } from 'agentrein';

const agentrein = new AgentRein({ apiKey: process.env.AGENTREIN_API_KEY! });
const session = await agentrein.newSession({ agentId: 'billing-agent', intent: 'Send Q4 invoices' });

// Wrap your existing client
const agentStripe = agentrein.wrap(stripe, session, { connector: 'stripe' });
```

---

## Four Protective Layers

AgentRein places four reliable guardrails between your autonomous agent and a bad outcome:

```
Action ──▶ Risk Assessment ──▶ Approval Gate ──▶ Rollback Engine ──▶ Restored
```

1. 🔄 **Automatic Rollback (`Made a mistake? Undo it.`)**  
   Automatically reverse agent actions when things go wrong. AgentRein unwinds tool calls in strict reverse order (LIFO) with zero manual cleanup.
2. 🚦 **Approval Gates (`High-risk action? Stop and ask.`)**  
   Pause critical actions (like deleting records or charging cards) for human sign-off via the AgentRein dashboard before execution.
3. 🎯 **Intent Drift Detection (`Agent drifting off course? Catch it.`)**  
   Detect when an agent's individual actions move away from the intended session goal.
4. 📋 **Unified Audit Trail (`Need to know what happened? See everything.`)**  
   Immutable, searchable audit trails and execution timelines for every action taken by your agents.

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

> **Note:** Ships with dual CommonJS (CJS) and ECMAScript Modules (ESM) builds, fully typed.

---

## Quick Start

```typescript
import { AgentRein, ApprovalRejectedError } from 'agentrein';
import Stripe from 'stripe';

// 1. Initialize AgentRein
const agentrein = new AgentRein({
  apiKey: process.env.AGENTREIN_API_KEY!,
  serverUrl: 'https://api.agentrein.com', // optional
  failureMode: 'open',                   // 'open' (resilient) | 'closed' (strict)
});

// 2. Start a safety session with an explicit intent
const session = await agentrein.newSession({
  agentId: 'billing-agent-01',
  intent: 'Send Q4 invoices to active corporate clients',
});

try {
  // 3. Initialize your standard vendor client
  const stripe = new Stripe(process.env.STRIPE_SECRET_KEY!, { apiVersion: '2023-10-16' });

  // 4. Wrap the client — no changes to underlying method calls
  const safeStripe = agentrein.wrap(stripe, session, {
    connector: 'stripe',
    requiresApproval: ['invoices.del', 'subscriptions.cancel'],
    retryable: ['charges.retrieve'],
  });

  // 5. Agent executes operations
  const invoice = await safeStripe.invoices.create({
    customer: 'cus_123',
    collection_method: 'send_invoice',
    days_until_due: 30,
  });

  // 6. Complete session to lock audit trail
  await agentrein.completeSession(session);
  console.log('Session completed successfully:', session.id);

} catch (err) {
  if (err instanceof ApprovalRejectedError) {
    console.error(`Action rejected by dashboard reviewer: ${err.reason}`);
  } else {
    console.error('Workflow error encountered. Initiating rollback...', err);
  }

  // Trigger server-side LIFO rollback for all actions in this session
  await agentrein.rollbackSession(session);
}
```

---

## Framework Compatibility

AgentRein integrates seamlessly with the TypeScript agent stack:

- **Vercel AI SDK**
- **LangChain & LangGraph (JS/TS)**
- **Mastra**
- **OpenAI & Anthropic SDKs**
- **Custom Agent Loops & Workflows**

---

## Usage Guide

### 1. Automatic Rollback

If an agent crashes after executing multiple mutations, `rollbackSession(session)` unwinds operations in reverse order:

```typescript
try {
  await safeGithub.issues.create({ ... });
  await safeSlack.chat.postMessage({ ... });
  throw new Error("Model hallucinated invalid parameters");
} catch (error) {
  // Unwinds Slack message, then closes GitHub issue
  await agentrein.rollbackSession(session);
}
```

### 2. Human Approval Gates

Flag sensitive method paths with `requiresApproval` to hold execution until approved from the AgentRein dashboard:

```typescript
const safeGitHub = agentrein.wrap(octokit, session, {
  connector: 'github',
  requiresApproval: ['repos.delete', 'issues.delete'],
  pollIntervalMs: 2000,
  timeoutMs: 300_000, // 5-minute timeout
});

// Execution pauses here until approved in the dashboard
await safeGitHub.repos.delete({ owner: 'acme-corp', repo: 'critical-repo' });
```

### 3. Idempotent Retries

Handle transient timeouts and 429 rate limits automatically with exponential backoff:

```typescript
const safeSlack = agentrein.wrap(slackClient, session, {
  connector: 'slack',
  retryable: ['chat.postMessage'],
});
```

### 4. Fail Modes (Open vs. Closed)

- **`failureMode: 'open'` (Default)**: If AgentRein servers are unreachable, calls proceed directly to vendor APIs to ensure uptime.
- **`failureMode: 'closed'`**: High-compliance mode. Intercepted calls fail fast with `AgentReinUnavailableError` if the safety plane cannot be reached.

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
  Starts a safety session with an optional agent ID and task intent.
- **`agentrein.wrap<T>(client: T, session: Session, options: WrapOptions): T`**  
  Wraps any third-party SDK client with the transparent safety proxy.
- **`agentrein.resumeSession(sessionId: string): Promise<Session>`**  
  Retrieves an active session by its ID (alias: `getSession`).
- **`agentrein.completeSession(session: Session): Promise<void>`**  
  Marks the session as `COMPLETED`. Locks the execution timeline.
- **`agentrein.rollbackSession(session: Session): Promise<void>`**  
  Triggers server-side LIFO compensation for all recorded actions in the session.
- **`agentrein.validateConfig(connectors: string[]): Promise<Record<string, unknown>>`**  
  Verifies API credentials and connector health.

---

## Error Handling

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

Distributed under the [MIT License](https://github.com/agentrein/agentrein/blob/main/LICENSE). See `LICENSE` for more information.

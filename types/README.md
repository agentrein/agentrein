<div align="center">

# @agentrein/types

**Canonical TypeScript definitions for AgentRein reversible-action connectors.**

[![npm version](https://img.shields.io/npm/v/@agentrein/types.svg?style=flat-square&color=blue)](https://www.npmjs.com/package/@agentrein/types)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.0+-3178C6.svg?style=flat-square&logo=typescript&logoColor=white)](https://www.typescriptlang.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=flat-square)](https://opensource.org/licenses/MIT)
[![CI Status](https://img.shields.io/github/actions/workflow/status/agentrein/agentrein/ci-ts.yml?branch=main&style=flat-square&label=CI)](https://github.com/agentrein/agentrein/actions)

[Website](https://agentrein.com) • [Documentation](https://agentrein.com/docs) • [Connectors Directory](https://github.com/agentrein/agentrein/tree/main/connectors) • [Issues](https://github.com/agentrein/agentrein/issues)

</div>

---

## Overview

`@agentrein/types` contains the canonical TypeScript type contracts and interfaces used across the AgentRein platform. It defines:

1. **Connector Architecture**: The standardized interface for defining reversible external tool integrations.
2. **Action Contracts**: Metadata requirements for each API operation (`apiName`, safety level, snapshot policy, inverse compensation handler).
3. **Safety Classifications**: The 4-tier action categorization system that dictates approval gating and rollback mechanisms.

Whether you are authoring a new community connector or building custom rollback handlers in your own infrastructure, this package provides strict compile-time type safety.

---

## Table of Contents

- [Installation](#installation)
- [Core Types Reference](#core-types-reference)
  - [`Connector`](#connector)
  - [`ConnectorAction`](#connectoraction)
  - [`OperationType`](#operationtype)
  - [`SafetyLevel`](#safetylevel)
  - [`RollbackStrategy` and `RollbackType`](#rollbackstrategy-and-rollbacktype)
  - [`RollbackContext`](#rollbackcontext)
- [Building a Connector](#building-a-connector)
- [Action Classification Rules](#action-classification-rules)
- [Mirror Synchronization in Monorepo](#mirror-synchronization-in-monorepo)
- [Development & Verification](#development--verification)
- [License](#license)

---

## Installation

Install using your preferred package manager:

```bash
# npm
npm install @agentrein/types

# pnpm
pnpm add @agentrein/types

# yarn
yarn add @agentrein/types

# bun
bun add @agentrein/types
```

---

## Core Types Reference

### `Connector`

The top-level descriptor for an integration provider:

```typescript
export interface Connector {
  connector: string;           // Unique provider slug, e.g. "github", "stripe"
  actions: ConnectorAction[];  // Array of supported action definitions
}
```

---

### `ConnectorAction`

The contract defining a single reversible API action:

```typescript
export interface ConnectorAction {
  apiName: string;                     // Flat 3-segment dot notation: provider.resource.action
  intentTag?: string;                  // Optional semantic category for intent drift analysis
  captureBeforeState: boolean;         // Whether AgentRein must snapshot existing state before execution
  operationType: OperationType;        // "CREATE" | "UPDATE" | "DELETE"
  safetyLevel: SafetyLevel;            // "LOW" | "MEDIUM" | "HIGH"
  rollback: RollbackStrategy;          // Compensation strategy and execution handler
}
```

---

### `OperationType`

String-literal union indicating the nature of the state mutation:

```typescript
export type OperationType = "CREATE" | "UPDATE" | "DELETE";
```

> **Note:** These are string-literal types, not runtime enums. Pass literal strings like `'CREATE'`, never `OperationType.CREATE`.

---

### `SafetyLevel`

Risk tier governing default human approval requirements:

```typescript
export type SafetyLevel = "LOW" | "MEDIUM" | "HIGH";
```

| Level | Intended Actions | Default Approval Policy |
| :--- | :--- | :--- |
| **`LOW`** | Low-blast-radius operations (adding a reaction, creating an issue comment). | Auto-executed without pause unless specifically gated. |
| **`MEDIUM`** | Standard business mutations (creating contacts, updating deals, modifying drafts). | Configurable per-organization or per-agent. |
| **`HIGH`** | Irreversible, destructive, or financial actions (deleting repositories, charging credit cards). | Pauses execution for human-in-the-loop sign-off. |

---

### `RollbackStrategy` and `RollbackType`

Defines how the platform undoes the action:

```typescript
export type RollbackType = "API_CALL" | "CORRECTION_MESSAGE" | "NONE";

export interface RollbackStrategy {
  type: RollbackType;
  execute: (action: unknown, context: RollbackContext, idempotencyKey?: string) => Promise<void>;
  requires: string[]; // Required scopes/credentials, e.g. ["github.token"]
}
```

- **`API_CALL`**: Executes an explicit compensation call (e.g., deleting a created resource, restoring previous state).
- **`CORRECTION_MESSAGE`**: For immutable messaging platforms (e.g., sending a correction reply in a Slack thread).
- **`NONE`**: For non-compensable actions where rollback is physically impossible.

---

### `RollbackContext`

Contains the runtime execution dependencies injected during compensation:

```typescript
export interface RollbackContext {
  client: unknown;  // Connector casts this to the vendor SDK type (e.g., Octokit, Stripe)
  orgId?: string;   // Tenant or organization identifier
}
```

---

## Building a Connector

Here is how you use `@agentrein/types` to define a production-grade connector:

```typescript
import type { Connector, RollbackContext } from '@agentrein/types';
import { Octokit } from '@octokit/rest';

interface ActionPayload {
  owner: string;
  repo: string;
  title: string;
  body?: string;
}

interface ActionResponse {
  number: number;
}

export const githubConnector: Connector = {
  connector: 'github',
  actions: [
    {
      apiName: 'github.issues.create',
      operationType: 'CREATE',
      captureBeforeState: false,
      safetyLevel: 'MEDIUM',
      rollback: {
        type: 'API_CALL',
        requires: ['github.token'],
        execute: async (rawAction, context) => {
          const client = context.client as Octokit;
          const action = rawAction as { payload: ActionPayload; response: ActionResponse };

          // Group 1 rule: Identifier is read from action.response
          await client.issues.update({
            owner: action.payload.owner,
            repo: action.payload.repo,
            issue_number: action.response.number,
            state: 'closed',
          });
        },
      },
    },
  ],
};
```

---

## Action Classification Rules

When defining actions, every connector adheres to the 4-Group system:

| Group | `operationType` | `captureBeforeState` | Rollback Mechanism |
| :--- | :--- | :--- | :--- |
| **Group 1: Create** | `CREATE` | `false` | Inverse operation (soft/hard deletion). ID read from `action.response`. |
| **Group 2: Update/Delete** | `UPDATE` \| `DELETE` | `true` | Restores snapshot state from `action.snapshot.beforeState`. |
| **Group 3: Toggle** | `UPDATE` | `false` | Self-sufficient inverse operation (e.g. lock ↔ unlock, archive ↔ unarchive). |
| **Group 4: Non-Reversible** | Varies | `false` | Destructive or non-compensable actions. Sets `safetyLevel: 'HIGH'` and `type: 'NONE'`. |

---

## Mirror Synchronization in Monorepo

Within the [AgentRein monorepo](https://github.com/agentrein/agentrein), `types/src/index.ts` is the single source of truth. 

To maintain decoupling without symlink complexity during CI:
- `connectors/types/index.ts` is a **byte-identical mirror** of `types/src/index.ts`.
- The repository includes a verification script: `scripts/check-types-mirror.sh`.
- Continuous Integration enforces that any modification to `@agentrein/types` must be mirrored identically to connectors.

---

## Development & Verification

To build and typecheck `@agentrein/types`:

```bash
# Build TypeScript declarations and JavaScript outputs
npm run build --workspace types

# Run TypeScript compiler checks without emitting files
(cd types && npx tsc --noEmit)

# Verify mirror integrity
bash scripts/check-types-mirror.sh
```

---

## License

Distributed under the [MIT License](https://github.com/agentrein/agentrein/blob/main/LICENSE). See `LICENSE` for more information.

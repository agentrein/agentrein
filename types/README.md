<div align="center">

# @agentrein/types

### Canonical TypeScript definitions for AgentRein.

*Automatic rollback for AI agents.*

[![npm version](https://img.shields.io/npm/v/@agentrein/types.svg?style=flat-square&color=blue)](https://www.npmjs.com/package/@agentrein/types)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.0+-3178C6.svg?style=flat-square&logo=typescript&logoColor=white)](https://www.typescriptlang.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=flat-square)](https://opensource.org/licenses/MIT)
[![CI Status](https://img.shields.io/github/actions/workflow/status/agentrein/agentrein/ci-ts.yml?branch=main&style=flat-square&label=CI)](https://github.com/agentrein/agentrein/actions)

[Website](https://agentrein.com) • [Documentation](https://agentrein.com/docs) • [Connectors Directory](https://github.com/agentrein/agentrein/tree/main/connectors) • [Issues](https://github.com/agentrein/agentrein/issues)

</div>

---

## Overview

`@agentrein/types` provides the canonical type contracts that power the **Four Protective Layers** of the AgentRein platform:

| Protective Layer | Type Property | Role in Contract |
| :--- | :--- | :--- |
| 🔄 **Automatic Rollback** | `action.rollback` | Encapsulates the inverse compensation strategy (`API_CALL`, `CORRECTION_MESSAGE`, `NONE`) and execution handler. |
| 🚦 **Approval Gates** | `action.safetyLevel` | Classifies risk (`LOW`, `MEDIUM`, `HIGH`) to automatically pause high-blast-radius operations for human sign-off. |
| 🎯 **Intent Drift Detection** | `action.intentTag` | Semantic classification tag matching tool calls against declared session intent. |
| 📋 **Pre-Execution Snapshots** | `action.captureBeforeState` | Flag instructing the engine to capture resource state before destructive mutation. |

Whether you are authoring a new community connector or building custom rollback handlers, this package provides compile-time type safety.

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
- [Action Classification System](#action-classification-system)
- [Mirror Synchronization](#mirror-synchronization)
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
  intentTag?: string;                  // Semantic tag for Intent Drift Detection
  captureBeforeState: boolean;         // Snapshot resource state before execution
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

> **Note:** These are string-literal types, not runtime enums. Use literal strings like `'CREATE'`, never `OperationType.CREATE`.

---

### `SafetyLevel`

Risk tier governing default human approval requirements:

```typescript
export type SafetyLevel = "LOW" | "MEDIUM" | "HIGH";
```

| Level | Typical Actions | Approval Behavior |
| :--- | :--- | :--- |
| **`LOW`** | Adding reactions, creating draft comments, minor queries. | Executed without pause unless gated by user policy. |
| **`MEDIUM`** | Standard business mutations (creating contacts, updating deals). | Configurable per-organization or per-agent. |
| **`HIGH`** | Destructive, financial, or permission mutations (deleting repos, charging cards). | Enforces human sign-off via the dashboard. |

---

### `RollbackStrategy` and `RollbackType`

Defines how the platform unwinds the tool call:

```typescript
export type RollbackType = "API_CALL" | "CORRECTION_MESSAGE" | "NONE";

export interface RollbackStrategy {
  type: RollbackType;
  execute: (action: unknown, context: RollbackContext, idempotencyKey?: string) => Promise<void>;
  requires: string[]; // Required scopes/credentials, e.g. ["github.token"]
}
```

- **`API_CALL`**: Executes an explicit compensation call (e.g., closing an issue, restoring prior snapshot).
- **`CORRECTION_MESSAGE`**: For immutable communications (e.g., sending a correction reply in a Slack thread).
- **`NONE`**: For non-compensable actions where rollback is physically impossible.

---

### `RollbackContext`

Contains the runtime execution dependencies injected during compensation:

```typescript
export interface RollbackContext {
  client: unknown;  // Connector casts this to vendor SDK type (e.g., Octokit, Stripe)
  orgId?: string;   // Tenant or organization identifier
}
```

---

## Building a Connector

```typescript
import type { Connector, RollbackContext } from '@agentrein/types';
import { Octokit } from '@octokit/rest';

interface ActionPayload {
  owner: string;
  repo: string;
  title: string;
}

interface ActionResponse {
  number: number;
}

export const githubConnector: Connector = {
  connector: 'github',
  actions: [
    {
      apiName: 'github.issues.create',
      intentTag: 'issue_tracking',
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

## Action Classification System

Every action definition follows a standardized 4-Group system:

| Group | `operationType` | `captureBeforeState` | Rollback Mechanism | Identifier Source |
| :--- | :---: | :---: | :--- | :--- |
| **Group 1: Create** | `CREATE` | `false` | Inverse deletion or closure. | `action.response` (Returned resource ID). |
| **Group 2: Update/Delete** | `UPDATE` \| `DELETE` | `true` | Restores snapshot from `action.snapshot.beforeState`. | `action.payload` + snapshot. |
| **Group 3: Toggle** | `UPDATE` | `false` | Self-sufficient inverse operation (lock ↔ unlock, archive ↔ unarchive). | Both directions independently verified. |
| **Group 4: Non-Reversible** | Varies | `false` | Destructive or non-compensable actions. Sets `safetyLevel: 'HIGH'` and `type: 'NONE'`. | Requires approval before execution. |

---

## Mirror Synchronization

Within the [AgentRein monorepo](https://github.com/agentrein/agentrein), `types/src/index.ts` is the single source of truth.

- `connectors/types/index.ts` is maintained as a **byte-identical mirror** of `types/src/index.ts`.
- The repository includes a verification script: `scripts/check-types-mirror.sh`.
- Continuous Integration enforces that any type change is mirrored identically to connectors.

---

## Development & Verification

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

<div align="center">

# AgentRein Connectors

### Automatic rollback for AI agents.

*AI agents can act. They shouldn't be irreversible.*

[![Actions Count](https://img.shields.io/badge/Actions-142%20Reversible-brightgreen.svg?style=flat-square)](https://github.com/agentrein/agentrein/tree/main/connectors)
[![Connectors Count](https://img.shields.io/badge/Connectors-9%20Platforms-blue.svg?style=flat-square)](https://github.com/agentrein/agentrein/tree/main/connectors)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=flat-square)](https://opensource.org/licenses/MIT)
[![CI Status](https://img.shields.io/github/actions/workflow/status/agentrein/agentrein/ci-ts.yml?branch=main&style=flat-square&label=CI)](https://github.com/agentrein/agentrein/actions)

[Website](https://agentrein.com) • [Documentation](https://agentrein.com/docs) • [Contributing Guide](./CONTRIBUTING.md) • [Report Issue](https://github.com/agentrein/agentrein/issues)

</div>

---

## Overview

When autonomous AI agents make tool calls across external services, unexpected errors or model hallucinations can leave third-party systems corrupted.

**AgentRein Connectors** provide the canonical contracts, snapshot rules, and inverse compensation handlers that make external tool execution safe across four protective layers:

1. 🔄 **Automatic Rollback (`Made a mistake? Undo it.`)**: Unwinds tool calls in strict reverse order (LIFO) when a step fails.
2. 🚦 **Approval Gates (`High-risk action? Stop and ask.`)**: Pauses high-risk operations for human sign-off before execution.
3. 🎯 **Intent Drift Detection (`Agent drifting off course? Catch it.`)**: Validates action tags against declared session intent.
4. 📋 **Unified Audit Trail (`Need to know what happened? See everything.`)**: Resolves deterministic resource URLs for every action to provide an immutable audit timeline.

---

## Architecture & Sync Mechanism

This directory (`connectors/`) is the **single source of truth** for all connector implementations across the AgentRein platform.

```
┌─────────────────────────────────────────────────────────────┐
│  agentrein / connectors (Public Open-Source Repository)      │
│  - connectors/connectors/*.connector.ts                      │
│  - connectors/types/index.ts (Type mirror)                  │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               │ Automated GitHub Action
                               │ (.github/workflows/sync-connectors.yml)
                               ▼
┌─────────────────────────────────────────────────────────────┐
│  agentrein / backend (Private Platform Service)             │
│  - backend/src/core/registry/connectors/ (Read-Only Mirror) │
│  - backend/src/core/registry/types.ts                       │
└─────────────────────────────────────────────────────────────┘
```

- All community and maintainer contributions are developed, tested, and reviewed here.
- When pull requests merge to `main`, an automated GitHub workflow opens a synchronization PR against the private backend registry.
- Direct edits to the backend mirror are strictly prohibited to prevent repository drift.

---

## Supported Connectors

Works out of the box with the tools your agents already use across **9 platforms** and **142 reversible actions**:

| Connector | Actions | What AgentRein Does on Rollback | Implementation File |
| :--- | :---: | :--- | :--- |
| **Stripe** | **10** | Reverses charges & deletes invoices | [`stripe.connector.ts`](./connectors/stripe.connector.ts) |
| **Slack** | **24** | Unsends messages & deletes posts | [`slack.connector.ts`](./connectors/slack.connector.ts) |
| **GitHub** | **20** | Closes issues & reverts commits | [`github.connector.ts`](./connectors/github.connector.ts) |
| **HubSpot** | **17** | Restores contacts & deals | [`hubspot.connector.ts`](./connectors/hubspot.connector.ts) |
| **Salesforce** | **28** | Rolls back records & opportunities | [`salesforce.connector.ts`](./connectors/salesforce.connector.ts) |
| **Gmail** | **16** | Unsends drafts & deletes threads | [`gmail.connector.ts`](./connectors/gmail.connector.ts) |
| **Google Drive** | **10** | Restores files & permissions | [`gdrive.connector.ts`](./connectors/gdrive.connector.ts) |
| **Google Sheets**| **8** | Reverts cell edits & row changes | [`gsheets.connector.ts`](./connectors/gsheets.connector.ts) |
| **Notion** | **9** | Deletes pages & restores blocks | [`notion.connector.ts`](./connectors/notion.connector.ts) |

---

## Action Classification System

Every action definition adheres to a standardized **4-Group Classification System**:

| Group | `operationType` | `captureBeforeState` | Rollback Mechanism | Identifier Source |
| :--- | :---: | :---: | :--- | :--- |
| **Group 1: Create** | `CREATE` | `false` | Inverse deletion or closure. | `action.response` (Returned resource ID). |
| **Group 2: Update/Delete** | `UPDATE` \| `DELETE` | `true` | Restores snapshot state from `action.snapshot.beforeState`. | `action.payload` + snapshot. |
| **Group 3: Toggle** | `UPDATE` | `false` | Self-sufficient inverse operation (lock ↔ unlock, archive ↔ unarchive). | Both directions independently verified. |
| **Group 4: Non-Reversible** | Varies | `false` | Destructive or non-compensable actions. Sets `safetyLevel: 'HIGH'` and `type: 'NONE'`. | Requires approval before execution. |

---

## Naming Conventions

All connector actions strictly implement a flat three-segment dot notation:

```
provider.resource.action
```

Examples:
- `github.issues.create`
- `slack.chat.postMessage`
- `salesforce.contacts.update`
- `stripe.invoices.del`

### Rules
1. **Segment Count**: Exactly three dot-separated segments.
2. **Compound Sub-Resources**: Represent sub-entities in camelCase within the second segment (e.g., `github.issueComments.create`, **not** `github.issues.comments.create`).
3. **Composite Keys**: For operations identified by tuples rather than a single ID (e.g., Slack reactions requiring `channel` + `timestamp` + `name`), read parameters directly from `action.payload` and document the exception in code comments.

---

## Authoring a Connector

To implement a new connector or add actions to an existing one:

1. **Use the Template**: Copy [`examples/custom-connector.example.ts`](./examples/custom-connector.example.ts) to `connectors/<name>.connector.ts`.
2. **Implement Actions**: Define actions adhering strictly to the `@agentrein/types` contracts.
3. **Standard Error Formatting**: All thrown rollback exceptions must match this exact format:
   ```typescript
   `[${connectorName}Connector] rollback failed | action: ${id} | org: ${orgId} | op: ${op} | reason: ...`
   ```
4. **Idempotent 404 Handling**: API `404 Not Found` errors during deletion must be swallowed silently to prevent rollback failure when resources were already removed.
5. **Resource URL Resolvers**: Provide null-safe URL resolvers for all actions to populate audit logs in the user dashboard.

For complete development guidelines, review our [Contributing Guide](./CONTRIBUTING.md).

---

## Verification & Testing

Before submitting a pull request, verify that all connectors compile without errors:

```bash
# 1. Install dependencies from monorepo root
npm ci

# 2. Build canonical types
npm run build --workspace types

# 3. Verify types mirror is byte-identical
bash scripts/check-types-mirror.sh

# 4. Run TypeScript compiler across all connectors
cd connectors && npx tsc --noEmit
```

---

## License

Distributed under the [MIT License](https://github.com/agentrein/agentrein/blob/main/LICENSE). See `LICENSE` for more information.

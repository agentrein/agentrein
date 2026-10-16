# AgentRein Connectors

[![CI Status](https://img.shields.io/github/actions/workflow/status/agentrein/agentrein/ci-ts.yml?branch=main&style=flat-square)](https://github.com/agentrein/agentrein/actions)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg?style=flat-square)](https://opensource.org/licenses/MIT)
[![Reversible Actions](https://img.shields.io/badge/actions-142%20reversible-333333.svg?style=flat-square)](https://agentrein.com)

Reversible action contracts and compensation handlers for AI agent tool calls.

[Documentation](https://agentrein.com/docs) | [Contributing Guide](CONTRIBUTING.md) | [Website](https://agentrein.com) | [Report Issue](https://github.com/agentrein/agentrein/issues)

---

## Overview

When autonomous AI agents interact with external platforms (GitHub, Slack, Salesforce, Stripe, Google Workspace), any runtime error, model hallucination, or network timeout can leave third-party systems in an inconsistent state.

AgentRein Connectors provide the canonical contracts, snapshot rules, and inverse compensation handlers required for deterministic rollback. Each connector defines:

- **Pre-execution snapshot policy**: Dictates whether pre-existing resource state must be captured prior to mutating operations.
- **Compensation routines**: Explicit handlers that reverse side-effects in last-in, first-out (LIFO) order.
- **Safety classification**: Risk levels (`LOW`, `MEDIUM`, `HIGH`) that determine whether an action requires human approval before execution.
- **Audit resolvers**: Deterministic resource URL builders that provide deep links into vendor dashboards for every logged action.

---

## Architecture & Synchronization

This directory is the single source of truth for all connector implementations across the AgentRein platform.

```
+-------------------------------------------------------------+
|  Public Repository (agentrein/connectors)                   |
|  - connectors/*.connector.ts                                |
|  - types/index.ts (Type mirror)                             |
+------------------------------+------------------------------+
                               |
                               | Automated GitHub Action
                               | (.github/workflows/sync-connectors.yml)
                               v
+-------------------------------------------------------------+
|  Private Platform Service (agentrein/backend)               |
|  - src/core/registry/connectors/ (Read-only mirror)         |
|  - src/core/registry/types.ts                               |
+-------------------------------------------------------------+
```

- Connector definitions are authored, tested, and reviewed in this repository.
- Merging to `main` triggers an automated GitHub workflow that submits a synchronization pull request against the private backend registry.
- Direct edits to the backend mirror are prohibited to prevent repository drift.

---

## Supported Connectors

The repository includes 9 production connectors covering 142 reversible actions:

| Connector | Actions | Supported Primitives | Rollback Mechanism | Implementation |
| :--- | :---: | :--- | :--- | :--- |
| **Stripe** | 10 | Customers, Invoices, Payment Links, Subscriptions, Refunds | Deletes draft invoices, cancels subscriptions, refunds charges | [`stripe.connector.ts`](./connectors/stripe.connector.ts) |
| **Slack** | 24 | Messages, Threads, Reactions, Pins, Channel Topics | Deletes messages, posts thread correction replies, removes reactions | [`slack.connector.ts`](./connectors/slack.connector.ts) |
| **GitHub** | 20 | Issues, Comments, Pull Requests, Reviews, Labels, Stars | Closes issues, soft-deletes comments, unstars repos, reverts states | [`github.connector.ts`](./connectors/github.connector.ts) |
| **HubSpot** | 17 | Contacts, Companies, Deals, Tickets, Line Items | Restores `beforeState` snapshot or soft-deletes created entities | [`hubspot.connector.ts`](./connectors/hubspot.connector.ts) |
| **Salesforce** | 28 | Contacts, Accounts, Leads, Opportunities, Custom SObjects | Restores pre-execution SObject snapshot or deletes created records | [`salesforce.connector.ts`](./connectors/salesforce.connector.ts) |
| **Gmail** | 16 | Messages, Drafts, Labels, Threads, Signatures | Trashes sent messages, restores labels, posts correction replies | [`gmail.connector.ts`](./connectors/gmail.connector.ts) |
| **Google Drive** | 10 | Files, Folders, Permissions, Revisions | Trashes files, reverts permissions, restores previous revisions | [`gdrive.connector.ts`](./connectors/gdrive.connector.ts) |
| **Google Sheets**| 8 | Spreadsheets, Sheets, Rows, Cell Ranges | Clears inserted rows, restores overwritten cell ranges | [`gsheets.connector.ts`](./connectors/gsheets.connector.ts) |
| **Notion** | 9 | Pages, Database Items, Blocks, Comments | Archives pages, deletes blocks, restores properties | [`notion.connector.ts`](./connectors/notion.connector.ts) |

---

## Action Classification System

Every action definition follows a standardized four-group classification:

| Group | `operationType` | `captureBeforeState` | Rollback Strategy | Identifier Source |
| :--- | :---: | :---: | :--- | :--- |
| **Group 1: Create** | `CREATE` | `false` | Inverse deletion or closure. | `action.response` (Resource ID returned by API). |
| **Group 2: Update / Delete** | `UPDATE` \| `DELETE` | `true` | Restores snapshot state from `action.snapshot.beforeState`. | `action.payload` (Target ID) + snapshot. |
| **Group 3: Toggle** | `UPDATE` | `false` | Self-sufficient inverse operation (e.g. lock/unlock, archive/unarchive). | Both directions independently verified against SDK. |
| **Group 4: Non-Reversible** | Varies | `false` | Destructive or non-compensable. Sets `safetyLevel: 'HIGH'` and `type: 'NONE'`. | Requires manual approval before execution. |

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
1. **Segment count**: Exactly three dot-separated segments.
2. **Compound sub-resources**: Represent nested resources using camelCase in the second segment (e.g., `github.issueComments.create`, not `github.issues.comments.create`).
3. **Composite identifiers**: For resources identified by compound keys rather than a single entity ID (e.g., Slack reactions requiring `channel` + `timestamp` + `name`), read parameters directly from `action.payload` and document the exception in code comments.

---

## Implementation Standards

All connector pull requests must comply with the following standards:

1. **Deterministic error formatting**: Thrown rollback exceptions must match this exact format:
   ```typescript
   `[${connectorName}Connector] rollback failed | action: ${id} | org: ${orgId} | op: ${op} | reason: ...`
   ```
2. **Idempotent 404 handling**: HTTP `404 Not Found` responses encountered during deletion or rollback must be caught and swallowed silently to ensure idempotency.
3. **Null-safe resource URL resolvers**: Every action must define a `resourceUrlResolver` that returns a valid URL string or `null` without throwing errors.
4. **No speculative fallbacks**: Select a single deterministic API endpoint and document the rationale in an inline comment. Do not attempt chained fallbacks.

---

## Authoring a New Connector

1. Copy [`examples/custom-connector.example.ts`](./examples/custom-connector.example.ts) to `connectors/<name>.connector.ts`.
2. Define actions adhering to `@agentrein/types` contracts.
3. Verify that all dependencies are declared in `package.json`.
4. Run compiler and mirror verification checks.

For complete development and contribution guidelines, see [CONTRIBUTING.md](./CONTRIBUTING.md).

---

## Verification & Testing

Verify that all connectors pass strict TypeScript type checks:

```bash
# 1. Install dependencies from monorepo root
npm ci

# 2. Build canonical types
npm run build --workspace types

# 3. Verify types mirror integrity
bash scripts/check-types-mirror.sh

# 4. Typecheck connectors workspace
cd connectors && npx tsc --noEmit
```

---

## License

Distributed under the [MIT License](https://github.com/agentrein/agentrein/blob/main/LICENSE).

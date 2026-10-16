# AgentRein Core

> Deploy AI agents. Undo anything.

AgentRein is an AI agent reliability platform: wrap existing AI agents with automatic rollback, human approval gates, intent drift detection, and unified audit logs across external tools.

This repository (`agentrein-core`) contains the core open-source components of AgentRein: the TypeScript and Python SDKs, canonical type definitions, and reversible action connectors.

## Installation

```bash
# TypeScript SDK
npm install agentrein

# Python SDK
pip install agentrein

# TypeScript Types for Connectors
npm install @agentrein/types
```

## Packages

| Package | Language | Registry | Directory | Description |
|---|---|---|---|---|
| `agentrein` | TypeScript | [npm](https://www.npmjs.com/package/agentrein) | [`sdk-ts/`](sdk-ts/) | AgentRein TypeScript SDK with automatic rollback and approval gates |
| `agentrein` | Python | [PyPI](https://pypi.org/project/agentrein/) | [`sdk-python/`](sdk-python/) | AgentRein Python SDK for AI agent execution tracking and undo |
| `@agentrein/types` | TypeScript | [npm](https://www.npmjs.com/package/@agentrein/types) | [`types/`](types/) | Canonical type definitions for connectors, safety levels, and rollback contracts |

## Connectors

The [`connectors/`](connectors/) directory provides **9 connectors / 142 reversible actions**.

Connectors define standard action contracts, resource URL resolvers, pre-execution snapshot rules, and inverse compensation handlers across third-party APIs:

- **GitHub** (20 actions)
- **Slack** (24 actions)
- **Gmail** (16 actions)
- **Google Drive** (10 actions)
- **Google Sheets** (8 actions)
- **HubSpot** (17 actions)
- **Notion** (9 actions)
- **Salesforce** (28 actions)
- **Stripe** (10 actions)

Connectors are open for community contributions and are not published as an npm package. Changes to connectors are type-checked in CI and proposed to the platform registry through an automated pull request that a maintainer reviews.

## Contributing

We welcome community contributions, especially new connectors and connector actions! Please see our [Contributing Guide](CONTRIBUTING.md) for architecture patterns, testing instructions, and checklists.

## Note on Architecture

The AgentRein backend server and web dashboard are proprietary components and are not part of this repository. This repository houses only the open-source client libraries, canonical types, and connector definitions.

## License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.

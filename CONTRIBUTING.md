# Contributing to AgentRein

Thank you for your interest in contributing to AgentRein! This repository houses the core open-source components of the AgentRein reliability platform.

## Repository Layout

- [`sdk-ts/`](sdk-ts/): AgentRein TypeScript SDK (`agentrein` on npm).
- [`sdk-python/`](sdk-python/): AgentRein Python SDK (`agentrein` on PyPI).
- [`types/`](types/): Canonical TypeScript type definitions (`@agentrein/types` on npm).
- [`connectors/`](connectors/): Reversible action connectors across third-party APIs.

> **Working on Connectors?** Connector action definitions follow specific safety classification rules, naming standards, and rollback contracts. Please read the [Connector Contribution Guide](connectors/CONTRIBUTING.md) before submitting connector PRs.

## Local Setup & Verification

### TypeScript Projects (`sdk-ts`, `types`, `connectors`)

Install workspace dependencies and build the types package from the repository root:

```bash
# Install workspace dependencies
npm ci

# Verify byte-identical types mirror
bash scripts/check-types-mirror.sh

# Build types package (required before checking connectors or building sdk-ts)
npm run build --workspace types

# Typecheck each TypeScript package
(cd sdk-ts && npx tsc --noEmit)
(cd types && npx tsc --noEmit)
(cd connectors && npx tsc --noEmit)

# Build TypeScript SDK (dual CJS/ESM build)
npm run build --workspace agentrein
```

### Python SDK (`sdk-python`)

Create a virtual environment and run the test suite:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e "sdk-python[dev]"
pytest sdk-python/tests
```

## Pull Request Guidelines

- Keep PRs small, focused, and scoped to a single logical change.
- Ensure all relevant checks pass locally before opening a pull request.
- CI workflows (`ci-ts.yml` and `ci-python.yml`) must pass on GitHub before PRs are merged.

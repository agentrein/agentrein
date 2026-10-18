# Contributing to AgentRein

Thank you for your interest in contributing to AgentRein! This repository houses the core open-source components of the AgentRein reliability and execution-safety platform.

---

## Repository Layout

- [`sdk-ts/`](sdk-ts/): AgentRein TypeScript SDK (`agentrein` on npm).
- [`sdk-python/`](sdk-python/): AgentRein Python SDK (`agentrein` on PyPI).
- [`types/`](types/): Canonical TypeScript type definitions (`@agentrein/types` on npm).
- [`connectors/`](connectors/): Reversible action connectors across third-party APIs.

---

## What Can You Contribute?

We welcome community contributions across all layers of the monorepo:

1. **Connectors & Actions**: Adding support for new vendor APIs (e.g. Jira, Linear, Discord, AWS) or adding missing actions to existing connectors.
2. **Client SDK Features**: Improving transparent proxy performance, adding framework integrations (e.g., LangGraph, Vercel AI SDK), or refining error handling.
3. **Bug Reports & Fixes**: Submitting reproducible bug reports or PRs with accompanying test cases.
4. **Documentation**: Improving code examples, correcting discrepancies, or expanding usage guides.

---

## Contributing Connectors

Connectors represent the largest area of community contribution. Each connector defines reversible action contracts, pre-execution snapshot rules, and inverse compensation handlers for a specific third-party provider.

### Core Rules for Connector Actions

1. **Strict 3-Segment Dot Notation:**  
   All action names must follow `provider.resource.action`:
   - `github.issues.create`
   - `slack.chat.postMessage`
   - `stripe.invoices.create`
   *(Compound sub-resources use camelCase in the second segment, e.g. `github.issueComments.create`).*

2. **Standard 4-Group Classification:**
   - **Group 1 (Create):** Reversible via inverse deletion or closure. Resource ID is read from `action.response`.
   - **Group 2 (Update / Delete):** Reversible via state restoration. Requires pre-execution snapshot (`captureBeforeState: true`). Restores state from `action.snapshot.beforeState`.
   - **Group 3 (Toggle):** Reversible via inverse operation (e.g. lock/unlock). Self-sufficient without state capture.
   - **Group 4 (High-Risk / Non-Reversible):** Destructive or financial operations where inverse action is physically impossible. Set `safetyLevel: 'HIGH'` and `rollback: { type: 'NONE' }`.

3. **Null-Safe Resource URL Resolvers:**  
   Every action must provide a `resourceUrlResolver` that returns a vendor dashboard URL (or `null`) without throwing runtime errors.

### Workflow: Adding or Modifying a Connector

- **To add an action:** Locate the matching file in `connectors/connectors/<name>.connector.ts` and add the action definition.
- **To create a new connector:** Copy [`connectors/examples/custom-connector.example.ts`](connectors/examples/custom-connector.example.ts) to `connectors/connectors/<newprovider>.connector.ts`.

> [!TIP]
> **Deep Engineering Specification:** For detailed guidelines on error format strings, idempotent 404 handling, mirror synchronization, and backend registration, consult the dedicated [Connectors Contributing Guide](connectors/CONTRIBUTING.md).

---

## Local Setup & Verification

### TypeScript Workspaces (`sdk-ts`, `types`, `connectors`)

Install workspace dependencies and verify type correctness from the repository root:

```bash
# 1. Install workspace dependencies
npm ci

# 2. Verify byte-identical types mirror
bash scripts/check-types-mirror.sh

# 3. Build types package (required before checking connectors or building sdk-ts)
npm run build --workspace types

# 4. Typecheck each TypeScript workspace
(cd sdk-ts && npx tsc --noEmit)
(cd types && npx tsc --noEmit)
(cd connectors && npx tsc --noEmit)

# 5. Build TypeScript SDK (produces dual CJS/ESM outputs in sdk-ts/dist/)
npm run build --workspace agentrein
```

### Python SDK (`sdk-python`)

Create a virtual environment and run the test suite:

```bash
# 1. Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 2. Install editable package with dev dependencies
pip install -e "sdk-python[dev]"

# 3. Run test suite
pytest sdk-python/tests
```

---

## Pull Request Guidelines

Before opening a pull request, ensure:
- [ ] PR is small, focused, and scoped to a single logical change.
- [ ] All local verification checks pass cleanly (typechecks, mirror verification, and tests).
- [ ] Added connector actions adhere to the 3-segment naming standard and 4-group classification.
- [ ] Automated CI workflows (`ci-ts.yml` and `ci-python.yml`) pass on GitHub.

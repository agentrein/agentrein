# @agentrein/types

TypeScript types for building AgentRein rollback connectors.

## Install

```bash
npm install @agentrein/types
```

## Usage

```typescript
import type { Connector, ConnectorAction, RollbackContext } from '@agentrein/types';
import { Octokit } from '@octokit/rest';

export const myConnector: Connector = {
  connector: 'my-service',
  actions: [
    {
      apiName: 'my-service.items.create',
      operationType: 'CREATE',
      captureBeforeState: false,
      safetyLevel: 'MEDIUM',
      rollback: {
        type: 'API_CALL',
        execute: async (rawAction, context) => {
          const client = context.client as MySDKClient;
          // your rollback logic here
        },
        requires: ['my-service.apiKey'],
      },
    },
  ],
};
```

## Types

| Type | Description |
|------|-------------|
| `Connector` | Top-level connector definition |
| `ConnectorAction` | Single action with rollback strategy |
| `RollbackContext` | Contains the injected SDK client |
| `RollbackStrategy` | The rollback execute function + metadata |
| `SafetyLevel` | `LOW`, `MEDIUM`, or `HIGH` |
| `OperationType` | `CREATE`, `UPDATE`, or `DELETE` |

## Links
- [AgentRein](https://agentrein.com)
- [Connectors Repo](https://github.com/agentrein/agentrein/tree/main/connectors)
- [Docs](https://agentrein.com/docs)

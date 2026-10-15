export type SafetyLevel = 'LOW' | 'MEDIUM' | 'HIGH';

export type OperationType = 'CREATE' | 'UPDATE' | 'DELETE';

export interface RollbackContext {
  /**
   * The SDK client for the connector.
   * Cast to the appropriate type inside your connector:
   * const client = context.client as Octokit;
   */
  client: unknown;
}

export interface RollbackStrategy {
  type: 'API_CALL' | 'CORRECTION_MESSAGE' | 'NONE';
  execute: (
    action: unknown,
    context: RollbackContext,
    idempotencyKey?: string,
  ) => Promise<void>;
  requires: string[];
}

export interface ConnectorAction {
  apiName: string;
  operationType: OperationType;
  captureBeforeState: boolean;
  safetyLevel: SafetyLevel;
  rollback: RollbackStrategy;
}

export interface Connector {
  connector: string;
  actions: ConnectorAction[];
}

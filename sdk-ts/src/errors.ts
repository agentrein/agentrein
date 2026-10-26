/**
 * Custom errors for the AgentRein SDK.
 */

export class AgentReinUnavailableError extends Error {
    constructor(message?: string) {
        super(message ?? 'AgentRein safety layer is unavailable');
        this.name = 'AgentReinUnavailableError';
    }
}

export class ApprovalRejectedError extends Error {
  public readonly approvalId: string;
  public readonly reason: string | undefined;
  constructor(approvalId: string, reason?: string) {
    super(`Approval ${approvalId} was rejected${reason ? ': ' + reason : ''}`);
    this.name = 'ApprovalRejectedError';
    this.approvalId = approvalId;
    this.reason = reason;
    Object.setPrototypeOf(this, ApprovalRejectedError.prototype);
  }
}

export class ApprovalTimeoutError extends Error {
  public readonly approvalId: string;
  public readonly timeoutMs: number;
  constructor(approvalId: string, timeoutMs: number) {
    super(`Approval ${approvalId} timed out after ${timeoutMs}ms`);
    this.name = 'ApprovalTimeoutError';
    this.approvalId = approvalId;
    this.timeoutMs = timeoutMs;
    Object.setPrototypeOf(this, ApprovalTimeoutError.prototype);
  }
}

export class ConfigValidationError extends Error {
    constructor(message: string) {
        super(message);
        this.name = 'ConfigValidationError';
        Object.setPrototypeOf(this, ConfigValidationError.prototype);
    }
}

export class WrapOptionsValidationError extends Error {
    constructor(message: string) {
        super(message);
        this.name = 'WrapOptionsValidationError';
        Object.setPrototypeOf(this, WrapOptionsValidationError.prototype);
    }
}

export class AgentReinDeniedError extends Error {
    public readonly status: number;
    public readonly errorType: string;
    public readonly detail: string;

    constructor(status: number, errorType: string, detail: string) {
        super(`AgentRein denied request (${status} ${errorType}): ${detail}`);
        this.name = 'AgentReinDeniedError';
        this.status = status;
        this.errorType = errorType;
        this.detail = detail;
        Object.setPrototypeOf(this, AgentReinDeniedError.prototype);
    }
}

export function isServerDecision(err: unknown): boolean {
    if (err && typeof err === 'object' && 'response' in err) {
        const res = (err as { response?: { status?: number } }).response;
        if (res && typeof res.status === 'number') {
            return res.status === 401 || res.status === 403 || res.status === 409 || res.status === 429;
        }
    }
    return false;
}

export function toServerDeniedError(err: unknown): AgentReinDeniedError {
    if (err && typeof err === 'object' && 'response' in err) {
        const resp = (err as { response?: { status?: number; data?: unknown } }).response;
        const status = resp?.status ?? 500;
        let errorType = 'unknown';
        let detail = (err instanceof Error ? err.message : '') || 'Server denied request';

        const data = resp?.data;
        if (data && typeof data === 'object') {
            const errObj = ('error' in data && (data as any).error && typeof (data as any).error === 'object')
                ? (data as any).error
                : data;
            const rawType = (errObj as any).type;
            if (typeof rawType === 'string' && rawType.length > 0) {
                if (rawType.includes('/')) {
                    errorType = rawType.replace(/\/$/, '').split('/').pop() || rawType;
                } else {
                    errorType = rawType;
                }
            }
            const rawDetail = (errObj as any).detail || (errObj as any).title || (errObj as any).message;
            if (typeof rawDetail === 'string' && rawDetail.length > 0) {
                detail = rawDetail;
            }
        }
        return new AgentReinDeniedError(status, errorType, detail);
    }
    return new AgentReinDeniedError(500, 'unknown', err instanceof Error ? err.message : String(err));
}

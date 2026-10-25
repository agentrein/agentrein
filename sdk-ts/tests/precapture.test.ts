import { describe, it, expect, vi, beforeEach } from 'vitest';
import axios from 'axios';
import { AgentRein } from '../src/agentreinClient';
import { AgentReinDeniedError } from '../src/errors';
import type { Session } from '../src/agentreinClient';

vi.mock('axios');

function makeSession(isSandbox = false): Session {
    return {
        id: 'sess_prec_ts_123',
        organizationId: 'org_123',
        agentId: 'agent_123',
        intent: 'test precapture',
        status: 'ACTIVE',
        isSandbox,
        createdAt: '2026-10-25T00:00:00Z',
        updatedAt: '2026-10-25T00:00:00Z',
    };
}

describe('TypeScript SDK Wrap and Precapture Parity (SKI-24)', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        vi.mocked(axios.post).mockImplementation(async (url: string) => {
            if (url.includes('/auth/token')) {
                return { data: { data: { token: 'mock-token' } } } as any;
            }
            if (url.includes('/actions/precapture')) {
                return { data: { data: { precaptureId: 'snap_prec_ts_001', captureFailed: false } } } as any;
            }
            if (url.includes('/actions')) {
                return { data: { data: { id: 'act_ts_1', status: 'SUCCESS' } } } as any;
            }
            return { data: { data: {} } } as any;
        });

        vi.mocked(axios.get).mockImplementation(async (url: string) => {
            if (url.includes('/registry')) {
                return {
                    data: {
                        data: [
                            { apiName: 'stripe.customers.update', captureBeforeState: true },
                            { apiName: 'stripe.customers.delete', captureBeforeState: true },
                            { apiName: 'slack.messages.post', captureBeforeState: false },
                        ],
                    },
                } as any;
            }
            return { data: { data: {} } } as any;
        });
    });

    it('CREATE operation skips precapture call', async () => {
        const client = new AgentRein({ apiKey: 'ar_test_key' });
        const vendor = {
            create: vi.fn().mockResolvedValue({ id: 'cus_new' }),
        };

        const wrapped = client.wrap(vendor, makeSession(), { connector: 'stripe.customers' });
        const result = await wrapped.create({ email: 'new@example.com' });

        expect(result).toEqual({ id: 'cus_new' });
        expect(vendor.create).toHaveBeenCalledTimes(1);

        const precaptureCalls = vi.mocked(axios.post).mock.calls.filter(c => String(c[0]).includes('/actions/precapture'));
        expect(precaptureCalls.length).toBe(0);

        const actionCalls = vi.mocked(axios.post).mock.calls.filter(c => String(c[0]).endsWith('/actions'));
        expect(actionCalls.length).toBe(1);
        const actionBody = actionCalls[0][1] as any;
        expect(actionBody.operationType).toBe('CREATE');
        expect(actionBody.precaptureId).toBeUndefined();
    });

    it('UPDATE operation executes precapture and attaches precaptureId to action log', async () => {
        const client = new AgentRein({ apiKey: 'ar_test_key' });
        const vendor = {
            update: vi.fn().mockResolvedValue({ id: 'cus_upd', email: 'updated@example.com' }),
        };

        const wrapped = client.wrap(vendor, makeSession(), { connector: 'stripe.customers' });
        const result = await wrapped.update({ id: 'cus_upd', email: 'updated@example.com' });

        expect(result).toEqual({ id: 'cus_upd', email: 'updated@example.com' });

        const precaptureCalls = vi.mocked(axios.post).mock.calls.filter(c => String(c[0]).includes('/actions/precapture'));
        expect(precaptureCalls.length).toBe(1);
        expect(precaptureCalls[0][1]).toEqual({
            apiName: 'stripe.customers.update',
            payload: { id: 'cus_upd', email: 'updated@example.com' },
        });

        const actionCalls = vi.mocked(axios.post).mock.calls.filter(c => String(c[0]).endsWith('/actions'));
        expect(actionCalls.length).toBe(1);
        const actionBody = actionCalls[0][1] as any;
        expect(actionBody.operationType).toBe('UPDATE');
        expect(actionBody.precaptureId).toBe('snap_prec_ts_001');
    });

    it('skips precapture when registry sets captureBeforeState to false', async () => {
        const client = new AgentRein({ apiKey: 'ar_test_key' });
        const vendor = {
            post: vi.fn().mockResolvedValue({ ok: true }),
        };

        const wrapped = client.wrap(vendor, makeSession(), { connector: 'slack.messages' });
        await wrapped.post({ text: 'hello' });

        const precaptureCalls = vi.mocked(axios.post).mock.calls.filter(c => String(c[0]).includes('/actions/precapture'));
        expect(precaptureCalls.length).toBe(0);
    });

    it('transient failure in precapture logs warning and passes captureFailed: true', async () => {
        const client = new AgentRein({ apiKey: 'ar_test_key' });
        vi.mocked(axios.post).mockImplementation(async (url: string) => {
            if (url.includes('/auth/token')) {
                return { data: { data: { token: 'mock-token' } } } as any;
            }
            if (url.includes('/actions/precapture')) {
                throw new Error('Precapture network timeout');
            }
            if (url.includes('/actions')) {
                return { data: { data: { id: 'act_ts_1', status: 'SUCCESS' } } } as any;
            }
            return { data: { data: {} } } as any;
        });

        const vendor = {
            delete: vi.fn().mockResolvedValue({ deleted: true }),
        };

        const wrapped = client.wrap(vendor, makeSession(), { connector: 'stripe.customers' });
        const res = await wrapped.delete({ id: 'cus_1' });

        expect(res).toEqual({ deleted: true });
        const actionCalls = vi.mocked(axios.post).mock.calls.filter(c => String(c[0]).endsWith('/actions'));
        const actionBody = actionCalls[0][1] as any;
        expect(actionBody.captureFailed).toBe(true);
        expect(actionBody.precaptureId).toBeUndefined();
    });

    it('server decision 403 on precapture throws AgentReinDeniedError and blocks call', async () => {
        const client = new AgentRein({ apiKey: 'ar_test_key' });
        vi.mocked(axios.post).mockImplementation(async (url: string) => {
            if (url.includes('/auth/token')) {
                return { data: { data: { token: 'mock-token' } } } as any;
            }
            if (url.includes('/actions/precapture')) {
                const err = {
                    isAxiosError: true,
                    response: {
                        status: 403,
                        data: {
                            error: {
                                type: 'https://agentrein.com/errors/policy-blocked',
                                title: 'Policy Blocked',
                                status: 403,
                                detail: 'Precapture forbidden',
                            },
                        },
                    },
                };
                throw err;
            }
            return { data: { data: {} } } as any;
        });

        const vendor = {
            delete: vi.fn().mockResolvedValue({ deleted: true }),
        };

        const wrapped = client.wrap(vendor, makeSession(), { connector: 'stripe.customers' });
        await expect(wrapped.delete({ id: 'cus_1' })).rejects.toThrow(AgentReinDeniedError);
        expect(vendor.delete).not.toHaveBeenCalled();
    });

    it('approval gate path includes precaptureId in PENDING_APPROVAL action', async () => {
        const client = new AgentRein({ apiKey: 'ar_test_key' });
        let pendingActionPayload: any = null;

        vi.mocked(axios.post).mockImplementation(async (url: string, body: any) => {
            if (url.includes('/auth/token')) {
                return { data: { data: { token: 'mock-token' } } } as any;
            }
            if (url.includes('/actions/precapture')) {
                return { data: { data: { precaptureId: 'snap_appr_ts_1', captureFailed: false } } } as any;
            }
            if (url.includes('/actions')) {
                pendingActionPayload = body;
                return {
                    data: {
                        data: {
                            id: 'act_appr_1',
                            status: 'PENDING_APPROVAL',
                            approvalRequest: { id: 'appr_req_1' },
                        },
                    },
                } as any;
            }
            return { data: { data: {} } } as any;
        });

        vi.mocked(axios.get).mockImplementation(async (url: string) => {
            if (url.includes('/registry')) {
                return {
                    data: {
                        data: [{ apiName: 'stripe.customers.delete', captureBeforeState: true }],
                    },
                } as any;
            }
            if (url.includes('/approvals/')) {
                return { data: { data: { status: 'APPROVED' } } } as any;
            }
            return { data: { data: {} } } as any;
        });

        vi.mocked(axios.patch).mockResolvedValue({ data: { data: { status: 'SUCCESS' } } } as any);

        const vendor = {
            delete: vi.fn().mockResolvedValue({ deleted: true }),
        };

        const wrapped = client.wrap(vendor, makeSession(), {
            connector: 'stripe.customers',
            requiresApproval: ['delete'],
        });

        const res = await wrapped.delete({ id: 'cus_1' });
        expect(res).toEqual({ deleted: true });
        expect(pendingActionPayload).not.toBeNull();
        expect(pendingActionPayload.status).toBe('PENDING_APPROVAL');
        expect(pendingActionPayload.precaptureId).toBe('snap_appr_ts_1');
    });
});

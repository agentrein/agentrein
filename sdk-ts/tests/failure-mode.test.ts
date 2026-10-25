import { describe, it, expect, vi, beforeEach } from 'vitest';
import axios from 'axios';
import { AgentRein } from '../src/agentreinClient';
import {
    AgentReinDeniedError,
    AgentReinUnavailableError,
    isServerDecision,
    toServerDeniedError,
} from '../src/errors';
import type { Session } from '../src/agentreinClient';

vi.mock('axios');

function makeSession(isSandbox = false): Session {
    return {
        id: 'sess_123',
        organizationId: 'org_123',
        agentId: 'agent_123',
        intent: 'test intent',
        status: 'ACTIVE',
        isSandbox,
        createdAt: '2026-10-25T00:00:00Z',
        updatedAt: '2026-10-25T00:00:00Z',
    };
}

function makeAxiosError(status: number, typeSlug = 'policy-blocked', detail = 'Action blocked') {
    return {
        isAxiosError: true,
        response: {
            status,
            data: {
                error: {
                    type: `https://agentrein.com/errors/${typeSlug}`,
                    title: 'Denied',
                    status,
                    detail,
                },
            },
        },
        message: `Request failed with status code ${status}`,
    };
}

describe('SDK failureMode Option A & Server Decisions', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        // Default token response
        vi.mocked(axios.post).mockImplementation(async (url: string) => {
            if (url.includes('/auth/token')) {
                return { data: { data: { token: 'mock-token' } } } as any;
            }
            if (url.includes('/registry')) {
                return { data: { data: [] } } as any;
            }
            return { data: { data: {} } } as any;
        });
        vi.mocked(axios.get).mockImplementation(async (url: string) => {
            if (url.includes('/registry')) {
                return { data: { data: [] } } as any;
            }
            return { data: { data: {} } } as any;
        });
    });

    describe('isServerDecision & toServerDeniedError', () => {
        it('identifies 401, 403, 409, 429 as server decisions and not others', () => {
            expect(isServerDecision(makeAxiosError(401))).toBe(true);
            expect(isServerDecision(makeAxiosError(403))).toBe(true);
            expect(isServerDecision(makeAxiosError(409))).toBe(true);
            expect(isServerDecision(makeAxiosError(429))).toBe(true);

            expect(isServerDecision(makeAxiosError(200))).toBe(false);
            expect(isServerDecision(makeAxiosError(500))).toBe(false);
            expect(isServerDecision(makeAxiosError(503))).toBe(false);
            expect(isServerDecision(new Error('Network error'))).toBe(false);
        });

        it('parses RFC 7807 problem details correctly', () => {
            const err = toServerDeniedError(makeAxiosError(403, 'plan-required', 'Upgrade to PRO'));
            expect(err).toBeInstanceOf(AgentReinDeniedError);
            expect(err.status).toBe(403);
            expect(err.errorType).toBe('plan-required');
            expect(err.detail).toBe('Upgrade to PRO');
        });
    });

    describe('wrap() with requiresApproval', () => {
        const statuses = [401, 403, 409, 429] as const;
        const modes = ['open', 'closed'] as const;

        for (const status of statuses) {
            for (const mode of modes) {
                it(`raises AgentReinDeniedError and NEVER executes target function on ${status} in ${mode} mode`, async () => {
                    const client = new AgentRein({ apiKey: 'ar_test_key', failureMode: mode });
                    vi.mocked(axios.post).mockImplementation(async (url: string) => {
                        if (url.includes('/auth/token')) {
                            return { data: { data: { token: 'mock-token' } } } as any;
                        }
                        if (url.includes('/actions')) {
                            throw makeAxiosError(status, 'policy-blocked', 'Action blocked by policy');
                        }
                        return { data: { data: {} } } as any;
                    });

                    const targetFn = vi.fn().mockResolvedValue('executed');
                    const vendor = { deleteItem: targetFn };

                    const wrapped = client.wrap(vendor, makeSession(), {
                        connector: 'stripe',
                        requiresApproval: ['deleteItem'],
                    });

                    await expect(wrapped.deleteItem({ id: 'item_1' })).rejects.toThrow(AgentReinDeniedError);
                    expect(targetFn).not.toHaveBeenCalled();
                });
            }
        }

        it('falls open and executes target function on 5xx under open mode', async () => {
            const client = new AgentRein({ apiKey: 'ar_test_key', failureMode: 'open' });
            vi.mocked(axios.post).mockImplementation(async (url: string) => {
                if (url.includes('/auth/token')) {
                    return { data: { data: { token: 'mock-token' } } } as any;
                }
                if (url.includes('/actions')) {
                    throw makeAxiosError(500, 'internal-error', 'Server error');
                }
                return { data: { data: {} } } as any;
            });

            const targetFn = vi.fn().mockResolvedValue('executed_fall_open');
            const vendor = { deleteItem: targetFn };

            const wrapped = client.wrap(vendor, makeSession(), {
                connector: 'stripe',
                requiresApproval: ['deleteItem'],
            });

            const result = await wrapped.deleteItem({ id: 'item_1' });
            expect(result).toBe('executed_fall_open');
            expect(targetFn).toHaveBeenCalledTimes(1);
        });
    });

    describe('standard path post-execution logging', () => {
        const statuses = [401, 403, 409, 429] as const;
        for (const status of statuses) {
            it(`raises AgentReinDeniedError when server denies log action on ${status}`, async () => {
                const client = new AgentRein({ apiKey: 'ar_test_key', failureMode: 'open' });
                vi.mocked(axios.post).mockImplementation(async (url: string) => {
                    if (url.includes('/auth/token')) {
                        return { data: { data: { token: 'mock-token' } } } as any;
                    }
                    if (url.includes('/actions')) {
                        throw makeAxiosError(status, 'policy-blocked', 'Post-check policy block');
                    }
                    return { data: { data: {} } } as any;
                });

                const targetFn = vi.fn().mockResolvedValue('vendor_success');
                const vendor = { createMessage: targetFn };

                const wrapped = client.wrap(vendor, makeSession(), {
                    connector: 'slack',
                });

                await expect(wrapped.createMessage({ text: 'hi' })).rejects.toThrow(AgentReinDeniedError);
            });
        }
    });

    describe('lifecycle methods (newSession, rollbackSession, completeSession)', () => {
        const statuses = [401, 403, 409, 429] as const;

        for (const status of statuses) {
            it(`newSession throws AgentReinDeniedError on ${status}`, async () => {
                const client = new AgentRein({ apiKey: 'ar_test_key', failureMode: 'open' });
                vi.mocked(axios.post).mockImplementation(async (url: string) => {
                    if (url.includes('/auth/token')) {
                        return { data: { data: { token: 'mock-token' } } } as any;
                    }
                    if (url.includes('/sessions')) {
                        throw makeAxiosError(status, 'quota-exceeded', 'Quota exceeded');
                    }
                    return { data: { data: {} } } as any;
                });

                await expect(client.newSession({ agentId: 'test' })).rejects.toThrow(AgentReinDeniedError);
            });

            it(`rollbackSession throws AgentReinDeniedError on ${status}`, async () => {
                const client = new AgentRein({ apiKey: 'ar_test_key', failureMode: 'open' });
                vi.mocked(axios.post).mockImplementation(async (url: string) => {
                    if (url.includes('/auth/token')) {
                        return { data: { data: { token: 'mock-token' } } } as any;
                    }
                    if (url.includes('/rollback')) {
                        throw makeAxiosError(status, 'plan-required', 'Upgrade required');
                    }
                    return { data: { data: {} } } as any;
                });

                await expect(client.rollbackSession(makeSession())).rejects.toThrow(AgentReinDeniedError);
            });

            it(`completeSession throws AgentReinDeniedError on ${status}`, async () => {
                const client = new AgentRein({ apiKey: 'ar_test_key', failureMode: 'open' });
                vi.mocked(axios.patch).mockImplementation(async () => {
                    throw makeAxiosError(status, 'conflict', 'Session cannot be completed');
                });

                await expect(client.completeSession(makeSession())).rejects.toThrow(AgentReinDeniedError);
            });
        }

        it('rollbackSession and completeSession log warning and do not throw on 5xx under open mode', async () => {
            const client = new AgentRein({ apiKey: 'ar_test_key', failureMode: 'open' });
            vi.mocked(axios.post).mockImplementation(async (url: string) => {
                if (url.includes('/auth/token')) {
                    return { data: { data: { token: 'mock-token' } } } as any;
                }
                if (url.includes('/rollback')) {
                    throw makeAxiosError(500, 'internal-error', 'Server error');
                }
                return { data: { data: {} } } as any;
            });
            vi.mocked(axios.patch).mockImplementation(async () => {
                throw makeAxiosError(503, 'unavailable', 'DB error');
            });

            const consoleSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});

            await expect(client.rollbackSession(makeSession())).resolves.toBeUndefined();
            await expect(client.completeSession(makeSession())).resolves.toBeUndefined();

            expect(consoleSpy).toHaveBeenCalledTimes(2);
            consoleSpy.mockRestore();
        });

        it('newSession throws AgentReinDeniedError when agent is paused (HTTP 403 agent-paused)', async () => {
            const client = new AgentRein({ apiKey: 'ar_test_key', failureMode: 'open' });
            vi.mocked(axios.post).mockImplementation(async (url: string) => {
                if (url.includes('/auth/token')) {
                    return { data: { data: { token: 'mock-token' } } } as any;
                }
                if (url.endsWith('/sessions')) {
                    throw makeAxiosError(403, 'agent-paused', 'Agent "test-agent" is paused');
                }
                return { data: { data: {} } } as any;
            });

            await expect(client.newSession({ agentId: 'test-agent' })).rejects.toThrow(AgentReinDeniedError);
            try {
                await client.newSession({ agentId: 'test-agent' });
            } catch (err) {
                expect(err).toBeInstanceOf(AgentReinDeniedError);
                const denied = err as AgentReinDeniedError;
                expect(denied.status).toBe(403);
                expect(denied.errorType).toBe('agent-paused');
                expect(denied.detail).toBe('Agent "test-agent" is paused');
            }
        });
    });
});

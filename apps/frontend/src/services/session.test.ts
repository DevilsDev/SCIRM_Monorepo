import { describe, expect, it, vi } from 'vitest';
import { decodeJwt, isAuthRequest, isExpired, Session, TokenStorage } from './session';

function memoryStorage(initial: Record<string, string> = {}): TokenStorage & { data: Record<string, string> } {
  const data = { ...initial };
  return {
    data,
    getItem: (k) => (k in data ? data[k] : null),
    setItem: (k, v) => { data[k] = v; },
    removeItem: (k) => { delete data[k]; },
  };
}

function jwt(payload: Record<string, unknown>): string {
  const b64 = (o: unknown) => btoa(JSON.stringify(o)).replace(/=+$/, '').replace(/\+/g, '-').replace(/\//g, '_');
  return `${b64({ alg: 'HS256' })}.${b64(payload)}.sig`;
}

const inAnHour = () => Math.floor(Date.now() / 1000) + 3600;
const anHourAgo = () => Math.floor(Date.now() / 1000) - 3600;

describe('tokens', () => {
  it('decodes claims and spots expiry', () => {
    const token = jwt({ sub: 'u1', email: 'a@b.c', name: 'A', roles: ['admin'], exp: inAnHour() });
    expect(decodeJwt(token)).toMatchObject({ id: 'u1', email: 'a@b.c', roles: ['admin'] });
    expect(isExpired(token)).toBe(false);
    expect(isExpired(jwt({ sub: 'u1', exp: anHourAgo() }))).toBe(true);
    expect(isExpired('undefined')).toBe(true);
    expect(isExpired(null)).toBe(true);
  });

  it('recognises auth endpoints, whose 401s belong to the form', () => {
    expect(isAuthRequest('/api/v1/auth/login')).toBe(true);
    expect(isAuthRequest('/api/v1/auth/mfa/verify')).toBe(true);
    expect(isAuthRequest('/api/v1/auth/refresh')).toBe(true);
    expect(isAuthRequest('/api/v1/suppliers')).toBe(false);
    expect(isAuthRequest('/api/v1/auth/mfa/setup')).toBe(false);
  });
});

describe('Session', () => {
  it('counts a live refresh token as a session even when the access token has expired', () => {
    const s = new Session(memoryStorage({
      auth_token: jwt({ sub: 'u', exp: anHourAgo() }),
      refresh_token: jwt({ sub: 'u', exp: inAnHour() }),
    }), async () => 'x');
    expect(s.hasSession()).toBe(true);
  });

  it('refreshes once for many simultaneous 401s', async () => {
    const fresh = jwt({ sub: 'u', exp: inAnHour() });
    const refresher = vi.fn(async () => fresh);
    const storage = memoryStorage({ refresh_token: jwt({ sub: 'u', exp: inAnHour() }) });
    const s = new Session(storage, refresher);
    const results = await Promise.all([s.handleUnauthorized(), s.handleUnauthorized(), s.handleUnauthorized()]);
    expect(results).toEqual([fresh, fresh, fresh]);
    expect(refresher).toHaveBeenCalledTimes(1);
    expect(storage.data.auth_token).toBe(fresh);
  });

  it('ends the session once when refreshing fails, however many requests fail', async () => {
    const storage = memoryStorage({ auth_token: 'a', refresh_token: jwt({ sub: 'u', exp: inAnHour() }) });
    const s = new Session(storage, async () => { throw new Error('401'); });
    const expired = vi.fn();
    s.onExpired(expired);
    expect(await Promise.all([s.handleUnauthorized(), s.handleUnauthorized()])).toEqual([null, null]);
    expect(await s.handleUnauthorized()).toBeNull();
    expect(expired).toHaveBeenCalledTimes(1);
    expect(storage.data).toEqual({});
  });

  it('ends at once without a refresh token, and can start again after signing in', async () => {
    const storage = memoryStorage({ auth_token: 'a' });
    const s = new Session(storage, vi.fn());
    const expired = vi.fn();
    s.onExpired(expired);
    expect(await s.handleUnauthorized()).toBeNull();
    s.start('new-access', 'new-refresh');
    expect(storage.data).toEqual({ auth_token: 'new-access', refresh_token: 'new-refresh' });
    await s.handleUnauthorized(); // 'new-refresh' is not a valid token: ends again, and tells listeners again
    expect(expired).toHaveBeenCalledTimes(2);
  });
});

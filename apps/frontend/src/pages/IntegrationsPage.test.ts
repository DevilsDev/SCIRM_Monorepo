import { describe, expect, it, vi } from 'vitest';

// The page imports the API client, which needs a browser; only the helpers are tested.
vi.mock('../services/api', () => ({ api: {} }));
vi.mock('../contexts/AuthContext', () => ({ useAuth: () => ({}) }));

import { sapHealth, sourceHealth } from './IntegrationsPage';

const NOW = new Date('2026-10-23T12:00:00Z');

describe('sourceHealth', () => {
  it('flags failed, rate-limited, stale and never-run sources', () => {
    expect(sourceHealth({ label: 'x', status: 'error' }, NOW).tone).toBe('bad');
    expect(sourceHealth({ label: 'x', status: 'rate_limited' }, NOW).tone).toBe('warn');
    expect(sourceHealth({ label: 'x', status: 'never_run' }, NOW).tone).toBe('off');
    expect(sourceHealth({ label: 'x', status: 'ok', last_success_at: '2026-10-21T12:00:00+00:00' }, NOW).tone).toBe('warn');
  });

  it('reads zone-less times as UTC', () => {
    expect(sourceHealth({ label: 'x', status: 'ok', last_success_at: '2026-10-23T11:00:00' }, NOW).tone).toBe('ok');
  });
});

describe('sapHealth', () => {
  const base = { id: '1', system: 'sap' as const, base_url: 'https://s4', sap_client: null, username: 'u',
    has_password: true, last_import: null, updated_at: '' };
  it('summarises the connection', () => {
    expect(sapHealth(null).tone).toBe('off');
    expect(sapHealth({ ...base, last_test: null }).tone).toBe('warn');
    expect(sapHealth({ ...base, last_test: { ok: false, checks: [], at: '' } }).tone).toBe('bad');
    expect(sapHealth({ ...base, last_test: { ok: true, checks: [], at: '' } }).tone).toBe('ok');
    expect(sapHealth({ ...base, last_test: { ok: true, checks: [], at: '' },
      last_import: { kind: 'spend', ok: false, error: 'x', at: '' } }).tone).toBe('bad');
  });
});

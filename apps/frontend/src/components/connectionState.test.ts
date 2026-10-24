import { describe, expect, it, vi } from 'vitest';

// The component module imports the API client and auth context, which need a browser.
vi.mock('../services/api', () => ({ api: {} }));
vi.mock('../contexts/AuthContext', () => ({ useAuth: () => ({ user: null }) }));

import { connectionState } from './SapConnectionPanel';
import type { SapConnection } from '../services/api';

const base: SapConnection = {
  id: 'c1', system: 'sap', base_url: 'https://my-s4.example.com', sap_client: '100', username: 'SCIRM_COMM',
  has_password: true, last_test: null, last_import: null, updated_at: '2026-10-21T10:00:00',
};

describe('connectionState', () => {
  it('reports no connection, untested, working and failing', () => {
    expect(connectionState(null)).toBe('none');
    expect(connectionState(base)).toBe('untested');
    expect(connectionState({ ...base, last_test: { ok: true, checks: [], at: 'x' } })).toBe('ok');
    expect(connectionState({ ...base, last_test: { ok: false, checks: [], at: 'x' } })).toBe('failing');
  });
});

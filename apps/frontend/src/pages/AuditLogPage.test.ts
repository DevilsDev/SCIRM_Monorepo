import { describe, expect, it, vi } from 'vitest';

// The page imports the API client, which needs a browser; only the helpers are tested.
vi.mock('../services/api', () => ({ api: {} }));
vi.mock('../contexts/AuthContext', () => ({ useAuth: () => ({}) }));

import { dayRange, describeAction } from './AuditLogPage';

describe('describeAction', () => {
  it('names known actions and routes in plain language', () => {
    expect(describeAction('auth.login_failed')).toBe('Failed sign-in');
    expect(describeAction('POST /api/v1/org/invitations')).toBe('Invited a teammate');
    expect(describeAction('PATCH /api/v1/org/members/{member_id}')).toBe("Changed a teammate's role or access");
  });

  it('falls back to the verb and resource, then to the raw action', () => {
    expect(describeAction('DELETE /api/v1/risk-events/{id}')).toBe('Deleted risk events');
    expect(describeAction('something.new')).toBe('something.new');
  });
});

describe('dayRange', () => {
  it('turns local days into a UTC range with an exclusive end', () => {
    const { since, until } = dayRange('2026-10-01', '2026-10-01');
    expect(new Date(until!).getTime() - new Date(since!).getTime()).toBe(24 * 3600 * 1000);
    expect(new Date(since!).getDate()).toBe(1); // midnight local time on the day chosen
  });

  it('leaves out bounds that are not set', () => {
    expect(dayRange('', '')).toEqual({});
  });
});

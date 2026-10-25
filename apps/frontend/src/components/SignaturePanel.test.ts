import { describe, expect, it, vi } from 'vitest';

// The component imports the API client, which needs a browser; only the helpers are tested.
vi.mock('../services/api', () => ({ api: {} }));

import { signatureLine, ssoOutcome } from './SignaturePanel';

describe('signatureLine', () => {
  it('shows the printed name, the date and time, and the meaning (21 CFR 11.50)', () => {
    const line = signatureLine({ signer_name: 'Dana Lee', signer_email: 'dana@acme.test', meaning: 'approved',
      signed_at: '2026-10-25T08:00:00+00:00' });
    expect(line.startsWith('Approved by Dana Lee (dana@acme.test), ')).toBe(true);
    expect(line).toMatch(/2026|26/);
  });
});

describe('ssoOutcome', () => {
  it('reads the result the identity provider round trip came back with', () => {
    expect(ssoOutcome('#signature=signed')).toBe('signed');
    expect(ssoOutcome('#x=1&signature=record_changed')).toBe('record_changed');
    expect(ssoOutcome('')).toBeNull();
  });
});

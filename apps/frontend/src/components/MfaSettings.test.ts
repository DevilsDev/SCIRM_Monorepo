import { describe, expect, it, vi } from 'vitest';

// The component module imports the API client, which needs a browser; only groupKey is tested.
vi.mock('../services/api', () => ({ api: {} }));

import { groupKey } from './MfaSettings';

describe('groupKey', () => {
  it('shows the key in groups of four, as authenticator apps do', () => {
    expect(groupKey('JBSWY3DPEHPK3PXP')).toBe('JBSW Y3DP EHPK 3PXP');
    expect(groupKey('ABCDEF')).toBe('ABCD EF');
  });
});

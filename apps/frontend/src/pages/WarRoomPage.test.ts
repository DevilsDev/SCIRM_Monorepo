import { describe, expect, it, vi } from 'vitest';

// The page imports the API client, which needs a browser; only the helper is tested.
vi.mock('../services/api', () => ({ api: {} }));
vi.mock('../contexts/AuthContext', () => ({ useAuth: () => ({}) }));

import { formatMoney } from './WarRoomPage';

describe('formatMoney', () => {
  it('formats an amount in its own currency', () => {
    expect(formatMoney('1000.5', 'EUR')).toMatch(/1,000\.50|1\.000,50|1 000,50/);
    expect(formatMoney('1000.5', 'EUR')).toContain('€');
  });

  it('falls back to the raw amount for unknown codes or values', () => {
    expect(formatMoney('12', 'XY')).toBe('12 XY');
    expect(formatMoney('n/a', 'EUR')).toBe('n/a EUR');
  });
});

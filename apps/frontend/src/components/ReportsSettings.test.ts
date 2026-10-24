import { describe, expect, it, vi } from 'vitest';

// The component module imports the API client, which needs a browser; only hourLabel is tested.
vi.mock('../services/api', () => ({ api: {} }));

import { hourLabel } from './ReportsSettings';

describe('hourLabel', () => {
  it('shows the UTC hour and the same moment in local time', () => {
    const label = hourLabel(7, new Date('2026-10-23T12:00:00Z'));
    expect(label.startsWith('07:00 UTC (')).toBe(true);
    expect(label.endsWith('your time)')).toBe(true);
  });
});

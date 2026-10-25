import { describe, expect, it, vi } from 'vitest';

// The page imports the API client, which needs a browser; only the helper is tested.
vi.mock('../services/api', () => ({ api: {} }));
vi.mock('../contexts/AuthContext', () => ({ useAuth: () => ({}) }));

import { describeDefinition } from './ScenarioStudioPage';
import { formatTotals, sumByCurrency } from '../services/money';

describe('describeDefinition', () => {
  it('says who is out and for how long', () => {
    expect(describeDefinition({ scope: { type: 'country', country: 'in' }, duration_weeks: 4 })).toBe('Suppliers in IN out for 4 weeks');
    expect(describeDefinition({ scope: { type: 'all' }, duration_weeks: 1 })).toBe('All suppliers out for 1 week');
  });
});

describe('money', () => {
  it('sums per currency and never across currencies', () => {
    const totals = sumByCurrency([{ EUR: '100', USD: '5' }, { EUR: '50.25' }, null]);
    expect(totals).toEqual({ EUR: 150.25, USD: 5 });
    expect(formatTotals({})).toBe('-');
    expect(formatTotals(totals)).toContain(' + ');
  });
});

import { describe, expect, it, vi } from 'vitest';

// The component module imports the API client, which needs a browser; only formatSpend is tested.
vi.mock('../services/api', () => ({ api: {} }));

import { formatSpend, spendParts } from './SapSpendImport';

describe('spendParts', () => {
  it('puts the main currency first and never invents a zero in it', () => {
    expect(spendParts({ USD: '12000', EUR: '900' }, 'EUR')).toEqual([formatSpend('900', 'EUR'), formatSpend('12000', 'USD')]);
    expect(spendParts({ JPY: '3000000' }, 'EUR')).toEqual([formatSpend('3000000', 'JPY')]);
    expect(spendParts({}, 'EUR')).toEqual([]);
  });
});

describe('formatSpend', () => {
  it('formats in the given currency without converting', () => {
    expect(formatSpend('7500.00', 'EUR')).toMatch(/7[,.\s ]?500/);
    expect(formatSpend('7500.00', 'EUR')).toMatch(/€|EUR/);
    expect(formatSpend('123', 'JPY')).toMatch(/123/);
  });

  it('shows a dash when there is no spend or currency', () => {
    expect(formatSpend(undefined, 'EUR')).toBe('–');
    expect(formatSpend('5', null)).toBe('–');
  });

  it('falls back to plain digits for an unknown currency code', () => {
    expect(formatSpend('1000', 'XQQ')).toMatch(/1[,.\s ]?000/);
  });
});

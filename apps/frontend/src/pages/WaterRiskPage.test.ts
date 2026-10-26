import { describe, expect, it, vi } from 'vitest';

// The page imports the API client, which needs a browser; only the helpers are tested.
vi.mock('../services/api', () => ({ api: {} }));
import { atLeast, indicatorOf, sortSites } from './WaterRiskPage';
import { categoryRank, siteNote } from '../components/SupplierWaterRisk';
import type { WaterSite } from '../services/api';

function site(supplier: string, bws: number | null, extra: Partial<WaterSite> = {}): WaterSite {
  return {
    supplier, label: `${supplier} plant`, status: 'inside', precision: 'exact',
    indicators: [{ key: 'bws', name: 'Baseline water stress', group: 'quantity', category: bws, label: `cat ${bws}`, raw: null }],
    future_water_stress: [{ scenario: 'bau', scenario_label: 'Business as usual', year: '2050', period: '', category: 2, label: 'x' }],
    ...extra,
  };
}

describe('water risk page', () => {
  it('puts the highest WRI category first and no data last', () => {
    const ordered = sortSites([site('Arid', -1), site('None', -9999), site('High', 3), site('Low', 0), site('Missing', null)], 'bws');
    expect(ordered.map((s) => s.supplier)).toEqual(['High', 'Low', 'Arid', 'Missing', 'None']);
  });

  it('filters by a minimum category without counting no data or special classes', () => {
    expect(atLeast([site('A', 4), site('B', 3), site('C', -1), site('D', -9999)], 'bws', 3).map((s) => s.supplier)).toEqual(['A', 'B']);
  });

  it('reads projections by scenario and year', () => {
    expect(indicatorOf(site('A', 1), 'future:bau:2050')?.category).toBe(2);
    expect(indicatorOf(site('A', 1), 'future:pes:2030')).toBeUndefined();
  });

  it('ranks special classes above no data', () => {
    expect(categoryRank(-1)).toBeGreaterThan(categoryRank(-9999));
    expect(categoryRank(null)).toBe(categoryRank(-9999));
  });

  it('says how a site was placed when it matters', () => {
    expect(siteNote(site('A', 1))).toBe('');
    expect(siteNote(site('A', 1, { precision: 'city' }))).toContain('city centre');
    expect(siteNote(site('A', 1, { status: 'nearest', distance_km: 5.6 }))).toContain('5.6 km');
    expect(siteNote(site('A', 1, { near_boundary: true }))).toContain('boundary');
  });
});

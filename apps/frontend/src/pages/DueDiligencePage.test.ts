import { describe, expect, it, vi } from 'vitest';

// The page imports the API client, which needs a browser; only the helpers are tested.
vi.mock('../services/api', () => ({ api: {} }));
vi.mock('../contexts/AuthContext', () => ({ useAuth: () => ({}) }));
import { attentionOrder, ratingText, REVIEW_LABEL } from './DueDiligencePage';
import type { DdOverviewRow, DdReview } from '../services/api';

const catalog = {
  likelihood: { 1: 'Unlikely', 2: 'Possible', 3: 'Likely', 4: 'Very likely or occurring' },
  severity: { 1: 'Low', 2: 'Moderate', 3: 'High', 4: 'Severe' },
};

function row(name: string, state: DdReview['state'], severity = 0, openRisks = 0): DdOverviewRow {
  return {
    supplier_id: name, name, country_code: null, site_countries: [], spend_12m: null, spend_main_currency: null,
    spend_rank: null, incidents: 0, questionnaires: 0, open_risks: openRisks, open_measures: 0,
    top_risk: severity ? { area: 'fair_wage', likelihood: 2, severity } : null,
    review: { state, last_review: null, next_review: null, reasons: [] },
  };
}

describe('due diligence page', () => {
  it('states severity before likelihood, in words', () => {
    expect(ratingText(catalog, 2, 4)).toBe('Severity severe, likelihood possible');
  });

  it('puts suppliers that need attention first', () => {
    const ordered = attentionOrder([
      row('Current', 'current', 4, 1), row('Never', 'not_analysed'), row('Due', 'due'),
      row('Suggested low', 'suggested', 1, 1), row('Suggested high', 'suggested', 3, 1),
    ]);
    expect(ordered.map((r) => r.name)).toEqual(['Due', 'Suggested high', 'Suggested low', 'Never', 'Current']);
  });

  it('labels every review state', () => {
    expect(Object.keys(REVIEW_LABEL).sort()).toEqual(['current', 'due', 'not_analysed', 'suggested']);
  });
});

import { describe, expect, it, vi } from 'vitest';

// The page imports the API client, which needs a browser; only the helper is tested.
vi.mock('../services/api', () => ({ api: {} }));
vi.mock('../contexts/AuthContext', () => ({ useAuth: () => ({}) }));

import { highlightParts } from './RegulatoryWatchPage';

describe('highlightParts', () => {
  it('marks watched terms as whole words, ignoring case', () => {
    expect(highlightParts('Recall: METFORMIN HCl tablets', ['metformin'])).toEqual([
      { text: 'Recall: ', hit: false }, { text: 'METFORMIN', hit: true }, { text: ' HCl tablets', hit: false }]);
    expect(highlightParts('Metformina', ['metformin'])).toEqual([{ text: 'Metformina', hit: false }]);
  });

  it('treats terms as text, not patterns', () => {
    expect(highlightParts('a (b) c', ['(b)']).some((p) => p.hit)).toBe(false);
    expect(highlightParts('axb', ['a.b'])).toEqual([{ text: 'axb', hit: false }]);
  });
});

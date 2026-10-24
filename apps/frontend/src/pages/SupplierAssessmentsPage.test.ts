import { describe, expect, it, vi } from 'vitest';

// The page imports the API client, which needs a browser; only the helpers are tested.
vi.mock('../services/api', () => ({ api: {} }));
vi.mock('../contexts/AuthContext', () => ({ useAuth: () => ({}) }));

import { formatAnswer } from './SupplierAssessmentsPage';
import { portalToken } from '../services/portal';
import type { AssessmentQuestion } from '../services/api';

const q = (type: AssessmentQuestion['type']): AssessmentQuestion => ({ id: 'q', text: 'Q', type, required: false });

describe('formatAnswer', () => {
  it('shows supplier answers as plain text', () => {
    expect(formatAnswer(q('yes_no'), 'yes')).toBe('Yes');
    expect(formatAnswer(q('yes_no'), 'no')).toBe('No');
    expect(formatAnswer(q('number'), 6)).toBe('6');
    expect(formatAnswer(q('text'), '')).toBe('-');
    expect(formatAnswer(q('subtier'), [{ name: 'A' }, { name: 'B' }])).toBe('2 listed');
  });
});

describe('portalToken', () => {
  it('reads the token from the link fragment', () => {
    expect(portalToken('#abc_DEF-123')).toBe('abc_DEF-123');
    expect(portalToken('')).toBe('');
  });
});

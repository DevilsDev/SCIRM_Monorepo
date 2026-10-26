import { describe, expect, it, vi } from 'vitest';

vi.mock('../contexts/AuthContext', () => ({ useAuth: () => ({}) }));

import { readHandoff } from './SsoCompletePage';

describe('readHandoff', () => {
  it('reads the code and destination from the fragment', () => {
    expect(readHandoff('#code=abc123&next=/suppliers%3Fx%3D1')).toEqual({ code: 'abc123', next: '/suppliers?x=1' });
  });

  it('never leaves the app', () => {
    for (const next of ['https://evil.example.com', '//evil.example.com', '/\\evil', 'javascript:alert(1)']) {
      expect(readHandoff(`#code=c&next=${encodeURIComponent(next)}`).next).toBe('/dashboard');
    }
  });

  it('copes with a missing code', () => {
    expect(readHandoff('')).toEqual({ code: '', next: '/dashboard' });
  });
});

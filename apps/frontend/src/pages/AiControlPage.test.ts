import { describe, expect, it, vi } from 'vitest';

// The page imports the API client, which needs a browser; only the helper is tested.
vi.mock('../services/api', () => ({ api: {} }));
vi.mock('../contexts/AuthContext', () => ({ useAuth: () => ({}) }));

import { describeRun } from './AiControlPage';
import type { AiRun } from '../services/api';

const run = (extra: Partial<AiRun>): AiRun => ({
  id: 'r', kind: 'ask', actor: 'a@b.test', actor_type: 'user', status: 'answered', method: 'llm', degraded: false,
  input: { supplier: 'Acme', question: 'Any recalls?' }, llm: null, latency_ms: 10, created_at: '2026-10-25T00:00:00Z', ...extra,
});

describe('describeRun', () => {
  it('says who was asked what, the outcome and the model', () => {
    expect(describeRun(run({ llm: { provider: 'bedrock', model: 'eu.anthropic.claude-sonnet-5-5', calls: 1, failures: 0 } })))
      .toBe('Ask about Acme: "Any recalls?" → answered · eu.anthropic.claude-sonnet-5-5');
  });

  it('flags degraded runs and runs without a model', () => {
    expect(describeRun(run({ method: 'extractive_after_llm_failed', degraded: true }))).toContain('(degraded)');
    expect(describeRun(run({ method: 'extractive' }))).toContain("no model (records' own wording)");
  });
});

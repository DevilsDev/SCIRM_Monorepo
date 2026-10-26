import { describe, expect, it } from 'vitest';
import { utcDate } from './time';

describe('utcDate', () => {
  it('reads a zone-less timestamp as UTC', () => {
    expect(utcDate('2026-10-22T00:23:21').toISOString()).toBe('2026-10-22T00:23:21.000Z');
    expect(utcDate('2026-10-22T00:23:21.123456').getTime()).toBe(Date.UTC(2026, 9, 22, 0, 23, 21, 123));
  });

  it('leaves timestamps with a zone alone', () => {
    expect(utcDate('2026-10-22T00:23:21+00:00').toISOString()).toBe('2026-10-22T00:23:21.000Z');
    expect(utcDate('2026-10-22T13:23:21+13:00').toISOString()).toBe('2026-10-22T00:23:21.000Z');
    expect(utcDate('2026-10-22T00:23:21Z').toISOString()).toBe('2026-10-22T00:23:21.000Z');
  });
});

import { describe, expect, it } from 'vitest';
import { newSsoBinding, takeSsoBinding } from './ssoBinding';

class MemoryStorage {
  private items = new Map<string, string>();
  getItem(k: string) { return this.items.get(k) ?? null; }
  setItem(k: string, v: string) { this.items.set(k, v); }
  removeItem(k: string) { this.items.delete(k); }
}

describe('ssoBinding', () => {
  it('keeps a value, sends its SHA-256, and gives it back once', async () => {
    const storage = new MemoryStorage() as unknown as Storage;
    const hash = await newSsoBinding(storage);
    expect(hash).toMatch(/^[0-9a-f]{64}$/);
    const value = takeSsoBinding(storage);
    const digest = Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(value))))
      .map((b) => b.toString(16).padStart(2, '0')).join('');
    expect(digest).toBe(hash);
    expect(takeSsoBinding(storage)).toBe('');
  });
});

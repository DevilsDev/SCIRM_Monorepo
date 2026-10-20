import { describe, expect, it, vi } from 'vitest';
import { clearInviteToken, inviteErrorMessage, readInviteToken } from './invite';
import { isAuthRequest } from './session';

describe('invitation links', () => {
  it('reads a token from the fragment', () => {
    const token = 'abcDEF_123-xyz'.repeat(3);
    expect(readInviteToken(`#${token}`)).toBe(token);
  });

  it('rejects empty, short or malformed fragments', () => {
    expect(readInviteToken('')).toBeNull();
    expect(readInviteToken('#short')).toBeNull();
    expect(readInviteToken('#has spaces and <script>')).toBeNull();
  });

  it('clears the token from the address bar, keeping path and query', () => {
    const replaceState = vi.fn();
    clearInviteToken({ history: { replaceState } as any, location: { pathname: '/invite', search: '?x=1' } as any });
    expect(replaceState).toHaveBeenCalledWith(null, '', '/invite?x=1');
  });

  it('explains failures without revealing which part was wrong', () => {
    expect(inviteErrorMessage(404)).toMatch(/not valid/);
    expect(inviteErrorMessage(409)).toMatch(/already has an account/);
  });

  it('treats invitation endpoints as auth requests (their 401s are not a session expiry)', () => {
    expect(isAuthRequest('/api/v1/invitations/accept')).toBe(true);
    expect(isAuthRequest('/api/v1/invitations/lookup')).toBe(true);
    expect(isAuthRequest('/api/v1/org/invitations')).toBe(false);
  });
});

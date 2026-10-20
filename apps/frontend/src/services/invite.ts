/**
 * Invitation links look like https://app/invite#<token>. The token sits in the URL
 * fragment, which browsers never send to a server, so it stays out of access logs.
 * Once read, it is removed from the address bar so it does not linger in history.
 */
export function readInviteToken(hash: string): string | null {
  const token = hash.replace(/^#/, '').trim();
  return /^[A-Za-z0-9_-]{20,200}$/.test(token) ? token : null;
}

export function clearInviteToken(win: Pick<Window, 'history' | 'location'> = window): void {
  win.history.replaceState(null, '', win.location.pathname + win.location.search);
}

export function inviteErrorMessage(status: number | undefined): string {
  if (status === 404) return 'This invitation is not valid any more. It may have been used, revoked or expired. Ask your administrator for a new one.';
  if (status === 409) return 'That email already has an account. Sign in instead.';
  if (status === 400) return 'Check the details and try again.';
  return 'Something went wrong. Try again in a moment.';
}

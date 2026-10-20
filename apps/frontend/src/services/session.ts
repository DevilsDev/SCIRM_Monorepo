/**
 * Session tokens and what happens when the API says 401.
 *
 * - The access token is short-lived; the refresh token gets a new one. Several
 *   requests failing at once share a single refresh call.
 * - If refreshing fails, the session ends once: listeners (the AuthProvider) clear
 *   state and route to /login, remembering the page the user was on. There is no
 *   full page reload. That reload used to wipe the login form's error message,
 *   and repeated 401s reloaded the page over and over.
 * - 401s from the auth endpoints themselves (a wrong password, a bad MFA code) are
 *   left to the form that made the request.
 */

export interface TokenStorage {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
}

const ACCESS_KEY = 'auth_token';
const REFRESH_KEY = 'refresh_token';
const AUTH_PATHS = ['/api/v1/auth/login', '/api/v1/auth/signup', '/api/v1/auth/mfa/verify', '/api/v1/auth/refresh',
  '/api/v1/invitations/lookup', '/api/v1/invitations/accept'];

export interface JwtUser {
  id: string;
  email: string;
  name: string;
  roles: string[];
}

export function decodeJwt(token: string | null): (JwtUser & { exp?: number }) | null {
  if (!token || token.split('.').length !== 3) return null;
  try {
    const part = token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/');
    const payload = JSON.parse(atob(part));
    return {
      id: payload.sub || '',
      email: payload.email || '',
      name: payload.name || '',
      roles: payload.roles || ['user'],
      exp: payload.exp,
    };
  } catch {
    return null;
  }
}

export function isExpired(token: string | null, now: number = Date.now()): boolean {
  const decoded = decodeJwt(token);
  return !decoded || (!!decoded.exp && decoded.exp * 1000 <= now);
}

export function isAuthRequest(url: string | undefined): boolean {
  return !!url && AUTH_PATHS.some((p) => url.endsWith(p) || url.includes(`${p}?`));
}

type Refresher = (refreshToken: string) => Promise<string>;

export class Session {
  private refreshing: Promise<string | null> | null = null;
  private expiredListeners = new Set<() => void>();
  private ended = false;

  constructor(private storage: TokenStorage, private refresher: Refresher) {}

  get accessToken(): string | null {
    return this.storage.getItem(ACCESS_KEY);
  }

  get refreshToken(): string | null {
    return this.storage.getItem(REFRESH_KEY);
  }

  /** Signed in, or able to become so silently: a live access token, or a live refresh token. */
  hasSession(now: number = Date.now()): boolean {
    return !isExpired(this.accessToken, now) || !isExpired(this.refreshToken, now);
  }

  start(accessToken: string, refreshToken?: string | null): void {
    this.storage.setItem(ACCESS_KEY, accessToken);
    if (refreshToken) this.storage.setItem(REFRESH_KEY, refreshToken);
    else this.storage.removeItem(REFRESH_KEY);
    this.ended = false;
  }

  clear(): void {
    this.storage.removeItem(ACCESS_KEY);
    this.storage.removeItem(REFRESH_KEY);
  }

  onExpired(listener: () => void): () => void {
    this.expiredListeners.add(listener);
    return () => this.expiredListeners.delete(listener);
  }

  /**
   * Called on a 401 from a non-auth request. Resolves to a new access token to retry
   * with, or null if the session is over (listeners have then been told, once).
   */
  async handleUnauthorized(): Promise<string | null> {
    const refreshToken = this.refreshToken;
    if (!refreshToken || isExpired(refreshToken)) {
      this.end();
      return null;
    }
    if (!this.refreshing) {
      this.refreshing = this.refresher(refreshToken)
        .then((access) => {
          this.storage.setItem(ACCESS_KEY, access);
          return access;
        })
        .catch(() => {
          this.end();
          return null;
        })
        .finally(() => {
          this.refreshing = null;
        });
    }
    return this.refreshing;
  }

  private end(): void {
    this.clear();
    if (this.ended) return;
    this.ended = true;
    this.expiredListeners.forEach((listener) => listener());
  }
}

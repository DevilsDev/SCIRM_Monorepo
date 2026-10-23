import React, { createContext, useCallback, useContext, useEffect, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { api, session } from '../services/api';
import { decodeJwt, JwtUser } from '../services/session';

type User = JwtUser;

export type LoginResult = { status: 'signed_in' } | { status: 'mfa_required'; mfaToken: string };

interface AuthContextType {
  user: User | null;
  token: string | null;
  isAuthenticated: boolean;
  login: (email: string, password: string) => Promise<LoginResult>;
  verifyMfa: (mfaToken: string, code: string) => Promise<void>;
  signup: (email: string, password: string, name: string) => Promise<void>;
  acceptInvitation: (token: string, name: string, password: string) => Promise<void>;
  /** Changes the password; other sessions end, this one continues with new tokens. */
  changePassword: (current: string, next: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType>({
  user: null,
  token: null,
  isAuthenticated: false,
  login: async () => ({ status: 'signed_in' }),
  verifyMfa: async () => {},
  signup: async () => {},
  acceptInvitation: async () => {},
  changePassword: async () => {},
  logout: () => {},
});

function userFrom(token: string | null): User | null {
  const decoded = decodeJwt(token);
  if (!decoded) return null;
  const { exp: _exp, ...user } = decoded;
  return user;
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  // Read synchronously on the first render. Reading in an effect made a page refresh
  // look signed out for one render: the guard sent the user to /login, then on to
  // /dashboard, and the page they were on was lost.
  const [token, setToken] = useState<string | null>(() => (session.hasSession() ? session.accessToken : null));
  const [user, setUser] = useState<User | null>(() => (session.hasSession() ? userFrom(session.accessToken) : null));
  const navigate = useNavigate();
  const location = useLocation();

  useEffect(() => {
    if (!session.hasSession()) session.clear();
  }, []);

  const begin = useCallback((tokens: { access_token?: string; refresh_token?: string }) => {
    if (!tokens.access_token) throw new Error('No access token returned');
    session.start(tokens.access_token, tokens.refresh_token);
    setToken(tokens.access_token);
    setUser(userFrom(tokens.access_token));
  }, []);

  const logout = useCallback(() => {
    session.clear();
    setToken(null);
    setUser(null);
  }, []);

  // The API client reports an ended session once; keep the page to come back to.
  useEffect(() => session.onExpired(() => {
    setToken(null);
    setUser(null);
    if (location.pathname !== '/login') {
      navigate('/login', { replace: true, state: { from: location.pathname + location.search, expired: true } });
    }
  }), [navigate, location.pathname, location.search]);

  const login = async (email: string, password: string): Promise<LoginResult> => {
    const response = await api.login(email, password);
    if (response.mfa_required && response.mfa_token) {
      return { status: 'mfa_required', mfaToken: response.mfa_token };
    }
    begin(response);
    return { status: 'signed_in' };
  };

  const verifyMfa = async (mfaToken: string, code: string) => {
    begin(await api.verifyMfa(mfaToken, code));
  };

  const signup = async (email: string, password: string, name: string) => {
    begin(await api.signup(email, password, name));
  };

  const acceptInvitation = async (token: string, name: string, password: string) => {
    begin(await api.acceptInvitation(token, name, password));
  };

  const changePassword = async (current: string, next: string) => {
    begin(await api.changePassword(current, next));
  };

  return (
    <AuthContext.Provider value={{ user, token, isAuthenticated: !!token, login, verifyMfa, signup, acceptInvitation, changePassword, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}

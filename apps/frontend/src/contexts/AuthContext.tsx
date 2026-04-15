import React, { createContext, useContext, useEffect, useState } from 'react';
import { api } from '../services/api';

interface User {
  id: string;
  email: string;
  name: string;
  roles: string[];
}

interface AuthContextType {
  user: User | null;
  token: string | null;
  isAuthenticated: boolean;
  login: (email: string, password: string) => Promise<void>;
  signup: (email: string, password: string, name: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType>({
  user: null,
  token: null,
  isAuthenticated: false,
  login: async () => {},
  signup: async () => {},
  logout: () => {},
});

function decodeToken(token: string): User | null {
  try {
    const payload = JSON.parse(atob(token.split('.')[1]));

    // Check if token is expired
    if (payload.exp && payload.exp * 1000 < Date.now()) {
      return null; // expired
    }

    return {
      id: payload.sub || '',
      email: payload.email || '',
      name: payload.name || '',
      roles: payload.roles || ['user'],
    };
  } catch {
    return null;
  }
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);

  useEffect(() => {
    const stored = localStorage.getItem('auth_token');
    if (stored) {
      const decoded = decodeToken(stored);
      if (decoded) {
        setToken(stored);
        setUser(decoded);
      } else {
        // Token expired or invalid — clear it
        localStorage.removeItem('auth_token');
      }
    }
  }, []);

  const login = async (email: string, password: string) => {
    const response = await api.login(email, password);
    const accessToken = response.access_token;
    localStorage.setItem('auth_token', accessToken);
    setToken(accessToken);
    setUser(decodeToken(accessToken));
  };

  const signup = async (email: string, password: string, name: string) => {
    const response = await api.signup(email, password, name);
    const accessToken = response.access_token;
    localStorage.setItem('auth_token', accessToken);
    setToken(accessToken);
    setUser(decodeToken(accessToken));
  };

  const logout = () => {
    localStorage.removeItem('auth_token');
    setToken(null);
    setUser(null);
  };

  return (
    <AuthContext.Provider value={{ user, token, isAuthenticated: !!token, login, signup, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}

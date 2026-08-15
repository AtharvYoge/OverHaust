import React, { createContext, useContext, useEffect, useMemo, useState, useCallback } from 'react';
import { AuthAPI } from '@/lib/api';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  const restore = useCallback(async () => {
    setLoading(true);
    try {
      const token = localStorage.getItem('oh_token');
      if (!token) {
        setUser(null);
        return;
      }
      const me = await AuthAPI.me();
      setUser(me);
    } catch {
      setUser(null);
      try { localStorage.removeItem('oh_token'); } catch { /* ignore */ }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    restore();
  }, [restore]);

  const login = useCallback(async (email) => {
    const res = await AuthAPI.login(email);
    localStorage.setItem('oh_token', res.token);
    setUser(res.user);
    return res.user;
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem('oh_token');
    setUser(null);
  }, []);

  const value = useMemo(
    () => ({ user, loading, login, logout, refresh: restore }),
    [user, loading, login, logout, restore],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>');
  return ctx;
}

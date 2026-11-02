import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { ApiClient } from '../api/client';
import type { RegisterInput, SessionUser } from '../api/types';
import { API_URL } from '../config';
import { secureTokenStore } from './tokenStorage';

type Status = 'loading' | 'signedOut' | 'signedIn';
interface AuthValue {
  status: Status; client: ApiClient; user: SessionUser | null;
  signIn(identifier: string, password: string): Promise<void>;
  register(input: RegisterInput): Promise<void>;
  signOut(): Promise<void>;
}
const Ctx = createContext<AuthValue | null>(null);

export function AuthProvider({ children, client: injected }: { children: React.ReactNode; client?: ApiClient }) {
  const qc = useQueryClient();
  const [status, setStatus] = useState<Status>('loading');
  const [user, setUser] = useState<SessionUser | null>(null);

  // A refresh failure anywhere in the app lands here: drop cached data and show Login.
  const onExpired = useCallback(() => { qc.clear(); setUser(null); setStatus('signedOut'); }, [qc]);
  const client = useMemo(
    () => injected ?? new ApiClient({ baseUrl: API_URL, store: secureTokenStore, onSessionExpired: onExpired }),
    [injected, onExpired],
  );

  useEffect(() => {
    let alive = true;
    client.getSession().then((s) => alive && setStatus(s ? 'signedIn' : 'signedOut'));
    return () => { alive = false; };
  }, [client]);

  const value = useMemo<AuthValue>(() => ({
    status, client, user,
    async signIn(identifier, password) {
      qc.clear(); // never show the previous user's cached data
      const t = await client.login(identifier, password);
      setUser(t.user); setStatus('signedIn');
    },
    async register(input) {
      qc.clear();
      const t = await client.register(input);
      setUser(t.user); setStatus('signedIn');
    },
    async signOut() {
      await client.logout();          // revokes server-side (best effort) and wipes secure storage
      qc.clear();                     // and in-memory caches
      setUser(null); setStatus('signedOut');
    },
  }), [status, client, user, qc]);

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAuth(): AuthValue {
  const v = useContext(Ctx);
  if (!v) throw new Error('useAuth must be used inside <AuthProvider>');
  return v;
}

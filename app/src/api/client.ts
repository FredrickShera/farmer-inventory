import { REFRESH_SKEW_MS } from '../config';
import type { StoredSession, TokenStore } from '../auth/tokenStorage';
import type { TokenResponse } from './types';

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string, public details?: { field: string; message: string }[]) {
    super(message);
  }
  get isNetwork() { return this.status === 0; }
}

interface Options {
  method?: 'GET' | 'POST' | 'PATCH' | 'DELETE';
  body?: unknown;
  query?: Record<string, string | number | undefined>;
  auth?: boolean; // default true
}

export interface ClientDeps {
  baseUrl: string;
  store: TokenStore;
  fetchFn?: typeof fetch;
  now?: () => number;
  onSessionExpired?: () => void;
}

/**
 * The ONE place that talks to the API. It:
 *   - attaches the access token,
 *   - refreshes it silently shortly before expiry,
 *   - on a 401 refreshes ONCE (single-flight: concurrent 401s share one refresh) and retries the request,
 *   - if refresh is rejected, clears all tokens and calls onSessionExpired (-> Login screen).
 */
export class ApiClient {
  private session: StoredSession | null | undefined; // undefined = not loaded from secure storage yet
  private refreshing: Promise<StoredSession> | null = null;
  private readonly fetchFn: typeof fetch;
  private readonly now: () => number;

  constructor(private deps: ClientDeps) {
    // Wrapped in an arrow function: browsers throw "Illegal invocation" if fetch is called as a method of another object.
    this.fetchFn = deps.fetchFn ?? ((input, init) => fetch(input, init));
    this.now = deps.now ?? Date.now;
  }

  // ---------------------------------------------------------------- session
  async getSession(): Promise<StoredSession | null> {
    if (this.session === undefined) this.session = await this.deps.store.load();
    return this.session;
  }

  async setSession(t: TokenResponse): Promise<void> {
    const s = { accessToken: t.access_token, refreshToken: t.refresh_token, expiresAt: this.now() + t.expires_in * 1000 };
    this.session = s;
    await this.deps.store.save(s);
  }

  /** Wipes memory AND secure storage. */
  async clearSession(): Promise<void> {
    this.session = null;
    this.refreshing = null;
    await this.deps.store.clear();
  }

  private async expire(): Promise<never> {
    await this.clearSession();
    this.deps.onSessionExpired?.();
    throw new ApiError(401, 'SESSION_EXPIRED', 'Your session has expired. Please sign in again.');
  }

  /** Single-flight refresh. Network errors do NOT sign the user out; a rejected refresh token does. */
  private refresh(): Promise<StoredSession> {
    if (this.refreshing) return this.refreshing;
    const current = this.session;
    this.refreshing = (async () => {
      if (!current) return this.expire();
      try {
        const t = await this.send<TokenResponse>('/auth/refresh', { method: 'POST', body: { refresh_token: current.refreshToken }, auth: false });
        await this.setSession(t);
        return this.session as StoredSession;
      } catch (e) {
        if (e instanceof ApiError && !e.isNetwork && e.status < 500) return this.expire();
        throw e;
      } finally {
        this.refreshing = null;
      }
    })();
    return this.refreshing;
  }

  // ---------------------------------------------------------------- requests
  private async send<T>(path: string, o: Options, token?: string): Promise<T> {
    const qs = o.query
      ? '?' + Object.entries(o.query).filter(([, v]) => v !== undefined && v !== '').map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`).join('&')
      : '';
    let res: Response;
    try {
      res = await this.fetchFn(`${this.deps.baseUrl}${path}${qs === '?' ? '' : qs}`, {
        method: o.method ?? 'GET',
        headers: { Accept: 'application/json', ...(o.body !== undefined ? { 'Content-Type': 'application/json' } : {}), ...(token ? { Authorization: `Bearer ${token}` } : {}) },
        body: o.body !== undefined ? JSON.stringify(o.body) : undefined,
      });
    } catch {
      throw new ApiError(0, 'NETWORK', 'Cannot reach the server. Check your connection and try again.');
    }
    if (res.status === 204) return undefined as T;
    let data: any = null;
    try { data = await res.json(); } catch { /* non-JSON body */ }
    if (!res.ok) {
      const err = data?.error;
      throw new ApiError(res.status, err?.code ?? 'HTTP_ERROR', err?.message ?? `Request failed (${res.status})`, err?.details);
    }
    return data as T;
  }

  async request<T>(path: string, o: Options = {}): Promise<T> {
    if (o.auth === false) return this.send<T>(path, o);
    let s = await this.getSession();
    if (!s) return this.expire();
    if (s.expiresAt - this.now() < REFRESH_SKEW_MS) s = await this.refresh();
    const usedToken = s.accessToken;
    try {
      return await this.send<T>(path, o, usedToken);
    } catch (e) {
      if (!(e instanceof ApiError) || e.status !== 401) throw e;
      // Another request may already have refreshed while ours was in flight: reuse that token if so.
      const latest = this.session;
      const fresh = latest && latest.accessToken !== usedToken ? latest : await this.refresh();
      return this.send<T>(path, o, fresh.accessToken);
    }
  }

  // ---------------------------------------------------------------- auth endpoints
  async login(identifier: string, password: string) {
    const t = await this.send<TokenResponse>('/auth/login', { method: 'POST', body: { identifier, password }, auth: false });
    await this.setSession(t);
    return t;
  }
  async register(input: unknown) {
    const t = await this.send<TokenResponse>('/auth/register', { method: 'POST', body: input, auth: false });
    await this.setSession(t);
    return t;
  }
  /** Best-effort server-side revoke, then ALWAYS wipe local tokens, even if the network call fails. */
  async logout() {
    try {
      const s = await this.getSession();
      if (s) await this.send('/auth/logout', { method: 'POST' }, s.accessToken);
    } catch { /* offline or already expired: local wipe below is what matters */ }
    await this.clearSession();
  }
}

import { ApiClient, ApiError } from '../src/api/client';
import type { StoredSession, TokenStore } from '../src/auth/tokenStorage';

const json = (status: number, body?: unknown) =>
  ({ status, ok: status >= 200 && status < 300, json: async () => body }) as unknown as Response;
const tokens = (n: number) => ({ access_token: `access-${n}`, refresh_token: `refresh-${n}`, token_type: 'bearer', expires_in: 3600, expires_at: 0, user: null });

function memoryStore(initial: StoredSession | null): TokenStore & { data: StoredSession | null } {
  const s = { data: initial, load: async () => s.data, save: async (v: StoredSession) => { s.data = v; }, clear: async () => { s.data = null; } };
  return s;
}

function setup(handler: (url: string, init: RequestInit) => Response | Promise<Response>, session: StoredSession | null = { accessToken: 'access-1', refreshToken: 'refresh-1', expiresAt: Date.now() + 3600_000 }) {
  const store = memoryStore(session);
  const calls: { url: string; auth?: string }[] = [];
  const fetchFn = jest.fn(async (url: any, init: any) => {
    calls.push({ url: String(url).replace('http://api', ''), auth: init?.headers?.Authorization });
    return handler(String(url).replace('http://api', ''), init);
  });
  const onSessionExpired = jest.fn();
  const client = new ApiClient({ baseUrl: 'http://api', store, fetchFn: fetchFn as any, onSessionExpired });
  return { client, store, calls, onSessionExpired };
}

describe('ApiClient token handling', () => {
  it('attaches the bearer token', async () => {
    const { client, calls } = setup(() => json(200, { ok: true }));
    await client.request('/farmers/me');
    expect(calls[0].auth).toBe('Bearer access-1');
  });

  it('on 401 refreshes once, stores the new tokens, and retries with the new access token', async () => {
    const { client, store, calls } = setup((url, init) => {
      if (url === '/auth/refresh') return json(200, tokens(2));
      return (init.headers as any).Authorization === 'Bearer access-1' ? json(401, { error: { code: 'TOKEN_EXPIRED', message: 'expired' } }) : json(200, { data: 'fresh' });
    });
    await expect(client.request('/inventory')).resolves.toEqual({ data: 'fresh' });
    expect(calls.map((c) => c.url)).toEqual(['/inventory', '/auth/refresh', '/inventory']);
    expect(calls[2].auth).toBe('Bearer access-2');
    expect(store.data?.refreshToken).toBe('refresh-2');
  });

  it('shares ONE refresh between concurrent 401s (refresh tokens rotate, so a second refresh would fail)', async () => {
    let refreshes = 0;
    const { client } = setup(async (url, init) => {
      if (url === '/auth/refresh') { refreshes++; await new Promise((r) => setTimeout(r, 20)); return json(200, tokens(2)); }
      return (init.headers as any).Authorization === 'Bearer access-1' ? json(401, {}) : json(200, { ok: url });
    });
    const out = await Promise.all([client.request('/a'), client.request('/b'), client.request('/c')]);
    expect(refreshes).toBe(1);
    expect(out).toHaveLength(3);
  });

  it('refreshes proactively when the token is about to expire (no wasted 401)', async () => {
    const { client, calls } = setup(
      (url) => (url === '/auth/refresh' ? json(200, tokens(2)) : json(200, {})),
      { accessToken: 'access-1', refreshToken: 'refresh-1', expiresAt: Date.now() + 5_000 },
    );
    await client.request('/farmers/me');
    expect(calls.map((c) => c.url)).toEqual(['/auth/refresh', '/farmers/me']);
    expect(calls[1].auth).toBe('Bearer access-2');
  });

  it('if refresh is rejected: wipes stored tokens, signals session expiry, and throws', async () => {
    const { client, store, onSessionExpired } = setup((url) =>
      url === '/auth/refresh' ? json(401, { error: { code: 'REFRESH_FAILED', message: 'no' } }) : json(401, {}));
    await expect(client.request('/inventory')).rejects.toMatchObject({ code: 'SESSION_EXPIRED' });
    expect(store.data).toBeNull();
    expect(onSessionExpired).toHaveBeenCalledTimes(1);
  });

  it('a network failure during refresh does NOT log the user out', async () => {
    const { client, store, onSessionExpired } = setup((url) => {
      if (url === '/auth/refresh') throw new TypeError('Network request failed');
      return json(401, {});
    });
    await expect(client.request('/inventory')).rejects.toBeInstanceOf(ApiError);
    expect(store.data).not.toBeNull();
    expect(onSessionExpired).not.toHaveBeenCalled();
  });

  it('403 and 404 are surfaced as errors without any refresh attempt', async () => {
    const { client, calls } = setup(() => json(403, { error: { code: 'FORBIDDEN', message: 'nope' } }));
    await expect(client.request('/farmers')).rejects.toMatchObject({ status: 403, code: 'FORBIDDEN' });
    expect(calls).toHaveLength(1);
  });

  it('with no stored session, requests fail with SESSION_EXPIRED and never hit the network', async () => {
    const { client, calls, onSessionExpired } = setup(() => json(200, {}), null);
    await expect(client.request('/inventory')).rejects.toMatchObject({ code: 'SESSION_EXPIRED' });
    expect(calls).toHaveLength(0);
    expect(onSessionExpired).toHaveBeenCalled();
  });

  it('logout clears all stored tokens even when the server call fails', async () => {
    const { client, store } = setup(() => { throw new TypeError('offline'); });
    await client.logout();
    expect(store.data).toBeNull();
    expect(await client.getSession()).toBeNull();
  });

  it('login stores tokens; sends no Authorization header', async () => {
    const { client, store, calls } = setup(() => json(200, tokens(7)), null);
    await client.login('0712345678', 'Passw0rd1');
    expect(calls[0].auth).toBeUndefined();
    expect(store.data?.accessToken).toBe('access-7');
  });
});

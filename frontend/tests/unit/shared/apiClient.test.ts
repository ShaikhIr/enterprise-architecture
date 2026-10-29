import { http, HttpResponse } from 'msw';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import {
  apiClient,
  refreshAccessTokenOnce,
  setSessionExpiredHandler,
} from '@shared/services/apiClient';
import { storageService } from '@shared/services/storageService';

import { server } from '../../mocks/server';

const REFRESH_URL = '/api/v1/auth/refresh';
const refreshOk = (token: string) =>
  http.post(REFRESH_URL, () =>
    HttpResponse.json({ access_token: token, token_type: 'Bearer', expires_in: 1800 }),
  );

/**
 * `apiClient` keeps its refresh-dedup state (`inFlightRefresh`) and its
 * session-expired handler at module scope, so every test resets the pieces
 * it can reach: the in-memory token via `storageService`, and the handler
 * via `setSessionExpiredHandler` (the module's own default handler
 * navigates the real `window.location`, which is not something any test
 * here wants to trigger for real).
 */
describe('apiClient', () => {
  const sessionExpired = vi.fn();

  beforeEach(() => {
    storageService.clearAccessToken();
    sessionExpired.mockClear();
    setSessionExpiredHandler(sessionExpired);
  });

  describe('request interceptor', () => {
    it('attaches the in-memory access token as a Bearer header', async () => {
      storageService.setAccessToken('token-abc');
      server.use(
        http.get('/api/v1/ping', ({ request }) =>
          HttpResponse.json({ auth: request.headers.get('authorization') }),
        ),
      );

      const { data } = await apiClient.get('/ping');

      expect(data.auth).toBe('Bearer token-abc');
    });

    it('attaches a correlation id header to every request', async () => {
      storageService.setAccessToken('token-abc');
      server.use(
        http.get('/api/v1/ping', ({ request }) =>
          HttpResponse.json({ correlationId: request.headers.get('x-correlation-id') }),
        ),
      );

      const { data } = await apiClient.get('/ping');

      expect(data.correlationId).toBeTruthy();
    });

    it('silently refreshes before sending when the tab has no access token yet', async () => {
      let refreshCalls = 0;
      server.use(
        http.post(REFRESH_URL, () => {
          refreshCalls += 1;
          return HttpResponse.json({
            access_token: 'fresh-token',
            token_type: 'Bearer',
            expires_in: 1800,
          });
        }),
        http.get('/api/v1/ping', ({ request }) =>
          HttpResponse.json({ auth: request.headers.get('authorization') }),
        ),
      );

      const { data } = await apiClient.get('/ping');

      expect(refreshCalls).toBe(1);
      expect(data.auth).toBe('Bearer fresh-token');
      expect(storageService.getAccessToken()).toBe('fresh-token');
    });

    it('sends without a token rather than refreshing when the refresh itself fails', async () => {
      server.use(
        http.post(REFRESH_URL, () => new HttpResponse(null, { status: 401 })),
        http.get('/api/v1/ping', ({ request }) =>
          HttpResponse.json({ auth: request.headers.get('authorization') }),
        ),
      );

      const { data } = await apiClient.get('/ping');

      expect(data.auth).toBeNull();
    });

    it('does not wait for a refresh on the login/refresh endpoints themselves', async () => {
      let refreshCalls = 0;
      server.use(
        http.post(REFRESH_URL, () => {
          refreshCalls += 1;
          return HttpResponse.json({ access_token: 'x', token_type: 'Bearer', expires_in: 1800 });
        }),
        http.post('/api/v1/auth/login', () =>
          HttpResponse.json({
            access_token: 'login-token',
            token_type: 'Bearer',
            expires_in: 1800,
          }),
        ),
      );

      await apiClient.post('/auth/login', { username: 'a', password: 'b' });

      expect(refreshCalls).toBe(0);
    });
  });

  describe('response interceptor (401 handling)', () => {
    it('retries once with a refreshed token after a 401', async () => {
      storageService.setAccessToken('stale-token');
      let pingCalls = 0;
      server.use(
        refreshOk('new-token'),
        http.get('/api/v1/ping', ({ request }) => {
          pingCalls += 1;
          const auth = request.headers.get('authorization');
          if (auth === 'Bearer stale-token') return new HttpResponse(null, { status: 401 });
          return HttpResponse.json({ auth });
        }),
      );

      const { data } = await apiClient.get('/ping');

      expect(pingCalls).toBe(2);
      expect(data.auth).toBe('Bearer new-token');
      expect(storageService.getAccessToken()).toBe('new-token');
    });

    it('collapses concurrent 401s from different callers into a single refresh', async () => {
      storageService.setAccessToken('stale-token');
      let refreshCalls = 0;
      server.use(
        http.post(REFRESH_URL, () => {
          refreshCalls += 1;
          return HttpResponse.json({
            access_token: 'new-token',
            token_type: 'Bearer',
            expires_in: 1800,
          });
        }),
        http.get('/api/v1/ping', ({ request }) => {
          const auth = request.headers.get('authorization');
          if (auth === 'Bearer stale-token') return new HttpResponse(null, { status: 401 });
          return HttpResponse.json({ auth });
        }),
      );

      const [first, second] = await Promise.all([apiClient.get('/ping'), apiClient.get('/ping')]);

      expect(refreshCalls).toBe(1);
      expect(first.data.auth).toBe('Bearer new-token');
      expect(second.data.auth).toBe('Bearer new-token');
    });

    it('clears the token and signals session-expired when the refresh itself fails', async () => {
      storageService.setAccessToken('stale-token');
      server.use(
        http.post(REFRESH_URL, () => new HttpResponse(null, { status: 401 })),
        http.get('/api/v1/ping', () => new HttpResponse(null, { status: 401 })),
      );

      await expect(apiClient.get('/ping')).rejects.toBeTruthy();

      expect(storageService.getAccessToken()).toBeNull();
      expect(sessionExpired).toHaveBeenCalledTimes(1);
    });

    it('only retries once, even if the retried request also comes back 401', async () => {
      storageService.setAccessToken('stale-token');
      let pingCalls = 0;
      server.use(
        refreshOk('still-unauthorized'),
        http.get('/api/v1/ping', () => {
          pingCalls += 1;
          return new HttpResponse(null, { status: 401 });
        }),
      );

      await expect(apiClient.get('/ping')).rejects.toBeTruthy();

      // Original attempt + exactly one retry, never a third.
      expect(pingCalls).toBe(2);
    });

    it('does not attempt to refresh when the refresh call itself returns a 401', async () => {
      let refreshCalls = 0;
      server.use(
        http.post(REFRESH_URL, () => {
          refreshCalls += 1;
          return new HttpResponse(null, { status: 401 });
        }),
      );

      await expect(refreshAccessTokenOnce()).rejects.toBeTruthy();

      expect(refreshCalls).toBe(1);
    });

    it('leaves non-401 errors untouched', async () => {
      storageService.setAccessToken('token-abc');
      server.use(http.get('/api/v1/ping', () => new HttpResponse(null, { status: 500 })));

      await expect(apiClient.get('/ping')).rejects.toMatchObject({
        response: { status: 500 },
      });
      // A server error is not a session problem.
      expect(sessionExpired).not.toHaveBeenCalled();
    });
  });
});

/**
 * A 401 from `/auth/login` means "wrong password", not "your session expired". Treating it
 * as the latter replays the login after a refresh, so one click on Sign in counts as two
 * attempts against the server's login throttle, and when there is no refresh cookie the
 * user is shown the refresh failure ("Missing refresh token") instead of why the login
 * failed.
 */
describe('apiClient — session endpoints', () => {
  const sessionExpired = vi.fn();

  beforeEach(() => {
    storageService.clearAccessToken();
    sessionExpired.mockClear();
    setSessionExpiredHandler(sessionExpired);
  });

  const loginRejects = (calls: { login: number }) =>
    http.post('/api/v1/auth/login', () => {
      calls.login += 1;
      return HttpResponse.json({ detail: 'Invalid username or password' }, { status: 401 });
    });

  it('does not refresh and replay a rejected login', async () => {
    const calls = { login: 0 };
    let refreshes = 0;
    server.use(
      loginRejects(calls),
      http.post(REFRESH_URL, () => {
        refreshes += 1;
        return HttpResponse.json({ access_token: 'fresh', token_type: 'Bearer', expires_in: 1800 });
      }),
    );

    await expect(
      apiClient.post('/auth/login', { username: 'alice', password: 'wrong' }),
    ).rejects.toMatchObject({ response: { status: 401 } });

    expect(calls.login).toBe(1); // one click, one attempt
    expect(refreshes).toBe(0);
  });

  it("surfaces the login's own error when there is no refresh cookie", async () => {
    server.use(
      loginRejects({ login: 0 }),
      http.post(REFRESH_URL, () =>
        HttpResponse.json({ detail: 'Missing refresh token' }, { status: 401 }),
      ),
    );

    await expect(
      apiClient.post('/auth/login', { username: 'alice', password: 'wrong' }),
    ).rejects.toMatchObject({
      response: { status: 401, data: { detail: 'Invalid username or password' } },
    });
    expect(sessionExpired).not.toHaveBeenCalled();
  });

  it('passes a throttled login (429) through untouched', async () => {
    let refreshes = 0;
    server.use(
      http.post('/api/v1/auth/login', () =>
        HttpResponse.json(
          { detail: 'Too many login attempts. Please try again later.' },
          { status: 429, headers: { 'Retry-After': '900' } },
        ),
      ),
      http.post(REFRESH_URL, () => {
        refreshes += 1;
        return HttpResponse.json({ access_token: 'fresh', token_type: 'Bearer', expires_in: 1800 });
      }),
    );

    await expect(
      apiClient.post('/auth/login', { username: 'alice', password: 'x' }),
    ).rejects.toMatchObject({ response: { status: 429, headers: { 'retry-after': '900' } } });
    expect(refreshes).toBe(0);
  });

  it('still refreshes and retries an expired token on an ordinary endpoint', async () => {
    // The change above must not have switched off the behaviour it sits next to.
    storageService.setAccessToken('stale');
    let attempts = 0;
    server.use(
      http.get('/api/v1/ping', ({ request }) => {
        attempts += 1;
        return request.headers.get('authorization') === 'Bearer fresh'
          ? HttpResponse.json({ ok: true })
          : HttpResponse.json({ detail: 'expired' }, { status: 401 });
      }),
      refreshOk('fresh'),
    );

    const { data } = await apiClient.get('/ping');

    expect(data).toEqual({ ok: true });
    expect(attempts).toBe(2);
  });
});

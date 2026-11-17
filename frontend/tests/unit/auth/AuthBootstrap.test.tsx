import { http, HttpResponse } from 'msw';
import { Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { AuthBootstrap } from '@app/router/AuthBootstrap';

import { apiClient } from '@shared/services/apiClient';
import { sessionBus, type SessionEvent } from '@shared/services/sessionBus';
import { sessionCache } from '@shared/services/sessionCache';
import { storageService } from '@shared/services/storageService';

import { server } from '../../mocks/server';
import type { RootState, TestPreloadedState } from '../../test-utils';
import { act, renderWithProviders, screen, waitFor } from '../../test-utils';

const REFRESH_URL = '/api/v1/auth/refresh';
const ME_URL = '/api/v1/auth/me';
const MENU_URL = '/api/v1/rbac/my-permissions/menu';

const alice = { id: 1, username: 'alice', is_active: true };
const bob = { id: 2, username: 'bob', is_active: true };

const tokenResponse = () =>
  HttpResponse.json({ access_token: 'bootstrap-token', token_type: 'Bearer', expires_in: 1800 });

const menuResponse = (keys: string[]) => HttpResponse.json({ menu_keys: keys, permissions: [] });

/** A signed-out store, as on a cold start. */
const signedOut = (): TestPreloadedState => ({
  auth: {
    user: null,
    isAuthenticated: false,
    isLoading: false,
    isBootstrapping: true,
    error: null,
  } satisfies RootState['auth'],
});

/** A store already holding a user, as when a cached session snapshot was found. */
const signedInAs = (user: typeof alice): TestPreloadedState => ({
  auth: {
    user,
    isAuthenticated: true,
    isLoading: false,
    isBootstrapping: false,
    error: null,
  } satisfies RootState['auth'],
});

const renderBootstrap = (preloadedState: TestPreloadedState) =>
  renderWithProviders(
    <Routes>
      <Route
        path="/"
        element={
          <AuthBootstrap>
            <div>App content</div>
          </AuthBootstrap>
        }
      />
      <Route path="/login" element={<div>Login page</div>} />
    </Routes>,
    { preloadedState },
  );

/** Capture the listener AuthBootstrap registers with the cross-tab bus, to fire events at it. */
const captureBusListener = () => {
  const unsubscribe = vi.fn();
  let listener: ((event: SessionEvent) => void) | null = null;
  vi.spyOn(sessionBus, 'subscribe').mockImplementation((fn) => {
    listener = fn;
    return unsubscribe;
  });
  return {
    unsubscribe,
    emit: (event: SessionEvent) => {
      if (!listener) throw new Error('AuthBootstrap has not subscribed to the session bus');
      const current = listener;
      act(() => current(event));
    },
  };
};

afterEach(() => {
  storageService.clearAccessToken();
  sessionStorage.clear();
});

describe('AuthBootstrap — cold start (no cached session)', () => {
  it('shows the splash and withholds the children while the session is being restored', async () => {
    server.use(
      http.post(REFRESH_URL, async () => {
        await new Promise((resolve) => setTimeout(resolve, 100));
        return tokenResponse();
      }),
      http.get(ME_URL, () => HttpResponse.json(alice)),
      http.get(MENU_URL, () => menuResponse(['dashboard'])),
    );

    renderBootstrap(signedOut());

    expect(screen.getByRole('progressbar')).toBeInTheDocument();
    expect(screen.queryByText('App content')).not.toBeInTheDocument();
    expect(await screen.findByText('App content')).toBeInTheDocument();
    expect(screen.queryByRole('progressbar')).not.toBeInTheDocument();
  });

  it('restores the session from the refresh cookie: user, token and menu permissions', async () => {
    server.use(
      http.post(REFRESH_URL, () => tokenResponse()),
      http.get(ME_URL, () => HttpResponse.json(alice)),
      http.get(MENU_URL, () => menuResponse(['dashboard', 'users'])),
    );

    const { store } = renderBootstrap(signedOut());

    expect(await screen.findByText('App content')).toBeInTheDocument();
    const state = store.getState();
    expect(state.auth.user).toEqual(alice);
    expect(state.auth.isAuthenticated).toBe(true);
    expect(state.auth.isBootstrapping).toBe(false);
    expect(state.rbac.menuKeys).toEqual(['dashboard', 'users']);
    expect(storageService.getAccessToken()).toBe('bootstrap-token');
    expect(sessionCache.getUser()).toEqual(alice);
  });

  it('attaches the restored token to the profile request', async () => {
    let authorization: string | null = null;
    server.use(
      http.post(REFRESH_URL, () => tokenResponse()),
      http.get(ME_URL, ({ request }) => {
        authorization = request.headers.get('Authorization');
        return HttpResponse.json(alice);
      }),
      http.get(MENU_URL, () => menuResponse([])),
    );

    renderBootstrap(signedOut());
    await screen.findByText('App content');

    expect(authorization).toBe('Bearer bootstrap-token');
  });

  it('renders the children signed out, and without a token, when there is no valid refresh cookie', async () => {
    server.use(http.post(REFRESH_URL, () => new HttpResponse(null, { status: 401 })));

    const { store } = renderBootstrap(signedOut());

    // The children still render: the route guards below decide to send the user to /login.
    expect(await screen.findByText('App content')).toBeInTheDocument();
    const state = store.getState();
    expect(state.auth.user).toBeNull();
    expect(state.auth.isAuthenticated).toBe(false);
    expect(state.auth.isBootstrapping).toBe(false);
    expect(storageService.getAccessToken()).toBeNull();
    expect(sessionCache.hasUser()).toBe(false);
  });

  it('treats a failing profile call after a good refresh as no session', async () => {
    server.use(
      http.post(REFRESH_URL, () => tokenResponse()),
      http.get(ME_URL, () => HttpResponse.json({ detail: 'boom' }, { status: 500 })),
      http.get(MENU_URL, () => menuResponse([])),
    );

    const { store } = renderBootstrap(signedOut());

    expect(await screen.findByText('App content')).toBeInTheDocument();
    expect(store.getState().auth.isAuthenticated).toBe(false);
    expect(store.getState().auth.user).toBeNull();
  });
});

describe('AuthBootstrap — warm start (cached session)', () => {
  it('renders the children at once, without a splash, while the silent refresh runs', async () => {
    sessionCache.setUser(alice);
    let releaseRefresh: () => void = () => {};
    const refreshGate = new Promise<void>((resolve) => {
      releaseRefresh = resolve;
    });
    server.use(
      http.post(REFRESH_URL, async () => {
        await refreshGate;
        return tokenResponse();
      }),
      http.get(ME_URL, () => HttpResponse.json(alice)),
      http.get(MENU_URL, () => menuResponse([])),
    );

    const { store } = renderBootstrap(signedInAs(alice));

    expect(screen.getByText('App content')).toBeInTheDocument();
    expect(screen.queryByRole('progressbar')).not.toBeInTheDocument();
    // The user stays signed in while the refresh is outstanding.
    expect(store.getState().auth.isAuthenticated).toBe(true);
    expect(store.getState().auth.isBootstrapping).toBe(false);

    releaseRefresh();
    await waitFor(() => expect(storageService.getAccessToken()).toBe('bootstrap-token'));
  });

  it('signs the user out when the background refresh turns out to be invalid', async () => {
    sessionCache.setUser(alice);
    server.use(http.post(REFRESH_URL, () => new HttpResponse(null, { status: 401 })));

    const { store } = renderBootstrap(signedInAs(alice));

    await waitFor(() => expect(store.getState().auth.isAuthenticated).toBe(false));
    expect(store.getState().auth.user).toBeNull();
    expect(sessionCache.hasUser()).toBe(false);
  });
});

describe('AuthBootstrap — session expiry handler', () => {
  it('clears auth and RBAC and navigates to /login when a later refresh fails', async () => {
    server.use(
      http.post(REFRESH_URL, () => tokenResponse()),
      http.get(ME_URL, () => HttpResponse.json(alice)),
      http.get(MENU_URL, () => menuResponse(['dashboard'])),
    );
    const { store } = renderBootstrap(signedOut());
    await screen.findByText('App content');
    expect(store.getState().auth.isAuthenticated).toBe(true);

    // The access token later expires, and the refresh cookie is no longer accepted.
    server.use(
      http.get('/api/v1/protected', () => new HttpResponse(null, { status: 401 })),
      http.post(REFRESH_URL, () => new HttpResponse(null, { status: 401 })),
    );
    await apiClient.get('/protected').catch(() => undefined);

    expect(await screen.findByText('Login page')).toBeInTheDocument();
    expect(store.getState().auth.isAuthenticated).toBe(false);
    expect(store.getState().auth.user).toBeNull();
    expect(store.getState().rbac.menuKeys).toEqual([]);
  });
});

describe('AuthBootstrap — cross-tab session events', () => {
  const signedInServer = (user: typeof alice) =>
    server.use(
      http.post(REFRESH_URL, () => tokenResponse()),
      http.get(ME_URL, () => HttpResponse.json(user)),
      http.get(MENU_URL, () => menuResponse(['dashboard'])),
    );

  it('clears this tab and goes to /login when another tab logs out', async () => {
    const bus = captureBusListener();
    signedInServer(alice);
    const { store } = renderBootstrap(signedOut());
    await screen.findByText('App content');
    expect(store.getState().auth.isAuthenticated).toBe(true);

    bus.emit({ type: 'logout' });

    expect(await screen.findByText('Login page')).toBeInTheDocument();
    expect(store.getState().auth.user).toBeNull();
    expect(store.getState().auth.isAuthenticated).toBe(false);
    expect(store.getState().rbac.menuKeys).toEqual([]);
    expect(sessionCache.hasUser()).toBe(false);
  });

  it('re-syncs to the new identity when another tab logs in as a different user', async () => {
    const bus = captureBusListener();
    signedInServer(alice);
    const { store } = renderBootstrap(signedOut());
    await screen.findByText('App content');
    expect(store.getState().auth.user).toEqual(alice);

    signedInServer(bob);
    bus.emit({ type: 'login' });

    await waitFor(() => expect(store.getState().auth.user).toEqual(bob));
    expect(screen.getByText('App content')).toBeInTheDocument();
  });

  it('ignores a second login event while a re-sync is already in flight', async () => {
    const bus = captureBusListener();
    let meCalls = 0;
    server.use(
      http.post(REFRESH_URL, () => tokenResponse()),
      http.get(ME_URL, async () => {
        meCalls += 1;
        // Slow enough that the second event arrives mid-flight.
        await new Promise((resolve) => setTimeout(resolve, 80));
        return HttpResponse.json(alice);
      }),
      http.get(MENU_URL, () => menuResponse([])),
    );
    renderBootstrap(signedOut());
    await screen.findByText('App content');
    expect(meCalls).toBe(1);

    bus.emit({ type: 'login' });
    bus.emit({ type: 'login' });

    await waitFor(() => expect(meCalls).toBe(2));
    // Give a would-be third call time to show up.
    await new Promise((resolve) => setTimeout(resolve, 200));
    expect(meCalls).toBe(2);
  });

  it('accepts a later login event once the earlier re-sync has finished', async () => {
    const bus = captureBusListener();
    let meCalls = 0;
    server.use(
      http.post(REFRESH_URL, () => tokenResponse()),
      http.get(ME_URL, () => {
        meCalls += 1;
        return HttpResponse.json(alice);
      }),
      http.get(MENU_URL, () => menuResponse([])),
    );
    renderBootstrap(signedOut());
    await screen.findByText('App content');

    bus.emit({ type: 'login' });
    await waitFor(() => expect(meCalls).toBe(2));
    // Let the guard reset after the first re-sync settles.
    await new Promise((resolve) => setTimeout(resolve, 50));
    bus.emit({ type: 'login' });

    await waitFor(() => expect(meCalls).toBe(3));
  });

  it('unsubscribes from the bus when it unmounts', async () => {
    const bus = captureBusListener();
    signedInServer(alice);
    const { unmount } = renderBootstrap(signedOut());
    await screen.findByText('App content');
    expect(bus.unsubscribe).not.toHaveBeenCalled();

    unmount();

    expect(bus.unsubscribe).toHaveBeenCalledTimes(1);
  });
});

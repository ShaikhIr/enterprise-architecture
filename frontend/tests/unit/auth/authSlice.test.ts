import { configureStore } from '@reduxjs/toolkit';
import { http, HttpResponse } from 'msw';
import { afterEach, describe, expect, it, vi } from 'vitest';

// Side-effect import, kept first and unused otherwise: `@app/store` sits at
// the top of a real (if latent) circular-import cycle — `@core/rbac`'s
// barrel pulls in `usePermissions.ts`, which imports `@app/store` for its
// hooks, and `authSlice.ts` separately imports `fetchMenuPermissions`/
// `clearRbac` from the same barrel. The real app never hits an ordering
// problem because `App.tsx` always reaches `@app/store` first, before
// anything needs a fully-built reducer map. A test file that imports
// `rbacSlice`/`authSlice` directly can resolve the cycle in the opposite
// order instead, which leaves `@app/store`'s own (unused, here) singleton
// assembled with undefined reducers and logs Redux's "No reducer provided"
// warning. Importing `@app/store` itself first, exactly like `App.tsx` does,
// forces the same safe resolution order and keeps the warning from firing.
import '@app/store';

import rbacReducer from '@core/rbac/rbacSlice';

import authReducer, {
  bootstrapSession,
  clearError,
  fetchCurrentUser,
  loginThunk,
  logoutThunk,
  sessionCleared,
} from '@features/authentication/store/authSlice';

import { sessionBus } from '@shared/services/sessionBus';
import { sessionCache } from '@shared/services/sessionCache';
import { storageService } from '@shared/services/storageService';

import { server } from '../../mocks/server';

const buildStore = () => configureStore({ reducer: { auth: authReducer, rbac: rbacReducer } });

const LOGIN_URL = '/api/v1/auth/login';
const ME_URL = '/api/v1/auth/me';
const LOGOUT_URL = '/api/v1/auth/logout';

const currentUser = { id: 1, username: 'alice', is_active: true };

describe('authSlice thunks and reducers', () => {
  describe('loginThunk', () => {
    it('authenticates, loads the profile, and broadcasts to other tabs on success', async () => {
      const broadcastSpy = vi.spyOn(sessionBus, 'broadcastLogin');
      server.use(
        http.post(LOGIN_URL, () =>
          HttpResponse.json({ access_token: 'tok', token_type: 'Bearer', expires_in: 1800 }),
        ),
        http.get(ME_URL, () => HttpResponse.json(currentUser)),
      );
      const store = buildStore();

      await store.dispatch(loginThunk({ username: 'alice', password: 'secret' }));

      const state = store.getState().auth;
      expect(state.isAuthenticated).toBe(true);
      expect(state.user).toEqual(currentUser);
      expect(state.isLoading).toBe(false);
      expect(sessionCache.getUser()).toEqual(currentUser);
      expect(broadcastSpy).toHaveBeenCalledTimes(1);
    });

    it('records the error message and does not authenticate on invalid credentials', async () => {
      server.use(
        http.post(LOGIN_URL, () =>
          HttpResponse.json({ detail: 'Invalid username or password' }, { status: 401 }),
        ),
      );
      const store = buildStore();

      await store.dispatch(loginThunk({ username: 'alice', password: 'wrong' }));

      const state = store.getState().auth;
      expect(state.isAuthenticated).toBe(false);
      expect(state.isLoading).toBe(false);
      expect(state.error).toBe('Invalid username or password');
    });
  });

  describe('fetchCurrentUser', () => {
    it('loads the profile and marks the session authenticated', async () => {
      server.use(http.get(ME_URL, () => HttpResponse.json(currentUser)));
      const store = buildStore();

      await store.dispatch(fetchCurrentUser());

      const state = store.getState().auth;
      expect(state.isAuthenticated).toBe(true);
      expect(state.user).toEqual(currentUser);
    });

    it('rejects with a session-expired message when the profile call fails', async () => {
      server.use(http.get(ME_URL, () => new HttpResponse(null, { status: 401 })));
      const store = buildStore();

      const result = await store.dispatch(fetchCurrentUser());

      expect(result.type).toBe('auth/fetchCurrentUser/rejected');
      expect(result.payload).toBe('Session expired');
    });
  });

  describe('bootstrapSession', () => {
    it('restores the session silently from the refresh cookie', async () => {
      server.use(
        http.post('/api/v1/auth/refresh', () =>
          HttpResponse.json({ access_token: 'tok', token_type: 'Bearer', expires_in: 1800 }),
        ),
        http.get(ME_URL, () => HttpResponse.json(currentUser)),
      );
      const store = buildStore();

      await store.dispatch(bootstrapSession());

      const state = store.getState().auth;
      expect(state.isBootstrapping).toBe(false);
      expect(state.isAuthenticated).toBe(true);
      expect(state.user).toEqual(currentUser);
    });

    it('clears the session and stops bootstrapping when there is no valid refresh cookie', async () => {
      server.use(http.post('/api/v1/auth/refresh', () => new HttpResponse(null, { status: 401 })));
      const store = buildStore();

      await store.dispatch(bootstrapSession());

      const state = store.getState().auth;
      expect(state.isBootstrapping).toBe(false);
      expect(state.isAuthenticated).toBe(false);
      expect(state.user).toBeNull();
    });

    it('does not flip isBootstrapping to true when a user is already in state', async () => {
      server.use(
        http.post('/api/v1/auth/refresh', () =>
          HttpResponse.json({ access_token: 'tok', token_type: 'Bearer', expires_in: 1800 }),
        ),
        http.get(ME_URL, () => HttpResponse.json(currentUser)),
      );
      // Preloaded directly rather than via loginThunk: loginThunk never
      // touches isBootstrapping either way, so the only way to test the
      // `pending` reducer's `if (!state.user) ...` guard is to start from a
      // state that already has both a user and isBootstrapping: false — the
      // shape AuthBootstrap is in in the background-revalidation case this
      // guards.
      const store = configureStore({
        reducer: { auth: authReducer, rbac: rbacReducer },
        preloadedState: {
          auth: {
            user: currentUser,
            isAuthenticated: true,
            isLoading: false,
            isBootstrapping: false,
            error: null,
          },
        },
      });

      // createAsyncThunk dispatches `pending` synchronously, so the flag can
      // be observed right after `dispatch(...)` returns, before the request
      // that follows it resolves.
      const inFlight = store.dispatch(bootstrapSession());
      expect(store.getState().auth.isBootstrapping).toBe(false);
      await inFlight;
      expect(store.getState().auth.isBootstrapping).toBe(false);
    });
  });

  describe('logoutThunk', () => {
    it('clears local state and broadcasts logout to other tabs', async () => {
      const broadcastSpy = vi.spyOn(sessionBus, 'broadcastLogout');
      server.use(
        http.post(LOGIN_URL, () =>
          HttpResponse.json({ access_token: 'tok', token_type: 'Bearer', expires_in: 1800 }),
        ),
        http.get(ME_URL, () => HttpResponse.json(currentUser)),
        http.post(LOGOUT_URL, () => HttpResponse.json({ detail: 'Logged out' })),
      );
      const store = buildStore();
      await store.dispatch(loginThunk({ username: 'alice', password: 'secret' }));

      await store.dispatch(logoutThunk());

      const state = store.getState().auth;
      expect(state.user).toBeNull();
      expect(state.isAuthenticated).toBe(false);
      expect(sessionCache.hasUser()).toBe(false);
      expect(broadcastSpy).toHaveBeenCalledTimes(1);
    });
  });

  describe('sessionCleared', () => {
    it('clears auth state locally without a server round-trip', () => {
      const store = buildStore();
      sessionCache.setUser(currentUser);

      store.dispatch(sessionCleared());

      const state = store.getState().auth;
      expect(state.user).toBeNull();
      expect(state.isAuthenticated).toBe(false);
      expect(state.isBootstrapping).toBe(false);
      expect(sessionCache.hasUser()).toBe(false);
    });
  });

  describe('clearError', () => {
    it('resets the error field back to null', async () => {
      server.use(http.post(LOGIN_URL, () => new HttpResponse(null, { status: 401 })));
      const store = buildStore();
      await store.dispatch(loginThunk({ username: 'alice', password: 'wrong' }));
      expect(store.getState().auth.error).toBeTruthy();

      store.dispatch(clearError());

      expect(store.getState().auth.error).toBeNull();
    });
  });
});

// Access token cleanup: authApi.login sets one via storageService, and
// leaving it set could let a later, unrelated test's apiClient call skip
// the refresh path it meant to exercise.
afterEach(() => {
  storageService.clearAccessToken();
});

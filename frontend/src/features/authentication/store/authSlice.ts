/**
 * Authentication Redux slice.
 * Manages global auth state: user, tokens, loading, errors.
 *
 * Session model:
 *   - Access token: in memory (storageService), attached as Bearer.
 *   - Refresh token: HttpOnly cookie (invisible to JS), used for silent refresh.
 *   - On startup, `bootstrapSession` silently restores the session from the cookie
 *     so reloads and new tabs stay logged in.
 *   - Login/logout broadcast to other tabs via sessionBus for a single, consistent
 *     browser session.
 */

import type { PayloadAction } from '@reduxjs/toolkit';
import { createSlice, createAsyncThunk } from '@reduxjs/toolkit';

import { fetchMenuPermissions, clearRbac } from '@core/rbac';

import { sessionBus } from '@shared/services/sessionBus';
import { sessionCache } from '@shared/services/sessionCache';
import { extractApiError } from '@shared/utils/apiError';

import { authApi } from '../api/authApi';
import type { AuthState, CurrentUser, LoginRequest } from '../models/auth.types';

// Hydrate optimistically from the cached session snapshot so a remount/reload
// renders immediately instead of blanking while the session is re-restored.
const cachedUser = sessionCache.getUser();

const initialState: AuthState = {
  user: cachedUser,
  isAuthenticated: !!cachedUser,
  isLoading: false,
  // If we already have a cached user, don't block the UI on the silent restore.
  isBootstrapping: !cachedUser,
  error: null,
};

export const loginThunk = createAsyncThunk(
  'auth/login',
  async (credentials: LoginRequest, { dispatch, rejectWithValue }) => {
    try {
      await authApi.login(credentials);
      // Fetch profile and RBAC permissions in parallel (both need the token that
      // login just placed in memory).
      const [user] = await Promise.all([
        authApi.getCurrentUser(),
        dispatch(fetchMenuPermissions()),
      ]);
      // Tell other tabs to converge on this (possibly new) identity.
      sessionBus.broadcastLogin();
      return user;
    } catch (error) {
      const message = extractApiError(error, 'Login failed. Please try again.');
      return rejectWithValue(message);
    }
  },
);

export const fetchCurrentUser = createAsyncThunk(
  'auth/fetchCurrentUser',
  async (_, { dispatch, rejectWithValue }) => {
    try {
      const [user] = await Promise.all([
        authApi.getCurrentUser(),
        dispatch(fetchMenuPermissions()),
      ]);
      sessionBus.broadcastLogin();
      return user;
    } catch {
      return rejectWithValue('Session expired');
    }
  },
);

/**
 * Silently restore the session on app startup (or when another tab signals a
 * login). Uses the HttpOnly refresh cookie — no credentials required.
 */
export const bootstrapSession = createAsyncThunk(
  'auth/bootstrap',
  async (_, { dispatch, rejectWithValue }) => {
    try {
      await authApi.refresh(); // sets access token in memory (throws if no valid cookie)
      // Profile + permissions in parallel once the token is in memory.
      const [user] = await Promise.all([
        authApi.getCurrentUser(),
        dispatch(fetchMenuPermissions()),
      ]);
      return user;
    } catch {
      return rejectWithValue('No active session');
    }
  },
);

/**
 * Full logout initiated by THIS tab: clears the server cookie, local state, RBAC,
 * and notifies other tabs.
 */
export const logoutThunk = createAsyncThunk('auth/logout', async (_, { dispatch }) => {
  await authApi.logout();
  dispatch(clearRbac());
  sessionBus.broadcastLogout();
});

const authSlice = createSlice({
  name: 'auth',
  initialState,
  reducers: {
    /**
     * Clear auth state locally without a server round-trip. Used when another
     * tab logs out (received via sessionBus) or when a silent refresh fails.
     */
    sessionCleared: (state) => {
      state.user = null;
      state.isAuthenticated = false;
      state.error = null;
      state.isBootstrapping = false;
      sessionCache.clear();
    },
    clearError: (state) => {
      state.error = null;
    },
  },
  extraReducers: (builder) => {
    builder
      // Login
      .addCase(loginThunk.pending, (state) => {
        state.isLoading = true;
        state.error = null;
      })
      .addCase(loginThunk.fulfilled, (state, action: PayloadAction<CurrentUser>) => {
        state.isLoading = false;
        state.isAuthenticated = true;
        state.user = action.payload;
        sessionCache.setUser(action.payload);
      })
      .addCase(loginThunk.rejected, (state, action) => {
        state.isLoading = false;
        state.error = action.payload as string;
      })
      // Fetch current user
      .addCase(fetchCurrentUser.pending, (state) => {
        state.isLoading = true;
      })
      .addCase(fetchCurrentUser.fulfilled, (state, action) => {
        state.isLoading = false;
        state.isAuthenticated = true;
        state.user = action.payload;
        sessionCache.setUser(action.payload);
      })
      .addCase(fetchCurrentUser.rejected, (state) => {
        state.isLoading = false;
        state.isAuthenticated = false;
        state.user = null;
        sessionCache.clear();
      })
      // Bootstrap (startup silent refresh)
      .addCase(bootstrapSession.pending, (state) => {
        // Only show the blocking splash on a truly cold start (no cached user).
        // With a cached user we render optimistically and refresh in background.
        if (!state.user) state.isBootstrapping = true;
      })
      .addCase(bootstrapSession.fulfilled, (state, action) => {
        state.isBootstrapping = false;
        state.isAuthenticated = true;
        state.user = action.payload;
        sessionCache.setUser(action.payload);
      })
      .addCase(bootstrapSession.rejected, (state) => {
        state.isBootstrapping = false;
        state.isAuthenticated = false;
        state.user = null;
        sessionCache.clear();
      })
      // Logout
      .addCase(logoutThunk.fulfilled, (state) => {
        state.user = null;
        state.isAuthenticated = false;
        state.error = null;
        sessionCache.clear();
      });
  },
});

export const { sessionCleared, clearError } = authSlice.actions;
export default authSlice.reducer;

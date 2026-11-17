/**
 * Authentication API calls.
 * Maps to backend: POST /api/v1/auth/login, /refresh, /logout, GET /auth/me
 *
 * The refresh token is delivered/consumed via an HttpOnly cookie, so it never
 * appears in these payloads. Only the short-lived access token is handled in JS
 * (kept in memory by storageService).
 */

import { apiClient, refreshAccessTokenOnce } from '@shared/services/apiClient';
import { storageService } from '@shared/services/storageService';

import type { CurrentUser, LoginRequest, TokenResponse } from '../models/auth.types';

export const authApi = {
  login: async (credentials: LoginRequest): Promise<TokenResponse> => {
    const { data } = await apiClient.post<TokenResponse>('/auth/login', credentials);
    // Access token → memory. Refresh token → HttpOnly cookie (set by server).
    storageService.setAccessToken(data.access_token);
    return data;
  },

  /**
   * Silent refresh using the HttpOnly cookie. Returns the new access token.
   *
   * Shares the in-flight attempt with the API client, so the startup bootstrap and the
   * first screen's queries restore the session once between them rather than each
   * calling `/auth/refresh` on its own.
   */
  refresh: async (): Promise<string> => {
    return refreshAccessTokenOnce();
  },

  getCurrentUser: async (): Promise<CurrentUser> => {
    const { data } = await apiClient.get<CurrentUser>('/auth/me');
    return data;
  },

  logout: async (): Promise<void> => {
    // Ask the server to clear the refresh cookie + record the audit event.
    // Best-effort: even if it fails (e.g. expired access token), we still clear
    // local state so the user is logged out on this device.
    try {
      await apiClient.post('/auth/logout');
    } catch {
      /* ignore — proceed to clear local state regardless */
    } finally {
      storageService.clearAccessToken();
    }
  },
};

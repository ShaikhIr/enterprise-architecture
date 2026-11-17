/**
 * Microsoft SSO API calls.
 * Maps to backend: GET /api/v1/auth/microsoft/login, POST /api/v1/auth/microsoft/callback
 */

import { apiClient } from '@shared/services/apiClient';

import type { TokenResponse } from '../models/auth.types';

export interface MicrosoftLoginUrlResponse {
  auth_url: string;
  redirect_uri: string;
}

export interface MicrosoftCallbackRequest {
  code: string;
  /**
   * The `state` Microsoft returned. The server compares it with the one it issued to this
   * browser at sign-in start (held in an HttpOnly cookie) and refuses the callback otherwise.
   */
  state: string;
}

export const microsoftApi = {
  /**
   * Get the Azure AD authorization URL from the backend.
   * Frontend should redirect the browser to the returned auth_url.
   */
  getLoginUrl: async (): Promise<MicrosoftLoginUrlResponse> => {
    const { data } = await apiClient.get<MicrosoftLoginUrlResponse>('/auth/microsoft/login');
    return data;
  },

  /**
   * Exchange the Microsoft authorization code for application JWT tokens.
   * Called after Azure AD redirects back with ?code=XXX&state=YYY.
   */
  exchangeCode: async (code: string, state: string): Promise<TokenResponse> => {
    const { data } = await apiClient.post<TokenResponse>('/auth/microsoft/callback', {
      code,
      state,
    });
    return data;
  },
};

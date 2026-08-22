/** Authentication domain models */

export interface LoginRequest {
  username: string;
  password: string;
}

export interface RefreshRequest {
  refresh_token: string;
}

export interface TokenResponse {
  access_token: string;
  /** Deprecated: refresh token is delivered via an HttpOnly cookie, not the body. */
  refresh_token?: string;
  token_type: string;
  expires_in: number;
}

export interface CurrentUser {
  id: string;
  username: string;
  is_active: boolean;
}

export interface AuthState {
  user: CurrentUser | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  /** True while the app is silently restoring the session on startup. */
  isBootstrapping: boolean;
  error: string | null;
}

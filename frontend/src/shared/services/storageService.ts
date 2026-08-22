/**
 * In-memory access-token store.
 *
 * The access token is kept in memory only (never in localStorage/sessionStorage)
 * to minimize XSS exposure. It naturally dies with the tab.
 *
 * The refresh token is NOT stored here at all — it lives in an HttpOnly cookie
 * set by the backend, invisible to JavaScript. Session continuity across page
 * reloads and new tabs is achieved by silently calling /auth/refresh (which
 * reads that cookie) on startup and on access-token expiry.
 */

let accessToken: string | null = null;

export const storageService = {
  getAccessToken: (): string | null => accessToken,

  setAccessToken: (token: string): void => {
    accessToken = token;
  },

  clearAccessToken: (): void => {
    accessToken = null;
  },

  isAuthenticated: (): boolean => accessToken !== null,
};

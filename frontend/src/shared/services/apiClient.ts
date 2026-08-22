/**
 * Axios API client with interceptors.
 * - Sends cookies (HttpOnly refresh token) with every request via withCredentials
 * - Attaches in-memory Bearer access token to requests
 * - Restores the access token *before* sending, when the tab has none yet
 * - On 401, silently refreshes the access token using the refresh cookie
 * - Collapses concurrent refreshes into one, and retries each caller once
 * - Correlation ID header
 *
 * The access token lives in memory only, so a page reload starts with none. The UI
 * meanwhile renders straight away from the cached session snapshot, which means screens
 * mount and fire their queries before the silent refresh has finished. Recovering from
 * that on the way back — retry whatever came back unauthorised — is not enough on its
 * own: it depends on every protected endpoint answering 401 for a missing token, and it
 * turns each first paint into a round of failures. So the request side waits for the
 * token instead, and the 401 path is left to handle the case it is actually for, an
 * access token that expired mid-session.
 */

import type { AxiosError, InternalAxiosRequestConfig } from 'axios';
import axios from 'axios';

import { storageService } from './storageService';

const API_BASE_URL = '/api/v1';

/*
  `axios.create` on the default export is the documented way to build an instance. The
  import/no-named-as-default-member rule flags it because axios also exports `create`
  standalone, but the two are the same function and the default form is what every axios
  example and its own typings assume. Silenced here rather than app-wide, so the rule keeps
  catching the mistake it is actually for.
*/
// eslint-disable-next-line import/no-named-as-default-member
export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000,
  withCredentials: true, // send/receive the HttpOnly refresh cookie
  headers: {
    'Content-Type': 'application/json',
    Accept: 'application/json',
  },
});

/**
 * Handler invoked when the session cannot be recovered (refresh failed).
 * The app registers a router-aware handler so we can clear state and navigate
 * to /login WITHOUT a full page reload (which would wipe in-memory state and
 * cause flicker). Falls back to a hard redirect if nothing is registered.
 */
type SessionExpiredHandler = () => void;
let onSessionExpired: SessionExpiredHandler = () => {
  window.location.href = '/login';
};

export const setSessionExpiredHandler = (handler: SessionExpiredHandler): void => {
  onSessionExpired = handler;
};

/**
 * Perform a silent refresh using the HttpOnly cookie. Returns the new access token.
 *
 * Deliberately on the bare `axios`, not `apiClient`: going through the instance would
 * put the refresh through the very interceptors that call it.
 *
 * Private on purpose — callers want `refreshAccessTokenOnce`, so that two of them asking
 * at the same time do not become two refreshes.
 */
const refreshAccessToken = async (): Promise<string> => {
  const { data } = await axios.post(`${API_BASE_URL}/auth/refresh`, {}, { withCredentials: true });
  const token = data.access_token as string;
  storageService.setAccessToken(token);
  return token;
};

/**
 * The one refresh in flight, if any.
 *
 * On reload a screen can easily fire a dozen requests in the same tick, and each of them
 * wants the same token. Sharing the promise makes that one call to `/auth/refresh`
 * instead of a dozen, and — more importantly — one outcome, so they cannot disagree about
 * whether the session survived.
 */
let inFlightRefresh: Promise<string> | null = null;

/** Refresh, joining the in-flight attempt when there is one. Rejects if it fails. */
export const refreshAccessTokenOnce = (): Promise<string> => {
  inFlightRefresh ??= refreshAccessToken().finally(() => {
    inFlightRefresh = null;
  });
  return inFlightRefresh;
};

/**
 * The endpoints that establish a session, and so must never wait for one.
 *
 * Logging in with no token is the normal case, and a refresh cannot wait for itself.
 */
const isSessionEndpoint = (url?: string): boolean =>
  Boolean(url && (url.includes('/auth/login') || url.includes('/auth/refresh')));

/**
 * The access token, restoring it first when this tab does not have one.
 *
 * Returns null rather than throwing when there is no session to restore: the caller is a
 * request that will fail on its own merits, and the response interceptor is the place
 * that decides a session is over.
 */
const resolveAccessToken = async (): Promise<string | null> => {
  const token = storageService.getAccessToken();
  if (token) return token;
  try {
    return await refreshAccessTokenOnce();
  } catch {
    return null;
  }
};

// Request interceptor: attach token + correlation ID
apiClient.interceptors.request.use(
  async (config: InternalAxiosRequestConfig) => {
    const token = isSessionEndpoint(config.url)
      ? storageService.getAccessToken()
      : await resolveAccessToken();
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    config.headers['X-Correlation-ID'] = crypto.randomUUID();
    return config;
  },
  (error) => Promise.reject(error),
);

// Response interceptor: handle 401 with a single shared refresh
apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const originalRequest = error.config as InternalAxiosRequestConfig & {
      _retry?: boolean;
    };

    // Never try to refresh the refresh call itself, and only retry once.
    const isAuthRefreshCall = originalRequest?.url?.includes('/auth/refresh');

    if (error.response?.status === 401 && !originalRequest._retry && !isAuthRefreshCall) {
      originalRequest._retry = true;

      // Whoever gets here first starts the refresh; the rest join it. Each then retries
      // its own request, which is why no queue of pending callers is needed.
      try {
        const accessToken = await refreshAccessTokenOnce();
        originalRequest.headers.Authorization = `Bearer ${accessToken}`;
        return apiClient(originalRequest);
      } catch (refreshError) {
        storageService.clearAccessToken();
        onSessionExpired();
        return Promise.reject(refreshError);
      }
    }

    return Promise.reject(error);
  },
);

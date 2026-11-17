/**
 * Non-sensitive session snapshot cache (sessionStorage).
 *
 * Purpose: make app (re)mounts instant. On any remount/reload the in-memory
 * access token is gone and the app would otherwise show a blank splash while it
 * sequentially re-runs refresh → me → menu. Caching the *non-sensitive* parts of
 * the session (user profile + RBAC menu keys/permissions) lets the UI hydrate
 * and render immediately, while the access token is silently refreshed in the
 * background.
 *
 * SECURITY: The access token is deliberately NOT stored here (it stays in memory
 * via storageService). Only the user profile and menu permissions live here.
 * sessionStorage is per-tab and cleared when the tab closes.
 */

import type { PermissionAction, Permission } from '@core/rbac/types';

import type { CurrentUser } from '@features/authentication/models/auth.types';

const KEY = 'session_snapshot_v1';

interface Snapshot {
  user?: CurrentUser | null;
  menuKeys?: string[];
  permissions?: Permission[];
  /** API-scope permission codes, cached for the same reason as menu keys. */
  apiCodes?: string[];
  apiResourceActions?: Record<string, PermissionAction[]>;
}

function read(): Snapshot {
  try {
    return JSON.parse(sessionStorage.getItem(KEY) || '{}') as Snapshot;
  } catch {
    return {};
  }
}

function write(patch: Snapshot): void {
  try {
    sessionStorage.setItem(KEY, JSON.stringify({ ...read(), ...patch }));
  } catch {
    /* storage full / unavailable — non-fatal, caching is best-effort */
  }
}

export const sessionCache = {
  getUser: (): CurrentUser | null => read().user ?? null,
  getMenuKeys: (): string[] => read().menuKeys ?? [],
  getPermissions: (): Permission[] => read().permissions ?? [],
  getApiCodes: (): string[] => read().apiCodes ?? [],
  getApiResourceActions: (): Record<string, PermissionAction[]> => read().apiResourceActions ?? {},
  hasUser: (): boolean => !!read().user,

  setUser: (user: CurrentUser | null): void => write({ user }),
  setRbac: (menuKeys: string[], permissions: Permission[]): void =>
    write({ menuKeys, permissions }),
  setApiRbac: (apiCodes: string[], apiResourceActions: Record<string, PermissionAction[]>): void =>
    write({ apiCodes, apiResourceActions }),

  clear: (): void => {
    try {
      sessionStorage.removeItem(KEY);
    } catch {
      /* ignore */
    }
  },
};

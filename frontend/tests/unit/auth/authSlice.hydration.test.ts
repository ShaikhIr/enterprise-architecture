import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

/**
 * `authSlice.ts` imports `fetchMenuPermissions`/`clearRbac` from the
 * `@core/rbac` barrel, which re-exports `usePermissions.ts`/`PermissionGate.tsx`
 * — and those import `@app/store` for `useAppSelector`, which in turn imports
 * `authSlice.ts` for its `auth` reducer. That cycle is harmless during a normal
 * app boot (nothing at module-top-level scope reads the circular value before
 * the whole graph settles), but re-entering it here — via `vi.resetModules()`
 * plus a dynamic re-import with `authSlice.ts` as the fresh entry point —
 * resolves the cycle in a different order: `@app/store` ends up building its
 * store from an `authReducer` binding that has not finished initialising yet,
 * and Redux logs "No reducer provided for key ...". Mocking the barrel avoids
 * pulling that chain in at all; the hydration test only calls the exported
 * reducer function directly, never the thunks that use these two exports.
 */
vi.mock('@core/rbac', () => ({
  fetchMenuPermissions: vi.fn(),
  clearRbac: vi.fn(),
}));

/**
 * `authSlice.ts` reads `sessionCache.getUser()` once at module-evaluation
 * time to build `initialState`. Observing both the cold and warm starting
 * states requires resetting the module registry and re-importing between
 * them.
 */
describe('authSlice initial state hydration', () => {
  beforeEach(() => {
    sessionStorage.clear();
    vi.resetModules();
  });

  afterEach(() => {
    sessionStorage.clear();
  });

  it('starts unauthenticated and bootstrapping when there is no cached user', async () => {
    const { default: authReducer } = await import('@features/authentication/store/authSlice');

    const state = authReducer(undefined, { type: '@@INIT' });

    expect(state.user).toBeNull();
    expect(state.isAuthenticated).toBe(false);
    expect(state.isBootstrapping).toBe(true);
  });

  it('hydrates the user and skips the bootstrap splash when a session snapshot is cached', async () => {
    sessionStorage.setItem(
      'session_snapshot_v1',
      JSON.stringify({ user: { id: 1, username: 'alice', is_active: true } }),
    );

    const { default: authReducer } = await import('@features/authentication/store/authSlice');
    const state = authReducer(undefined, { type: '@@INIT' });

    expect(state.user).toEqual({ id: 1, username: 'alice', is_active: true });
    expect(state.isAuthenticated).toBe(true);
    expect(state.isBootstrapping).toBe(false);
  });
});

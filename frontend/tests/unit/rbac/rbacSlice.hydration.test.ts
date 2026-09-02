import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

/**
 * `rbacSlice.ts` computes its `initialState` once, at module-evaluation time,
 * by reading `sessionCache`. That means the only way to observe both the
 * "cold" and "warm" starting states in the same test file is to reset the
 * module registry and re-import between them — a normal top-of-file import
 * would only ever see whatever sessionStorage happened to hold when this
 * file's imports were first evaluated.
 */
describe('rbacSlice initial state hydration', () => {
  beforeEach(() => {
    sessionStorage.clear();
    vi.resetModules();
  });

  afterEach(() => {
    sessionStorage.clear();
  });

  it('starts empty and not-loaded when there is no cached session snapshot', async () => {
    const { default: rbacReducer } = await import('@core/rbac/rbacSlice');

    const state = rbacReducer(undefined, { type: '@@INIT' });

    expect(state.menuKeys).toEqual([]);
    expect(state.menuPermissions).toEqual([]);
    expect(state.apiCodes).toEqual([]);
    expect(state.apiResourceActions).toEqual({});
    expect(state.isLoaded).toBe(false);
    expect(state.isApiLoaded).toBe(false);
  });

  it('hydrates menu keys/permissions and flips isLoaded from a cached snapshot', async () => {
    sessionStorage.setItem(
      'session_snapshot_v1',
      JSON.stringify({
        menuKeys: ['dashboard', 'masters'],
        permissions: [
          {
            id: 1,
            code: 'countries.read',
            name: 'Read countries',
            description: '',
            scope: 'MENU',
            resource: 'countries',
            action: 'READ',
            is_active: true,
          },
        ],
      }),
    );

    const { default: rbacReducer } = await import('@core/rbac/rbacSlice');
    const state = rbacReducer(undefined, { type: '@@INIT' });

    expect(state.menuKeys).toEqual(['dashboard', 'masters']);
    expect(state.menuPermissions).toHaveLength(1);
    expect(state.isLoaded).toBe(true);
  });

  it('hydrates API codes/resource-actions and flips isApiLoaded from a cached snapshot', async () => {
    sessionStorage.setItem(
      'session_snapshot_v1',
      JSON.stringify({
        apiCodes: ['countries.create'],
        apiResourceActions: { countries: ['CREATE', 'READ'] },
      }),
    );

    const { default: rbacReducer } = await import('@core/rbac/rbacSlice');
    const state = rbacReducer(undefined, { type: '@@INIT' });

    expect(state.apiCodes).toEqual(['countries.create']);
    expect(state.apiResourceActions).toEqual({ countries: ['CREATE', 'READ'] });
    expect(state.isApiLoaded).toBe(true);
  });

  it('treats an empty cached menu-keys array the same as no cache at all', async () => {
    sessionStorage.setItem('session_snapshot_v1', JSON.stringify({ menuKeys: [] }));

    const { default: rbacReducer } = await import('@core/rbac/rbacSlice');
    const state = rbacReducer(undefined, { type: '@@INIT' });

    expect(state.isLoaded).toBe(false);
  });
});

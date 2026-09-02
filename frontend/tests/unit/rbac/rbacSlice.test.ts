import { configureStore } from '@reduxjs/toolkit';
import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';

import rbacReducer, {
  clearRbac,
  fetchApiPermissions,
  fetchFieldPermissions,
  fetchMenuPermissions,
} from '@core/rbac/rbacSlice';

import { sessionCache } from '@shared/services/sessionCache';

import { server } from '../../mocks/server';

const buildStore = () => configureStore({ reducer: { rbac: rbacReducer } });

const MENU_URL = '/api/v1/rbac/my-permissions/menu';
const API_URL = '/api/v1/rbac/my-permissions/api';
const fieldsUrl = (resource: string) => `/api/v1/rbac/my-permissions/fields/${resource}`;

describe('rbacSlice thunks and reducers', () => {
  describe('fetchMenuPermissions', () => {
    it('loads menu keys/permissions on success and caches the snapshot', async () => {
      server.use(
        http.get(MENU_URL, () =>
          HttpResponse.json({
            menu_keys: ['dashboard', 'masters'],
            permissions: [
              {
                id: 1,
                code: 'masters.read',
                name: 'Masters',
                description: '',
                scope: 'MENU',
                resource: 'masters',
                action: 'READ',
                is_active: true,
              },
            ],
          }),
        ),
      );
      const store = buildStore();

      await store.dispatch(fetchMenuPermissions());

      const state = store.getState().rbac;
      expect(state.isLoaded).toBe(true);
      expect(state.isLoading).toBe(false);
      expect(state.menuKeys).toEqual(['dashboard', 'masters']);
      expect(sessionCache.getMenuKeys()).toEqual(['dashboard', 'masters']);
    });

    it('records the error message and leaves isLoaded false on failure', async () => {
      server.use(http.get(MENU_URL, () => new HttpResponse(null, { status: 500 })));
      const store = buildStore();

      await store.dispatch(fetchMenuPermissions());

      const state = store.getState().rbac;
      expect(state.isLoaded).toBe(false);
      expect(state.isLoading).toBe(false);
      expect(state.error).toBeTruthy();
    });
  });

  describe('fetchApiPermissions', () => {
    it('loads API codes/resource-actions on success and caches the snapshot', async () => {
      server.use(
        http.get(API_URL, () =>
          HttpResponse.json({
            codes: ['countries.create'],
            resource_actions: { countries: ['CREATE'] },
            permissions: [],
          }),
        ),
      );
      const store = buildStore();

      await store.dispatch(fetchApiPermissions());

      const state = store.getState().rbac;
      expect(state.isApiLoaded).toBe(true);
      expect(state.apiCodes).toEqual(['countries.create']);
      expect(sessionCache.getApiCodes()).toEqual(['countries.create']);
    });

    it('does not dispatch a second request while one is already loading (condition guard)', async () => {
      let calls = 0;
      server.use(
        http.get(API_URL, async () => {
          calls += 1;
          // Hold the response open long enough for a second dispatch to race it.
          await new Promise((resolve) => setTimeout(resolve, 20));
          return HttpResponse.json({ codes: [], resource_actions: {}, permissions: [] });
        }),
      );
      const store = buildStore();

      await Promise.all([
        store.dispatch(fetchApiPermissions()),
        store.dispatch(fetchApiPermissions()),
      ]);

      expect(calls).toBe(1);
    });

    it('does not re-fetch once already loaded', async () => {
      let calls = 0;
      server.use(
        http.get(API_URL, () => {
          calls += 1;
          return HttpResponse.json({ codes: ['x'], resource_actions: {}, permissions: [] });
        }),
      );
      const store = buildStore();

      await store.dispatch(fetchApiPermissions());
      await store.dispatch(fetchApiPermissions());

      expect(calls).toBe(1);
    });

    it('leaves isApiLoaded false on failure, so gates stay closed', async () => {
      server.use(http.get(API_URL, () => new HttpResponse(null, { status: 500 })));
      const store = buildStore();

      await store.dispatch(fetchApiPermissions());

      expect(store.getState().rbac.isApiLoaded).toBe(false);
    });
  });

  describe('fetchFieldPermissions', () => {
    it('stores the grants under the requested resource and marks it loaded', async () => {
      server.use(
        http.get(fieldsUrl('users'), () =>
          HttpResponse.json({ resource: 'users', fields: { salary: ['READ'] } }),
        ),
      );
      const store = buildStore();

      await store.dispatch(fetchFieldPermissions('users'));

      const state = store.getState().rbac;
      expect(state.fieldPermissions.users).toEqual({ salary: ['READ'] });
      expect(state.fieldPermissionStatus.users).toBe('loaded');
    });

    it('marks the resource as errored (not loading forever) on failure', async () => {
      server.use(http.get(fieldsUrl('users'), () => new HttpResponse(null, { status: 403 })));
      const store = buildStore();

      await store.dispatch(fetchFieldPermissions('users'));

      expect(store.getState().rbac.fieldPermissionStatus.users).toBe('error');
    });

    it('tracks status per resource independently', async () => {
      server.use(
        http.get(fieldsUrl('users'), () =>
          HttpResponse.json({ resource: 'users', fields: { salary: ['READ'] } }),
        ),
        http.get(fieldsUrl('employees'), () => new HttpResponse(null, { status: 500 })),
      );
      const store = buildStore();

      await store.dispatch(fetchFieldPermissions('users'));
      await store.dispatch(fetchFieldPermissions('employees'));

      const state = store.getState().rbac;
      expect(state.fieldPermissionStatus.users).toBe('loaded');
      expect(state.fieldPermissionStatus.employees).toBe('error');
    });
  });

  describe('clearRbac', () => {
    it('resets every loaded/loading flag and empties the caches', async () => {
      server.use(
        http.get(MENU_URL, () => HttpResponse.json({ menu_keys: ['dashboard'], permissions: [] })),
        http.get(API_URL, () =>
          HttpResponse.json({ codes: ['x'], resource_actions: {}, permissions: [] }),
        ),
      );
      const store = buildStore();
      await store.dispatch(fetchMenuPermissions());
      await store.dispatch(fetchApiPermissions());

      store.dispatch(clearRbac());

      const state = store.getState().rbac;
      expect(state.menuKeys).toEqual([]);
      expect(state.apiCodes).toEqual([]);
      expect(state.isLoaded).toBe(false);
      expect(state.isApiLoaded).toBe(false);
      expect(sessionCache.getMenuKeys()).toEqual([]);
    });
  });
});

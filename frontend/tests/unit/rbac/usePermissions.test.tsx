import type { PropsWithChildren } from 'react';

import { renderHook, waitFor } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { Provider } from 'react-redux';
import { describe, expect, it } from 'vitest';

import {
  useApiPermissions,
  useCan,
  useFieldPermissions,
  useHasPermission,
  useMenuPermission,
  useMenuPermissions,
} from '@core/rbac/usePermissions';

import { server } from '../../mocks/server';
import { createTestStore, type TestStore } from '../../test-utils';

const MENU_URL = '/api/v1/rbac/my-permissions/menu';
const API_URL = '/api/v1/rbac/my-permissions/api';
const fieldsUrl = (resource: string) => `/api/v1/rbac/my-permissions/fields/${resource}`;

const wrapperFor = (store: TestStore) => {
  const Wrapper = ({ children }: PropsWithChildren) => (
    <Provider store={store}>{children}</Provider>
  );
  return Wrapper;
};

describe('useMenuPermission', () => {
  it('is inaccessible while menu permissions have not loaded', () => {
    const store = createTestStore();
    const { result } = renderHook(() => useMenuPermission('masters'), {
      wrapper: wrapperFor(store),
    });

    expect(result.current.isLoaded).toBe(false);
    expect(result.current.canAccess).toBe(false);
  });

  it('grants access once the menu key is present in loaded state', () => {
    const store = createTestStore({
      rbac: {
        menuKeys: ['masters'],
        menuPermissions: [],
        apiCodes: [],
        apiResourceActions: {},
        fieldPermissions: {},
        fieldPermissionStatus: {},
        isLoaded: true,
        isApiLoaded: false,
        isLoading: false,
        isApiLoading: false,
        error: null,
      },
    });

    const { result } = renderHook(() => useMenuPermission('masters'), {
      wrapper: wrapperFor(store),
    });

    expect(result.current.canAccess).toBe(true);
  });

  it('denies access to a menu key absent from the loaded set', () => {
    const store = createTestStore({
      rbac: {
        menuKeys: ['dashboard'],
        menuPermissions: [],
        apiCodes: [],
        apiResourceActions: {},
        fieldPermissions: {},
        fieldPermissionStatus: {},
        isLoaded: true,
        isApiLoaded: false,
        isLoading: false,
        isApiLoading: false,
        error: null,
      },
    });

    const { result } = renderHook(() => useMenuPermission('masters'), {
      wrapper: wrapperFor(store),
    });

    expect(result.current.canAccess).toBe(false);
  });
});

describe('useMenuPermissions', () => {
  it('self-dispatches a fetch on mount when not already loaded/loading', async () => {
    server.use(
      http.get(MENU_URL, () =>
        HttpResponse.json({ menu_keys: ['dashboard', 'masters'], permissions: [] }),
      ),
    );
    const store = createTestStore();

    const { result } = renderHook(() => useMenuPermissions(), { wrapper: wrapperFor(store) });

    await waitFor(() => expect(result.current.isLoaded).toBe(true));
    expect(result.current.menuKeys).toEqual(['dashboard', 'masters']);
  });
});

describe('useApiPermissions', () => {
  it('self-dispatches a fetch on mount and reports readiness', async () => {
    server.use(
      http.get(API_URL, () =>
        HttpResponse.json({ codes: ['countries.create'], resource_actions: {}, permissions: [] }),
      ),
    );
    const store = createTestStore();

    const { result } = renderHook(() => useApiPermissions(), { wrapper: wrapperFor(store) });

    await waitFor(() => expect(result.current.isLoaded).toBe(true));
    expect(result.current.apiCodes).toEqual(['countries.create']);
  });
});

describe('useHasPermission', () => {
  it('grants access for a code present in the API-scope grants', async () => {
    const store = createTestStore({
      rbac: {
        menuKeys: [],
        menuPermissions: [],
        apiCodes: ['reports.export'],
        apiResourceActions: {},
        fieldPermissions: {},
        fieldPermissionStatus: {},
        isLoaded: false,
        isApiLoaded: true,
        isLoading: false,
        isApiLoading: false,
        error: null,
      },
    });

    const { result } = renderHook(() => useHasPermission('reports.export'), {
      wrapper: wrapperFor(store),
    });

    expect(result.current).toBe(true);
  });

  it('falls back to the menu-scope permission list when not an API code', () => {
    const store = createTestStore({
      rbac: {
        menuKeys: [],
        menuPermissions: [
          {
            id: 1,
            code: 'reports.export',
            name: '',
            description: '',
            scope: 'MENU',
            resource: 'reports',
            action: 'EXPORT',
            is_active: true,
          },
        ],
        apiCodes: [],
        apiResourceActions: {},
        fieldPermissions: {},
        fieldPermissionStatus: {},
        isLoaded: true,
        isApiLoaded: true,
        isLoading: false,
        isApiLoading: false,
        error: null,
      },
    });

    const { result } = renderHook(() => useHasPermission('reports.export'), {
      wrapper: wrapperFor(store),
    });

    expect(result.current).toBe(true);
  });

  it('denies a code found in neither set', () => {
    const store = createTestStore({
      rbac: {
        menuKeys: [],
        menuPermissions: [],
        apiCodes: [],
        apiResourceActions: {},
        fieldPermissions: {},
        fieldPermissionStatus: {},
        isLoaded: true,
        isApiLoaded: true,
        isLoading: false,
        isApiLoading: false,
        error: null,
      },
    });

    const { result } = renderHook(() => useHasPermission('reports.export'), {
      wrapper: wrapperFor(store),
    });

    expect(result.current).toBe(false);
  });
});

describe('useCan', () => {
  it('stays closed until the API grants have loaded, even if a later render would allow it', () => {
    const store = createTestStore({
      rbac: {
        menuKeys: [],
        menuPermissions: [],
        apiCodes: [],
        apiResourceActions: { countries: ['CREATE'] },
        fieldPermissions: {},
        fieldPermissionStatus: {},
        isLoaded: false,
        isApiLoaded: false,
        isLoading: false,
        isApiLoading: false,
        error: null,
      },
    });

    const { result } = renderHook(() => useCan('countries', 'CREATE'), {
      wrapper: wrapperFor(store),
    });

    expect(result.current).toBe(false);
  });

  it('grants the (resource, action) pair once loaded and present', () => {
    const store = createTestStore({
      rbac: {
        menuKeys: [],
        menuPermissions: [],
        apiCodes: [],
        apiResourceActions: { countries: ['CREATE', 'READ'] },
        fieldPermissions: {},
        fieldPermissionStatus: {},
        isLoaded: false,
        isApiLoaded: true,
        isLoading: false,
        isApiLoading: false,
        error: null,
      },
    });

    const { result } = renderHook(() => useCan('countries', 'CREATE'), {
      wrapper: wrapperFor(store),
    });

    expect(result.current).toBe(true);
  });

  it('denies an action the resource does not grant', () => {
    const store = createTestStore({
      rbac: {
        menuKeys: [],
        menuPermissions: [],
        apiCodes: [],
        apiResourceActions: { countries: ['READ'] },
        fieldPermissions: {},
        fieldPermissionStatus: {},
        isLoaded: false,
        isApiLoaded: true,
        isLoading: false,
        isApiLoading: false,
        error: null,
      },
    });

    const { result } = renderHook(() => useCan('countries', 'DELETE'), {
      wrapper: wrapperFor(store),
    });

    expect(result.current).toBe(false);
  });
});

describe('useFieldPermissions', () => {
  it('lazy-loads field grants for the resource on first access', async () => {
    server.use(
      http.get(fieldsUrl('users'), () =>
        HttpResponse.json({ resource: 'users', fields: { salary: ['READ'] } }),
      ),
    );
    const store = createTestStore();

    const { result } = renderHook(() => useFieldPermissions('users'), {
      wrapper: wrapperFor(store),
    });

    expect(result.current.isLoading).toBe(true);
    await waitFor(() => expect(result.current.isLoaded).toBe(true));
    expect(result.current.canReadField('salary')).toBe(true);
    expect(result.current.canWriteField('salary')).toBe(false);
    expect(result.current.isSettled).toBe(true);
  });

  it('settles (but does not load) on failure, so a caller stops waiting', async () => {
    server.use(http.get(fieldsUrl('users'), () => new HttpResponse(null, { status: 403 })));
    const store = createTestStore();

    const { result } = renderHook(() => useFieldPermissions('users'), {
      wrapper: wrapperFor(store),
    });

    await waitFor(() => expect(result.current.failed).toBe(true));
    expect(result.current.isLoaded).toBe(false);
    expect(result.current.isSettled).toBe(true);
    expect(result.current.canReadField('salary')).toBe(false);
  });
});

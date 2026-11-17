import type { PropsWithChildren } from 'react';

import { QueryClientProvider, type QueryClient } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';

import {
  useAllUsers,
  useCreateUser,
  useImportEmployees,
  useUpdateUser,
  useUser,
  useUsers,
} from '@features/user-management/hooks/useUsers';
import type { User } from '@features/user-management/models/User';

import { server } from '../../mocks/server';
import { createTestQueryClient } from '../../test-utils';

const wrapperWith = (queryClient: QueryClient) => {
  const Wrapper = ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  return Wrapper;
};

const makeUser = (overrides: Partial<User> = {}): User => ({
  id: 1,
  username: 'alice',
  is_active: true,
  is_blocked: false,
  is_validate_ad: false,
  employee_id: null,
  employee_name: null,
  email: null,
  last_login: null,
  created_by: 'system',
  created_date: '2024-01-01T00:00:00Z',
  modified_by: 'system',
  modified_date: '2024-01-01T00:00:00Z',
  ...overrides,
});

const listing = (users: User[], total = users.length) =>
  HttpResponse.json({ users, total, skip: 0, limit: 100 });

/**
 * A test client that keeps unobserved cache entries around.
 *
 * `createTestQueryClient` uses `gcTime: 0`, which evicts a seeded entry the moment nothing
 * observes it, leaving nothing for an `isInvalidated` check to read.
 */
const createRetainingQueryClient = (): QueryClient => {
  const queryClient = createTestQueryClient();
  queryClient.setDefaultOptions({
    ...queryClient.getDefaultOptions(),
    queries: { ...queryClient.getDefaultOptions().queries, gcTime: Infinity },
  });
  return queryClient;
};

/** Seed a cache entry under `key`, so a later `isInvalidated` check has something to read. */
const seed = (queryClient: QueryClient, key: unknown[]) =>
  queryClient.prefetchQuery({ queryKey: key, queryFn: () => Promise.resolve('seeded') });

describe('useUsers', () => {
  it('sends skip and limit as query params and returns the page', async () => {
    let captured = null as URL | null;
    server.use(
      http.get('/api/v1/users', ({ request }) => {
        captured = new URL(request.url);
        return listing([makeUser()]);
      }),
    );

    const { result } = renderHook(() => useUsers(20, 10), {
      wrapper: wrapperWith(createTestQueryClient()),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(captured?.searchParams.get('skip')).toBe('20');
    expect(captured?.searchParams.get('limit')).toBe('10');
    expect(result.current.data?.users).toEqual([makeUser()]);
  });

  it('defaults to the first page of 100', async () => {
    let captured = null as URL | null;
    server.use(
      http.get('/api/v1/users', ({ request }) => {
        captured = new URL(request.url);
        return listing([]);
      }),
    );

    const { result } = renderHook(() => useUsers(), {
      wrapper: wrapperWith(createTestQueryClient()),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(captured?.searchParams.get('skip')).toBe('0');
    expect(captured?.searchParams.get('limit')).toBe('100');
  });

  it('surfaces a server failure as an error state', async () => {
    server.use(
      http.get('/api/v1/users', () => HttpResponse.json({ detail: 'boom' }, { status: 500 })),
    );

    const { result } = renderHook(() => useUsers(), {
      wrapper: wrapperWith(createTestQueryClient()),
    });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.data).toBeUndefined();
  });
});

describe('useAllUsers', () => {
  it('reads every page, 500 rows at a time, and returns a flat list', async () => {
    const skips: (string | null)[] = [];
    server.use(
      http.get('/api/v1/users', ({ request }) => {
        const params = new URL(request.url).searchParams;
        skips.push(params.get('skip'));
        expect(params.get('limit')).toBe('500');
        const first = params.get('skip') === '0';
        return listing(first ? [makeUser({ id: 1 })] : [makeUser({ id: 2, username: 'bob' })], 501);
      }),
    );

    const { result } = renderHook(() => useAllUsers(), {
      wrapper: wrapperWith(createTestQueryClient()),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(skips).toEqual(['0', '500']);
    expect(result.current.data?.map((u) => u.id)).toEqual([1, 2]);
  });

  it('does not share a cache entry with the paged useUsers query', async () => {
    server.use(http.get('/api/v1/users', () => listing([makeUser()])));
    const queryClient = createRetainingQueryClient();

    const paged = renderHook(() => useUsers(), { wrapper: wrapperWith(queryClient) });
    const all = renderHook(() => useAllUsers(), { wrapper: wrapperWith(queryClient) });

    await waitFor(() => expect(paged.result.current.isSuccess).toBe(true));
    await waitFor(() => expect(all.result.current.isSuccess).toBe(true));
    // One is the page envelope, the other the flattened array.
    expect(paged.result.current.data).toHaveProperty('users');
    expect(Array.isArray(all.result.current.data)).toBe(true);
  });
});

describe('useUser', () => {
  it('fetches the user by numeric id', async () => {
    server.use(
      http.get('/api/v1/users/:id', ({ params }) =>
        HttpResponse.json(makeUser({ id: Number(params.id), username: 'carol' })),
      ),
    );

    const { result } = renderHook(() => useUser(501), {
      wrapper: wrapperWith(createTestQueryClient()),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toMatchObject({ id: 501, username: 'carol' });
  });

  it('stays idle (no request) when the id is the unsaved sentinel 0', async () => {
    let requested = false;
    server.use(
      http.get('/api/v1/users/:id', () => {
        requested = true;
        return HttpResponse.json(makeUser());
      }),
    );

    const { result } = renderHook(() => useUser(0), {
      wrapper: wrapperWith(createTestQueryClient()),
    });

    expect(result.current.fetchStatus).toBe('idle');
    expect(requested).toBe(false);
  });
});

describe('useCreateUser', () => {
  it('posts the request body to /users', async () => {
    let body: unknown = null;
    server.use(
      http.post('/api/v1/users', async ({ request }) => {
        body = await request.json();
        return HttpResponse.json(makeUser({ id: 9, username: 'newbie' }), { status: 201 });
      }),
    );

    const { result } = renderHook(() => useCreateUser(), {
      wrapper: wrapperWith(createTestQueryClient()),
    });
    result.current.mutate({
      username: 'newbie',
      password: 'Passw0rd!',
      is_validate_ad: false,
      role_id: 3,
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(body).toEqual({
      username: 'newbie',
      password: 'Passw0rd!',
      is_validate_ad: false,
      role_id: 3,
    });
    expect(result.current.data?.id).toBe(9);
  });

  it('invalidates the users caches (list and all), and nothing unrelated', async () => {
    server.use(http.post('/api/v1/users', () => HttpResponse.json(makeUser({ id: 9 }))));
    const queryClient = createRetainingQueryClient();
    await seed(queryClient, ['users', 0, 100]);
    await seed(queryClient, ['users', 'all']);
    await seed(queryClient, ['masters', 'countries']);

    const { result } = renderHook(() => useCreateUser(), { wrapper: wrapperWith(queryClient) });
    result.current.mutate({
      username: 'x1',
      password: 'Passw0rd!',
      is_validate_ad: true,
      role_id: 1,
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(queryClient.getQueryState(['users', 0, 100])?.isInvalidated).toBe(true);
    expect(queryClient.getQueryState(['users', 'all'])?.isInvalidated).toBe(true);
    expect(queryClient.getQueryState(['masters', 'countries'])?.isInvalidated).toBe(false);
  });

  it('propagates a 409 duplicate-username conflict and invalidates nothing', async () => {
    server.use(
      http.post('/api/v1/users', () =>
        HttpResponse.json({ detail: 'Username already exists' }, { status: 409 }),
      ),
    );
    const queryClient = createRetainingQueryClient();
    await seed(queryClient, ['users', 0, 100]);

    const { result } = renderHook(() => useCreateUser(), { wrapper: wrapperWith(queryClient) });
    result.current.mutate({
      username: 'dup',
      password: 'Passw0rd!',
      is_validate_ad: true,
      role_id: 1,
    });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect((result.current.error as { response?: { status?: number } }).response?.status).toBe(409);
    expect(queryClient.getQueryState(['users', 0, 100])?.isInvalidated).toBe(false);
  });
});

describe('useUpdateUser', () => {
  it('patches /users/:id with the request body and invalidates the users caches', async () => {
    let url: string | null = null;
    let body: unknown = null;
    server.use(
      http.patch('/api/v1/users/:id', async ({ request, params }) => {
        url = String(params.id);
        body = await request.json();
        return HttpResponse.json(makeUser({ id: Number(params.id), is_blocked: true }));
      }),
    );
    const queryClient = createRetainingQueryClient();
    await seed(queryClient, ['users', 0, 100]);
    await seed(queryClient, ['user', 42]);

    const { result } = renderHook(() => useUpdateUser(), { wrapper: wrapperWith(queryClient) });
    result.current.mutate({ userId: 42, request: { is_blocked: true, role_id: null } });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(url).toBe('42');
    expect(body).toEqual({ is_blocked: true, role_id: null });
    expect(queryClient.getQueryState(['users', 0, 100])?.isInvalidated).toBe(true);
    // The single-user cache lives under a different root key and is not part of the declared set.
    expect(queryClient.getQueryState(['user', 42])?.isInvalidated).toBe(false);
  });

  it('reports a 404 for an unknown user', async () => {
    server.use(
      http.patch('/api/v1/users/:id', () =>
        HttpResponse.json({ detail: 'User not found' }, { status: 404 }),
      ),
    );

    const { result } = renderHook(() => useUpdateUser(), {
      wrapper: wrapperWith(createTestQueryClient()),
    });
    result.current.mutate({ userId: 7, request: { is_active: false } });

    await waitFor(() => expect(result.current.isError).toBe(true));
  });
});

describe('useImportEmployees', () => {
  const importResponse = {
    total: 2,
    created: 1,
    updated: 1,
    failed: 0,
    results: [
      { employee_id: '1001', status: 'created' },
      { employee_id: '1002', status: 'updated' },
    ],
  };

  it('posts employee_ids and the trimmed default_password, then invalidates the users caches', async () => {
    let body: unknown = null;
    server.use(
      http.post('/api/v1/users/import-employees', async ({ request }) => {
        body = await request.json();
        return HttpResponse.json(importResponse);
      }),
    );
    const queryClient = createRetainingQueryClient();
    await seed(queryClient, ['users', 'all']);

    const { result } = renderHook(() => useImportEmployees(), {
      wrapper: wrapperWith(queryClient),
    });
    result.current.mutate({ employeeIds: ['1001', '1002'], defaultPassword: '  Welcome@1  ' });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(body).toEqual({ employee_ids: ['1001', '1002'], default_password: 'Welcome@1' });
    expect(result.current.data).toEqual(importResponse);
    expect(queryClient.getQueryState(['users', 'all'])?.isInvalidated).toBe(true);
  });

  it('leaves default_password off the request when it is blank', async () => {
    let body: unknown = null;
    server.use(
      http.post('/api/v1/users/import-employees', async ({ request }) => {
        body = await request.json();
        return HttpResponse.json(importResponse);
      }),
    );

    const { result } = renderHook(() => useImportEmployees(), {
      wrapper: wrapperWith(createTestQueryClient()),
    });
    result.current.mutate({ employeeIds: ['1001'], defaultPassword: '   ' });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(body).toEqual({ employee_ids: ['1001'] });
  });
});

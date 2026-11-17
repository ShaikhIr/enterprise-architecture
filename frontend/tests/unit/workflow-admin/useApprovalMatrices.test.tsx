import { renderHook, waitFor } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';

import {
  useApprovalMatrices,
  useCreateApprovalMatrix,
  useDeleteApprovalMatrix,
  useMyApprovalTasks,
  useResolveApprovalMatrix,
  useUpdateApprovalMatrix,
} from '@features/workflow-admin/hooks/useApprovalMatrices';

import { server } from '../../mocks/server';

import { createHookQueryClient, hookWrapper, matrix, seedQuery } from './fixtures';

const LIST_KEY = ['approval-matrices', {}];
const OTHER_KEYS = [['workflow-definitions', {}], ['my-approval-tasks']];

const isInvalidated = (queryClient: ReturnType<typeof createHookQueryClient>, key: unknown[]) =>
  queryClient.getQueryState(key)?.isInvalidated;

const seedAll = async (queryClient: ReturnType<typeof createHookQueryClient>) => {
  await seedQuery(queryClient, LIST_KEY);
  for (const key of OTHER_KEYS) await seedQuery(queryClient, key);
};

const expectOnlyMatricesInvalidated = (queryClient: ReturnType<typeof createHookQueryClient>) => {
  expect(isInvalidated(queryClient, LIST_KEY)).toBe(true);
  for (const key of OTHER_KEYS) expect(isInvalidated(queryClient, key)).toBe(false);
};

describe('useApprovalMatrices', () => {
  it('sends default paging and every filter to the list endpoint', async () => {
    let captured: URL | undefined;
    server.use(
      http.get('/api/v1/workflow/approval-matrices', ({ request }) => {
        captured = new URL(request.url);
        return HttpResponse.json({ matrices: [matrix], total: 1, skip: 0, limit: 100 });
      }),
    );
    const queryClient = createHookQueryClient();

    const { result } = renderHook(
      () => useApprovalMatrices({ search: 'filing', is_active: false, entity_type: 'task' }),
      { wrapper: hookWrapper(queryClient) },
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(captured?.searchParams.get('skip')).toBe('0');
    expect(captured?.searchParams.get('limit')).toBe('100');
    expect(captured?.searchParams.get('search')).toBe('filing');
    expect(captured?.searchParams.get('is_active')).toBe('false');
    expect(captured?.searchParams.get('entity_type')).toBe('task');
    expect(result.current.data?.matrices[0]?.code).toBe('FILING_BY_AMOUNT');
  });
});

describe('approval matrix mutations', () => {
  it('create posts the whole matrix and invalidates only the matrices list', async () => {
    let body: unknown;
    server.use(
      http.post('/api/v1/workflow/approval-matrices', async ({ request }) => {
        body = await request.json();
        return HttpResponse.json(matrix);
      }),
    );
    const queryClient = createHookQueryClient();
    await seedAll(queryClient);

    const { result } = renderHook(() => useCreateApprovalMatrix(), {
      wrapper: hookWrapper(queryClient),
    });
    const request = {
      code: 'FILING_BY_AMOUNT',
      name: 'Filing approval by amount',
      entity_type: 'compliance_task',
      priority: 5,
      is_active: true,
      rules: [],
      assignments: [],
    };
    result.current.mutate(request);

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(body).toEqual(request);
    expectOnlyMatricesInvalidated(queryClient);
  });

  it('update patches the matrix by id and invalidates only the matrices list', async () => {
    let body: unknown;
    server.use(
      http.patch('/api/v1/workflow/approval-matrices/31', async ({ request }) => {
        body = await request.json();
        return HttpResponse.json(matrix);
      }),
    );
    const queryClient = createHookQueryClient();
    await seedAll(queryClient);

    const { result } = renderHook(() => useUpdateApprovalMatrix(), {
      wrapper: hookWrapper(queryClient),
    });
    result.current.mutate({ matrixId: 31, request: { priority: 1 } });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(body).toEqual({ priority: 1 });
    expectOnlyMatricesInvalidated(queryClient);
  });

  it('delete removes the matrix by id and invalidates only the matrices list', async () => {
    server.use(
      http.delete(
        '/api/v1/workflow/approval-matrices/31',
        () => new HttpResponse(null, { status: 204 }),
      ),
    );
    const queryClient = createHookQueryClient();
    await seedAll(queryClient);

    const { result } = renderHook(() => useDeleteApprovalMatrix(), {
      wrapper: hookWrapper(queryClient),
    });
    result.current.mutate(31);

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expectOnlyMatricesInvalidated(queryClient);
  });

  it('does not invalidate the list when a mutation fails', async () => {
    server.use(
      http.delete('/api/v1/workflow/approval-matrices/31', () =>
        HttpResponse.json({ message: 'nope' }, { status: 409 }),
      ),
    );
    const queryClient = createHookQueryClient();
    await seedAll(queryClient);

    const { result } = renderHook(() => useDeleteApprovalMatrix(), {
      wrapper: hookWrapper(queryClient),
    });
    result.current.mutate(31);

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(isInvalidated(queryClient, LIST_KEY)).toBe(false);
  });
});

describe('useResolveApprovalMatrix', () => {
  it('posts the sample record and returns the routing result without invalidating anything', async () => {
    let body: unknown;
    server.use(
      http.post('/api/v1/workflow/approval-matrices/resolve', async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({
          matched: true,
          matrix,
          levels: [1, 2],
          assignments: matrix.assignments,
        });
      }),
    );
    const queryClient = createHookQueryClient();
    await seedAll(queryClient);

    const { result } = renderHook(() => useResolveApprovalMatrix(), {
      wrapper: hookWrapper(queryClient),
    });
    result.current.mutate({ entity_type: 'compliance_task', entity_data: { amount: 5 } });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(body).toEqual({ entity_type: 'compliance_task', entity_data: { amount: 5 } });
    expect(result.current.data?.matched).toBe(true);
    expect(result.current.data?.levels).toEqual([1, 2]);
    expect(isInvalidated(queryClient, LIST_KEY)).toBe(false);
    for (const key of OTHER_KEYS) expect(isInvalidated(queryClient, key)).toBe(false);
  });
});

describe('useMyApprovalTasks', () => {
  it('fetches the caller’s tasks', async () => {
    server.use(
      http.get('/api/v1/workflow/my-tasks', () =>
        HttpResponse.json([
          {
            id: 1,
            instance_id: 55,
            matrix_id: 31,
            assignee_id: 801,
            level: 1,
            status: 'PENDING',
            action_taken: null,
            due_date: null,
            comments: null,
            created_date: '2024-01-01T00:00:00Z',
          },
        ]),
      ),
    );
    const queryClient = createHookQueryClient();

    const { result } = renderHook(() => useMyApprovalTasks(), {
      wrapper: hookWrapper(queryClient),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toHaveLength(1);
    expect(result.current.data?.[0]?.status).toBe('PENDING');
  });
});

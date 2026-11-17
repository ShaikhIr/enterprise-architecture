import { renderHook, waitFor } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';

import {
  useCreateWorkflowDefinition,
  useCreateWorkflowStatus,
  useCreateWorkflowTransition,
  useDeleteWorkflowDefinition,
  useDeleteWorkflowStatus,
  useDeleteWorkflowTransition,
  useExecuteWorkflowAction,
  useUpdateWorkflowDefinition,
  useUpdateWorkflowStatus,
  useWorkflowDefinition,
  useWorkflowDefinitions,
  useWorkflowInstance,
  useWorkflowInstanceActions,
  useWorkflowInstanceHistory,
} from '@features/workflow-admin/hooks/useWorkflows';

import { server } from '../../mocks/server';

import {
  createHookQueryClient,
  definition,
  detail,
  hookWrapper,
  seedQuery,
} from './fixtures';

const LIST_KEY = ['workflow-definitions', {}];
const DETAIL_7_KEY = ['workflow-definition', 7];
const DETAIL_8_KEY = ['workflow-definition', 8];

const isInvalidated = (queryClient: ReturnType<typeof createHookQueryClient>, key: unknown[]) =>
  queryClient.getQueryState(key)?.isInvalidated;

describe('useWorkflowDefinitions', () => {
  it('sends the default paging plus every filter to the list endpoint', async () => {
    let captured: URL | undefined;
    server.use(
      http.get('/api/v1/workflow/definitions', ({ request }) => {
        captured = new URL(request.url);
        return HttpResponse.json({ definitions: [definition], total: 1, skip: 0, limit: 100 });
      }),
    );
    const queryClient = createHookQueryClient();

    const { result } = renderHook(
      () => useWorkflowDefinitions({ search: 'filing', is_active: true, entity_type: 'task' }),
      { wrapper: hookWrapper(queryClient) },
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(captured?.searchParams.get('skip')).toBe('0');
    expect(captured?.searchParams.get('limit')).toBe('100');
    expect(captured?.searchParams.get('search')).toBe('filing');
    expect(captured?.searchParams.get('is_active')).toBe('true');
    expect(captured?.searchParams.get('entity_type')).toBe('task');
    expect(result.current.data?.definitions).toHaveLength(1);
  });

  it('lets explicit paging params override the defaults', async () => {
    let captured: URL | undefined;
    server.use(
      http.get('/api/v1/workflow/definitions', ({ request }) => {
        captured = new URL(request.url);
        return HttpResponse.json({ definitions: [], total: 0, skip: 20, limit: 5 });
      }),
    );
    const queryClient = createHookQueryClient();

    const { result } = renderHook(() => useWorkflowDefinitions({ skip: 20, limit: 5 }), {
      wrapper: hookWrapper(queryClient),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(captured?.searchParams.get('skip')).toBe('20');
    expect(captured?.searchParams.get('limit')).toBe('5');
  });

  it('caches each distinct params object under its own key', async () => {
    server.use(
      http.get('/api/v1/workflow/definitions', () =>
        HttpResponse.json({ definitions: [], total: 0, skip: 0, limit: 100 }),
      ),
    );
    const queryClient = createHookQueryClient();

    const { result } = renderHook(() => useWorkflowDefinitions({ search: 'a' }), {
      wrapper: hookWrapper(queryClient),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(queryClient.getQueryState(['workflow-definitions', { search: 'a' }])).toBeDefined();
  });
});

describe('useWorkflowDefinition', () => {
  it('does not fire a request while the id is undefined', () => {
    const queryClient = createHookQueryClient();

    const { result } = renderHook(() => useWorkflowDefinition(undefined), {
      wrapper: hookWrapper(queryClient),
    });

    // An unhandled request would error loudly (onUnhandledRequest: 'error'); `idle` proves none was sent.
    expect(result.current.fetchStatus).toBe('idle');
    expect(result.current.data).toBeUndefined();
  });

  it('fetches the definition detail by id', async () => {
    server.use(http.get('/api/v1/workflow/definitions/7', () => HttpResponse.json(detail())));
    const queryClient = createHookQueryClient();

    const { result } = renderHook(() => useWorkflowDefinition(7), {
      wrapper: hookWrapper(queryClient),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.definition.code).toBe('RETURN_FILING');
    expect(result.current.data?.statuses).toHaveLength(3);
  });
});

describe('definition mutations', () => {
  it('create posts the request and invalidates only the definitions list', async () => {
    let body: unknown;
    server.use(
      http.post('/api/v1/workflow/definitions', async ({ request }) => {
        body = await request.json();
        return HttpResponse.json(definition);
      }),
    );
    const queryClient = createHookQueryClient();
    await seedQuery(queryClient, LIST_KEY);
    await seedQuery(queryClient, DETAIL_7_KEY);
    await seedQuery(queryClient, ['approval-matrices', {}]);

    const { result } = renderHook(() => useCreateWorkflowDefinition(), {
      wrapper: hookWrapper(queryClient),
    });
    const request = {
      code: 'RETURN_FILING',
      name: 'Return Filing Approval',
      entity_type: 'compliance_task',
      description: '',
      is_active: true,
    };
    result.current.mutate(request);

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(body).toEqual(request);
    expect(isInvalidated(queryClient, LIST_KEY)).toBe(true);
    expect(isInvalidated(queryClient, DETAIL_7_KEY)).toBe(false);
    expect(isInvalidated(queryClient, ['approval-matrices', {}])).toBe(false);
  });

  it('update patches the definition and invalidates the list and that one detail', async () => {
    let body: unknown;
    server.use(
      http.patch('/api/v1/workflow/definitions/7', async ({ request }) => {
        body = await request.json();
        return HttpResponse.json(definition);
      }),
    );
    const queryClient = createHookQueryClient();
    await seedQuery(queryClient, LIST_KEY);
    await seedQuery(queryClient, DETAIL_7_KEY);
    await seedQuery(queryClient, DETAIL_8_KEY);

    const { result } = renderHook(() => useUpdateWorkflowDefinition(), {
      wrapper: hookWrapper(queryClient),
    });
    result.current.mutate({ definitionId: 7, request: { name: 'Renamed' } });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(body).toEqual({ name: 'Renamed' });
    expect(isInvalidated(queryClient, LIST_KEY)).toBe(true);
    expect(isInvalidated(queryClient, DETAIL_7_KEY)).toBe(true);
    expect(isInvalidated(queryClient, DETAIL_8_KEY)).toBe(false);
  });

  it('delete removes the definition and invalidates only the list', async () => {
    server.use(
      http.delete('/api/v1/workflow/definitions/7', () => new HttpResponse(null, { status: 204 })),
    );
    const queryClient = createHookQueryClient();
    await seedQuery(queryClient, LIST_KEY);
    await seedQuery(queryClient, DETAIL_7_KEY);

    const { result } = renderHook(() => useDeleteWorkflowDefinition(), {
      wrapper: hookWrapper(queryClient),
    });
    result.current.mutate(7);

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(isInvalidated(queryClient, LIST_KEY)).toBe(true);
    expect(isInvalidated(queryClient, DETAIL_7_KEY)).toBe(false);
  });

  it('does not invalidate anything when the mutation fails', async () => {
    server.use(
      http.delete('/api/v1/workflow/definitions/7', () =>
        HttpResponse.json({ message: 'Workflow has instances' }, { status: 409 }),
      ),
    );
    const queryClient = createHookQueryClient();
    await seedQuery(queryClient, LIST_KEY);

    const { result } = renderHook(() => useDeleteWorkflowDefinition(), {
      wrapper: hookWrapper(queryClient),
    });
    result.current.mutate(7);

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(isInvalidated(queryClient, LIST_KEY)).toBe(false);
  });
});

/**
 * State and transition mutations all read through the single definition-detail
 * response, so each one must invalidate that definition's detail query and
 * nothing else (not the list, and not another definition's detail).
 */
describe('state and transition mutations', () => {
  const seedAll = async (queryClient: ReturnType<typeof createHookQueryClient>) => {
    await seedQuery(queryClient, LIST_KEY);
    await seedQuery(queryClient, DETAIL_7_KEY);
    await seedQuery(queryClient, DETAIL_8_KEY);
  };

  const expectOnlyDetail7Invalidated = (queryClient: ReturnType<typeof createHookQueryClient>) => {
    expect(isInvalidated(queryClient, DETAIL_7_KEY)).toBe(true);
    expect(isInvalidated(queryClient, DETAIL_8_KEY)).toBe(false);
    expect(isInvalidated(queryClient, LIST_KEY)).toBe(false);
  };

  it('createStatus posts to the definition and invalidates its detail only', async () => {
    let body: unknown;
    server.use(
      http.post('/api/v1/workflow/definitions/7/statuses', async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({ id: 1 });
      }),
    );
    const queryClient = createHookQueryClient();
    await seedAll(queryClient);

    const { result } = renderHook(() => useCreateWorkflowStatus(7), {
      wrapper: hookWrapper(queryClient),
    });
    const request = {
      code: 'DRAFT',
      name: 'Draft',
      is_initial: true,
      is_terminal: false,
      sequence: 0,
    };
    result.current.mutate(request);

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(body).toEqual(request);
    expectOnlyDetail7Invalidated(queryClient);
  });

  it('updateStatus patches the status by its own id', async () => {
    let body: unknown;
    server.use(
      http.patch('/api/v1/workflow/statuses/101', async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({ id: 101 });
      }),
    );
    const queryClient = createHookQueryClient();
    await seedAll(queryClient);

    const { result } = renderHook(() => useUpdateWorkflowStatus(7), {
      wrapper: hookWrapper(queryClient),
    });
    result.current.mutate({ statusId: 101, request: { name: 'Renamed' } });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(body).toEqual({ name: 'Renamed' });
    expectOnlyDetail7Invalidated(queryClient);
  });

  it('deleteStatus deletes the status by id', async () => {
    server.use(
      http.delete('/api/v1/workflow/statuses/101', () => new HttpResponse(null, { status: 204 })),
    );
    const queryClient = createHookQueryClient();
    await seedAll(queryClient);

    const { result } = renderHook(() => useDeleteWorkflowStatus(7), {
      wrapper: hookWrapper(queryClient),
    });
    result.current.mutate(101);

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expectOnlyDetail7Invalidated(queryClient);
  });

  it('createTransition posts to the definition and invalidates its detail only', async () => {
    let body: unknown;
    server.use(
      http.post('/api/v1/workflow/definitions/7/transitions', async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({ id: 1 });
      }),
    );
    const queryClient = createHookQueryClient();
    await seedAll(queryClient);

    const { result } = renderHook(() => useCreateWorkflowTransition(7), {
      wrapper: hookWrapper(queryClient),
    });
    const request = {
      from_status_id: 101,
      to_status_id: 102,
      action_code: 'SUBMIT',
      action_type: 'SUBMIT' as const,
      guard_expression: null,
      requires_comment: false,
      auto_execute: false,
      priority: 0,
    };
    result.current.mutate(request);

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(body).toEqual(request);
    expectOnlyDetail7Invalidated(queryClient);
  });

  it('deleteTransition deletes the transition by id', async () => {
    server.use(
      http.delete(
        '/api/v1/workflow/transitions/201',
        () => new HttpResponse(null, { status: 204 }),
      ),
    );
    const queryClient = createHookQueryClient();
    await seedAll(queryClient);

    const { result } = renderHook(() => useDeleteWorkflowTransition(7), {
      wrapper: hookWrapper(queryClient),
    });
    result.current.mutate(201);

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expectOnlyDetail7Invalidated(queryClient);
  });
});

describe('runtime queries', () => {
  it.each([
    ['useWorkflowInstance', useWorkflowInstance, '/api/v1/workflow/instances/55', { id: 55 }],
    [
      'useWorkflowInstanceActions',
      useWorkflowInstanceActions,
      '/api/v1/workflow/instances/55/actions',
      [{ action_code: 'APPROVE' }],
    ],
    [
      'useWorkflowInstanceHistory',
      useWorkflowInstanceHistory,
      '/api/v1/workflow/instances/55/history',
      [{ id: 1 }],
    ],
  ] as const)('%s stays idle without an id and fetches with one', async (_name, hook, path, body) => {
    server.use(http.get(path, () => HttpResponse.json(body)));
    const queryClient = createHookQueryClient();

    const idle = renderHook(() => hook(undefined), { wrapper: hookWrapper(queryClient) });
    expect(idle.result.current.fetchStatus).toBe('idle');

    const active = renderHook(() => hook(55), { wrapper: hookWrapper(queryClient) });
    await waitFor(() => expect(active.result.current.isSuccess).toBe(true));
    expect(active.result.current.data).toEqual(body);
  });
});

describe('useExecuteWorkflowAction', () => {
  it('posts the action and invalidates the instance, its actions and its history', async () => {
    let body: unknown;
    server.use(
      http.post('/api/v1/workflow/instances/55/actions', async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({ id: 55 });
      }),
    );
    const queryClient = createHookQueryClient();
    await seedQuery(queryClient, ['workflow-instance', 55]);
    await seedQuery(queryClient, ['workflow-instance-actions', 55]);
    await seedQuery(queryClient, ['workflow-instance-history', 55]);
    await seedQuery(queryClient, ['workflow-instance', 56]);
    await seedQuery(queryClient, DETAIL_7_KEY);

    const { result } = renderHook(() => useExecuteWorkflowAction(), {
      wrapper: hookWrapper(queryClient),
    });
    result.current.mutate({
      instanceId: 55,
      request: { action_code: 'APPROVE', comments: 'ok' },
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(body).toEqual({ action_code: 'APPROVE', comments: 'ok' });
    expect(isInvalidated(queryClient, ['workflow-instance', 55])).toBe(true);
    expect(isInvalidated(queryClient, ['workflow-instance-actions', 55])).toBe(true);
    expect(isInvalidated(queryClient, ['workflow-instance-history', 55])).toBe(true);
    // A different instance and the definition detail are untouched.
    expect(isInvalidated(queryClient, ['workflow-instance', 56])).toBe(false);
    expect(isInvalidated(queryClient, DETAIL_7_KEY)).toBe(false);
  });
});

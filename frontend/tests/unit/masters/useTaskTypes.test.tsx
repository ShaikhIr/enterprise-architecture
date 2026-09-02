import type { PropsWithChildren } from 'react';

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { describe, expect, it, vi } from 'vitest';

import { useCreateTaskType, useTaskTypes } from '@features/masters/hooks/useTaskTypes';

import { server } from '../../mocks/server';

const wrapperWith = (queryClient: QueryClient) => {
  const Wrapper = ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  return Wrapper;
};

/**
 * TaskType is independent of the country/state hierarchy: no filter params
 * beyond the generic ones, and no dependent caches to invalidate.
 */
describe('useTaskTypes (independent master, no dependent keys)', () => {
  it('fetches the task type list through the real endpoint', async () => {
    server.use(
      http.get('/api/v1/masters/task-types', () =>
        HttpResponse.json({
          task_types: [
            {
              id: 1,
              code: 'RETURN_FILING',
              name: 'Return Filing',
              description: '',
              is_active: true,
              created_by: 'system',
              created_date: '2024-01-01T00:00:00Z',
              modified_by: 'system',
              modified_date: '2024-01-01T00:00:00Z',
            },
          ],
          total: 1,
          skip: 0,
          limit: 100,
        }),
      ),
    );
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    const { result } = renderHook(() => useTaskTypes(), { wrapper: wrapperWith(queryClient) });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.items[0]?.code).toBe('RETURN_FILING');
  });

  it('invalidates only its own cache after a create', async () => {
    server.use(
      http.post('/api/v1/masters/task-types', () =>
        HttpResponse.json({
          id: 1,
          code: 'AUDIT',
          name: 'Audit',
          description: '',
          is_active: true,
          created_by: 'system',
          created_date: '2024-01-01T00:00:00Z',
          modified_by: 'system',
          modified_date: '2024-01-01T00:00:00Z',
        }),
      ),
    );
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries');

    const { result } = renderHook(() => useCreateTaskType(), { wrapper: wrapperWith(queryClient) });
    result.current.mutate({ code: 'AUDIT', name: 'Audit', description: '', is_active: true });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(invalidateSpy).toHaveBeenCalledTimes(1);
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['masters', 'task-types'] });
  });
});

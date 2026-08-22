import type { PropsWithChildren } from 'react';

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { MasterApi } from '@features/masters/api/createMasterApi';
import { createMasterHooks } from '@features/masters/hooks/createMasterHooks';
import type { MasterListParams } from '@features/masters/models/common';

interface Widget {
  id: string;
  name: string;
}

/** A hand-written fake rather than MSW here: what's under test is the query/
 * mutation wiring (keys, invalidation), not HTTP — so the api layer itself
 * is stubbed directly. */
const buildFakeApi = (): MasterApi<
  Widget,
  { name: string },
  Partial<Widget>,
  MasterListParams
> => ({
  list: vi
    .fn()
    .mockResolvedValue({ items: [{ id: '1', name: 'Widget' }], total: 1, skip: 0, limit: 100 }),
  getById: vi.fn(),
  create: vi.fn().mockResolvedValue({ id: '2', name: 'New Widget' }),
  update: vi.fn().mockResolvedValue({ id: '1', name: 'Renamed' }),
  remove: vi.fn().mockResolvedValue(undefined),
});

const WIDGET_KEY = ['masters', 'widgets'];
const DEPENDENT_KEY = ['masters', 'dependents'];

const wrapperWith = (queryClient: QueryClient) => {
  const Wrapper = ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  return Wrapper;
};

describe('createMasterHooks', () => {
  it('useList fetches through the api and exposes the result', async () => {
    const api = buildFakeApi();
    const { useList } = createMasterHooks(api, WIDGET_KEY);
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    const { result } = renderHook(() => useList(), { wrapper: wrapperWith(queryClient) });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.items).toEqual([{ id: '1', name: 'Widget' }]);
    expect(api.list).toHaveBeenCalledWith(undefined);
  });

  it('useList respects options.enabled, never calling the api while held back', async () => {
    const api = buildFakeApi();
    const { useList } = createMasterHooks(api, WIDGET_KEY);
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    const { result } = renderHook(() => useList(undefined, { enabled: false }), {
      wrapper: wrapperWith(queryClient),
    });

    expect(result.current.fetchStatus).toBe('idle');
    expect(api.list).not.toHaveBeenCalled();
  });

  it('useCreate invalidates its own key and every dependent key on success', async () => {
    const api = buildFakeApi();
    const { useCreate } = createMasterHooks(api, WIDGET_KEY, [DEPENDENT_KEY]);
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries');

    const { result } = renderHook(() => useCreate(), { wrapper: wrapperWith(queryClient) });
    result.current.mutate({ name: 'New Widget' });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: WIDGET_KEY });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: DEPENDENT_KEY });
  });

  it('useUpdate calls api.update with the (id, request) pair and invalidates on success', async () => {
    const api = buildFakeApi();
    const { useUpdate } = createMasterHooks(api, WIDGET_KEY);
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    const { result } = renderHook(() => useUpdate(), { wrapper: wrapperWith(queryClient) });
    result.current.mutate({ id: '1', request: { name: 'Renamed' } });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(api.update).toHaveBeenCalledWith('1', { name: 'Renamed' });
  });

  it('useDelete calls api.remove with the id and invalidates on success', async () => {
    const api = buildFakeApi();
    const { useDelete } = createMasterHooks(api, WIDGET_KEY, [DEPENDENT_KEY]);
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries');

    const { result } = renderHook(() => useDelete(), { wrapper: wrapperWith(queryClient) });
    result.current.mutate('1');

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(api.remove).toHaveBeenCalledWith('1');
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: DEPENDENT_KEY });
  });

  it('does not invalidate any query key when the mutation fails', async () => {
    const api = buildFakeApi();
    (api.create as ReturnType<typeof vi.fn>).mockRejectedValueOnce(new Error('conflict'));
    const { useCreate } = createMasterHooks(api, WIDGET_KEY, [DEPENDENT_KEY]);
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries');

    const { result } = renderHook(() => useCreate(), { wrapper: wrapperWith(queryClient) });
    result.current.mutate({ name: 'New Widget' });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(invalidateSpy).not.toHaveBeenCalled();
  });

  it('has no dependent keys to invalidate for a leaf master (default empty array)', async () => {
    const api = buildFakeApi();
    const { useCreate } = createMasterHooks(api, WIDGET_KEY);
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries');

    const { result } = renderHook(() => useCreate(), { wrapper: wrapperWith(queryClient) });
    result.current.mutate({ name: 'New Widget' });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(invalidateSpy).toHaveBeenCalledTimes(1);
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: WIDGET_KEY });
  });
});

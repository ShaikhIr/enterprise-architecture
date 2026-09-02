import type { PropsWithChildren } from 'react';

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';

import { useCreateState, useStates } from '@features/masters/hooks/useStates';

import { server } from '../../mocks/server';

const wrapperWith = (queryClient: QueryClient) => {
  const Wrapper = ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  return Wrapper;
};

/**
 * Only what is specific to State's position in the hierarchy: it sits
 * between Country and three children (CategoryOfLaw, Legislation, Rule), so
 * a write here must invalidate all three — unlike Country (which also
 * invalidates States) or Rule (a leaf, with none). The list/create/update/
 * delete request mechanics themselves are already covered generically by
 * `createMasterHooks.test.tsx`.
 */
describe('useStates dependent-key wiring', () => {
  it('sends the country_id filter through to the list endpoint', async () => {
    let captured: URL | undefined;
    server.use(
      http.get('/api/v1/masters/states', ({ request }) => {
        captured = new URL(request.url);
        return HttpResponse.json({ states: [], total: 0, skip: 0, limit: 100 });
      }),
    );
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    const { result } = renderHook(() => useStates({ country_id: 501 }), {
      wrapper: wrapperWith(queryClient),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(captured?.searchParams.get('country_id')).toBe('501');
  });

  it('invalidates categories-of-law, legislations and rules after a create', async () => {
    server.use(
      http.post('/api/v1/masters/states', () =>
        HttpResponse.json({
          id: 1,
          code: 'IN-MH',
          name: 'Maharashtra',
          country_id: 501,
          is_union_territory: false,
          is_active: true,
          created_by: 'system',
          created_date: '2024-01-01T00:00:00Z',
          modified_by: 'system',
          modified_date: '2024-01-01T00:00:00Z',
        }),
      ),
    );
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    for (const key of [
      ['masters', 'categories-of-law'],
      ['masters', 'legislations'],
      ['masters', 'rules'],
    ]) {
      await queryClient.prefetchQuery({
        queryKey: [...key, {}],
        queryFn: () => Promise.resolve({ items: [], total: 0, skip: 0, limit: 100 }),
      });
    }

    const { result } = renderHook(() => useCreateState(), { wrapper: wrapperWith(queryClient) });
    result.current.mutate({
      code: 'IN-MH',
      name: 'Maharashtra',
      country_id: 501,
      is_union_territory: false,
      is_active: true,
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(queryClient.getQueryState(['masters', 'categories-of-law', {}])?.isInvalidated).toBe(
      true,
    );
    expect(queryClient.getQueryState(['masters', 'legislations', {}])?.isInvalidated).toBe(true);
    expect(queryClient.getQueryState(['masters', 'rules', {}])?.isInvalidated).toBe(true);
  });
});

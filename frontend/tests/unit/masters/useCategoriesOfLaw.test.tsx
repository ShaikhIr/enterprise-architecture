import type { PropsWithChildren } from 'react';

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';

import {
  useCategoriesOfLaw,
  useCreateCategoryOfLaw,
} from '@features/masters/hooks/useCategoriesOfLaw';

import { server } from '../../mocks/server';

const wrapperWith = (queryClient: QueryClient) => {
  const Wrapper = ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  return Wrapper;
};

/**
 * CategoryOfLaw sits between State and Legislation: one dependent key
 * (legislations), and a state_id filter param on its list endpoint.
 */
describe('useCategoriesOfLaw dependent-key wiring', () => {
  it('sends the state_id filter through to the list endpoint', async () => {
    let captured: URL | undefined;
    server.use(
      http.get('/api/v1/masters/categories-of-law', ({ request }) => {
        captured = new URL(request.url);
        return HttpResponse.json({ categories_of_law: [], total: 0, skip: 0, limit: 100 });
      }),
    );
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    const { result } = renderHook(() => useCategoriesOfLaw({ state_id: 601 }), {
      wrapper: wrapperWith(queryClient),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(captured?.searchParams.get('state_id')).toBe('601');
  });

  it('invalidates only the legislations cache after a create (single dependent)', async () => {
    server.use(
      http.post('/api/v1/masters/categories-of-law', () =>
        HttpResponse.json({
          id: 1,
          code: 'LABOUR',
          name: 'Labour Law',
          description: '',
          state_id: null,
          is_active: true,
          created_by: 'system',
          created_date: '2024-01-01T00:00:00Z',
          modified_by: 'system',
          modified_date: '2024-01-01T00:00:00Z',
        }),
      ),
    );
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    await queryClient.prefetchQuery({
      queryKey: ['masters', 'legislations', {}],
      queryFn: () => Promise.resolve({ items: [], total: 0, skip: 0, limit: 100 }),
    });

    const { result } = renderHook(() => useCreateCategoryOfLaw(), {
      wrapper: wrapperWith(queryClient),
    });
    result.current.mutate({
      code: 'LABOUR',
      name: 'Labour Law',
      description: '',
      state_id: null,
      is_active: true,
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(queryClient.getQueryState(['masters', 'legislations', {}])?.isInvalidated).toBe(true);
  });
});

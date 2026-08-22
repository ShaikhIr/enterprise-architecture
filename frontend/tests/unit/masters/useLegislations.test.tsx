import type { PropsWithChildren } from 'react';

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';

import { useCreateLegislation, useLegislations } from '@features/masters/hooks/useLegislations';

import { server } from '../../mocks/server';

const wrapperWith = (queryClient: QueryClient) => {
  const Wrapper = ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  return Wrapper;
};

describe('useLegislations dependent-key wiring', () => {
  it('sends the country/state/category filters through to the list endpoint', async () => {
    let captured: URL | undefined;
    server.use(
      http.get('/api/v1/masters/legislations', ({ request }) => {
        captured = new URL(request.url);
        return HttpResponse.json({ legislations: [], total: 0, skip: 0, limit: 100 });
      }),
    );
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    const { result } = renderHook(
      () =>
        useLegislations({
          country_id: 'country-1',
          state_id: 'state-1',
          category_of_law_id: 'cat-1',
        }),
      { wrapper: wrapperWith(queryClient) },
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(captured?.searchParams.get('country_id')).toBe('country-1');
    expect(captured?.searchParams.get('state_id')).toBe('state-1');
    expect(captured?.searchParams.get('category_of_law_id')).toBe('cat-1');
  });

  it('invalidates only the rules cache after a create (single dependent)', async () => {
    server.use(
      http.post('/api/v1/masters/legislations', () =>
        HttpResponse.json({
          id: '1',
          code: 'IN-X',
          name: 'Some Act',
          description: '',
          category_of_law_id: 'cat-1',
          country_id: 'country-1',
          state_id: null,
          legislation_number: null,
          effective_date: null,
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
      queryKey: ['masters', 'rules', {}],
      queryFn: () => Promise.resolve({ items: [], total: 0, skip: 0, limit: 100 }),
    });

    const { result } = renderHook(() => useCreateLegislation(), {
      wrapper: wrapperWith(queryClient),
    });
    result.current.mutate({
      code: 'IN-X',
      name: 'Some Act',
      description: '',
      category_of_law_id: 'cat-1',
      country_id: 'country-1',
      state_id: null,
      legislation_number: null,
      effective_date: null,
      is_active: true,
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(queryClient.getQueryState(['masters', 'rules', {}])?.isInvalidated).toBe(true);
  });
});

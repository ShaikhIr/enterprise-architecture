import type { PropsWithChildren } from 'react';

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { describe, expect, it, vi } from 'vitest';

import { useCreateRule, useRules } from '@features/masters/hooks/useRules';

import { server } from '../../mocks/server';

const wrapperWith = (queryClient: QueryClient) => {
  const Wrapper = ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  return Wrapper;
};

/** Rule is the leaf of the hierarchy: nothing depends on its cache. */
describe('useRules (leaf master, no dependent keys)', () => {
  it('sends the legislation_id filter through to the list endpoint', async () => {
    let captured: URL | undefined;
    server.use(
      http.get('/api/v1/masters/rules', ({ request }) => {
        captured = new URL(request.url);
        return HttpResponse.json({ rules: [], total: 0, skip: 0, limit: 100 });
      }),
    );
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    const { result } = renderHook(() => useRules({ legislation_id: 'leg-1' }), {
      wrapper: wrapperWith(queryClient),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(captured?.searchParams.get('legislation_id')).toBe('leg-1');
  });

  it('invalidates only its own cache after a create (no dependent keys)', async () => {
    server.use(
      http.post('/api/v1/masters/rules', () =>
        HttpResponse.json({
          id: '1',
          code: 'R1',
          name: 'Rule One',
          description: '',
          legislation_id: 'leg-1',
          country_id: 'country-1',
          state_id: null,
          rule_number: null,
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
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries');

    const { result } = renderHook(() => useCreateRule(), { wrapper: wrapperWith(queryClient) });
    result.current.mutate({
      code: 'R1',
      name: 'Rule One',
      description: '',
      legislation_id: 'leg-1',
      country_id: 'country-1',
      state_id: null,
      rule_number: null,
      effective_date: null,
      is_active: true,
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(invalidateSpy).toHaveBeenCalledTimes(1);
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['masters', 'rules'] });
  });
});

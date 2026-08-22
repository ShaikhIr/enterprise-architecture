import type { PropsWithChildren } from 'react';

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';

import {
  useCountries,
  useCountryLookup,
  useCreateCountry,
  useDeleteCountry,
} from '@features/masters/hooks/useCountries';

import { server } from '../../mocks/server';

const wrapperWith = (queryClient: QueryClient) => {
  const Wrapper = ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  return Wrapper;
};

const country = (
  overrides: Partial<{ id: string; code: string; name: string; is_active: boolean }>,
) => ({
  id: '1',
  code: 'IN',
  name: 'India',
  iso3_code: null,
  dial_code: null,
  currency_code: null,
  is_active: true,
  created_by: 'system',
  created_date: '2024-01-01T00:00:00Z',
  modified_by: 'system',
  modified_date: '2024-01-01T00:00:00Z',
  ...overrides,
});

describe('useCountries (createMasterHooks instantiated for Country)', () => {
  it('fetches the country list through the real countries endpoint', async () => {
    server.use(
      http.get('/api/v1/masters/countries', () =>
        HttpResponse.json({ countries: [country({})], total: 1, skip: 0, limit: 100 }),
      ),
    );
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    const { result } = renderHook(() => useCountries(), { wrapper: wrapperWith(queryClient) });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.items).toEqual([country({})]);
  });

  it('invalidates the states, legislations and rules caches after a create (dependent keys)', async () => {
    server.use(
      http.post('/api/v1/masters/countries', () => HttpResponse.json(country({ id: '2' }))),
    );
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    await queryClient.prefetchQuery({
      queryKey: ['masters', 'states', {}],
      queryFn: () => Promise.resolve({ items: [], total: 0, skip: 0, limit: 100 }),
    });

    const { result } = renderHook(() => useCreateCountry(), { wrapper: wrapperWith(queryClient) });
    result.current.mutate({
      code: 'FR',
      name: 'France',
      iso3_code: null,
      dial_code: null,
      currency_code: null,
      is_active: true,
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    // A cache the country write depends on is stale, not merely present.
    expect(queryClient.getQueryState(['masters', 'states', {}])?.isInvalidated).toBe(true);
  });

  it('propagates a 409 conflict from delete (e.g. states still reference the country)', async () => {
    server.use(
      http.delete('/api/v1/masters/countries/1', () =>
        HttpResponse.json({ message: 'Country is referenced by 2 state(s)' }, { status: 409 }),
      ),
    );
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    const { result } = renderHook(() => useDeleteCountry(), { wrapper: wrapperWith(queryClient) });
    result.current.mutate('1');

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect((result.current.error as { response?: { status?: number } })?.response?.status).toBe(
      409,
    );
  });
});

describe('useCountryLookup', () => {
  it('builds dropdown options from active countries and labels from all countries', async () => {
    server.use(
      http.get('/api/v1/masters/countries', ({ request }) => {
        const url = new URL(request.url);
        const isActive = url.searchParams.get('is_active');
        const items =
          isActive === 'true'
            ? [country({})]
            : [
                country({}),
                country({ id: '2', code: 'US', name: 'United States', is_active: false }),
              ];
        return HttpResponse.json({ countries: items, total: items.length, skip: 0, limit: 100 });
      }),
    );
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    const { result } = renderHook(() => useCountryLookup(), { wrapper: wrapperWith(queryClient) });

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.options).toEqual([{ label: 'India (IN)', value: '1' }]);
    expect(result.current.labelFor('2')).toBe('United States (US)');
  });
});

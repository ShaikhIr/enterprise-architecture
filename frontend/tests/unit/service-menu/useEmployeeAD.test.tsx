import type { PropsWithChildren } from 'react';

import { QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';

import {
  useEmployeeADHealth,
  useGetEmployees,
  useGetHierarchy,
  useGetSelectedEmployees,
  useValidateCredentials,
} from '@features/service-menu/hooks/useEmployeeAD';

import { server } from '../../mocks/server';
import { createTestQueryClient } from '../../test-utils';

/** A fresh client per hook under test, held stable across re-renders of the wrapper. */
const freshWrapper = () => {
  const queryClient = createTestQueryClient();
  const Wrapper = ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  return Wrapper;
};

const BASE = '/api/v1/services/employee-ad';

const statusOf = (error: unknown) => (error as { response?: { status?: number } }).response?.status;

describe('useEmployeeADHealth', () => {
  it('fetches the service health report', async () => {
    const report = {
      service: 'Employee AD (Darwin)',
      configured: true,
      base_url: 'https://ad.example.test',
      status: 'reachable',
      status_code: 200,
      url: 'https://ad.example.test/health',
    };
    server.use(http.get(`${BASE}/health`, () => HttpResponse.json(report)));

    const { result } = renderHook(() => useEmployeeADHealth(), { wrapper: freshWrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual(report);
  });

  it('retries a failed health check once before reporting the error', async () => {
    let calls = 0;
    server.use(
      http.get(`${BASE}/health`, () => {
        calls += 1;
        return HttpResponse.json({ detail: 'down' }, { status: 502 });
      }),
    );

    const { result } = renderHook(() => useEmployeeADHealth(), { wrapper: freshWrapper() });

    await waitFor(() => expect(result.current.isError).toBe(true), { timeout: 5000 });
    expect(calls).toBe(2);
    expect(statusOf(result.current.error)).toBe(502);
  });
});

describe('useValidateCredentials', () => {
  it('posts employee_id and password and returns the validation result', async () => {
    let body: unknown = null;
    server.use(
      http.post(`${BASE}/validate-credentials`, async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({
          is_success: true,
          is_valid_user: true,
          raw_response: { IsSuccess: true },
        });
      }),
    );

    const { result } = renderHook(() => useValidateCredentials(), { wrapper: freshWrapper() });
    result.current.mutate({ employee_id: '93300040', password: 'secret' });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(body).toEqual({ employee_id: '93300040', password: 'secret' });
    expect(result.current.data?.is_valid_user).toBe(true);
  });

  it('exposes a server error on the mutation', async () => {
    server.use(
      http.post(`${BASE}/validate-credentials`, () =>
        HttpResponse.json({ detail: 'AD unreachable' }, { status: 502 }),
      ),
    );

    const { result } = renderHook(() => useValidateCredentials(), { wrapper: freshWrapper() });
    result.current.mutate({ employee_id: '1', password: 'x' });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(statusOf(result.current.error)).toBe(502);
  });
});

describe('useGetSelectedEmployees', () => {
  it('posts the ids as employee_ids', async () => {
    let body: unknown = null;
    server.use(
      http.post(`${BASE}/selected-employees`, async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({ employees: [{ id: '1001' }] });
      }),
    );

    const { result } = renderHook(() => useGetSelectedEmployees(), { wrapper: freshWrapper() });
    result.current.mutate(['1001', '1002']);

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(body).toEqual({ employee_ids: ['1001', '1002'] });
    expect(result.current.data).toEqual({ employees: [{ id: '1001' }] });
  });
});

describe('useGetEmployees', () => {
  it('GETs every employee record', async () => {
    server.use(
      http.get(`${BASE}/employees`, () =>
        HttpResponse.json({ employees: [{ id: '1' }, { id: '2' }] }),
      ),
    );

    const { result } = renderHook(() => useGetEmployees(), { wrapper: freshWrapper() });
    result.current.mutate();

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual({ employees: [{ id: '1' }, { id: '2' }] });
  });
});

describe('useGetHierarchy', () => {
  it('GETs the hierarchy data', async () => {
    server.use(http.get(`${BASE}/hierarchy`, () => HttpResponse.json({ root: 'CEO' })));

    const { result } = renderHook(() => useGetHierarchy(), { wrapper: freshWrapper() });
    result.current.mutate();

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual({ root: 'CEO' });
  });

  it('exposes a server error on the mutation', async () => {
    server.use(
      http.get(`${BASE}/hierarchy`, () => HttpResponse.json({ detail: 'nope' }, { status: 500 })),
    );

    const { result } = renderHook(() => useGetHierarchy(), { wrapper: freshWrapper() });
    result.current.mutate();

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(statusOf(result.current.error)).toBe(500);
  });
});

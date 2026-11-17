import { renderHook, waitFor } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';

import { useRoles } from '@features/user-management/hooks/useRoles';

import { server } from '../../mocks/server';

const role = (id: number, code: string, name: string, is_active = true) => ({
  id,
  code,
  name,
  is_active,
});

describe('useRoles', () => {
  it('starts in the loading state with no options', () => {
    server.use(http.get('/api/v1/rbac/roles', () => HttpResponse.json({ roles: [], total: 0 })));

    const { result } = renderHook(() => useRoles());

    expect(result.current.loading).toBe(true);
    expect(result.current.roleOptions).toEqual([]);
  });

  it('maps active roles to "Name (CODE)" options keyed by numeric role id', async () => {
    server.use(
      http.get('/api/v1/rbac/roles', () =>
        HttpResponse.json({
          roles: [role(11, 'ADMIN', 'Administrator'), role(12, 'USER', 'User')],
          total: 2,
        }),
      ),
    );

    const { result } = renderHook(() => useRoles());

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.roleOptions).toEqual([
      { label: 'Administrator (ADMIN)', value: 11 },
      { label: 'User (USER)', value: 12 },
    ]);
  });

  it('leaves inactive roles out of the options', async () => {
    server.use(
      http.get('/api/v1/rbac/roles', () =>
        HttpResponse.json({
          roles: [role(11, 'ADMIN', 'Administrator'), role(13, 'OLD', 'Retired', false)],
          total: 2,
        }),
      ),
    );

    const { result } = renderHook(() => useRoles());

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.roleOptions.map((o) => o.value)).toEqual([11]);
  });

  it('falls back to no options, and stops loading, when the request fails', async () => {
    server.use(
      http.get('/api/v1/rbac/roles', () =>
        HttpResponse.json({ detail: 'Forbidden' }, { status: 403 }),
      ),
    );

    const { result } = renderHook(() => useRoles());

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.roleOptions).toEqual([]);
  });

  it('requests the roles endpoint exactly once per mount', async () => {
    let calls = 0;
    server.use(
      http.get('/api/v1/rbac/roles', () => {
        calls += 1;
        return HttpResponse.json({ roles: [], total: 0 });
      }),
    );

    const { result, rerender } = renderHook(() => useRoles());
    await waitFor(() => expect(result.current.loading).toBe(false));
    rerender();

    expect(calls).toBe(1);
  });
});

/**
 * Tests for the Audit Logs page's authentication events.
 *
 * A login lockout is a security event someone will go looking for, so it has to be
 * filterable by name and read as the warning it is rather than as a neutral entry. The
 * network is mocked (MSW) so the real rbacAdminApi → apiClient path runs.
 */

import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';

import { AuditLogsPage } from '@features/rbac-admin/pages/AuditLogsPage';

import { server } from '../../mocks/server';
import { renderWithProviders, screen, selectDropdownOption, waitFor } from '../../test-utils';

const entry = (id: string, action: string, actor = 'alice') => ({
  id: Number(id),
  actor_id: null,
  actor_username: actor,
  action,
  resource_type: 'Authentication',
  resource_id: actor,
  tenant_id: null,
  old_value: null,
  new_value: null,
  ip_address: '203.0.113.9',
  user_agent: 'vitest',
  extra_data: null,
  created_at: '2026-10-27T10:00:00Z',
});

const listing = (logs: ReturnType<typeof entry>[]) =>
  http.get('/api/v1/rbac/audit-logs', () =>
    HttpResponse.json({ logs, total: logs.length, skip: 0, limit: 20 }),
  );

/** The PrimeReact tag that wraps an action's text. */
const tagFor = (action: string): HTMLElement => {
  const tag = screen.getByText(action).closest('.p-tag');
  if (!tag) throw new Error(`no tag rendered for ${action}`);
  return tag as HTMLElement;
};

describe('AuditLogsPage — authentication events', () => {
  it('shows a lockout as a danger tag, like a failed login, and a success as success', async () => {
    server.use(
      listing([
        entry('1', 'LOGIN_LOCKED'),
        entry('2', 'LOGIN_FAILED'),
        entry('3', 'LOGIN_SUCCESS'),
      ]),
    );

    renderWithProviders(<AuditLogsPage />);

    await waitFor(() => expect(screen.getByText('LOGIN_LOCKED')).toBeInTheDocument());
    expect(tagFor('LOGIN_LOCKED')).toHaveClass('p-tag-danger');
    expect(tagFor('LOGIN_FAILED')).toHaveClass('p-tag-danger');
    expect(tagFor('LOGIN_SUCCESS')).toHaveClass('p-tag-success');
  });

  it('can be filtered to lockouts only', async () => {
    const requested: (string | null)[] = [];
    server.use(
      http.get('/api/v1/rbac/audit-logs', ({ request }) => {
        requested.push(new URL(request.url).searchParams.get('action'));
        return HttpResponse.json({ logs: [], total: 0, skip: 0, limit: 20 });
      }),
    );
    const user = userEvent.setup();
    renderWithProviders(<AuditLogsPage />);
    await waitFor(() => expect(requested.length).toBeGreaterThan(0));

    await selectDropdownOption(user, 'Filter by action type', 'Login Locked');

    await waitFor(() => expect(requested).toContain('LOGIN_LOCKED'));
    expect(requested[0]).toBeNull(); // the unfiltered first load sent no action at all
  });
});

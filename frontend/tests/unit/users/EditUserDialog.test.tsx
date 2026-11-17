import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { EditUserDialog } from '@features/user-management/components/EditUserDialog';
import type { User } from '@features/user-management/models/User';

import { server } from '../../mocks/server';
import { renderWithProviders, screen, waitFor } from '../../test-utils';

/**
 * The Edit User dialog exposes an AD credential check that is only relevant
 * while the "Validate with AD" switch is on — mirroring the backend login
 * branch that calls the Darwin AD service only when is_validate_ad is true.
 * These tests cover the gating (hidden vs. shown) and the end-to-end call
 * through the shared EmployeeAdService validate-credentials endpoint.
 */

const baseUser: User = {
  id: 42,
  username: 'jdoe',
  is_active: true,
  is_blocked: false,
  is_validate_ad: true,
  employee_id: '93300040',
  employee_name: 'John Doe',
  email: 'jdoe@example.com',
  last_login: null,
  created_by: 'system',
  created_date: '2024-01-01T00:00:00Z',
  modified_by: 'system',
  modified_date: '2024-01-01T00:00:00Z',
};

// Endpoints the dialog hits on open, independent of what each test asserts:
// the role dropdown (useRoles) and the user's current role assignment.
beforeEach(() => {
  server.use(
    http.get('/api/v1/rbac/roles', () =>
      HttpResponse.json({
        roles: [{ id: 1, code: 'ADMIN', name: 'Administrator', is_active: true }],
        total: 1,
      }),
    ),
    http.get('/api/v1/users/:id/roles', ({ params }) =>
      HttpResponse.json({ user_id: Number(params.id), roles: [] }),
    ),
  );
});

describe('EditUserDialog — Validate AD', () => {
  it('does not render dialog content while not visible', () => {
    renderWithProviders(
      <EditUserDialog visible={false} user={baseUser} onHide={vi.fn()} onSubmit={vi.fn()} />,
    );

    expect(screen.queryByLabelText('Edit user dialog')).not.toBeInTheDocument();
  });

  it('shows the Validate AD section pre-filled with the employee id when is_validate_ad is on', async () => {
    renderWithProviders(
      <EditUserDialog visible user={baseUser} onHide={vi.fn()} onSubmit={vi.fn()} />,
    );

    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Validate AD credentials' })).toBeInTheDocument(),
    );
    expect(screen.getByLabelText('Employee ID to validate')).toHaveValue('93300040');
  });

  it('hides the Validate AD section when is_validate_ad is off', () => {
    renderWithProviders(
      <EditUserDialog
        visible
        user={{ ...baseUser, is_validate_ad: false }}
        onHide={vi.fn()}
        onSubmit={vi.fn()}
      />,
    );

    expect(
      screen.queryByRole('button', { name: 'Validate AD credentials' }),
    ).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Employee ID to validate')).not.toBeInTheDocument();
  });

  it('calls the EmployeeAdService validate-credentials endpoint and shows a valid result', async () => {
    const user = userEvent.setup();
    let captured: { employee_id: string; password: string } | null = null;
    server.use(
      http.post('/api/v1/services/employee-ad/validate-credentials', async ({ request }) => {
        captured = (await request.json()) as { employee_id: string; password: string };
        return HttpResponse.json({
          is_success: true,
          is_valid_user: true,
          raw_response: { IsSuccess: true, IsValidUser: true },
        });
      }),
    );

    renderWithProviders(
      <EditUserDialog visible user={baseUser} onHide={vi.fn()} onSubmit={vi.fn()} />,
    );

    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Validate AD credentials' })).toBeInTheDocument(),
    );

    await user.type(screen.getByPlaceholderText('Enter password'), 'secret-pass');
    await user.click(screen.getByRole('button', { name: 'Validate AD credentials' }));

    await waitFor(() => expect(screen.getByText('Valid AD user')).toBeInTheDocument());
    expect(captured).toEqual({ employee_id: '93300040', password: 'secret-pass' });
  });

  it('shows an invalid result when the AD service rejects the credentials', async () => {
    const user = userEvent.setup();
    server.use(
      http.post('/api/v1/services/employee-ad/validate-credentials', () =>
        HttpResponse.json({
          is_success: true,
          is_valid_user: false,
          raw_response: { IsSuccess: true, IsValidUser: false },
        }),
      ),
    );

    renderWithProviders(
      <EditUserDialog visible user={baseUser} onHide={vi.fn()} onSubmit={vi.fn()} />,
    );

    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Validate AD credentials' })).toBeInTheDocument(),
    );

    await user.type(screen.getByPlaceholderText('Enter password'), 'wrong-pass');
    await user.click(screen.getByRole('button', { name: 'Validate AD credentials' }));

    await waitFor(() => expect(screen.getByText('Invalid AD credentials')).toBeInTheDocument());
  });

  it('keeps the Validate AD button disabled until a password is entered', async () => {
    renderWithProviders(
      <EditUserDialog visible user={baseUser} onHide={vi.fn()} onSubmit={vi.fn()} />,
    );

    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Validate AD credentials' })).toBeInTheDocument(),
    );

    // Employee id is pre-filled, but with no password the button stays disabled.
    expect(screen.getByRole('button', { name: 'Validate AD credentials' })).toHaveClass(
      'p-disabled',
    );
  });
});

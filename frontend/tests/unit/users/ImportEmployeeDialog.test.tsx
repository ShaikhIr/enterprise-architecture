import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { describe, expect, it, vi } from 'vitest';

import { ImportEmployeeDialog } from '@features/user-management/components/ImportEmployeeDialog';
import type { ImportEmployeesResponse } from '@features/user-management/models/User';

import { server } from '../../mocks/server';
import { renderWithProviders, screen, waitFor, within } from '../../test-utils';

const IMPORT_URL = '/api/v1/users/import-employees';

const IMPORT_RESPONSE: ImportEmployeesResponse = {
  total: 1,
  created: 1,
  updated: 0,
  failed: 0,
  results: [{ employee_id: '93300040', status: 'created', message: '' }],
};

describe('ImportEmployeeDialog — default password', () => {
  it('omits default_password from the request when the field is left blank', async () => {
    const user = userEvent.setup();
    let captured: Record<string, unknown> | null = null;
    server.use(
      http.post(IMPORT_URL, async ({ request }) => {
        captured = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(IMPORT_RESPONSE);
      }),
    );

    renderWithProviders(<ImportEmployeeDialog visible onHide={vi.fn()} />);

    await user.type(screen.getByLabelText('Employee IDs to import'), '93300040');
    await user.click(screen.getByRole('button', { name: 'Import' }));

    await waitFor(() => expect(captured).not.toBeNull());
    expect(captured).toEqual({ employee_ids: ['93300040'] });
  });

  it('sends the trimmed default_password when the admin provides one', async () => {
    const user = userEvent.setup();
    let captured: Record<string, unknown> | null = null;
    server.use(
      http.post(IMPORT_URL, async ({ request }) => {
        captured = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(IMPORT_RESPONSE);
      }),
    );

    renderWithProviders(<ImportEmployeeDialog visible onHide={vi.fn()} />);

    await user.type(screen.getByLabelText('Employee IDs to import'), '93300040');
    await user.type(screen.getByPlaceholderText('Defaults to Employee ID'), '  Welcome@123  ');
    await user.click(screen.getByRole('button', { name: 'Import' }));

    await waitFor(() => expect(captured).not.toBeNull());
    expect(captured).toEqual({
      employee_ids: ['93300040'],
      default_password: 'Welcome@123',
    });
  });

  it('renders the per-employee results and the count tags after import', async () => {
    const user = userEvent.setup();
    server.use(http.post(IMPORT_URL, () => HttpResponse.json(IMPORT_RESPONSE)));

    renderWithProviders(<ImportEmployeeDialog visible onHide={vi.fn()} />);

    await user.type(screen.getByLabelText('Employee IDs to import'), '93300040');
    await user.click(screen.getByRole('button', { name: 'Import' }));

    const table = await screen.findByLabelText('Import results');
    expect(within(table).getByText('93300040')).toBeInTheDocument();
    expect(within(table).getByText('created')).toBeInTheDocument();
    expect(screen.getByText('Created: 1')).toBeInTheDocument();
  });

  it('does not call the endpoint when no employee ids are entered', () => {
    const handler = vi.fn(() => HttpResponse.json(IMPORT_RESPONSE));
    server.use(http.post(IMPORT_URL, handler));

    renderWithProviders(<ImportEmployeeDialog visible onHide={vi.fn()} />);

    // The Import button is disabled with an empty id field; typing only spaces
    // keeps the parsed id list empty so no request is issued.
    expect(screen.getByRole('button', { name: 'Import' })).toHaveClass('p-disabled');
    expect(handler).not.toHaveBeenCalled();
  });
});

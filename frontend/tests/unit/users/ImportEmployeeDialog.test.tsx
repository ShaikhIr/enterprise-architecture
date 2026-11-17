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
    await user.type(
      screen.getByPlaceholderText('Blank: a random password is set'),
      '  Welcome@123  ',
    );
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

describe('ImportEmployeeDialog — password rules and failures', () => {
  const PASSWORD_PLACEHOLDER = 'Blank: a random password is set';

  it('no longer promises the Employee ID as the initial password', () => {
    renderWithProviders(<ImportEmployeeDialog visible onHide={vi.fn()} />);

    expect(screen.queryByText(/use the Employee ID as the initial password/i)).toBeNull();
    expect(screen.getByText(/random password nobody knows/i)).toBeInTheDocument();
  });

  it('blocks a password shorter than 8 characters and says why', async () => {
    const user = userEvent.setup();
    const handler = vi.fn(() => HttpResponse.json(IMPORT_RESPONSE));
    server.use(http.post(IMPORT_URL, handler));
    renderWithProviders(<ImportEmployeeDialog visible onHide={vi.fn()} />);

    await user.type(screen.getByLabelText('Employee IDs to import'), '93300040');
    await user.type(screen.getByPlaceholderText(PASSWORD_PLACEHOLDER), 'short');

    expect(screen.getByText('Use 8 to 72 characters, or leave it blank.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Import' })).toHaveClass('p-disabled');
    expect(handler).not.toHaveBeenCalled();
  });

  it('blocks a password longer than 72 characters', async () => {
    const user = userEvent.setup();
    renderWithProviders(<ImportEmployeeDialog visible onHide={vi.fn()} />);

    await user.type(screen.getByLabelText('Employee IDs to import'), '93300040');
    await user.type(screen.getByPlaceholderText(PASSWORD_PLACEHOLDER), 'x'.repeat(73));

    expect(screen.getByText('Use 8 to 72 characters, or leave it blank.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Import' })).toHaveClass('p-disabled');
  });

  it('accepts a password at the lower and upper bounds', async () => {
    const user = userEvent.setup();
    renderWithProviders(<ImportEmployeeDialog visible onHide={vi.fn()} />);
    await user.type(screen.getByLabelText('Employee IDs to import'), '93300040');
    const field = screen.getByPlaceholderText(PASSWORD_PLACEHOLDER);

    await user.type(field, '12345678');
    expect(screen.queryByText('Use 8 to 72 characters, or leave it blank.')).toBeNull();

    await user.clear(field);
    await user.type(field, 'x'.repeat(72));
    expect(screen.queryByText('Use 8 to 72 characters, or leave it blank.')).toBeNull();
    expect(screen.getByRole('button', { name: 'Import' })).not.toHaveClass('p-disabled');
  });

  it('treats spaces alone as blank, not as a too-short password', async () => {
    const user = userEvent.setup();
    renderWithProviders(<ImportEmployeeDialog visible onHide={vi.fn()} />);

    await user.type(screen.getByLabelText('Employee IDs to import'), '93300040');
    await user.type(screen.getByPlaceholderText(PASSWORD_PLACEHOLDER), '   ');

    expect(screen.queryByText('Use 8 to 72 characters, or leave it blank.')).toBeNull();
    expect(screen.getByRole('button', { name: 'Import' })).not.toHaveClass('p-disabled');
  });

  it('shows the server message inside the dialog when the import fails', async () => {
    const user = userEvent.setup();
    server.use(
      http.post(IMPORT_URL, () =>
        HttpResponse.json({ detail: 'Darwin API error: unavailable' }, { status: 502 }),
      ),
    );
    renderWithProviders(<ImportEmployeeDialog visible onHide={vi.fn()} />);

    await user.type(screen.getByLabelText('Employee IDs to import'), '93300040');
    await user.click(screen.getByRole('button', { name: 'Import' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('Darwin API error: unavailable');
  });

  it('clears an earlier failure when the import is retried', async () => {
    const user = userEvent.setup();
    let calls = 0;
    server.use(
      http.post(IMPORT_URL, () => {
        calls += 1;
        return calls === 1
          ? HttpResponse.json({ detail: 'try later' }, { status: 502 })
          : HttpResponse.json(IMPORT_RESPONSE);
      }),
    );
    renderWithProviders(<ImportEmployeeDialog visible onHide={vi.fn()} />);

    await user.type(screen.getByLabelText('Employee IDs to import'), '93300040');
    await user.click(screen.getByRole('button', { name: 'Import' }));
    await screen.findByRole('alert');
    await user.click(screen.getByRole('button', { name: 'Import' }));

    await screen.findByLabelText('Import results');
    expect(screen.queryByRole('alert')).toBeNull();
  });
});

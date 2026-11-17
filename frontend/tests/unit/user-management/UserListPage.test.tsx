import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { beforeEach, describe, expect, it } from 'vitest';

import { UserListPage } from '@features/user-management/pages/UserListPage';

import { server } from '../../mocks/server';
import {
  getDropdownLabel,
  renderWithProviders,
  screen,
  selectDropdownOption,
  waitFor,
} from '../../test-utils';

const baseUser = {
  id: 1,
  username: 'alice',
  is_active: true,
  is_blocked: false,
  is_validate_ad: false,
  employee_id: 'E100',
  employee_name: 'Alice Anderson',
  email: 'alice@example.com',
  last_login: null,
  created_by: 'system',
  created_date: '2024-01-01T00:00:00Z',
  modified_by: 'system',
  modified_date: '2024-01-01T00:00:00Z',
};

const ROLES = [
  { id: 11, code: 'ADMIN', name: 'Administrator', is_active: true },
  { id: 12, code: 'USER', name: 'User', is_active: true },
];

const usersListing = (users: (typeof baseUser)[]) =>
  http.get('/api/v1/users', () =>
    HttpResponse.json({ users, total: users.length, skip: 0, limit: 100 }),
  );

beforeEach(() => {
  server.use(
    usersListing([baseUser]),
    http.get('/api/v1/rbac/roles', () => HttpResponse.json({ roles: ROLES, total: ROLES.length })),
    http.get('/api/v1/users/:id/roles', ({ params }) =>
      HttpResponse.json({
        user_id: Number(params.id),
        roles: [{ id: 11, code: 'ADMIN', name: 'Administrator', permissions: [] }],
      }),
    ),
  );
});

const actionButton = (username: string, icon: string): HTMLElement => {
  const row = screen.getByRole('cell', { name: username }).closest('tr');
  const button = row?.querySelector(`.${icon}`)?.closest('button');
  if (!button) throw new Error(`no ${icon} button for ${username}`);
  return button as HTMLElement;
};

describe('UserListPage — list', () => {
  it('renders the heading, the toolbar buttons and the fetched users', async () => {
    renderWithProviders(<UserListPage />);

    expect(screen.getByRole('heading', { name: 'User Management' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Create new user' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Fetch employees from AD' })).toBeInTheDocument();
    expect(await screen.findByRole('cell', { name: 'alice' })).toBeInTheDocument();
    expect(screen.getByText('Alice Anderson')).toBeInTheDocument();
  });

  it('shows the busy overlay until the list resolves', async () => {
    server.use(
      http.get('/api/v1/users', async () => {
        await new Promise((resolve) => setTimeout(resolve, 100));
        return HttpResponse.json({ users: [baseUser], total: 1, skip: 0, limit: 100 });
      }),
    );

    renderWithProviders(<UserListPage />);

    expect(document.querySelector('.p-datatable-loading-overlay')).toBeInTheDocument();
    await screen.findByRole('cell', { name: 'alice' });
    expect(document.querySelector('.p-datatable-loading-overlay')).not.toBeInTheDocument();
  });

  it('shows the empty message when there are no users', async () => {
    server.use(usersListing([]));

    renderWithProviders(<UserListPage />);

    expect(await screen.findByText('No users found.')).toBeInTheDocument();
  });

  it('falls back to the empty table when the list request fails', async () => {
    server.use(
      http.get('/api/v1/users', () => HttpResponse.json({ detail: 'boom' }, { status: 500 })),
    );

    renderWithProviders(<UserListPage />);

    expect(await screen.findByText('No users found.')).toBeInTheDocument();
  });

  it('requests the first page of 100 users', async () => {
    let captured = null as URL | null;
    server.use(
      http.get('/api/v1/users', ({ request }) => {
        captured = new URL(request.url);
        return HttpResponse.json({ users: [], total: 0, skip: 0, limit: 100 });
      }),
    );

    renderWithProviders(<UserListPage />);

    await waitFor(() => expect(captured).not.toBeNull());
    expect(captured!.searchParams.get('skip')).toBe('0');
    expect(captured!.searchParams.get('limit')).toBe('100');
  });
});

describe('UserListPage — create user', () => {
  it('opens the create dialog from the New User button and closes it on Cancel', async () => {
    const user = userEvent.setup();
    renderWithProviders(<UserListPage />);
    await screen.findByRole('cell', { name: 'alice' });

    await user.click(screen.getByRole('button', { name: 'Create new user' }));
    expect(screen.getByText('Create New User')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Cancel' }));
    await waitFor(() => expect(screen.queryByText('Create New User')).not.toBeInTheDocument());
  });

  it('creates a user end to end: posts the form, closes the dialog, toasts and refetches the list', async () => {
    const user = userEvent.setup();
    let posted: unknown = null;
    let listCalls = 0;
    server.use(
      http.get('/api/v1/users', () => {
        listCalls += 1;
        return HttpResponse.json({ users: [baseUser], total: 1, skip: 0, limit: 100 });
      }),
      http.post('/api/v1/users', async ({ request }) => {
        posted = await request.json();
        return HttpResponse.json({ ...baseUser, id: 2, username: 'newbie' }, { status: 201 });
      }),
    );
    renderWithProviders(<UserListPage />);
    await screen.findByRole('cell', { name: 'alice' });
    expect(listCalls).toBe(1);

    await user.click(screen.getByRole('button', { name: 'Create new user' }));
    await user.type(screen.getByPlaceholderText('Enter username'), 'newbie');
    await user.type(screen.getByPlaceholderText('Enter password'), 'Passw0rd!');
    await waitFor(() =>
      expect(screen.getByLabelText('Assign role').closest('.p-dropdown')).not.toHaveClass(
        'p-disabled',
      ),
    );
    await selectDropdownOption(user, 'Assign role', 'User (USER)');
    await user.click(screen.getByRole('button', { name: 'Create' }));

    expect(await screen.findByText("User 'newbie' created successfully")).toBeInTheDocument();
    expect(posted).toEqual({
      username: 'newbie',
      password: 'Passw0rd!',
      is_validate_ad: true,
      role_id: 12,
    });
    await waitFor(() => expect(screen.queryByText('Create New User')).not.toBeInTheDocument());
    // The mutation invalidates the users cache, so the list is requested again.
    await waitFor(() => expect(listCalls).toBeGreaterThan(1));
  });

  it('toasts the backend message and keeps the dialog open when the username already exists', async () => {
    const user = userEvent.setup();
    server.use(
      http.post('/api/v1/users', () =>
        HttpResponse.json({ detail: 'Username already exists' }, { status: 409 }),
      ),
    );
    renderWithProviders(<UserListPage />);
    await screen.findByRole('cell', { name: 'alice' });

    await user.click(screen.getByRole('button', { name: 'Create new user' }));
    await user.type(screen.getByPlaceholderText('Enter username'), 'alice');
    await user.type(screen.getByPlaceholderText('Enter password'), 'Passw0rd!');
    await waitFor(() =>
      expect(screen.getByLabelText('Assign role').closest('.p-dropdown')).not.toHaveClass(
        'p-disabled',
      ),
    );
    await selectDropdownOption(user, 'Assign role', 'Administrator (ADMIN)');
    await user.click(screen.getByRole('button', { name: 'Create' }));

    expect(await screen.findByText('Username already exists')).toBeInTheDocument();
    expect(screen.getByText('Create New User')).toBeInTheDocument();
  });

  it('flattens a Pydantic 422 error array into the toast', async () => {
    const user = userEvent.setup();
    server.use(
      http.post('/api/v1/users', () =>
        HttpResponse.json(
          {
            detail: [
              {
                loc: ['body', 'password'],
                msg: 'Password too weak',
                type: 'value_error',
              },
            ],
          },
          { status: 422 },
        ),
      ),
    );
    renderWithProviders(<UserListPage />);
    await screen.findByRole('cell', { name: 'alice' });

    await user.click(screen.getByRole('button', { name: 'Create new user' }));
    await user.type(screen.getByPlaceholderText('Enter username'), 'newbie');
    await user.type(screen.getByPlaceholderText('Enter password'), 'Passw0rd!');
    await waitFor(() =>
      expect(screen.getByLabelText('Assign role').closest('.p-dropdown')).not.toHaveClass(
        'p-disabled',
      ),
    );
    await selectDropdownOption(user, 'Assign role', 'User (USER)');
    await user.click(screen.getByRole('button', { name: 'Create' }));

    expect(await screen.findByText('password: Password too weak')).toBeInTheDocument();
  });
});

describe('UserListPage — edit user', () => {
  it('opens the edit dialog for the clicked row and preloads the user’s current role', async () => {
    const user = userEvent.setup();
    renderWithProviders(<UserListPage />);
    await screen.findByRole('cell', { name: 'alice' });

    await user.click(actionButton('alice', 'pi-pencil'));

    expect(await screen.findByText('Edit User: alice')).toBeInTheDocument();
    await waitFor(() => expect(getDropdownLabel('Assign role')).toBe('Administrator (ADMIN)'));
    expect(screen.getByRole('switch', { name: 'Active status' })).toBeChecked();
    expect(screen.getByRole('switch', { name: 'Blocked status' })).not.toBeChecked();
  });

  it('updates a user end to end: patches only the form values, closes, toasts and refetches', async () => {
    const user = userEvent.setup();
    let patched: unknown = null;
    let patchedId: string | null = null;
    let listCalls = 0;
    server.use(
      http.get('/api/v1/users', () => {
        listCalls += 1;
        return HttpResponse.json({ users: [baseUser], total: 1, skip: 0, limit: 100 });
      }),
      http.patch('/api/v1/users/:id', async ({ request, params }) => {
        patched = await request.json();
        patchedId = String(params.id);
        return HttpResponse.json({ ...baseUser, is_blocked: true });
      }),
    );
    renderWithProviders(<UserListPage />);
    await screen.findByRole('cell', { name: 'alice' });

    await user.click(actionButton('alice', 'pi-pencil'));
    await waitFor(() => expect(getDropdownLabel('Assign role')).toBe('Administrator (ADMIN)'));
    await selectDropdownOption(user, 'Assign role', 'User (USER)');
    await user.click(screen.getByRole('switch', { name: 'Blocked status' }));
    await user.click(screen.getByRole('button', { name: 'Save' }));

    expect(await screen.findByText('User updated successfully')).toBeInTheDocument();
    expect(patchedId).toBe('1');
    expect(patched).toEqual({
      is_active: true,
      is_blocked: true,
      is_validate_ad: false,
      role_id: 12,
    });
    await waitFor(() => expect(screen.queryByText('Edit User: alice')).not.toBeInTheDocument());
    await waitFor(() => expect(listCalls).toBeGreaterThan(1));
  });

  it('toasts the backend message and keeps the edit dialog open when the update fails', async () => {
    const user = userEvent.setup();
    server.use(
      http.patch('/api/v1/users/:id', () =>
        HttpResponse.json({ detail: 'Cannot block the last administrator' }, { status: 409 }),
      ),
    );
    renderWithProviders(<UserListPage />);
    await screen.findByRole('cell', { name: 'alice' });

    await user.click(actionButton('alice', 'pi-pencil'));
    await waitFor(() => expect(getDropdownLabel('Assign role')).toBe('Administrator (ADMIN)'));
    await user.click(screen.getByRole('button', { name: 'Save' }));

    expect(await screen.findByText('Cannot block the last administrator')).toBeInTheDocument();
    expect(screen.getByText('Edit User: alice')).toBeInTheDocument();
  });

  it('closes the edit dialog on Cancel without sending a request', async () => {
    const user = userEvent.setup();
    let patched = false;
    server.use(
      http.patch('/api/v1/users/:id', () => {
        patched = true;
        return HttpResponse.json(baseUser);
      }),
    );
    renderWithProviders(<UserListPage />);
    await screen.findByRole('cell', { name: 'alice' });

    await user.click(actionButton('alice', 'pi-pencil'));
    await screen.findByText('Edit User: alice');
    await user.click(screen.getByRole('button', { name: 'Cancel' }));

    await waitFor(() => expect(screen.queryByText('Edit User: alice')).not.toBeInTheDocument());
    expect(patched).toBe(false);
  });
});

describe('UserListPage — import employees', () => {
  const importResponse = {
    total: 1,
    created: 1,
    updated: 0,
    failed: 0,
    results: [{ employee_id: '93300040', status: 'created', message: '' }],
  };

  it('opens the import dialog and toasts after a successful import', async () => {
    const user = userEvent.setup();
    server.use(
      http.post('/api/v1/users/import-employees', () => HttpResponse.json(importResponse)),
    );
    renderWithProviders(<UserListPage />);
    await screen.findByRole('cell', { name: 'alice' });

    await user.click(screen.getByRole('button', { name: 'Fetch employees from AD' }));
    await user.type(screen.getByLabelText('Employee IDs to import'), '93300040');
    await user.click(screen.getByRole('button', { name: 'Import' }));

    expect(await screen.findByText('Employees imported successfully')).toBeInTheDocument();
  });

  it('does not toast success when nothing was created or updated', async () => {
    const user = userEvent.setup();
    server.use(
      http.post('/api/v1/users/import-employees', () =>
        HttpResponse.json({
          total: 1,
          created: 0,
          updated: 0,
          failed: 1,
          results: [{ employee_id: '1', status: 'failed', message: 'Not found in AD' }],
        }),
      ),
    );
    renderWithProviders(<UserListPage />);
    await screen.findByRole('cell', { name: 'alice' });

    await user.click(screen.getByRole('button', { name: 'Fetch employees from AD' }));
    await user.type(screen.getByLabelText('Employee IDs to import'), '1');
    await user.click(screen.getByRole('button', { name: 'Import' }));

    expect(await screen.findByText('Not found in AD')).toBeInTheDocument();
    expect(screen.queryByText('Employees imported successfully')).not.toBeInTheDocument();
  });

  // SUSPECTED SRC BUG: ImportEmployeeDialog swallows a failed import with the comment
  // "Error handled via toast in parent", but UserListPage only passes `onSuccess` and shows
  // no error toast, so an admin gets no feedback at all when the import request fails.
  it('shows the error when the import request fails', async () => {
    const user = userEvent.setup();
    server.use(
      http.post('/api/v1/users/import-employees', () =>
        HttpResponse.json({ detail: 'Darwin AD unreachable' }, { status: 502 }),
      ),
    );
    renderWithProviders(<UserListPage />);
    await screen.findByRole('cell', { name: 'alice' });

    await user.click(screen.getByRole('button', { name: 'Fetch employees from AD' }));
    await user.type(screen.getByLabelText('Employee IDs to import'), '93300040');
    await user.click(screen.getByRole('button', { name: 'Import' }));

    expect(
      await screen.findByText('Darwin AD unreachable', undefined, { timeout: 1500 }),
    ).toBeInTheDocument();
  });
});

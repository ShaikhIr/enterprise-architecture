import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { describe, expect, it, vi } from 'vitest';

import { UserTable } from '@features/user-management/components/UserTable';
import type { User } from '@features/user-management/models/User';

import { server } from '../../mocks/server';
import { renderWithProviders, screen, waitFor, within } from '../../test-utils';

const makeUser = (overrides: Partial<User> = {}): User => ({
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
  ...overrides,
});

const alice = makeUser();
const bob = makeUser({
  id: 2,
  username: 'bob',
  employee_id: 'E200',
  employee_name: 'Bob Brown',
  email: 'bob@example.com',
  is_active: false,
});
const carol = makeUser({
  id: 3,
  username: 'carol',
  employee_id: 'E300',
  employee_name: 'Carol Clark',
  email: 'carol@example.com',
  is_blocked: true,
});

/** The body row whose first cell is `username`. */
const rowFor = (username: string): HTMLElement => {
  const cell = screen.getByRole('cell', { name: username });
  const row = cell.closest('tr');
  if (!row) throw new Error(`no row for ${username}`);
  return row;
};

/** A row's icon-only action button, found by its PrimeIcons class. */
const actionButton = (username: string, icon: string): HTMLElement => {
  const button = rowFor(username).querySelector(`.${icon}`)?.closest('button');
  if (!button) throw new Error(`no ${icon} button for ${username}`);
  return button as HTMLElement;
};

describe('UserTable — table rendering', () => {
  it('renders one row per user with employee columns', () => {
    renderWithProviders(<UserTable users={[alice, bob]} loading={false} onEdit={vi.fn()} />);

    const row = rowFor('alice');
    expect(within(row).getByText('E100')).toBeInTheDocument();
    expect(within(row).getByText('Alice Anderson')).toBeInTheDocument();
    expect(within(row).getByText('alice@example.com')).toBeInTheDocument();
    expect(screen.getByRole('cell', { name: 'bob' })).toBeInTheDocument();
  });

  it('shows the empty message when there are no users', () => {
    renderWithProviders(<UserTable users={[]} loading={false} onEdit={vi.fn()} />);

    expect(screen.getByText('No users found.')).toBeInTheDocument();
  });

  it('shows the busy overlay while loading', () => {
    renderWithProviders(<UserTable users={[]} loading onEdit={vi.fn()} />);

    expect(document.querySelector('.p-datatable-loading-overlay')).toBeInTheDocument();
  });

  it('shows Blocked over Inactive over Active in the status column', () => {
    renderWithProviders(
      <UserTable
        users={[alice, bob, makeUser({ ...carol, is_active: false })]}
        loading={false}
        onEdit={vi.fn()}
      />,
    );

    const tagOf = (username: string) => rowFor(username).querySelector('.p-tag');
    expect(tagOf('alice')).toHaveTextContent('Active');
    expect(tagOf('alice')).toHaveClass('p-tag-success');
    expect(tagOf('bob')).toHaveTextContent('Inactive');
    expect(tagOf('bob')).toHaveClass('p-tag-warning');
    // Blocked wins even when the account is also inactive.
    expect(tagOf('carol')).toHaveTextContent('Blocked');
    expect(tagOf('carol')).toHaveClass('p-tag-danger');
  });

  it('formats last login as dd-MM-yyyy hh:mm:ss AM/PM, and shows a dash when never logged in', () => {
    const loggedIn = makeUser({
      id: 4,
      username: 'dave',
      last_login: new Date(2024, 0, 15, 14, 5, 9).toISOString(),
    });
    const morning = makeUser({
      id: 5,
      username: 'erin',
      last_login: new Date(2024, 10, 3, 0, 30, 0).toISOString(),
    });
    renderWithProviders(
      <UserTable users={[alice, loggedIn, morning]} loading={false} onEdit={vi.fn()} />,
    );

    expect(within(rowFor('dave')).getByText('15-01-2024 02:05:09 PM')).toBeInTheDocument();
    // Midnight hour renders as 12, not 00.
    expect(within(rowFor('erin')).getByText('03-11-2024 12:30:00 AM')).toBeInTheDocument();
    expect(within(rowFor('alice')).getByText('—')).toBeInTheDocument();
  });
});

describe('UserTable — filtering', () => {
  it('narrows the rows by username using the column filter', async () => {
    const user = userEvent.setup();
    renderWithProviders(<UserTable users={[alice, bob, carol]} loading={false} onEdit={vi.fn()} />);

    // Four searchable columns: username, employee id, employee name, email (in that order).
    const [usernameFilter] = screen.getAllByPlaceholderText('Search...');
    await user.type(usernameFilter!, 'bo');

    await waitFor(() =>
      expect(screen.queryByRole('cell', { name: 'alice' })).not.toBeInTheDocument(),
    );
    expect(screen.getByRole('cell', { name: 'bob' })).toBeInTheDocument();
    expect(screen.queryByRole('cell', { name: 'carol' })).not.toBeInTheDocument();
  });

  it('narrows the rows by employee name using its own column filter', async () => {
    const user = userEvent.setup();
    renderWithProviders(<UserTable users={[alice, bob, carol]} loading={false} onEdit={vi.fn()} />);

    const filters = screen.getAllByPlaceholderText('Search...');
    await user.type(filters[2]!, 'Clark');

    await waitFor(() =>
      expect(screen.queryByRole('cell', { name: 'alice' })).not.toBeInTheDocument(),
    );
    expect(screen.getByRole('cell', { name: 'carol' })).toBeInTheDocument();
  });

  it('shows the empty message when no row matches', async () => {
    const user = userEvent.setup();
    renderWithProviders(<UserTable users={[alice, bob]} loading={false} onEdit={vi.fn()} />);

    await user.type(screen.getAllByPlaceholderText('Search...')[0]!, 'zzz');

    expect(await screen.findByText('No users found.')).toBeInTheDocument();
  });
});

describe('UserTable — edit action', () => {
  it('calls onEdit with the row user when the pencil is clicked', async () => {
    const user = userEvent.setup();
    const onEdit = vi.fn();
    renderWithProviders(<UserTable users={[alice, bob]} loading={false} onEdit={onEdit} />);

    await user.click(actionButton('bob', 'pi-pencil'));

    expect(onEdit).toHaveBeenCalledTimes(1);
    expect(onEdit).toHaveBeenCalledWith(bob);
  });
});

describe('UserTable — roles dialog', () => {
  it('loads the user roles and shows each role as a tree node', async () => {
    const user = userEvent.setup();
    let requestedId: string | null = null;
    server.use(
      http.get('/api/v1/users/:id/roles', ({ params }) => {
        requestedId = String(params.id);
        return HttpResponse.json({
          user_id: 1,
          roles: [
            {
              id: 11,
              code: 'ADMIN',
              name: 'Administrator',
              permissions: [
                {
                  code: 'menu.users',
                  name: 'Users Menu',
                  scope: 'MENU',
                  resource: 'users',
                  action: 'READ',
                },
                {
                  code: 'users.list',
                  name: 'List Users',
                  scope: 'API',
                  resource: 'users',
                  action: 'READ',
                },
              ],
            },
          ],
        });
      }),
    );
    renderWithProviders(<UserTable users={[alice]} loading={false} onEdit={vi.fn()} />);

    await user.click(actionButton('alice', 'pi-shield'));

    expect(screen.getByText('Roles — alice')).toBeInTheDocument();
    expect(await screen.findByText('Administrator (ADMIN)')).toBeInTheDocument();
    expect(requestedId).toBe('1');
  });

  it('reveals a role’s permissions when its node is expanded', async () => {
    const user = userEvent.setup();
    server.use(
      http.get('/api/v1/users/:id/roles', () =>
        HttpResponse.json({
          user_id: 1,
          roles: [
            {
              id: 11,
              code: 'ADMIN',
              name: 'Administrator',
              permissions: [
                {
                  code: 'users.list',
                  name: 'List Users',
                  scope: 'API',
                  resource: 'users',
                  action: 'READ',
                },
              ],
            },
          ],
        }),
      ),
    );
    renderWithProviders(<UserTable users={[alice]} loading={false} onEdit={vi.fn()} />);

    await user.click(actionButton('alice', 'pi-shield'));
    await screen.findByText('Administrator (ADMIN)');
    expect(screen.queryByText('List Users')).not.toBeInTheDocument();

    await user.click(document.querySelector('.p-tree-toggler') as HTMLElement);

    expect(await screen.findByText('List Users')).toBeInTheDocument();
  });

  it('says so when the user has no roles', async () => {
    const user = userEvent.setup();
    server.use(
      http.get('/api/v1/users/:id/roles', () => HttpResponse.json({ user_id: 1, roles: [] })),
    );
    renderWithProviders(<UserTable users={[alice]} loading={false} onEdit={vi.fn()} />);

    await user.click(actionButton('alice', 'pi-shield'));

    expect(await screen.findByText('No roles assigned.')).toBeInTheDocument();
  });

  it('shows a failure node when the roles request fails', async () => {
    const user = userEvent.setup();
    server.use(
      http.get('/api/v1/users/:id/roles', () =>
        HttpResponse.json({ detail: 'nope' }, { status: 500 }),
      ),
    );
    renderWithProviders(<UserTable users={[alice]} loading={false} onEdit={vi.fn()} />);

    await user.click(actionButton('alice', 'pi-shield'));

    expect(await screen.findByText('Failed to load roles')).toBeInTheDocument();
  });
});

describe('UserTable — employee details dialog', () => {
  const detail = {
    employee_id: 'E100',
    employee_name: 'Alice Anderson',
    first_name: 'Alice',
    middle_name: null,
    last_name: 'Anderson',
    email: 'alice@example.com',
    designation_title: 'Engineer',
    department: 'Platform',
    business_unit: null,
    reporting_manager: 'Zed',
    date_of_joining: null,
    created_date: new Date(2024, 1, 29, 9, 7, 3).toISOString(),
    is_active: true,
    id: 1,
  };

  it('fetches /users/:id/details and shows each non-empty field with a readable label', async () => {
    const user = userEvent.setup();
    let requestedId: string | null = null;
    server.use(
      http.get('/api/v1/users/:id/details', ({ params }) => {
        requestedId = String(params.id);
        return HttpResponse.json(detail);
      }),
    );
    renderWithProviders(<UserTable users={[alice]} loading={false} onEdit={vi.fn()} />);

    await user.click(actionButton('alice', 'pi-id-card'));

    expect(screen.getByText('Employee Details — alice')).toBeInTheDocument();
    expect(await screen.findByText('designation title')).toBeInTheDocument();
    expect(screen.getByText('Engineer')).toBeInTheDocument();
    expect(screen.getByText('reporting manager')).toBeInTheDocument();
    expect(requestedId).toBe('1');
  });

  it('omits empty values and the id/is_active flags, and formats created_date', async () => {
    const user = userEvent.setup();
    server.use(http.get('/api/v1/users/:id/details', () => HttpResponse.json(detail)));
    renderWithProviders(<UserTable users={[alice]} loading={false} onEdit={vi.fn()} />);

    await user.click(actionButton('alice', 'pi-id-card'));
    await screen.findByText('designation title');

    expect(screen.queryByText('middle name')).not.toBeInTheDocument();
    expect(screen.queryByText('business unit')).not.toBeInTheDocument();
    expect(screen.queryByText('is active')).not.toBeInTheDocument();
    expect(screen.queryByText('id')).not.toBeInTheDocument();
    expect(screen.getByText('29-02-2024 09:07:03 AM')).toBeInTheDocument();
  });

  it('says no details are available when the request fails', async () => {
    const user = userEvent.setup();
    server.use(
      http.get('/api/v1/users/:id/details', () =>
        HttpResponse.json({ detail: 'missing' }, { status: 404 }),
      ),
    );
    renderWithProviders(<UserTable users={[alice]} loading={false} onEdit={vi.fn()} />);

    await user.click(actionButton('alice', 'pi-id-card'));

    expect(await screen.findByText('No employee details available.')).toBeInTheDocument();
  });
});

describe('UserTable — login history dialog', () => {
  it('lists the history rows with action tags coloured by outcome', async () => {
    const user = userEvent.setup();
    let requestedId: string | null = null;
    server.use(
      http.get('/api/v1/users/:id/login-history', ({ params }) => {
        requestedId = String(params.id);
        return HttpResponse.json([
          {
            action: 'LOGIN_SUCCESS',
            ip_address: '10.0.0.1',
            user_agent: 'vitest',
            created_at: new Date(2024, 4, 6, 13, 0, 0).toISOString(),
          },
          {
            action: 'LOGOUT',
            ip_address: '10.0.0.2',
            user_agent: 'vitest',
            created_at: new Date(2024, 4, 6, 14, 0, 0).toISOString(),
          },
          {
            action: 'LOGIN_FAILED',
            ip_address: '10.0.0.3',
            user_agent: 'vitest',
            created_at: new Date(2024, 4, 6, 15, 0, 0).toISOString(),
          },
        ]);
      }),
    );
    renderWithProviders(<UserTable users={[alice]} loading={false} onEdit={vi.fn()} />);

    await user.click(actionButton('alice', 'pi-history'));

    expect(screen.getByText('Login History — alice')).toBeInTheDocument();
    const tag = async (action: string) => (await screen.findByText(action)).closest('.p-tag');
    expect(await tag('LOGIN_SUCCESS')).toHaveClass('p-tag-success');
    expect(await tag('LOGOUT')).toHaveClass('p-tag-info');
    expect(await tag('LOGIN_FAILED')).toHaveClass('p-tag-danger');
    expect(screen.getByText('10.0.0.1')).toBeInTheDocument();
    expect(screen.getByText('06-05-2024 01:00:00 PM')).toBeInTheDocument();
    expect(requestedId).toBe('1');
  });

  it('says so when there is no history', async () => {
    const user = userEvent.setup();
    server.use(http.get('/api/v1/users/:id/login-history', () => HttpResponse.json([])));
    renderWithProviders(<UserTable users={[alice]} loading={false} onEdit={vi.fn()} />);

    await user.click(actionButton('alice', 'pi-history'));

    expect(await screen.findByText('No login history available.')).toBeInTheDocument();
  });

  it('also shows the empty state when the request fails', async () => {
    const user = userEvent.setup();
    server.use(
      http.get('/api/v1/users/:id/login-history', () =>
        HttpResponse.json({ detail: 'boom' }, { status: 500 }),
      ),
    );
    renderWithProviders(<UserTable users={[alice]} loading={false} onEdit={vi.fn()} />);

    await user.click(actionButton('alice', 'pi-history'));

    expect(await screen.findByText('No login history available.')).toBeInTheDocument();
  });
});

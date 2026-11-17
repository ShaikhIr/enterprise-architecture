import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { beforeEach, describe, expect, it } from 'vitest';

import type { Permission, Role } from '@features/rbac-admin/models/rbac-admin.types';
import { RolesPage } from '@features/rbac-admin/pages/RolesPage';

import { server } from '../../mocks/server';
import { renderWithProviders, screen, waitFor, within } from '../../test-utils';

type UserEventInstance = ReturnType<typeof userEvent.setup>;

const perm = (
  id: number,
  code: string,
  name: string,
  scope: Permission['scope'],
  resource: string,
  action: string,
): Permission => ({
  id,
  code,
  name,
  description: '',
  scope,
  resource,
  action,
  is_active: true,
  created_date: '2024-01-01T00:00:00Z',
});

const MENU_USERS = perm(101, 'menu.users', 'Users Menu', 'MENU', 'users', 'READ');
const API_LIST = perm(201, 'users.list', 'List Users', 'API', 'users', 'READ');
const API_CREATE = perm(202, 'users.create', 'Create Users', 'API', 'users', 'CREATE');
const API_REPORTS = perm(203, 'reports.export', 'Export Reports', 'API', 'reports', 'EXPORT');
const FIELD_SALARY = perm(301, 'users.salary.read', 'Salary', 'FIELD', 'users.salary', 'READ');

const ALL_PERMISSIONS = [MENU_USERS, API_LIST, API_CREATE, API_REPORTS, FIELD_SALARY];

const role = (overrides: Partial<Role>): Role => ({
  id: 1,
  code: 'ADMIN',
  name: 'Administrator',
  description: 'Full access',
  is_system: true,
  is_active: true,
  tenant_id: null,
  parent_role_id: null,
  permissions: [],
  created_date: '2024-01-01T00:00:00Z',
  modified_date: '2024-01-01T00:00:00Z',
  ...overrides,
});

const ADMIN = role({ id: 1, permissions: [MENU_USERS, API_LIST, API_CREATE] });
const SUPERVISOR = role({
  id: 2,
  code: 'SUPERVISOR',
  name: 'Supervisor',
  description: 'Team lead',
  is_system: false,
  is_active: false,
  permissions: [],
});

const serveRoles = (roles: Role[], permissions: Permission[] = ALL_PERMISSIONS) =>
  server.use(
    http.get('/api/v1/rbac/roles', () => HttpResponse.json({ roles, total: roles.length })),
    http.get('/api/v1/rbac/permissions', () => HttpResponse.json(permissions)),
  );

beforeEach(() => {
  serveRoles([ADMIN, SUPERVISOR]);
});

/** Open the Manage Permissions dialog for a role by its display name. */
const openPermissions = async (user: UserEventInstance, roleName: string) => {
  await user.click(await screen.findByLabelText(`Manage permissions for ${roleName}`));
  await screen.findByText(`Permissions — ${roleName}`);
};

/** Expand every collapsible node in the permission tree, however deep. */
const expandAll = async (user: UserEventInstance) => {
  for (let pass = 0; pass < 4; pass += 1) {
    const collapsed = Array.from(
      document.querySelectorAll<HTMLElement>('li.p-treenode:not(.p-treenode-leaf)'),
    ).filter((li) => !li.querySelector(':scope > ul'));
    if (collapsed.length === 0) return;
    for (const li of collapsed) {
      const toggler = li.querySelector<HTMLElement>(
        ':scope > .p-treenode-content > .p-tree-toggler',
      );
      if (toggler) await user.click(toggler);
    }
  }
};

const treeItem = (name: string) => screen.getByRole('treeitem', { name });

/** Record every grant/revoke body the page posts. */
const captureGrants = () => {
  const grants: { role_id: unknown; permission_id: unknown }[] = [];
  const revokes: { role_id: unknown; permission_id: unknown }[] = [];
  server.use(
    http.post('/api/v1/rbac/roles/grant-permission', async ({ request }) => {
      grants.push((await request.json()) as { role_id: unknown; permission_id: unknown });
      return HttpResponse.json({ status: 'granted' });
    }),
    http.post('/api/v1/rbac/roles/revoke-permission', async ({ request }) => {
      revokes.push((await request.json()) as { role_id: unknown; permission_id: unknown });
      return HttpResponse.json({ status: 'revoked' });
    }),
  );
  return { grants, revokes };
};

describe('RolesPage — role list', () => {
  it('lists each role with its code, name, description, type, status and permission count', async () => {
    renderWithProviders(<RolesPage />);

    const adminRow = (await screen.findByRole('cell', { name: 'ADMIN' })).closest('tr')!;
    expect(within(adminRow).getByText('Administrator')).toBeInTheDocument();
    expect(within(adminRow).getByText('Full access')).toBeInTheDocument();
    expect(within(adminRow).getByText('System').closest('.p-tag')).toHaveClass('p-tag-info');
    expect(within(adminRow).getByText('Active').closest('.p-tag')).toHaveClass('p-tag-success');
    expect(within(adminRow).getByText('3')).toBeInTheDocument();

    const supervisorRow = screen.getByRole('cell', { name: 'SUPERVISOR' }).closest('tr')!;
    expect(within(supervisorRow).getByText('Custom').closest('.p-tag')).toHaveClass(
      'p-tag-warning',
    );
    expect(within(supervisorRow).getByText('Inactive').closest('.p-tag')).toHaveClass(
      'p-tag-danger',
    );
    expect(within(supervisorRow).getByText('0')).toBeInTheDocument();
  });

  it('shows the heading and the toolbar actions', async () => {
    renderWithProviders(<RolesPage />);

    expect(screen.getByRole('heading', { name: 'Roles & Permissions' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Create new role' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Refresh roles list' })).toBeInTheDocument();
    await screen.findByRole('cell', { name: 'ADMIN' });
  });

  it('shows the busy overlay until the data arrives', async () => {
    server.use(
      http.get('/api/v1/rbac/roles', async () => {
        await new Promise((resolve) => setTimeout(resolve, 100));
        return HttpResponse.json({ roles: [ADMIN], total: 1 });
      }),
    );

    renderWithProviders(<RolesPage />);

    expect(document.querySelector('.p-datatable-loading-overlay')).toBeInTheDocument();
    await screen.findByRole('cell', { name: 'ADMIN' });
    expect(document.querySelector('.p-datatable-loading-overlay')).not.toBeInTheDocument();
  });

  it('shows the empty message when there are no roles', async () => {
    serveRoles([]);

    renderWithProviders(<RolesPage />);

    expect(await screen.findByText('No roles found')).toBeInTheDocument();
  });

  it('toasts the backend message and shows an empty table when loading fails', async () => {
    server.use(
      http.get('/api/v1/rbac/roles', () =>
        HttpResponse.json({ detail: 'RBAC unavailable' }, { status: 503 }),
      ),
    );

    renderWithProviders(<RolesPage />);

    expect(await screen.findByText('RBAC unavailable')).toBeInTheDocument();
    expect(screen.getByText('No roles found')).toBeInTheDocument();
  });

  it('reloads both roles and permissions when Refresh is clicked', async () => {
    const user = userEvent.setup();
    let roleCalls = 0;
    let permissionCalls = 0;
    server.use(
      http.get('/api/v1/rbac/roles', () => {
        roleCalls += 1;
        return HttpResponse.json({ roles: [ADMIN], total: 1 });
      }),
      http.get('/api/v1/rbac/permissions', () => {
        permissionCalls += 1;
        return HttpResponse.json(ALL_PERMISSIONS);
      }),
    );
    renderWithProviders(<RolesPage />);
    await screen.findByRole('cell', { name: 'ADMIN' });
    expect([roleCalls, permissionCalls]).toEqual([1, 1]);

    await user.click(screen.getByRole('button', { name: 'Refresh roles list' }));

    await waitFor(() => expect([roleCalls, permissionCalls]).toEqual([2, 2]));
  });
});

describe('RolesPage — create role', () => {
  const openCreate = async (user: UserEventInstance) => {
    await screen.findByRole('cell', { name: 'ADMIN' });
    await user.click(screen.getByRole('button', { name: 'Create new role' }));
    await screen.findByText('Create New Role');
  };

  it('keeps Create disabled until both a code and a name are entered', async () => {
    const user = userEvent.setup();
    renderWithProviders(<RolesPage />);
    await openCreate(user);

    const create = screen.getByRole('button', { name: 'Create' });
    expect(create).toBeDisabled();

    await user.type(screen.getByLabelText('Code'), 'auditor');
    expect(create).toBeDisabled();

    await user.type(screen.getByLabelText('Name'), 'Auditor');
    expect(create).toBeEnabled();
  });

  it('upper-cases the code as it is typed', async () => {
    const user = userEvent.setup();
    renderWithProviders(<RolesPage />);
    await openCreate(user);

    await user.type(screen.getByLabelText('Code'), 'auditor');

    expect(screen.getByLabelText('Code')).toHaveValue('AUDITOR');
  });

  it('creates a role end to end: posts the form, closes, toasts and reloads the list', async () => {
    const user = userEvent.setup();
    let posted: unknown = null;
    let roleCalls = 0;
    server.use(
      http.get('/api/v1/rbac/roles', () => {
        roleCalls += 1;
        return HttpResponse.json({ roles: [ADMIN], total: 1 });
      }),
      http.post('/api/v1/rbac/roles', async ({ request }) => {
        posted = await request.json();
        return HttpResponse.json(role({ id: 3, code: 'AUDITOR', name: 'Auditor' }), {
          status: 201,
        });
      }),
    );
    renderWithProviders(<RolesPage />);
    await openCreate(user);

    await user.type(screen.getByLabelText('Code'), 'auditor');
    await user.type(screen.getByLabelText('Name'), 'Auditor');
    await user.type(screen.getByLabelText('Description'), 'Read-only reviewer');
    await user.click(screen.getByRole('button', { name: 'Create' }));

    expect(await screen.findByText("Role 'AUDITOR' created")).toBeInTheDocument();
    expect(posted).toEqual({
      code: 'AUDITOR',
      name: 'Auditor',
      description: 'Read-only reviewer',
    });
    await waitFor(() => expect(screen.queryByText('Create New Role')).not.toBeInTheDocument());
    expect(roleCalls).toBe(2);
  });

  it('clears the form after a successful create so the next open starts empty', async () => {
    const user = userEvent.setup();
    server.use(
      http.post('/api/v1/rbac/roles', () =>
        HttpResponse.json(role({ id: 3, code: 'AUDITOR' }), { status: 201 }),
      ),
    );
    renderWithProviders(<RolesPage />);
    await openCreate(user);
    await user.type(screen.getByLabelText('Code'), 'auditor');
    await user.type(screen.getByLabelText('Name'), 'Auditor');
    await user.click(screen.getByRole('button', { name: 'Create' }));
    await screen.findByText("Role 'AUDITOR' created");

    await user.click(screen.getByRole('button', { name: 'Create new role' }));

    expect(await screen.findByLabelText('Code')).toHaveValue('');
    expect(screen.getByLabelText('Name')).toHaveValue('');
  });

  it('toasts the backend message and keeps the dialog open when the code already exists', async () => {
    const user = userEvent.setup();
    server.use(
      http.post('/api/v1/rbac/roles', () =>
        HttpResponse.json({ detail: "Role 'ADMIN' already exists" }, { status: 409 }),
      ),
    );
    renderWithProviders(<RolesPage />);
    await openCreate(user);

    await user.type(screen.getByLabelText('Code'), 'admin');
    await user.type(screen.getByLabelText('Name'), 'Another');
    await user.click(screen.getByRole('button', { name: 'Create' }));

    expect(await screen.findByText("Role 'ADMIN' already exists")).toBeInTheDocument();
    expect(screen.getByText('Create New Role')).toBeInTheDocument();
    expect(screen.getByLabelText('Code')).toHaveValue('ADMIN');
  });

  it('closes on Cancel without posting', async () => {
    const user = userEvent.setup();
    let posted = false;
    server.use(
      http.post('/api/v1/rbac/roles', () => {
        posted = true;
        return HttpResponse.json(role({}));
      }),
    );
    renderWithProviders(<RolesPage />);
    await openCreate(user);

    await user.click(screen.getByRole('button', { name: 'Cancel' }));

    await waitFor(() => expect(screen.queryByText('Create New Role')).not.toBeInTheDocument());
    expect(posted).toBe(false);
  });
});

describe('RolesPage — permission tree', () => {
  it('groups permissions by scope, with a folder per resource that has several permissions', async () => {
    const user = userEvent.setup();
    renderWithProviders(<RolesPage />);
    await openPermissions(user, 'Administrator');

    expect(treeItem('📋 Menu Access')).toBeInTheDocument();
    expect(treeItem('🔌 API Access')).toBeInTheDocument();
    expect(treeItem('🔒 Field-Level Access')).toBeInTheDocument();

    await expandAll(user);

    // `users` has two API permissions, so it gets a folder; its leaves carry the action.
    expect(treeItem('Users')).toBeInTheDocument();
    expect(treeItem('List Users (READ)')).toBeInTheDocument();
    expect(treeItem('Create Users (CREATE)')).toBeInTheDocument();
    // `reports` has one API permission, so it sits directly under the scope, without the action.
    expect(treeItem('Export Reports')).toBeInTheDocument();
    expect(screen.queryByRole('treeitem', { name: 'Reports' })).not.toBeInTheDocument();
    // A dotted resource groups under its first segment (users.salary → users).
    expect(treeItem('Salary')).toBeInTheDocument();
  });

  it('omits a scope that has no permissions', async () => {
    serveRoles([ADMIN], [MENU_USERS, API_LIST]);
    const user = userEvent.setup();
    renderWithProviders(<RolesPage />);
    await openPermissions(user, 'Administrator');

    expect(treeItem('📋 Menu Access')).toBeInTheDocument();
    expect(treeItem('🔌 API Access')).toBeInTheDocument();
    expect(
      screen.queryByRole('treeitem', { name: '🔒 Field-Level Access' }),
    ).not.toBeInTheDocument();
  });

  it('pre-checks the permissions the role already has and counts them', async () => {
    const user = userEvent.setup();
    renderWithProviders(<RolesPage />);
    await openPermissions(user, 'Administrator');
    await expandAll(user);

    expect(treeItem('Users Menu')).toHaveAttribute('aria-checked', 'true');
    expect(treeItem('List Users (READ)')).toHaveAttribute('aria-checked', 'true');
    expect(treeItem('Create Users (CREATE)')).toHaveAttribute('aria-checked', 'true');
    expect(treeItem('Export Reports')).toHaveAttribute('aria-checked', 'false');
    expect(treeItem('Salary')).toHaveAttribute('aria-checked', 'false');
    // A fully-checked resource folder is checked itself; a partly-checked scope is not.
    expect(treeItem('Users')).toHaveAttribute('aria-checked', 'true');
    expect(treeItem('🔌 API Access')).toHaveAttribute('aria-checked', 'false');
    expect(screen.getByText('3 permissions selected')).toBeInTheDocument();
  });

  it('starts empty for a role with no permissions, and uses the singular for exactly one', async () => {
    const user = userEvent.setup();
    renderWithProviders(<RolesPage />);
    await openPermissions(user, 'Supervisor');
    await expandAll(user);

    expect(screen.getByText('0 permissions selected')).toBeInTheDocument();

    await user.click(screen.getByText('Salary'));

    expect(screen.getByText('1 permission selected')).toBeInTheDocument();
  });

  it('does not carry one role’s selection over to the next role opened', async () => {
    const user = userEvent.setup();
    renderWithProviders(<RolesPage />);
    await openPermissions(user, 'Administrator');
    expect(screen.getByText('3 permissions selected')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Cancel' }));
    await waitFor(() =>
      expect(screen.queryByText('Permissions — Administrator')).not.toBeInTheDocument(),
    );

    await openPermissions(user, 'Supervisor');

    expect(screen.getByText('0 permissions selected')).toBeInTheDocument();
  });

  it('checks every permission under a scope when the scope node is checked', async () => {
    const user = userEvent.setup();
    renderWithProviders(<RolesPage />);
    await openPermissions(user, 'Supervisor');

    await user.click(screen.getByText('🔌 API Access'));

    // List, Create (under the Users folder) and Export Reports.
    expect(screen.getByText('3 permissions selected')).toBeInTheDocument();
    await expandAll(user);
    expect(treeItem('Export Reports')).toHaveAttribute('aria-checked', 'true');
    expect(treeItem('Users')).toHaveAttribute('aria-checked', 'true');
  });

  it('narrows the tree with the search box', async () => {
    const user = userEvent.setup();
    renderWithProviders(<RolesPage />);
    await openPermissions(user, 'Administrator');

    await user.type(screen.getByPlaceholderText('Search permissions...'), 'salary');

    await waitFor(() =>
      expect(screen.queryByRole('treeitem', { name: '📋 Menu Access' })).not.toBeInTheDocument(),
    );
    expect(screen.getByText('Salary')).toBeInTheDocument();
  });
});

describe('RolesPage — saving permissions', () => {
  it('closes without any request when nothing changed', async () => {
    const user = userEvent.setup();
    const { grants, revokes } = captureGrants();
    renderWithProviders(<RolesPage />);
    await openPermissions(user, 'Administrator');

    await user.click(screen.getByRole('button', { name: 'Save Changes' }));

    await waitFor(() =>
      expect(screen.queryByText('Permissions — Administrator')).not.toBeInTheDocument(),
    );
    expect(grants).toEqual([]);
    expect(revokes).toEqual([]);
  });

  it('grants newly checked and revokes unchecked permissions, with numeric ids', async () => {
    const user = userEvent.setup();
    const { grants, revokes } = captureGrants();
    let roleCalls = 0;
    server.use(
      http.get('/api/v1/rbac/roles', () => {
        roleCalls += 1;
        return HttpResponse.json({ roles: [ADMIN, SUPERVISOR], total: 2 });
      }),
    );
    renderWithProviders(<RolesPage />);
    await openPermissions(user, 'Administrator');
    await expandAll(user);

    await user.click(screen.getByText('List Users (READ)')); // revoke 201
    await user.click(screen.getByText('Salary')); // grant 301
    await user.click(screen.getByText('Export Reports')); // grant 203
    await user.click(screen.getByRole('button', { name: 'Save Changes' }));

    expect(
      await screen.findByText("Permissions updated for 'ADMIN' (+2 / -1)"),
    ).toBeInTheDocument();
    // The tree keys are strings; the API boundary converts them back to numbers.
    expect(grants).toEqual(
      expect.arrayContaining([
        { role_id: 1, permission_id: 301 },
        { role_id: 1, permission_id: 203 },
      ]),
    );
    expect(grants).toHaveLength(2);
    expect(revokes).toEqual([{ role_id: 1, permission_id: 201 }]);
    await waitFor(() =>
      expect(screen.queryByText('Permissions — Administrator')).not.toBeInTheDocument(),
    );
    expect(roleCalls).toBe(2);
  });

  it('only grants when nothing was unchecked (no revoke calls)', async () => {
    const user = userEvent.setup();
    const { grants, revokes } = captureGrants();
    renderWithProviders(<RolesPage />);
    await openPermissions(user, 'Supervisor');

    await user.click(screen.getByText('🔒 Field-Level Access'));
    await user.click(screen.getByRole('button', { name: 'Save Changes' }));

    expect(
      await screen.findByText("Permissions updated for 'SUPERVISOR' (+1 / -0)"),
    ).toBeInTheDocument();
    expect(grants).toEqual([{ role_id: 2, permission_id: 301 }]);
    expect(revokes).toEqual([]);
  });

  it('only revokes when the role is cleared (no grant calls)', async () => {
    const user = userEvent.setup();
    const { grants, revokes } = captureGrants();
    renderWithProviders(<RolesPage />);
    await openPermissions(user, 'Administrator');
    await expandAll(user);

    await user.click(screen.getByText('Users Menu'));
    await user.click(screen.getByText('List Users (READ)'));
    await user.click(screen.getByText('Create Users (CREATE)'));
    await user.click(screen.getByRole('button', { name: 'Save Changes' }));

    expect(
      await screen.findByText("Permissions updated for 'ADMIN' (+0 / -3)"),
    ).toBeInTheDocument();
    expect(grants).toEqual([]);
    expect(revokes.map((r) => r.permission_id).sort()).toEqual([101, 201, 202]);
  });

  it('toasts the backend message and keeps the dialog open when a grant fails', async () => {
    const user = userEvent.setup();
    server.use(
      http.post('/api/v1/rbac/roles/grant-permission', () =>
        HttpResponse.json({ detail: 'Permission is inactive' }, { status: 409 }),
      ),
    );
    renderWithProviders(<RolesPage />);
    await openPermissions(user, 'Supervisor');
    await user.click(screen.getByText('🔒 Field-Level Access'));

    await user.click(screen.getByRole('button', { name: 'Save Changes' }));

    expect(await screen.findByText('Permission is inactive')).toBeInTheDocument();
    expect(screen.getByText('Permissions — Supervisor')).toBeInTheDocument();
  });

  it('discards the pending selection on Cancel without any request', async () => {
    const user = userEvent.setup();
    const { grants, revokes } = captureGrants();
    renderWithProviders(<RolesPage />);
    await openPermissions(user, 'Supervisor');
    await user.click(screen.getByText('🔒 Field-Level Access'));

    await user.click(screen.getByRole('button', { name: 'Cancel' }));

    await waitFor(() =>
      expect(screen.queryByText('Permissions — Supervisor')).not.toBeInTheDocument(),
    );
    expect(grants).toEqual([]);
    expect(revokes).toEqual([]);
  });
});

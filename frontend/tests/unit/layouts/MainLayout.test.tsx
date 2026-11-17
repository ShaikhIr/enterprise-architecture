import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it } from 'vitest';

import { MainLayout } from '@app/layouts/MainLayout';

import { server } from '../../mocks/server';
import type { RootState, TestPreloadedState } from '../../test-utils';
import { renderWithProviders, screen, waitFor, within } from '../../test-utils';

const currentUser = { id: 7, username: 'jdoe', is_active: true };

const authState = (user: RootState['auth']['user'] = currentUser): RootState['auth'] => ({
  user,
  isAuthenticated: !!user,
  isLoading: false,
  isBootstrapping: false,
  error: null,
});

const rbacState = (overrides: Partial<RootState['rbac']> = {}): RootState['rbac'] => ({
  menuKeys: [],
  menuPermissions: [],
  apiCodes: [],
  apiResourceActions: {},
  fieldPermissions: {},
  fieldPermissionStatus: {},
  isLoaded: true,
  isApiLoaded: true,
  isLoading: false,
  isApiLoading: false,
  error: null,
  ...overrides,
});

const stateWith = (
  menuKeys: string[],
  rbac: Partial<RootState['rbac']> = {},
  user: RootState['auth']['user'] = currentUser,
): TestPreloadedState => ({
  auth: authState(user),
  rbac: rbacState({ menuKeys, ...rbac }),
});

const renderLayout = (preloadedState: TestPreloadedState, path = '/dashboard') =>
  renderWithProviders(
    <Routes>
      <Route element={<MainLayout />}>
        <Route path="/dashboard" element={<div>Dashboard page</div>} />
        <Route path="/users" element={<div>Users page</div>} />
        <Route path="/roles" element={<div>Roles page</div>} />
        <Route path="/profile" element={<div>Profile page</div>} />
        <Route path="/somewhere-else" element={<div>Unlisted page</div>} />
      </Route>
      <Route path="/login" element={<div>Login page</div>} />
    </Routes>,
    { preloadedState, initialEntries: [path] },
  );

const sidebar = () => screen.getByLabelText('Sidebar navigation');
const navButton = (label: string) => within(sidebar()).queryByRole('button', { name: label });

afterEach(() => {
  sessionStorage.clear();
});

describe('MainLayout — permission-filtered sidebar', () => {
  it('shows only the items whose menu key the user holds', () => {
    renderLayout(stateWith(['dashboard', 'roles']));

    expect(navButton('Dashboard')).toBeInTheDocument();
    expect(navButton('Roles & Permissions')).toBeInTheDocument();
    expect(navButton('Users')).not.toBeInTheDocument();
    expect(navButton('Audit Logs')).not.toBeInTheDocument();
    expect(navButton('Employee AD')).not.toBeInTheDocument();
    expect(navButton('Workflows')).not.toBeInTheDocument();
  });

  it('shows every item for a user holding every key', () => {
    renderLayout(
      stateWith([
        'dashboard',
        'users',
        'roles',
        'audit_logs',
        'masters',
        'masters.countries',
        'masters.states',
        'masters.categories_of_law',
        'masters.legislations',
        'masters.rules',
        'masters.task_types',
        'workflows',
        'services',
      ]),
    );

    const labels = within(sidebar())
      .getAllByRole('button')
      .map((b) => b.getAttribute('aria-label'))
      .filter((label) => label !== 'Toggle sidebar');
    expect(labels).toEqual([
      'Dashboard',
      'Users',
      'Roles & Permissions',
      'Audit Logs',
      'Countries',
      'States',
      'Categories of Law',
      'Legislations',
      'Rules',
      'Task Types',
      'Workflows',
      'Approval Matrix',
      'Employee AD',
    ]);
  });

  it('shows no navigation at all when the user holds no menu keys', () => {
    renderLayout(stateWith([]));

    expect(within(sidebar()).getAllByRole('button')).toHaveLength(1); // just the toggle
    expect(screen.queryByText('Management')).not.toBeInTheDocument();
  });

  it('requires the section key AND the master’s own key for a master screen', () => {
    renderLayout(stateWith(['masters', 'masters.countries', 'masters.rules']));

    expect(navButton('Countries')).toBeInTheDocument();
    expect(navButton('Rules')).toBeInTheDocument();
    expect(navButton('States')).not.toBeInTheDocument();
    expect(navButton('Task Types')).not.toBeInTheDocument();
  });

  it('hides a master whose own key is held but whose section key is not', () => {
    renderLayout(stateWith(['masters.countries']));

    expect(navButton('Countries')).not.toBeInTheDocument();
  });

  it('hides every master when only the section key is held', () => {
    renderLayout(stateWith(['masters']));

    expect(navButton('Countries')).not.toBeInTheDocument();
    expect(screen.queryByText('Masters')).not.toBeInTheDocument();
  });

  it('shows both workflow screens under the single "workflows" key', () => {
    renderLayout(stateWith(['workflows']));

    expect(navButton('Workflows')).toBeInTheDocument();
    expect(navButton('Approval Matrix')).toBeInTheDocument();
  });

  it('groups items under section headers, and omits a header with no visible items', () => {
    renderLayout(stateWith(['dashboard', 'users', 'services']));

    expect(within(sidebar()).getByText('Main')).toBeInTheDocument();
    expect(within(sidebar()).getByText('Management')).toBeInTheDocument();
    expect(within(sidebar()).getByText('Services')).toBeInTheDocument();
    expect(within(sidebar()).queryByText('Masters')).not.toBeInTheDocument();
    expect(within(sidebar()).queryByText('Workflow')).not.toBeInTheDocument();
  });

  it('shows nothing until menu permissions have loaded, then reveals the permitted items', async () => {
    server.use(
      http.get('/api/v1/rbac/my-permissions/menu', () =>
        HttpResponse.json({ menu_keys: ['dashboard', 'users'], permissions: [] }),
      ),
    );
    renderLayout(stateWith([], { isLoaded: false }));

    expect(navButton('Dashboard')).not.toBeInTheDocument();

    expect(await within(sidebar()).findByRole('button', { name: 'Dashboard' })).toBeInTheDocument();
    expect(navButton('Users')).toBeInTheDocument();
    expect(navButton('Roles & Permissions')).not.toBeInTheDocument();
  });

  it('keeps the sidebar empty when loading the menu permissions fails', async () => {
    let calls = 0;
    server.use(
      http.get('/api/v1/rbac/my-permissions/menu', () => {
        calls += 1;
        // Stop answering after a few attempts so a retry loop cannot spin the test forever.
        return calls > 5
          ? new Promise<Response>(() => {})
          : HttpResponse.json({ detail: 'nope' }, { status: 500 });
      }),
    );
    renderLayout(stateWith([], { isLoaded: false }));

    await waitFor(() => expect(calls).toBeGreaterThan(0));
    expect(within(sidebar()).getAllByRole('button')).toHaveLength(1);
  });

  // SUSPECTED SRC BUG: `useMenuPermissions` re-dispatches fetchMenuPermissions whenever
  // `!isLoaded && !isLoading`. A rejected fetch leaves exactly that state (isLoaded stays
  // false, isLoading goes back to false), so the effect fires again and the layout retries
  // the failing endpoint in a tight loop instead of once.
  it.fails(
    'asks for the menu permissions once, not repeatedly, when the request fails',
    async () => {
      let calls = 0;
      server.use(
        http.get('/api/v1/rbac/my-permissions/menu', () => {
          calls += 1;
          return calls > 20
            ? new Promise<Response>(() => {})
            : HttpResponse.json({ detail: 'nope' }, { status: 500 });
        }),
      );
      const { store } = renderLayout(stateWith([], { isLoaded: false }));
      await waitFor(() => expect(store.getState().rbac.error).toBe('nope'));

      await new Promise((resolve) => setTimeout(resolve, 300));

      expect(calls).toBe(1);
    },
  );
});

describe('MainLayout — API permissions', () => {
  it('loads the API permissions once, up front, when they are not loaded yet', async () => {
    let calls = 0;
    server.use(
      http.get('/api/v1/rbac/my-permissions/api', () => {
        calls += 1;
        return HttpResponse.json({
          codes: ['countries.create'],
          resource_actions: { countries: ['CREATE'] },
          permissions: [],
        });
      }),
    );
    const { store } = renderLayout(stateWith(['dashboard'], { isApiLoaded: false }));

    await waitFor(() => expect(store.getState().rbac.isApiLoaded).toBe(true));
    expect(calls).toBe(1);
    expect(store.getState().rbac.apiResourceActions).toEqual({ countries: ['CREATE'] });
  });

  it('does not request them again when they are already loaded', async () => {
    let calls = 0;
    server.use(
      http.get('/api/v1/rbac/my-permissions/api', () => {
        calls += 1;
        return HttpResponse.json({ codes: [], resource_actions: {}, permissions: [] });
      }),
    );
    renderLayout(stateWith(['dashboard'], { isApiLoaded: true }));
    await screen.findByText('Dashboard page');

    expect(calls).toBe(0);
  });
});

describe('MainLayout — navigation', () => {
  it('renders the matched child route in the content area', () => {
    renderLayout(stateWith(['dashboard']), '/dashboard');

    expect(screen.getByText('Dashboard page')).toBeInTheDocument();
  });

  it('marks the current route’s item as the active page', () => {
    renderLayout(stateWith(['dashboard', 'users']), '/users');

    expect(navButton('Users')).toHaveAttribute('aria-current', 'page');
    expect(navButton('Dashboard')).not.toHaveAttribute('aria-current');
  });

  it('navigates to an item’s path when it is clicked', async () => {
    const user = userEvent.setup();
    renderLayout(stateWith(['dashboard', 'roles']), '/dashboard');

    await user.click(navButton('Roles & Permissions')!);

    expect(await screen.findByText('Roles page')).toBeInTheDocument();
    expect(navButton('Roles & Permissions')).toHaveAttribute('aria-current', 'page');
    expect(navButton('Dashboard')).not.toHaveAttribute('aria-current');
  });

  it('shows the current page label in the breadcrumb', () => {
    renderLayout(stateWith(['roles']), '/roles');

    expect(within(screen.getByRole('banner')).getByText('Roles & Permissions')).toBeInTheDocument();
  });

  it('shows no page label for a route that is not a nav item', () => {
    renderLayout(stateWith(['dashboard']), '/somewhere-else');

    expect(screen.getByText('Unlisted page')).toBeInTheDocument();
    expect(within(screen.getByRole('banner')).queryByText('/')).not.toBeInTheDocument();
  });

  it('shows the breadcrumb label even when the user lacks the item’s menu key', () => {
    // The label comes from the full nav list, not the permission-filtered one.
    renderLayout(stateWith([]), '/users');

    expect(within(screen.getByRole('banner')).getByText('Users')).toBeInTheDocument();
  });
});

describe('MainLayout — sidebar collapse', () => {
  it('starts expanded at 220px with the brand, section headers and item labels', () => {
    renderLayout(stateWith(['dashboard']));

    expect(sidebar()).toHaveStyle({ width: '220px' });
    expect(within(sidebar()).getByText('EMCURE')).toBeInTheDocument();
    expect(within(sidebar()).getByText('Main')).toBeInTheDocument();
    expect(within(navButton('Dashboard')!).getByText('Dashboard')).toBeInTheDocument();
  });

  it('collapses to 60px, dropping the brand, headers and labels but keeping the buttons', async () => {
    const user = userEvent.setup();
    renderLayout(stateWith(['dashboard', 'users']));

    await user.click(screen.getByRole('button', { name: 'Toggle sidebar' }));

    expect(sidebar()).toHaveStyle({ width: '60px' });
    expect(within(sidebar()).queryByText('EMCURE')).not.toBeInTheDocument();
    expect(within(sidebar()).queryByText('Main')).not.toBeInTheDocument();
    expect(within(sidebar()).queryByText('Management')).not.toBeInTheDocument();
    // The icon-only button is still reachable by name, and carries its tooltip text.
    expect(navButton('Dashboard')).toBeInTheDocument();
    expect(within(navButton('Dashboard')!).queryByText('Dashboard')).not.toBeInTheDocument();
    expect(navButton('Dashboard')).toHaveAttribute('data-pr-tooltip', 'Dashboard');
  });

  it('expands again on a second click', async () => {
    const user = userEvent.setup();
    renderLayout(stateWith(['dashboard']));

    await user.click(screen.getByRole('button', { name: 'Toggle sidebar' }));
    await user.click(screen.getByRole('button', { name: 'Toggle sidebar' }));

    expect(sidebar()).toHaveStyle({ width: '220px' });
    expect(within(sidebar()).getByText('EMCURE')).toBeInTheDocument();
    expect(navButton('Dashboard')).not.toHaveAttribute('data-pr-tooltip');
  });

  it('still navigates from a collapsed sidebar', async () => {
    const user = userEvent.setup();
    renderLayout(stateWith(['dashboard', 'users']));

    await user.click(screen.getByRole('button', { name: 'Toggle sidebar' }));
    await user.click(navButton('Users')!);

    expect(await screen.findByText('Users page')).toBeInTheDocument();
  });
});

describe('MainLayout — top bar and user menu', () => {
  it('shows the signed-in username and its initial', () => {
    renderLayout(stateWith(['dashboard']));

    const userMenuButton = screen.getByRole('button', { name: 'User menu' });
    expect(within(userMenuButton).getByText('jdoe')).toBeInTheDocument();
    expect(within(userMenuButton).getByText('J')).toBeInTheDocument();
  });

  it('falls back to a "U" avatar when no user is loaded', () => {
    renderLayout(stateWith(['dashboard'], {}, null));

    expect(
      within(screen.getByRole('button', { name: 'User menu' })).getByText('U'),
    ).toBeInTheDocument();
  });

  it('has a notifications button', () => {
    renderLayout(stateWith(['dashboard']));

    expect(screen.getByRole('button', { name: 'Notifications' })).toBeInTheDocument();
  });

  it('opens a menu with the username, Profile and Logout', async () => {
    const user = userEvent.setup();
    renderLayout(stateWith(['dashboard']));

    await user.click(screen.getByRole('button', { name: 'User menu' }));

    const menu = await screen.findByRole('menu');
    expect(within(menu).getByText('jdoe')).toBeInTheDocument();
    expect(within(menu).getByRole('menuitem', { name: 'Profile' })).toBeInTheDocument();
    expect(within(menu).getByRole('menuitem', { name: 'Logout' })).toBeInTheDocument();
  });

  it('goes to /profile from the Profile item', async () => {
    const user = userEvent.setup();
    renderLayout(stateWith(['dashboard']));

    await user.click(screen.getByRole('button', { name: 'User menu' }));
    await user.click(await screen.findByText('Profile'));

    expect(await screen.findByText('Profile page')).toBeInTheDocument();
  });

  it('logs out end to end: calls the server, clears auth and RBAC state, lands on /login', async () => {
    const user = userEvent.setup();
    let loggedOut = false;
    server.use(
      http.post('/api/v1/auth/logout', () => {
        loggedOut = true;
        return HttpResponse.json({ detail: 'Logged out' });
      }),
    );
    const { store } = renderLayout(stateWith(['dashboard']));

    await user.click(screen.getByRole('button', { name: 'User menu' }));
    await user.click(await screen.findByText('Logout'));

    expect(await screen.findByText('Login page')).toBeInTheDocument();
    expect(loggedOut).toBe(true);
    expect(store.getState().auth.user).toBeNull();
    expect(store.getState().auth.isAuthenticated).toBe(false);
    // The preloaded 'dashboard' key is gone. (Not asserting `isLoaded`: while the layout is
    // still mounted for a moment, its own hook refetches the now-cleared permissions.)
    expect(store.getState().rbac.menuKeys).toEqual([]);
  });

  it('still logs out locally when the server call fails', async () => {
    const user = userEvent.setup();
    server.use(
      http.post('/api/v1/auth/logout', () => HttpResponse.json({ detail: 'x' }, { status: 500 })),
    );
    const { store } = renderLayout(stateWith(['dashboard']));

    await user.click(screen.getByRole('button', { name: 'User menu' }));
    await user.click(await screen.findByText('Logout'));

    expect(await screen.findByText('Login page')).toBeInTheDocument();
    expect(store.getState().auth.isAuthenticated).toBe(false);
  });
});

import { Route, Routes } from 'react-router-dom';
import { describe, expect, it } from 'vitest';

import { PublicRoute } from '@app/router/PublicRoute';

import type { RootState, TestPreloadedState } from '../../test-utils';
import { renderWithProviders, screen } from '../../test-utils';

const preloaded = (auth: Partial<RootState['auth']>): TestPreloadedState => ({
  auth: {
    user: null,
    isAuthenticated: false,
    isLoading: false,
    isBootstrapping: false,
    error: null,
    ...auth,
  },
  rbac: {
    menuKeys: [],
    menuPermissions: [],
    apiCodes: [],
    apiResourceActions: {},
    fieldPermissions: {},
    fieldPermissionStatus: {},
    isLoaded: false,
    isApiLoaded: false,
    isLoading: false,
    isApiLoading: false,
    error: null,
  },
});

const renderPublic = (preloadedState: TestPreloadedState) =>
  renderWithProviders(
    <Routes>
      <Route
        path="/login"
        element={
          <PublicRoute>
            <span>Login form</span>
          </PublicRoute>
        }
      />
      <Route path="/dashboard" element={<span>Dashboard</span>} />
    </Routes>,
    { preloadedState, initialEntries: ['/login'] },
  );

describe('PublicRoute', () => {
  it('renders nothing while the session is still bootstrapping', () => {
    const { container } = renderPublic(preloaded({ isBootstrapping: true }));

    expect(container).toBeEmptyDOMElement();
    expect(screen.queryByText('Login form')).not.toBeInTheDocument();
  });

  it('redirects an authenticated caller away from /login to /dashboard', () => {
    renderPublic(preloaded({ isAuthenticated: true }));

    expect(screen.getByText('Dashboard')).toBeInTheDocument();
    expect(screen.queryByText('Login form')).not.toBeInTheDocument();
  });

  it('renders the login form for an unauthenticated caller', () => {
    renderPublic(preloaded({ isAuthenticated: false }));

    expect(screen.getByText('Login form')).toBeInTheDocument();
  });
});

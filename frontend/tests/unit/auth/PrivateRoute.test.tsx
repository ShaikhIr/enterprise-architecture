import { Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it } from 'vitest';

import { PrivateRoute } from '@app/router/PrivateRoute';

import type { RootState, TestPreloadedState } from '../../test-utils';
import { renderWithProviders, screen } from '../../test-utils';

const preloaded = (
  auth: Partial<RootState['auth']>,
  rbac: Partial<RootState['rbac']> = {},
): TestPreloadedState => ({
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
    ...rbac,
  },
});

const renderProtected = (preloadedState: TestPreloadedState, menuKey?: string | string[]) =>
  renderWithProviders(
    <Routes>
      <Route
        path="/protected"
        element={
          <PrivateRoute menuKey={menuKey}>
            <span>Protected content</span>
          </PrivateRoute>
        }
      />
      <Route path="/login" element={<span>Login page</span>} />
      <Route path="/unauthorized" element={<span>Unauthorized page</span>} />
    </Routes>,
    { preloadedState, initialEntries: ['/protected'] },
  );

describe('PrivateRoute', () => {
  afterEach(() => {
    sessionStorage.clear();
  });

  it('renders nothing while the session is still bootstrapping', () => {
    const { container } = renderProtected(preloaded({ isBootstrapping: true }));

    expect(container).toBeEmptyDOMElement();
    expect(screen.queryByText('Login page')).not.toBeInTheDocument();
  });

  it('redirects to /login when not authenticated, saving the intended path', () => {
    renderProtected(preloaded({ isAuthenticated: false }));

    expect(screen.getByText('Login page')).toBeInTheDocument();
    expect(sessionStorage.getItem('redirectAfterLogin')).toBe('/protected');
  });

  it('renders children when authenticated and no menu key is required', () => {
    renderProtected(preloaded({ isAuthenticated: true }));

    expect(screen.getByText('Protected content')).toBeInTheDocument();
  });

  it('renders nothing while authenticated but RBAC permissions have not loaded yet', () => {
    const { container } = renderProtected(
      preloaded({ isAuthenticated: true }, { isLoaded: false }),
      'masters',
    );

    expect(container).toBeEmptyDOMElement();
  });

  it('renders children when the required single menu key is present', () => {
    renderProtected(
      preloaded({ isAuthenticated: true }, { menuKeys: ['masters'], isLoaded: true }),
      'masters',
    );

    expect(screen.getByText('Protected content')).toBeInTheDocument();
  });

  it('redirects to /unauthorized when the required single menu key is absent', () => {
    renderProtected(
      preloaded({ isAuthenticated: true }, { menuKeys: ['dashboard'], isLoaded: true }),
      'masters',
    );

    expect(screen.getByText('Unauthorized page')).toBeInTheDocument();
  });

  it('requires every key in an array (AND), rendering children only when all are present', () => {
    renderProtected(
      preloaded(
        { isAuthenticated: true },
        { menuKeys: ['masters', 'masters.countries'], isLoaded: true },
      ),
      ['masters', 'masters.countries'],
    );

    expect(screen.getByText('Protected content')).toBeInTheDocument();
  });

  it('redirects to /unauthorized when only some of the required array keys are present', () => {
    renderProtected(
      preloaded({ isAuthenticated: true }, { menuKeys: ['masters'], isLoaded: true }),
      ['masters', 'masters.countries'],
    );

    expect(screen.getByText('Unauthorized page')).toBeInTheDocument();
  });
});

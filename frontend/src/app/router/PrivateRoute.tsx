/**
 * Protected route wrapper.
 * Redirects to /login if not authenticated.
 * Uses RBAC menu permissions for access control.
 */

import { Navigate, useLocation } from 'react-router-dom';

import { useAppSelector } from '@app/store';

interface PrivateRouteProps {
  children: React.ReactNode;
  /**
   * Menu key(s) required to reach the route. An array means *all* of them are
   * required, which is how a nested area is gated: the masters screens ask for
   * both the section key (`masters`) and their own (`masters.countries`), so
   * revoking the section hides every screen under it while revoking one child
   * hides only that screen.
   */
  menuKey?: string | string[];
}

export const PrivateRoute = ({ children, menuKey }: PrivateRouteProps) => {
  const { isAuthenticated, isBootstrapping } = useAppSelector((state) => state.auth);
  const { menuKeys, isLoaded: rbacLoaded } = useAppSelector((state) => state.rbac);
  const location = useLocation();

  // While the session is being restored from the refresh cookie, don't decide
  // yet — avoids a premature bounce to /login on reload.
  if (isBootstrapping) {
    return null;
  }

  if (!isAuthenticated) {
    // Save intended destination
    sessionStorage.setItem('redirectAfterLogin', location.pathname);
    return <Navigate to="/login" replace />;
  }

  // If menu key(s) are specified, check RBAC permissions
  if (menuKey) {
    if (!rbacLoaded) {
      // Still loading permissions — show nothing briefly
      return null;
    }
    const required = Array.isArray(menuKey) ? menuKey : [menuKey];
    if (!required.every((key) => menuKeys.includes(key))) {
      return <Navigate to="/unauthorized" replace />;
    }
  }

  return <>{children}</>;
};

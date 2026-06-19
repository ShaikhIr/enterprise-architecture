/**
 * Protected route wrapper.
 * Redirects to /login if not authenticated.
 * Uses RBAC menu permissions for access control (with ADMIN fallback).
 */

import { Navigate, useLocation } from 'react-router-dom';
import { useAppSelector } from '@app/store';

interface PrivateRouteProps {
  children: React.ReactNode;
  requiredRole?: string;
  menuKey?: string;
}

export const PrivateRoute = ({ children, requiredRole, menuKey }: PrivateRouteProps) => {
  const { isAuthenticated, user } = useAppSelector((state) => state.auth);
  const { menuKeys, isLoaded: rbacLoaded } = useAppSelector((state) => state.rbac);
  const location = useLocation();

  if (!isAuthenticated) {
    // Save intended destination
    sessionStorage.setItem('redirectAfterLogin', location.pathname);
    return <Navigate to="/login" replace />;
  }

  // ADMIN always has full access (fallback for legacy role field)
  if (user?.role === 'ADMIN') {
    return <>{children}</>;
  }

  // If a menuKey is specified, check RBAC permissions
  if (menuKey) {
    if (!rbacLoaded) {
      // Still loading permissions — show nothing briefly
      return null;
    }
    if (!menuKeys.includes(menuKey)) {
      return <Navigate to="/unauthorized" replace />;
    }
    return <>{children}</>;
  }

  // Legacy: if requiredRole is specified but no menuKey, use old role check
  if (requiredRole && user?.role !== requiredRole) {
    return <Navigate to="/unauthorized" replace />;
  }

  return <>{children}</>;
};

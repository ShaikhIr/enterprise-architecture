/**
 * Guest-only route wrapper.
 *
 * Keeps an authenticated caller off /login. Without this, signing in and pressing
 * Back — or typing the URL, or following a stale bookmark — puts the login form in
 * front of someone who already has a session, which reads as being logged out.
 *
 * The counterpart to PrivateRoute, and it waits on the same bootstrap flag: while
 * the session is still being restored from the refresh cookie, `isAuthenticated` is
 * not yet meaningful, so deciding early would flash the form for anyone reloading.
 */

import { Navigate } from 'react-router-dom';

import { useAppSelector } from '@app/store';

interface PublicRouteProps {
  children: React.ReactNode;
}

export const PublicRoute = ({ children }: PublicRouteProps) => {
  const { isAuthenticated, isBootstrapping } = useAppSelector((state) => state.auth);

  if (isBootstrapping) {
    return null;
  }

  if (isAuthenticated) {
    // `replace` so a bounced visit does not add another entry to unwind.
    return <Navigate to="/dashboard" replace />;
  }

  return <>{children}</>;
};

/**
 * AuthBootstrap
 *
 * Runs inside the router and owns the browser-session lifecycle:
 *   1. On mount, silently restores the session from the HttpOnly refresh cookie
 *      (via bootstrapSession). Renders a splash until that resolves, which
 *      prevents protected routes from bouncing to /login on reload.
 *   2. Registers a router-aware "session expired" handler for the API client, so
 *      a failed refresh navigates to /login WITHOUT a full page reload.
 *   3. Subscribes to cross-tab session events: a login in another tab re-syncs
 *      this tab to the same identity; a logout clears this tab immediately.
 */

import { useEffect, useRef, useState } from 'react';

import { ProgressSpinner } from 'primereact/progressspinner';
import { useNavigate } from 'react-router-dom';

import { useAppDispatch } from '@app/store';

import { clearRbac } from '@core/rbac';

import { bootstrapSession, sessionCleared } from '@features/authentication/store/authSlice';

import { setSessionExpiredHandler } from '@shared/services/apiClient';
import { sessionBus } from '@shared/services/sessionBus';
import { sessionCache } from '@shared/services/sessionCache';

interface AuthBootstrapProps {
  children: React.ReactNode;
}

export const AuthBootstrap = ({ children }: AuthBootstrapProps) => {
  const dispatch = useAppDispatch();
  const navigate = useNavigate();
  // If we have a cached session snapshot, render immediately and let the silent
  // refresh happen in the background. Only a cold start shows the splash.
  const [ready, setReady] = useState(() => sessionCache.hasUser());
  // Avoid reacting to our own broadcasts causing loops.
  const bootstrappingRef = useRef(false);

  useEffect(() => {
    let active = true;

    // 1. Restore session from the refresh cookie.
    (async () => {
      await dispatch(bootstrapSession());
      if (active) setReady(true);
    })();

    // 2. When a refresh ultimately fails, clear state and route to login (SPA nav).
    setSessionExpiredHandler(() => {
      dispatch(sessionCleared());
      dispatch(clearRbac());
      navigate('/login', { replace: true });
    });

    // 3. Cross-tab synchronization.
    const unsubscribe = sessionBus.subscribe((event) => {
      if (event.type === 'logout') {
        dispatch(sessionCleared());
        dispatch(clearRbac());
        navigate('/login', { replace: true });
      } else if (event.type === 'login') {
        // Another tab authenticated (possibly as a different user). Re-sync this
        // tab to the shared cookie identity.
        if (bootstrappingRef.current) return;
        bootstrappingRef.current = true;
        dispatch(bootstrapSession()).finally(() => {
          bootstrappingRef.current = false;
        });
      }
    });

    return () => {
      active = false;
      unsubscribe();
    };
  }, [dispatch, navigate]);

  if (!ready) {
    return (
      <div
        className="flex align-items-center justify-content-center min-h-screen"
        style={{ background: 'var(--color-surface-ground, #f8f9fa)' }}
      >
        <ProgressSpinner
          style={{ width: '48px', height: '48px' }}
          strokeWidth="4"
          aria-label="Restoring session"
        />
      </div>
    );
  }

  return <>{children}</>;
};

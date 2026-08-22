/**
 * Microsoft OAuth2 Callback Page.
 * Handles the redirect back from Azure AD after user authenticates.
 * Exchanges the authorization code for app tokens and navigates to dashboard.
 */

import { useEffect, useState } from 'react';

import { Button } from 'primereact/button';
import { ProgressSpinner } from 'primereact/progressspinner';
import { useNavigate, useSearchParams } from 'react-router-dom';

import { useAppDispatch } from '@app/store';

import { storageService } from '@shared/services/storageService';
import { extractApiError } from '@shared/utils/apiError';

import { microsoftApi } from '../api/microsoftApi';
import { fetchCurrentUser } from '../store/authSlice';

export const MicrosoftCallbackPage = () => {
  const navigate = useNavigate();
  const dispatch = useAppDispatch();
  const [searchParams] = useSearchParams();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const code = searchParams.get('code');
    const errorParam = searchParams.get('error_description') || searchParams.get('error');

    if (errorParam) {
      setError(errorParam);
      return;
    }

    if (!code) {
      setError('No authorization code received from Microsoft.');
      return;
    }

    // Exchange code for app tokens
    microsoftApi
      .exchangeCode(code)
      .then(async (tokenRes) => {
        // Access token → memory. Refresh token was set as an HttpOnly cookie by the server.
        storageService.setAccessToken(tokenRes.access_token);

        // Fetch user profile (also loads RBAC + broadcasts login to other tabs)
        await dispatch(fetchCurrentUser());

        // Navigate to dashboard
        const redirect = sessionStorage.getItem('redirectAfterLogin') || '/dashboard';
        sessionStorage.removeItem('redirectAfterLogin');
        navigate(redirect, { replace: true });
      })
      .catch((err: unknown) => {
        // Falls back to the thrown error's own message, which is what a network failure
        // carries — it never reaches the server, so there is no response body to unwrap.
        const fallback = err instanceof Error ? err.message : 'Microsoft login failed';
        setError(extractApiError(err, fallback));
      });
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  if (error) {
    return (
      <div
        className="flex align-items-center justify-content-center min-h-screen"
        style={{ background: 'var(--color-surface-ground)' }}
      >
        <div className="em-login-card p-6 text-center" style={{ maxWidth: '420px' }}>
          <i
            className="pi pi-times-circle mb-3"
            style={{ fontSize: '3rem', color: 'var(--color-error)' }}
          />
          <h2 className="text-xl font-bold mb-2" style={{ color: 'var(--color-text-primary)' }}>
            Login Failed
          </h2>
          <p className="mb-4" style={{ color: 'var(--color-text-secondary)', fontSize: '14px' }}>
            {error}
          </p>
          <Button
            label="Back to Login"
            icon="pi pi-arrow-left"
            onClick={() => navigate('/login')}
          />
        </div>
      </div>
    );
  }

  return (
    <div
      className="flex align-items-center justify-content-center min-h-screen"
      style={{ background: 'var(--color-surface-ground)' }}
    >
      <div className="em-login-card p-6 text-center" style={{ maxWidth: '420px' }}>
        <ProgressSpinner
          style={{ width: '50px', height: '50px' }}
          strokeWidth="4"
          aria-label="Signing in with Microsoft"
        />
        <p className="mt-3" style={{ color: 'var(--color-text-secondary)' }}>
          Signing in with Microsoft…
        </p>
      </div>
    </div>
  );
};

import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { MicrosoftCallbackPage } from '@features/authentication/pages/MicrosoftCallbackPage';

import { storageService } from '@shared/services/storageService';

import { server } from '../../mocks/server';
import { renderWithProviders, screen, waitFor } from '../../test-utils';

const CALLBACK_URL = '/api/v1/auth/microsoft/callback';
const ME_URL = '/api/v1/auth/me';

const renderCallback = (query: string) =>
  renderWithProviders(
    <Routes>
      <Route path="/auth/microsoft/callback" element={<MicrosoftCallbackPage />} />
      <Route path="/dashboard" element={<div>Dashboard page</div>} />
      <Route path="/reports" element={<div>Reports page</div>} />
      <Route path="/login" element={<div>Login page</div>} />
    </Routes>,
    { initialEntries: [`/auth/microsoft/callback${query}`] },
  );

const signedIn = () => {
  server.use(
    http.post(CALLBACK_URL, () =>
      HttpResponse.json({ access_token: 'ms-access', token_type: 'Bearer', expires_in: 1800 }),
    ),
    http.get(ME_URL, () => HttpResponse.json({ id: 7, username: 'E12345', is_active: true })),
  );
};

beforeEach(() => {
  // Other tests in the run may have left a token in the module-level store.
  storageService.clearAccessToken();
});

afterEach(() => {
  sessionStorage.clear();
  storageService.clearAccessToken();
});

describe('MicrosoftCallbackPage', () => {
  it('shows a spinner while the code is being exchanged', async () => {
    server.use(
      http.post(CALLBACK_URL, async () => {
        await new Promise((resolve) => setTimeout(resolve, 50));
        return HttpResponse.json({ access_token: 't', token_type: 'Bearer', expires_in: 1800 });
      }),
      http.get(ME_URL, () => HttpResponse.json({ id: 7, username: 'E12345', is_active: true })),
    );

    renderCallback('?code=abc&state=xyz');

    expect(screen.getByLabelText('Signing in with Microsoft')).toBeInTheDocument();
    await screen.findByText('Dashboard page');
  });

  describe('the code exchange', () => {
    it('sends the code together with the state Microsoft returned', async () => {
      let body: unknown;
      server.use(
        http.post(CALLBACK_URL, async ({ request }) => {
          body = await request.json();
          return HttpResponse.json({ access_token: 't', token_type: 'Bearer', expires_in: 1800 });
        }),
        http.get(ME_URL, () => HttpResponse.json({ id: 7, username: 'E12345', is_active: true })),
      );

      renderCallback('?code=the-code&state=the-state');

      await screen.findByText('Dashboard page');
      expect(body).toEqual({ code: 'the-code', state: 'the-state' });
    });

    it('keeps the access token in memory and lands on the dashboard', async () => {
      signedIn();

      renderCallback('?code=abc&state=xyz');

      expect(await screen.findByText('Dashboard page')).toBeInTheDocument();
      expect(storageService.getAccessToken()).toBe('ms-access');
    });

    it('returns to the page the user was sent here from', async () => {
      signedIn();
      sessionStorage.setItem('redirectAfterLogin', '/reports');

      renderCallback('?code=abc&state=xyz');

      expect(await screen.findByText('Reports page')).toBeInTheDocument();
      expect(sessionStorage.getItem('redirectAfterLogin')).toBeNull();
    });
  });

  describe('a response that cannot be used', () => {
    it('refuses a redirect with no code, and calls nothing', async () => {
      let called = false;
      server.use(
        http.post(CALLBACK_URL, () => {
          called = true;
          return HttpResponse.json({});
        }),
      );

      renderCallback('?state=xyz');

      expect(await screen.findByText('No authorization code received from Microsoft.')).toBeVisible();
      expect(called).toBe(false);
    });

    it('refuses a redirect with no state, and calls nothing', async () => {
      let called = false;
      server.use(
        http.post(CALLBACK_URL, () => {
          called = true;
          return HttpResponse.json({});
        }),
      );

      renderCallback('?code=abc');

      expect(
        await screen.findByText(
          'The sign-in response from Microsoft was incomplete. Please try again.',
        ),
      ).toBeVisible();
      expect(called).toBe(false);
    });

    it('shows the reason Microsoft gave when it sends an error instead of a code', async () => {
      renderCallback('?error=access_denied&error_description=The+user+cancelled+the+sign-in');

      expect(await screen.findByText('The user cancelled the sign-in')).toBeVisible();
    });

    it('falls back to the short error code when there is no description', async () => {
      renderCallback('?error=access_denied');

      expect(await screen.findByText('access_denied')).toBeVisible();
    });

    it('shows the server message when the exchange is refused', async () => {
      server.use(
        http.post(CALLBACK_URL, () =>
          HttpResponse.json(
            { detail: 'Microsoft sign-in session is invalid or has expired. Please try again.' },
            { status: 400 },
          ),
        ),
      );

      renderCallback('?code=abc&state=forged');

      expect(
        await screen.findByText(
          'Microsoft sign-in session is invalid or has expired. Please try again.',
        ),
      ).toBeVisible();
      expect(screen.getByRole('heading', { name: 'Login Failed' })).toBeInTheDocument();
    });

    it('shows the not-provisioned message for an account that was never imported', async () => {
      server.use(
        http.post(CALLBACK_URL, () =>
          HttpResponse.json(
            { detail: 'No account found for this Microsoft email.' },
            { status: 403 },
          ),
        ),
      );

      renderCallback('?code=abc&state=xyz');

      expect(await screen.findByText('No account found for this Microsoft email.')).toBeVisible();
    });

    it('does not keep an access token after a refused exchange', async () => {
      server.use(
        http.post(CALLBACK_URL, () => HttpResponse.json({ detail: 'no' }, { status: 403 })),
      );

      renderCallback('?code=abc&state=xyz');

      await screen.findByRole('heading', { name: 'Login Failed' });
      expect(storageService.getAccessToken()).toBeNull();
    });

    it('offers a way back to the login page', async () => {
      const user = userEvent.setup();
      renderCallback('?error=access_denied');

      await user.click(await screen.findByRole('button', { name: 'Back to Login' }));

      await waitFor(() => expect(screen.getByText('Login page')).toBeInTheDocument());
    });
  });
});

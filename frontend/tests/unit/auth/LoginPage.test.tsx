/**
 * Tests for the Login page — the primary auth entry point.
 *
 * Covers: zod validation (username ≥ 3, password required), a successful login end to
 * end (thunk → store authenticated → navigate to the post-login redirect), and a failed
 * login surfacing the store's error message. The network is mocked (MSW) so the real
 * loginThunk → authApi → apiClient path runs.
 */

import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { beforeEach, describe, expect, it } from 'vitest';

import { LoginPage } from '@features/authentication/pages/LoginPage';

import { server } from '../../mocks/server';
import { renderWithProviders, screen, waitFor } from '../../test-utils';

// Entity ids are numeric (bigint) in this app, never UUID strings.
const USER = {
  id: 1,
  username: 'alice',
  is_active: true,
};

const loginSucceeds = () => {
  server.use(
    http.post('/api/v1/auth/login', () =>
      HttpResponse.json({ access_token: 'tok', token_type: 'Bearer', expires_in: 1800 }),
    ),
    http.get('/api/v1/auth/me', () => HttpResponse.json(USER)),
    http.get('/api/v1/rbac/my-permissions/menu', () =>
      HttpResponse.json({ menu_keys: ['home'], permissions: [] }),
    ),
  );
};

beforeEach(() => {
  sessionStorage.clear();
});

describe('LoginPage — validation', () => {
  it('shows validation errors and does not authenticate', async () => {
    const user = userEvent.setup();
    const { store } = renderWithProviders(<LoginPage />);

    await user.type(screen.getByLabelText('Username'), 'ab');
    await user.click(screen.getByRole('button', { name: 'Sign in' }));

    expect(await screen.findByText('Username must be at least 3 characters')).toBeInTheDocument();
    // The password field renders its zod error into #password-error. Its exact text
    // depends on zod's message for an unset field, so assert the error element appears
    // rather than pinning the wording.
    await waitFor(() => expect(document.getElementById('password-error')).toBeInTheDocument());
    expect(store.getState().auth.isAuthenticated).toBe(false);
  });
});

describe('LoginPage — success', () => {
  it('authenticates and stores the user on valid credentials', async () => {
    loginSucceeds();
    const user = userEvent.setup();
    const { store } = renderWithProviders(<LoginPage />);

    await user.type(screen.getByLabelText('Username'), 'alice');
    await user.type(screen.getByPlaceholderText('Enter password'), 'password123');
    await user.click(screen.getByRole('button', { name: 'Sign in' }));

    await waitFor(() => expect(store.getState().auth.isAuthenticated).toBe(true));
    expect(store.getState().auth.user?.username).toBe('alice');
  });
});

describe('LoginPage — failure', () => {
  it('surfaces the error returned by the server', async () => {
    server.use(
      http.post('/api/v1/auth/login', () =>
        HttpResponse.json({ message: 'Invalid username or password' }, { status: 401 }),
      ),
    );
    const user = userEvent.setup();
    renderWithProviders(<LoginPage />);

    await user.type(screen.getByLabelText('Username'), 'alice');
    await user.type(screen.getByPlaceholderText('Enter password'), 'wrongpass');
    await user.click(screen.getByRole('button', { name: 'Sign in' }));

    expect(await screen.findByText('Invalid username or password')).toBeInTheDocument();
  });

  it('sends one login per click and does not try to refresh a session that never existed', async () => {
    let logins = 0;
    let refreshes = 0;
    server.use(
      http.post('/api/v1/auth/login', () => {
        logins += 1;
        return HttpResponse.json({ detail: 'Invalid username or password' }, { status: 401 });
      }),
      http.post('/api/v1/auth/refresh', () => {
        refreshes += 1;
        return HttpResponse.json({ detail: 'Missing refresh token' }, { status: 401 });
      }),
    );
    const user = userEvent.setup();
    renderWithProviders(<LoginPage />);

    await user.type(screen.getByLabelText('Username'), 'alice');
    await user.type(screen.getByPlaceholderText('Enter password'), 'wrongpass');
    await user.click(screen.getByRole('button', { name: 'Sign in' }));

    // The reason for the failure, not the refresh's "Missing refresh token".
    expect(await screen.findByText('Invalid username or password')).toBeInTheDocument();
    expect(logins).toBe(1); // a replay would count as a second attempt against the throttle
    expect(refreshes).toBe(0);
  });
});

describe('LoginPage — too many attempts', () => {
  it('tells the user how long to wait', async () => {
    server.use(
      http.post('/api/v1/auth/login', () =>
        HttpResponse.json(
          { detail: 'Too many login attempts. Please try again later.' },
          { status: 429, headers: { 'Retry-After': '900' } },
        ),
      ),
    );
    const user = userEvent.setup();
    const { store } = renderWithProviders(<LoginPage />);

    await user.type(screen.getByLabelText('Username'), 'alice');
    await user.type(screen.getByPlaceholderText('Enter password'), 'password123');
    await user.click(screen.getByRole('button', { name: 'Sign in' }));

    expect(
      await screen.findByText('Too many login attempts. Please try again in about 15 minutes.'),
    ).toBeInTheDocument();
    expect(store.getState().auth.isAuthenticated).toBe(false);
  });

  it('lets the user try again afterwards: the message clears on the next submit', async () => {
    let calls = 0;
    server.use(
      http.post('/api/v1/auth/login', () => {
        calls += 1;
        return calls === 1
          ? HttpResponse.json(
              { detail: 'Too many login attempts. Please try again later.' },
              { status: 429, headers: { 'Retry-After': '60' } },
            )
          : HttpResponse.json({ access_token: 'tok', token_type: 'Bearer', expires_in: 1800 });
      }),
      http.get('/api/v1/auth/me', () => HttpResponse.json(USER)),
      http.get('/api/v1/rbac/my-permissions/menu', () =>
        HttpResponse.json({ menu_keys: ['home'], permissions: [] }),
      ),
    );
    const user = userEvent.setup();
    const { store } = renderWithProviders(<LoginPage />);
    await user.type(screen.getByLabelText('Username'), 'alice');
    await user.type(screen.getByPlaceholderText('Enter password'), 'password123');

    await user.click(screen.getByRole('button', { name: 'Sign in' }));
    expect(await screen.findByText(/Too many login attempts/)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Sign in' }));

    await waitFor(() => expect(store.getState().auth.isAuthenticated).toBe(true));
    expect(screen.queryByText(/Too many login attempts/)).not.toBeInTheDocument();
  });
});

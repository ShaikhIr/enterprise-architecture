import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';

import type { PermissionAction } from '@core/rbac/types';

import { CountriesPage } from '@features/masters/pages/CountriesPage';

import { server } from '../../mocks/server';
import { renderWithProviders, screen, waitFor, within } from '../../test-utils';

const country = {
  id: 1,
  code: 'IN',
  name: 'India',
  iso3_code: 'IND',
  dial_code: '+91',
  currency_code: 'INR',
  is_active: true,
  created_by: 'system',
  created_date: '2024-01-01T00:00:00Z',
  modified_by: 'system',
  modified_date: '2024-01-01T00:00:00Z',
};

const withApiGrants = (resource: string, actions: PermissionAction[]) => ({
  rbac: {
    menuKeys: [],
    menuPermissions: [],
    apiCodes: [],
    apiResourceActions: { [resource]: actions },
    fieldPermissions: {},
    fieldPermissionStatus: {},
    isLoaded: false,
    isApiLoaded: true,
    isLoading: false,
    isApiLoading: false,
    error: null,
  },
});

describe('CountriesPage', () => {
  it('renders the fetched countries in the table', async () => {
    server.use(
      http.get('/api/v1/masters/countries', () =>
        HttpResponse.json({ countries: [country], total: 1, skip: 0, limit: 100 }),
      ),
    );

    renderWithProviders(<CountriesPage />, {
      preloadedState: withApiGrants('countries', ['CREATE', 'UPDATE', 'DELETE']),
    });

    const table = screen.getByRole('table');
    // `findByRole('table')` would resolve as soon as DataTable mounts (in its
    // loading/empty state) — waiting for a fetched row's own text is what
    // actually confirms the list request has resolved and rendered.
    expect(await within(table).findByText('India')).toBeInTheDocument();
    expect(within(table).getByText('IN')).toBeInTheDocument();
    expect(within(table).getByText('IND')).toBeInTheDocument();
  });

  it('hides the New Country button when the caller lacks CREATE', async () => {
    server.use(
      http.get('/api/v1/masters/countries', () =>
        HttpResponse.json({ countries: [], total: 0, skip: 0, limit: 100 }),
      ),
    );

    renderWithProviders(<CountriesPage />, {
      preloadedState: withApiGrants('countries', ['READ']),
    });

    await screen.findByText('No countries defined yet.');
    expect(screen.queryByRole('button', { name: 'New Country' })).not.toBeInTheDocument();
  });

  it('hides the Actions column entirely when the caller can neither update nor delete', async () => {
    server.use(
      http.get('/api/v1/masters/countries', () =>
        HttpResponse.json({ countries: [country], total: 1, skip: 0, limit: 100 }),
      ),
    );

    renderWithProviders(<CountriesPage />, {
      preloadedState: withApiGrants('countries', ['READ']),
    });

    const table = screen.getByRole('table');
    await within(table).findByText('India');
    expect(within(table).queryByText('Actions')).not.toBeInTheDocument();
  });

  it('creates a country end to end: opens the dialog, submits, and shows a success toast', async () => {
    const user = userEvent.setup();
    server.use(
      http.get('/api/v1/masters/countries', () =>
        HttpResponse.json({ countries: [], total: 0, skip: 0, limit: 100 }),
      ),
      http.post('/api/v1/masters/countries', () =>
        HttpResponse.json({ ...country, id: 2, code: 'FR', name: 'France' }),
      ),
    );

    renderWithProviders(<CountriesPage />, {
      preloadedState: withApiGrants('countries', ['CREATE', 'UPDATE', 'DELETE']),
    });
    await screen.findByText('No countries defined yet.');

    await user.click(screen.getByRole('button', { name: 'New Country' }));
    await user.type(screen.getByLabelText('Code'), 'FR');
    await user.type(screen.getByLabelText('Name'), 'France');
    await user.click(screen.getByRole('button', { name: 'Create' }));

    await waitFor(() => expect(screen.getByText('Country created')).toBeInTheDocument());
  });

  it('deletes a country end to end: confirms, then shows a success toast', async () => {
    const user = userEvent.setup();
    server.use(
      http.get('/api/v1/masters/countries', () =>
        HttpResponse.json({ countries: [country], total: 1, skip: 0, limit: 100 }),
      ),
      http.delete('/api/v1/masters/countries/1', () => new HttpResponse(null, { status: 204 })),
    );

    renderWithProviders(<CountriesPage />, {
      preloadedState: withApiGrants('countries', ['CREATE', 'UPDATE', 'DELETE']),
    });
    await screen.findByText('India');

    await user.click(await screen.findByRole('button', { name: 'Delete India' }));
    const confirmDialog = await screen.findByRole('dialog', { name: 'Delete country' });
    await user.click(within(confirmDialog).getByText('Delete'));

    await waitFor(() => expect(screen.getByText("Country 'India' deleted")).toBeInTheDocument());
  });

  it('shows the backend conflict message when deleting a country that still has dependents', async () => {
    const user = userEvent.setup();
    server.use(
      http.get('/api/v1/masters/countries', () =>
        HttpResponse.json({ countries: [country], total: 1, skip: 0, limit: 100 }),
      ),
      http.delete('/api/v1/masters/countries/1', () =>
        HttpResponse.json({ message: 'Country is referenced by 2 state(s)' }, { status: 409 }),
      ),
    );

    renderWithProviders(<CountriesPage />, {
      preloadedState: withApiGrants('countries', ['CREATE', 'UPDATE', 'DELETE']),
    });
    await screen.findByText('India');

    await user.click(await screen.findByRole('button', { name: 'Delete India' }));
    const confirmDialog = await screen.findByRole('dialog', { name: 'Delete country' });
    await user.click(within(confirmDialog).getByText('Delete'));

    await waitFor(() =>
      expect(screen.getByText('Country is referenced by 2 state(s)')).toBeInTheDocument(),
    );
  });
});

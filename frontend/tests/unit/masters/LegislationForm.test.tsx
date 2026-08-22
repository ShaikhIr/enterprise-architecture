import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { describe, expect, it, vi } from 'vitest';

import { LegislationForm } from '@features/masters/components/LegislationForm';

import { server } from '../../mocks/server';
import {
  getValidationError,
  renderWithProviders,
  screen,
  selectDropdownOption,
  waitFor,
  within,
} from '../../test-utils';

const country = (id: string, code: string, name: string) => ({
  id,
  code,
  name,
  iso3_code: null,
  dial_code: null,
  currency_code: null,
  is_active: true,
  created_by: 'system',
  created_date: '2024-01-01T00:00:00Z',
  modified_by: 'system',
  modified_date: '2024-01-01T00:00:00Z',
});

const state = (id: string, code: string, name: string, countryId: string) => ({
  id,
  code,
  name,
  country_id: countryId,
  is_union_territory: false,
  is_active: true,
  created_by: 'system',
  created_date: '2024-01-01T00:00:00Z',
  modified_by: 'system',
  modified_date: '2024-01-01T00:00:00Z',
});

// LegislationForm's zod schema validates country_id and category_of_law_id
// with `z.string().uuid()`, so fixture ids must actually be UUID-shaped or
// submission silently fails validation instead of calling onSubmit.
const COUNTRY_IN_ID = '11111111-1111-1111-1111-111111111111';
const COUNTRY_US_ID = '22222222-2222-2222-2222-222222222222';
const CATEGORY_ID = '33333333-3333-3333-3333-333333333333';
const STATE_MH_ID = '44444444-4444-4444-4444-444444444444';

const category = {
  id: CATEGORY_ID,
  code: 'LABOUR',
  name: 'Labour Law',
  description: '',
  state_id: null,
  is_active: true,
  created_by: 'system',
  created_date: '2024-01-01T00:00:00Z',
  modified_by: 'system',
  modified_date: '2024-01-01T00:00:00Z',
};

const mockLookups = () =>
  server.use(
    http.get('/api/v1/masters/countries', () =>
      HttpResponse.json({
        countries: [
          country(COUNTRY_IN_ID, 'IN', 'India'),
          country(COUNTRY_US_ID, 'US', 'United States'),
        ],
        total: 2,
        skip: 0,
        limit: 100,
      }),
    ),
    http.get('/api/v1/masters/categories-of-law', () =>
      HttpResponse.json({ categories_of_law: [category], total: 1, skip: 0, limit: 100 }),
    ),
    http.get('/api/v1/masters/states', ({ request }) => {
      const url = new URL(request.url);
      const countryId = url.searchParams.get('country_id');
      const isActiveOnly = url.searchParams.get('is_active') === 'true';
      const all = [state(STATE_MH_ID, 'IN-MH', 'Maharashtra', COUNTRY_IN_ID)];
      const items = isActiveOnly ? all.filter((s) => s.country_id === countryId) : all;
      return HttpResponse.json({ states: items, total: items.length, skip: 0, limit: 100 });
    }),
  );

/** Open the given PrimeReact dropdown and return its listbox panel. */
const openDropdown = async (user: ReturnType<typeof userEvent.setup>, accessibleName: string) => {
  const container = screen.getByLabelText(accessibleName).closest('[data-pc-name="dropdown"]');
  await user.click(container!.querySelector('.p-dropdown-trigger')!);
  return screen.findByRole('listbox');
};

/**
 * Lighter than `CountryForm.test.tsx`, focused on what is specific to
 * Legislation: the cascading country -> state dropdown (via `useWatch` +
 * `useStateLookup(countryId)`), the "Central" state sentinel, and the
 * optional legislation_number/effective_date fields. Basic validation/reset
 * mechanics follow the same react-hook-form + zod shape already proven on
 * CountryForm.
 */
describe('LegislationForm', () => {
  it('offers a "Central" option in the state dropdown panel', async () => {
    mockLookups();
    const user = userEvent.setup();
    renderWithProviders(
      <LegislationForm visible legislation={null} onHide={vi.fn()} onSubmit={vi.fn()} />,
    );

    const listbox = await openDropdown(user, 'Owning state');
    expect(within(listbox).getByRole('option', { name: 'Central (no state)' })).toBeInTheDocument();
  });

  it('narrows the state options to the selected country', async () => {
    mockLookups();
    const user = userEvent.setup();
    renderWithProviders(
      <LegislationForm visible legislation={null} onHide={vi.fn()} onSubmit={vi.fn()} />,
    );

    // Before a country is chosen, useStateLookup(undefined) filters on no
    // country, so nothing state-specific should be assumed yet.
    await selectDropdownOption(user, 'Owning country', 'India (IN)');

    // Once India is selected, Maharashtra becomes an option in the state dropdown.
    const listbox = await openDropdown(user, 'Owning state');
    expect(
      await within(listbox).findByRole('option', { name: 'Maharashtra (IN-MH)' }),
    ).toBeInTheDocument();
  });

  it('submits state_id as null when left as Central', async () => {
    mockLookups();
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    renderWithProviders(
      <LegislationForm visible legislation={null} onHide={vi.fn()} onSubmit={onSubmit} />,
    );

    await selectDropdownOption(user, 'Owning country', 'India (IN)');
    await selectDropdownOption(user, 'Category of law', 'Labour Law (LABOUR)');
    await user.type(screen.getByLabelText('Code'), 'in-fact-1948');
    await user.type(screen.getByLabelText('Name'), 'The Factories Act, 1948');
    await user.click(screen.getByRole('button', { name: 'Create' }));

    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({
        code: 'IN-FACT-1948',
        country_id: COUNTRY_IN_ID,
        state_id: null,
        legislation_number: null,
        effective_date: null,
      }),
    );
  });

  it('sends legislation_number as null (not empty string) when left blank', async () => {
    mockLookups();
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    renderWithProviders(
      <LegislationForm visible legislation={null} onHide={vi.fn()} onSubmit={onSubmit} />,
    );

    await selectDropdownOption(user, 'Owning country', 'India (IN)');
    await selectDropdownOption(user, 'Category of law', 'Labour Law (LABOUR)');
    await user.type(screen.getByLabelText('Code'), 'IN-X');
    await user.type(screen.getByLabelText('Name'), 'Some Act');
    await user.click(screen.getByRole('button', { name: 'Create' }));

    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({ legislation_number: null }));
  });

  it('requires both country and category before submitting', async () => {
    mockLookups();
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    renderWithProviders(
      <LegislationForm visible legislation={null} onHide={vi.fn()} onSubmit={onSubmit} />,
    );

    await user.type(screen.getByLabelText('Code'), 'IN-X');
    await user.type(screen.getByLabelText('Name'), 'Some Act');
    await user.click(screen.getByRole('button', { name: 'Create' }));

    await waitFor(() => expect(getValidationError('Select a country')).toBeInTheDocument());
    expect(getValidationError('Select a category of law')).toBeInTheDocument();
    expect(onSubmit).not.toHaveBeenCalled();
  });
});

import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { describe, expect, it, vi } from 'vitest';

import { CategoryOfLawForm } from '@features/masters/components/CategoryOfLawForm';
import type { CategoryOfLaw } from '@features/masters/models/CategoryOfLaw';

import { server } from '../../mocks/server';
import {
  renderWithProviders,
  screen,
  selectDropdownOption,
  waitFor,
  within,
} from '../../test-utils';

// CategoryOfLawForm's zod schema declares `state_id: z.number().int().positive().nullable()`
// (the null sentinel is the "country-wide" choice), so this id is a positive
// number like every other bigint FK.
const STATE_ID = 501;

const stateRecord = {
  id: STATE_ID,
  code: 'IN-MH',
  name: 'Maharashtra',
  country_id: 11111111,
  is_union_territory: false,
  is_active: true,
  created_by: 'system',
  created_date: '2024-01-01T00:00:00Z',
  modified_by: 'system',
  modified_date: '2024-01-01T00:00:00Z',
};

const mockStatesList = () =>
  server.use(
    http.get('/api/v1/masters/states', () =>
      HttpResponse.json({ states: [stateRecord], total: 1, skip: 0, limit: 100 }),
    ),
  );

/**
 * Lighter than `CountryForm.test.tsx`: focuses on what is specific to
 * CategoryOfLaw — its state picker is optional, and an empty selection is a
 * meaningful value ("country-wide"), mapped through the `COUNTRY_WIDE`
 * sentinel rather than treated as an unset field.
 *
 * Note: PrimeReact's Dropdown renders an empty-string value as a blank
 * closed label regardless of whether an option maps to it, so the
 * country-wide *selection* cannot be asserted by reading the closed
 * dropdown's displayed text — these tests instead check the option exists
 * in the open panel, and that the sentinel round-trips correctly on submit.
 */
describe('CategoryOfLawForm', () => {
  it('offers a "Country-wide" option in the state dropdown panel', async () => {
    mockStatesList();
    const user = userEvent.setup();
    renderWithProviders(
      <CategoryOfLawForm visible category={null} onHide={vi.fn()} onSubmit={vi.fn()} />,
    );
    const container = screen.getByLabelText('Owning state').closest('[data-pc-name="dropdown"]');
    await user.click(container!.querySelector('.p-dropdown-trigger')!);

    const listbox = await screen.findByRole('listbox');
    expect(
      within(listbox).getByRole('option', { name: 'Country-wide (no state)' }),
    ).toBeInTheDocument();
    expect(
      await within(listbox).findByRole('option', { name: 'Maharashtra (IN-MH)' }),
    ).toBeInTheDocument();
  });

  it('submits state_id as null when left as country-wide (the default)', async () => {
    mockStatesList();
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    renderWithProviders(
      <CategoryOfLawForm visible category={null} onHide={vi.fn()} onSubmit={onSubmit} />,
    );

    await user.type(screen.getByLabelText('Code'), 'labour');
    await user.type(screen.getByLabelText('Name'), 'Labour Law');
    await user.click(screen.getByRole('button', { name: 'Create' }));

    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    expect(onSubmit).toHaveBeenCalledWith({
      code: 'LABOUR',
      name: 'Labour Law',
      description: '',
      state_id: null,
      is_active: true,
    });
  });

  it('submits the selected state id when a specific state is chosen', async () => {
    mockStatesList();
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    renderWithProviders(
      <CategoryOfLawForm visible category={null} onHide={vi.fn()} onSubmit={onSubmit} />,
    );

    await user.type(screen.getByLabelText('Code'), 'labour');
    await user.type(screen.getByLabelText('Name'), 'Labour Law');
    await selectDropdownOption(user, 'Owning state', 'Maharashtra (IN-MH)');
    await user.click(screen.getByRole('button', { name: 'Create' }));

    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({ state_id: STATE_ID }));
  });

  it('re-submits null state_id unchanged when editing a country-wide row', async () => {
    mockStatesList();
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    const category: CategoryOfLaw = {
      id: 1,
      code: 'TAX',
      name: 'Taxation',
      description: 'Central taxation matters',
      state_id: null,
      is_active: true,
      created_by: 'system',
      created_date: '2024-01-01T00:00:00Z',
      modified_by: 'system',
      modified_date: '2024-01-01T00:00:00Z',
    };
    renderWithProviders(
      <CategoryOfLawForm visible category={category} onHide={vi.fn()} onSubmit={onSubmit} />,
    );
    await waitFor(() => expect(screen.getByText('Edit Category — TAX')).toBeInTheDocument());

    await user.click(screen.getByRole('button', { name: 'Save Changes' }));

    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({ state_id: null }));
  });
});

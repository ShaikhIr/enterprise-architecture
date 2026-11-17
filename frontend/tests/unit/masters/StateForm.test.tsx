import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { describe, expect, it, vi } from 'vitest';

import { StateForm } from '@features/masters/components/StateForm';

import { server } from '../../mocks/server';
import {
  getDropdownLabel,
  getValidationError,
  renderWithProviders,
  screen,
  selectDropdownOption,
  waitFor,
} from '../../test-utils';

// country_id is a numeric bigint FK, validated with `z.number().int().positive()`,
// so a fixture id must be a positive number or submission silently fails
// validation instead of calling onSubmit.
const COUNTRY_ID = 11111111;

const mockCountriesList = () =>
  server.use(
    http.get('/api/v1/masters/countries', () =>
      HttpResponse.json({
        countries: [
          {
            id: COUNTRY_ID,
            code: 'IN',
            name: 'India',
            iso3_code: null,
            dial_code: null,
            currency_code: null,
            is_active: true,
            created_by: 'system',
            created_date: '2024-01-01T00:00:00Z',
            modified_by: 'system',
            modified_date: '2024-01-01T00:00:00Z',
          },
        ],
        total: 1,
        skip: 0,
        limit: 100,
      }),
    ),
  );

/**
 * Lighter than `CountryForm.test.tsx`: the shared validation/reset/submit
 * shape is already proven there. This file only covers what is specific to
 * State — the country picker is required (unlike Legislation/Rule, where it
 * is one of two required parents, and unlike CategoryOfLaw's state picker,
 * which is optional) — plus the `is_union_territory` flag.
 */
describe('StateForm', () => {
  it('rejects submission without a country selected', async () => {
    mockCountriesList();
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    renderWithProviders(<StateForm visible state={null} onHide={vi.fn()} onSubmit={onSubmit} />);
    await waitFor(() =>
      expect(getDropdownLabel('Owning country')).not.toBe('Loading countries...'),
    );

    await user.type(screen.getByLabelText('Code'), 'IN-MH');
    await user.type(screen.getByLabelText('Name'), 'Maharashtra');
    await user.click(screen.getByRole('button', { name: 'Create' }));

    await waitFor(() => expect(getValidationError('Select a country')).toBeInTheDocument());
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('shows a hint instead of a validation error when there are no active countries yet', async () => {
    server.use(
      http.get('/api/v1/masters/countries', () =>
        HttpResponse.json({ countries: [], total: 0, skip: 0, limit: 100 }),
      ),
    );
    renderWithProviders(<StateForm visible state={null} onHide={vi.fn()} onSubmit={vi.fn()} />);

    await waitFor(() =>
      expect(screen.getByText('No active countries — add a country first.')).toBeInTheDocument(),
    );
  });

  it('submits the selected country id together with is_union_territory', async () => {
    mockCountriesList();
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    renderWithProviders(<StateForm visible state={null} onHide={vi.fn()} onSubmit={onSubmit} />);
    await waitFor(() =>
      expect(getDropdownLabel('Owning country')).not.toBe('Loading countries...'),
    );

    await selectDropdownOption(user, 'Owning country', 'India (IN)');
    await user.type(screen.getByLabelText('Code'), 'in-mh');
    await user.type(screen.getByLabelText('Name'), 'Maharashtra');
    await user.click(screen.getByLabelText('Union territory'));
    await user.click(screen.getByRole('button', { name: 'Create' }));

    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    expect(onSubmit).toHaveBeenCalledWith({
      code: 'IN-MH',
      name: 'Maharashtra',
      country_id: COUNTRY_ID,
      is_union_territory: true,
      is_active: true,
    });
  });

  it('pre-fills the country picker from the row being edited', async () => {
    mockCountriesList();
    renderWithProviders(
      <StateForm
        visible
        state={{
          id: 1,
          code: 'IN-MH',
          name: 'Maharashtra',
          country_id: COUNTRY_ID,
          is_union_territory: false,
          is_active: true,
          created_by: 'system',
          created_date: '2024-01-01T00:00:00Z',
          modified_by: 'system',
          modified_date: '2024-01-01T00:00:00Z',
        }}
        onHide={vi.fn()}
        onSubmit={vi.fn()}
      />,
    );

    await waitFor(() => expect(screen.getByText('Edit State — IN-MH')).toBeInTheDocument());
    await waitFor(() => expect(getDropdownLabel('Owning country')).toBe('India (IN)'));
  });
});

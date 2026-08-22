import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { describe, expect, it, vi } from 'vitest';

import { RuleForm } from '@features/masters/components/RuleForm';

import { server } from '../../mocks/server';
import {
  getDropdownLabel,
  getValidationError,
  renderWithProviders,
  screen,
  selectDropdownOption,
  waitFor,
} from '../../test-utils';

// RuleForm's zod schema validates legislation_id and country_id with
// `z.string().uuid()`, so fixture ids must actually be UUID-shaped or
// submission silently fails validation instead of calling onSubmit.
const LEGISLATION_ID = '55555555-5555-5555-5555-555555555555';
const COUNTRY_ID = '11111111-1111-1111-1111-111111111111';

const legislation = {
  id: LEGISLATION_ID,
  code: 'IN-FACT-1948',
  name: 'The Factories Act, 1948',
  description: '',
  category_of_law_id: '33333333-3333-3333-3333-333333333333',
  country_id: COUNTRY_ID,
  state_id: null,
  legislation_number: null,
  effective_date: null,
  is_active: true,
  created_by: 'system',
  created_date: '2024-01-01T00:00:00Z',
  modified_by: 'system',
  modified_date: '2024-01-01T00:00:00Z',
};

const countryIn = {
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
};

const mockLookups = () =>
  server.use(
    http.get('/api/v1/masters/legislations', () =>
      HttpResponse.json({ legislations: [legislation], total: 1, skip: 0, limit: 100 }),
    ),
    http.get('/api/v1/masters/countries', () =>
      HttpResponse.json({ countries: [countryIn], total: 1, skip: 0, limit: 100 }),
    ),
    http.get('/api/v1/masters/states', () =>
      HttpResponse.json({ states: [], total: 0, skip: 0, limit: 100 }),
    ),
  );

/**
 * Rule mirrors Legislation's cascading country -> state pattern (already
 * exercised in depth in `LegislationForm.test.tsx`), but is keyed off a
 * legislation rather than a category. This file only checks that
 * legislation-specific wiring and the required-field validation, rather than
 * repeating the cascading-dropdown coverage.
 */
describe('RuleForm', () => {
  it('requires a legislation to be selected before submitting', async () => {
    mockLookups();
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    renderWithProviders(<RuleForm visible rule={null} onHide={vi.fn()} onSubmit={onSubmit} />);
    await waitFor(() => expect(getDropdownLabel('Parent legislation')).not.toBe('Loading...'));

    await user.type(screen.getByLabelText('Code'), 'IN-FACT-1948-R5');
    await user.type(screen.getByLabelText('Name'), 'Maintenance of health register');
    await user.click(screen.getByRole('button', { name: 'Create' }));

    await waitFor(() => expect(getValidationError('Select a legislation')).toBeInTheDocument());
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('shows a hint instead of a validation error when no active legislations exist yet', async () => {
    server.use(
      http.get('/api/v1/masters/legislations', () =>
        HttpResponse.json({ legislations: [], total: 0, skip: 0, limit: 100 }),
      ),
      http.get('/api/v1/masters/countries', () =>
        HttpResponse.json({ countries: [], total: 0, skip: 0, limit: 100 }),
      ),
      http.get('/api/v1/masters/states', () =>
        HttpResponse.json({ states: [], total: 0, skip: 0, limit: 100 }),
      ),
    );
    renderWithProviders(<RuleForm visible rule={null} onHide={vi.fn()} onSubmit={vi.fn()} />);

    await waitFor(() =>
      expect(
        screen.getByText('No active legislations — add a legislation first.'),
      ).toBeInTheDocument(),
    );
  });

  it('submits with the selected legislation and rule_number as null when left blank', async () => {
    mockLookups();
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    renderWithProviders(<RuleForm visible rule={null} onHide={vi.fn()} onSubmit={onSubmit} />);
    await waitFor(() => expect(getDropdownLabel('Parent legislation')).not.toBe('Loading...'));

    await selectDropdownOption(
      user,
      'Parent legislation',
      'The Factories Act, 1948 (IN-FACT-1948)',
    );
    await selectDropdownOption(user, 'Owning country', 'India (IN)');
    await user.type(screen.getByLabelText('Code'), 'in-fact-1948-r5');
    await user.type(screen.getByLabelText('Name'), 'Maintenance of health register');
    await user.click(screen.getByRole('button', { name: 'Create' }));

    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({
        code: 'IN-FACT-1948-R5',
        legislation_id: LEGISLATION_ID,
        country_id: COUNTRY_ID,
        state_id: null,
        rule_number: null,
      }),
    );
  });
});

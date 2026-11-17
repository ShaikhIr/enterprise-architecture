import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { CountryForm } from '@features/masters/components/CountryForm';
import type { Country } from '@features/masters/models/Country';

import { renderWithProviders, screen, waitFor } from '../../test-utils';

const existingCountry: Country = {
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

/**
 * This is the worked example the other five master forms (State, CategoryOfLaw,
 * Legislation, Rule, TaskType) follow the same shape as: validation via the
 * zod schema, the create-vs-edit header/reset, and the submit-time
 * normalisation (trim, upper-case codes, empty string -> null). New master
 * forms should cover the same three areas.
 */
describe('CountryForm', () => {
  it('does not render dialog content while not visible', () => {
    renderWithProviders(
      <CountryForm visible={false} country={null} onHide={vi.fn()} onSubmit={vi.fn()} />,
    );

    expect(screen.queryByLabelText('Country dialog')).not.toBeInTheDocument();
  });

  it('shows the "New Country" header with empty fields when creating', () => {
    renderWithProviders(<CountryForm visible country={null} onHide={vi.fn()} onSubmit={vi.fn()} />);

    expect(screen.getByText('New Country')).toBeInTheDocument();
    expect(screen.getByLabelText('Code')).toHaveValue('');
  });

  it('shows the "Edit Country" header pre-filled with the row being edited', () => {
    renderWithProviders(
      <CountryForm visible country={existingCountry} onHide={vi.fn()} onSubmit={vi.fn()} />,
    );

    expect(screen.getByText('Edit Country — IN')).toBeInTheDocument();
    expect(screen.getByLabelText('Code')).toHaveValue('IN');
    expect(screen.getByLabelText('Name')).toHaveValue('India');
    expect(screen.getByLabelText('ISO3')).toHaveValue('IND');
  });

  it('rejects a code shorter than 2 characters and does not call onSubmit', async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    renderWithProviders(
      <CountryForm visible country={null} onHide={vi.fn()} onSubmit={onSubmit} />,
    );

    await user.type(screen.getByLabelText('Code'), 'A');
    await user.type(screen.getByLabelText('Name'), 'Atlantis');
    await user.click(screen.getByRole('button', { name: 'Create' }));

    await waitFor(() =>
      expect(screen.getByText('Code must be at least 2 characters')).toBeInTheDocument(),
    );
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('rejects a blank name and does not call onSubmit', async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    renderWithProviders(
      <CountryForm visible country={null} onHide={vi.fn()} onSubmit={onSubmit} />,
    );

    await user.type(screen.getByLabelText('Code'), 'IN');
    await user.click(screen.getByRole('button', { name: 'Create' }));

    await waitFor(() => expect(screen.getByText('Name is required')).toBeInTheDocument());
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('trims and upper-cases codes, and trims the name, on submit', async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    renderWithProviders(
      <CountryForm visible country={null} onHide={vi.fn()} onSubmit={onSubmit} />,
    );

    await user.type(screen.getByLabelText('Code'), 'in');
    await user.type(screen.getByLabelText('Name'), '  India  ');
    await user.type(screen.getByLabelText('ISO3'), 'ind');
    await user.click(screen.getByRole('button', { name: 'Create' }));

    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    expect(onSubmit).toHaveBeenCalledWith({
      code: 'IN',
      name: 'India',
      iso3_code: 'IND',
      dial_code: null,
      currency_code: null,
      is_active: true,
    });
  });

  it('sends null (not an empty string) for optional fields left blank', async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    renderWithProviders(
      <CountryForm visible country={null} onHide={vi.fn()} onSubmit={onSubmit} />,
    );

    await user.type(screen.getByLabelText('Code'), 'US');
    await user.type(screen.getByLabelText('Name'), 'United States');
    await user.click(screen.getByRole('button', { name: 'Create' }));

    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({
        iso3_code: null,
        dial_code: null,
        currency_code: null,
      }),
    );
  });

  it('submits the editing row id-less payload with the "Save Changes" button in edit mode', async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    renderWithProviders(
      <CountryForm visible country={existingCountry} onHide={vi.fn()} onSubmit={onSubmit} />,
    );

    await user.click(screen.getByRole('button', { name: 'Save Changes' }));

    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    expect(onSubmit).toHaveBeenCalledWith({
      code: 'IN',
      name: 'India',
      iso3_code: 'IND',
      dial_code: '+91',
      currency_code: 'INR',
      is_active: true,
    });
  });

  it('calls onHide when Cancel is clicked, without calling onSubmit', async () => {
    const user = userEvent.setup();
    const onHide = vi.fn();
    const onSubmit = vi.fn();
    renderWithProviders(<CountryForm visible country={null} onHide={onHide} onSubmit={onSubmit} />);

    await user.click(screen.getByRole('button', { name: 'Cancel' }));

    expect(onHide).toHaveBeenCalledTimes(1);
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('disables the action button and shows a loading state while saving', () => {
    renderWithProviders(
      <CountryForm visible country={null} saving onHide={vi.fn()} onSubmit={vi.fn()} />,
    );

    expect(screen.getByRole('button', { name: 'Create' })).toHaveClass('p-disabled');
  });
});

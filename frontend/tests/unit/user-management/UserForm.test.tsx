import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { UserForm } from '@features/user-management/components/UserForm';

import { server } from '../../mocks/server';
import {
  getDropdownLabel,
  getValidationError,
  renderWithProviders,
  screen,
  selectDropdownOption,
  waitFor,
} from '../../test-utils';

const ROLES = [
  { id: 11, code: 'ADMIN', name: 'Administrator', is_active: true },
  { id: 12, code: 'USER', name: 'User', is_active: true },
  { id: 13, code: 'OLD', name: 'Retired', is_active: false },
];

beforeEach(() => {
  server.use(
    http.get('/api/v1/rbac/roles', () => HttpResponse.json({ roles: ROLES, total: ROLES.length })),
  );
});

/** Wait for the role dropdown to finish loading (it is disabled until then). */
const rolesLoaded = () =>
  waitFor(() =>
    expect(screen.getByLabelText('Assign role').closest('.p-dropdown')).not.toHaveClass(
      'p-disabled',
    ),
  );

const fillCredentials = async (user: ReturnType<typeof userEvent.setup>) => {
  await user.type(screen.getByPlaceholderText('Enter username'), 'new.user');
  await user.type(screen.getByPlaceholderText('Enter password'), 'Passw0rd!');
};

describe('UserForm — rendering', () => {
  it('renders nothing while not visible', () => {
    renderWithProviders(<UserForm visible={false} onHide={vi.fn()} onSubmit={vi.fn()} />);

    expect(screen.queryByText('Create New User')).not.toBeInTheDocument();
  });

  it('shows the create dialog with its fields when visible', async () => {
    renderWithProviders(<UserForm visible onHide={vi.fn()} onSubmit={vi.fn()} />);

    expect(screen.getByText('Create New User')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('Enter username')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('Enter password')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Create' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeInTheDocument();
    await rolesLoaded();
  });

  it('disables the role dropdown with a loading placeholder until the roles arrive', async () => {
    renderWithProviders(<UserForm visible onHide={vi.fn()} onSubmit={vi.fn()} />);

    expect(getDropdownLabel('Assign role')).toBe('Loading roles...');
    expect(screen.getByLabelText('Assign role').closest('.p-dropdown')).toHaveClass('p-disabled');

    await rolesLoaded();
    expect(getDropdownLabel('Assign role')).toBe('Select a role');
  });

  it('defaults the "Validate with AD" switch to on', async () => {
    renderWithProviders(<UserForm visible onHide={vi.fn()} onSubmit={vi.fn()} />);
    await rolesLoaded();

    expect(screen.getByRole('switch', { name: 'Validate with AD' })).toBeChecked();
  });

  it('puts the Create button in its loading state while the parent mutation is pending', async () => {
    renderWithProviders(<UserForm visible onHide={vi.fn()} onSubmit={vi.fn()} loading />);
    await rolesLoaded();

    expect(screen.getByRole('button', { name: 'Create' })).toBeDisabled();
  });
});

describe('UserForm — role options', () => {
  it('lists only active roles, labelled "Name (CODE)"', async () => {
    const user = userEvent.setup();
    renderWithProviders(<UserForm visible onHide={vi.fn()} onSubmit={vi.fn()} />);
    await rolesLoaded();

    await user.click(
      screen
        .getByLabelText('Assign role')
        .closest('.p-dropdown')!
        .querySelector('.p-dropdown-trigger')!,
    );

    const listbox = await screen.findByRole('listbox');
    const names = Array.from(listbox.querySelectorAll('[role="option"]')).map((o) =>
      o.getAttribute('aria-label'),
    );
    expect(names).toEqual(['Administrator (ADMIN)', 'User (USER)']);
  });

  it('shows the chosen role on the closed dropdown', async () => {
    const user = userEvent.setup();
    renderWithProviders(<UserForm visible onHide={vi.fn()} onSubmit={vi.fn()} />);
    await rolesLoaded();

    await selectDropdownOption(user, 'Assign role', 'User (USER)');

    expect(getDropdownLabel('Assign role')).toBe('User (USER)');
  });

  it('offers an empty dropdown (no crash) when the roles request fails', async () => {
    server.use(
      http.get('/api/v1/rbac/roles', () =>
        HttpResponse.json({ detail: 'Forbidden' }, { status: 403 }),
      ),
    );
    renderWithProviders(<UserForm visible onHide={vi.fn()} onSubmit={vi.fn()} />);

    await rolesLoaded();
    expect(getDropdownLabel('Assign role')).toBe('Select a role');
  });
});

describe('UserForm — validation', () => {
  it('requires every field on an empty submit and does not call onSubmit', async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    renderWithProviders(<UserForm visible onHide={vi.fn()} onSubmit={onSubmit} />);
    await rolesLoaded();

    await user.click(screen.getByRole('button', { name: 'Create' }));

    expect(await screen.findByText('Username must be at least 3 characters')).toBeInTheDocument();
    // `password` has no default value, so an untouched field reaches zod as `undefined`
    // and fails with zod's own "Required" rather than the min-length message.
    expect(getValidationError('Required')).toBeInTheDocument();
    expect(getValidationError('Role is required')).toBeInTheDocument();
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('rejects a username shorter than 3 characters', async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    renderWithProviders(<UserForm visible onHide={vi.fn()} onSubmit={onSubmit} />);
    await rolesLoaded();

    await user.type(screen.getByPlaceholderText('Enter username'), 'ab');
    await user.type(screen.getByPlaceholderText('Enter password'), 'Passw0rd!');
    await selectDropdownOption(user, 'Assign role', 'User (USER)');
    await user.click(screen.getByRole('button', { name: 'Create' }));

    expect(await screen.findByText('Username must be at least 3 characters')).toBeInTheDocument();
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('rejects a password shorter than 8 characters', async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    renderWithProviders(<UserForm visible onHide={vi.fn()} onSubmit={onSubmit} />);
    await rolesLoaded();

    await user.type(screen.getByPlaceholderText('Enter username'), 'new.user');
    await user.type(screen.getByPlaceholderText('Enter password'), 'short');
    await selectDropdownOption(user, 'Assign role', 'User (USER)');
    await user.click(screen.getByRole('button', { name: 'Create' }));

    expect(await screen.findByText('Password must be at least 8 characters')).toBeInTheDocument();
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('requires a role even when username and password are valid', async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    renderWithProviders(<UserForm visible onHide={vi.fn()} onSubmit={onSubmit} />);
    await rolesLoaded();

    await fillCredentials(user);
    await user.click(screen.getByRole('button', { name: 'Create' }));

    expect(await screen.findByText('Role is required')).toBeInTheDocument();
    expect(onSubmit).not.toHaveBeenCalled();
  });
});

describe('UserForm — submit', () => {
  it('submits the entered values with the numeric role id and AD validation on by default', async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    renderWithProviders(<UserForm visible onHide={vi.fn()} onSubmit={onSubmit} />);
    await rolesLoaded();

    await fillCredentials(user);
    await selectDropdownOption(user, 'Assign role', 'Administrator (ADMIN)');
    await user.click(screen.getByRole('button', { name: 'Create' }));

    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    expect(onSubmit).toHaveBeenCalledWith({
      username: 'new.user',
      password: 'Passw0rd!',
      is_validate_ad: true,
      role_id: 11,
    });
  });

  it('submits is_validate_ad false after the switch is turned off', async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    renderWithProviders(<UserForm visible onHide={vi.fn()} onSubmit={onSubmit} />);
    await rolesLoaded();

    await fillCredentials(user);
    await selectDropdownOption(user, 'Assign role', 'User (USER)');
    await user.click(screen.getByRole('switch', { name: 'Validate with AD' }));
    await user.click(screen.getByRole('button', { name: 'Create' }));

    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({ is_validate_ad: false, role_id: 12 }),
    );
  });

  it('clears the fields after a successful submit', async () => {
    const user = userEvent.setup();
    renderWithProviders(<UserForm visible onHide={vi.fn()} onSubmit={vi.fn()} />);
    await rolesLoaded();

    await fillCredentials(user);
    await selectDropdownOption(user, 'Assign role', 'User (USER)');
    await user.click(screen.getByRole('button', { name: 'Create' }));

    await waitFor(() => expect(screen.getByPlaceholderText('Enter username')).toHaveValue(''));
    expect(getDropdownLabel('Assign role')).toBe('Select a role');
  });
});

describe('UserForm — cancel', () => {
  it('calls onHide and discards what was typed', async () => {
    const user = userEvent.setup();
    const onHide = vi.fn();
    const onSubmit = vi.fn();
    renderWithProviders(<UserForm visible onHide={onHide} onSubmit={onSubmit} />);
    await rolesLoaded();

    await user.type(screen.getByPlaceholderText('Enter username'), 'draft');
    await user.click(screen.getByRole('button', { name: 'Cancel' }));

    expect(onHide).toHaveBeenCalledTimes(1);
    expect(onSubmit).not.toHaveBeenCalled();
    expect(screen.getByPlaceholderText('Enter username')).toHaveValue('');
  });
});

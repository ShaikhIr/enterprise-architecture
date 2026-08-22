import { describe, expect, it } from 'vitest';

import { ActionGate, FieldGate, MenuGate, PermissionGate } from '@core/rbac/PermissionGate';

import type { RootState, TestPreloadedState } from '../../test-utils';
import { renderWithProviders, screen } from '../../test-utils';

const rbacState = (overrides: Partial<RootState['rbac']> = {}): TestPreloadedState => ({
  rbac: {
    menuKeys: [],
    menuPermissions: [],
    apiCodes: [],
    apiResourceActions: {},
    fieldPermissions: {},
    fieldPermissionStatus: {},
    isLoaded: false,
    isApiLoaded: false,
    isLoading: false,
    isApiLoading: false,
    error: null,
    ...overrides,
  },
});

describe('PermissionGate', () => {
  it('renders children when the permission code is granted', () => {
    renderWithProviders(
      <PermissionGate permission="reports.export">
        <span>Export button</span>
      </PermissionGate>,
      { preloadedState: rbacState({ apiCodes: ['reports.export'], isApiLoaded: true }) },
    );

    expect(screen.getByText('Export button')).toBeInTheDocument();
  });

  it('renders the fallback when the permission is denied', () => {
    renderWithProviders(
      <PermissionGate permission="reports.export" fallback={<span>No access</span>}>
        <span>Export button</span>
      </PermissionGate>,
      { preloadedState: rbacState({ isApiLoaded: true, isLoaded: true }) },
    );

    expect(screen.queryByText('Export button')).not.toBeInTheDocument();
    expect(screen.getByText('No access')).toBeInTheDocument();
  });

  it('renders nothing (not the fallback) when no fallback is supplied and access is denied', () => {
    const { container } = renderWithProviders(
      <PermissionGate permission="reports.export">
        <span>Export button</span>
      </PermissionGate>,
      { preloadedState: rbacState({ isApiLoaded: true, isLoaded: true }) },
    );

    expect(container).toBeEmptyDOMElement();
  });
});

describe('ActionGate', () => {
  it('renders children when the (resource, action) pair is granted', () => {
    renderWithProviders(
      <ActionGate resource="countries" action="CREATE">
        <span>New Country</span>
      </ActionGate>,
      {
        preloadedState: rbacState({
          apiResourceActions: { countries: ['CREATE'] },
          isApiLoaded: true,
        }),
      },
    );

    expect(screen.getByText('New Country')).toBeInTheDocument();
  });

  it('renders the fallback when the action is not granted for the resource', () => {
    renderWithProviders(
      <ActionGate resource="countries" action="DELETE" fallback={<span>Hidden</span>}>
        <span>Delete Country</span>
      </ActionGate>,
      {
        preloadedState: rbacState({
          apiResourceActions: { countries: ['CREATE'] },
          isApiLoaded: true,
        }),
      },
    );

    expect(screen.queryByText('Delete Country')).not.toBeInTheDocument();
    expect(screen.getByText('Hidden')).toBeInTheDocument();
  });
});

describe('MenuGate', () => {
  it('renders nothing while menu permissions have not loaded (not the fallback)', () => {
    const { container } = renderWithProviders(
      <MenuGate menuKey="masters" fallback={<span>Fallback</span>}>
        <span>Masters nav item</span>
      </MenuGate>,
      { preloadedState: rbacState({ isLoaded: false }) },
    );

    expect(container).toBeEmptyDOMElement();
  });

  it('renders children once loaded and the menu key is present', () => {
    renderWithProviders(
      <MenuGate menuKey="masters">
        <span>Masters nav item</span>
      </MenuGate>,
      { preloadedState: rbacState({ menuKeys: ['masters'], isLoaded: true }) },
    );

    expect(screen.getByText('Masters nav item')).toBeInTheDocument();
  });

  it('renders the fallback once loaded when the menu key is absent', () => {
    renderWithProviders(
      <MenuGate menuKey="masters" fallback={<span>No menu</span>}>
        <span>Masters nav item</span>
      </MenuGate>,
      { preloadedState: rbacState({ menuKeys: ['dashboard'], isLoaded: true }) },
    );

    expect(screen.queryByText('Masters nav item')).not.toBeInTheDocument();
    expect(screen.getByText('No menu')).toBeInTheDocument();
  });
});

describe('FieldGate', () => {
  it('renders nothing while field permissions for the resource have not settled', () => {
    const { container } = renderWithProviders(
      <FieldGate resource="users" field="salary">
        <span>Salary value</span>
      </FieldGate>,
      { preloadedState: rbacState() },
    );

    expect(container).toBeEmptyDOMElement();
  });

  it('renders children when the READ grant is present for the field', () => {
    renderWithProviders(
      <FieldGate resource="users" field="salary" action="READ">
        <span>Salary value</span>
      </FieldGate>,
      {
        preloadedState: rbacState({
          fieldPermissions: { users: { salary: ['READ'] } },
          fieldPermissionStatus: { users: 'loaded' },
        }),
      },
    );

    expect(screen.getByText('Salary value')).toBeInTheDocument();
  });

  it('checks the UPDATE grant separately from READ', () => {
    renderWithProviders(
      <FieldGate resource="users" field="salary" action="UPDATE" fallback={<span>Read-only</span>}>
        <span>Salary input</span>
      </FieldGate>,
      {
        preloadedState: rbacState({
          fieldPermissions: { users: { salary: ['READ'] } },
          fieldPermissionStatus: { users: 'loaded' },
        }),
      },
    );

    expect(screen.queryByText('Salary input')).not.toBeInTheDocument();
    expect(screen.getByText('Read-only')).toBeInTheDocument();
  });
});

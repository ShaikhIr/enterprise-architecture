/**
 * Shared fixtures for the workflow-admin tests. Not a test file (vitest only
 * collects `*.test.ts(x)`); it holds the entity fixtures and the two helpers
 * every page/form test in this folder needs.
 *
 * Ids are positive numeric bigints on purpose: the forms validate parent ids with
 * `z.number().int().positive()`, so a `0` or string id fails silently client-side.
 */

import type { PropsWithChildren } from 'react';

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { UserEvent } from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { expect } from 'vitest';

import type { PermissionAction } from '@core/rbac/types';

import type { ApprovalMatrix } from '@features/workflow-admin/models/ApprovalMatrix';
import type {
  WorkflowDefinition,
  WorkflowDefinitionDetail,
  WorkflowStatus,
  WorkflowTransition,
} from '@features/workflow-admin/models/Workflow';

import { server } from '../../mocks/server';
import { screen, waitFor, within, type TestPreloadedState } from '../../test-utils';

/**
 * Open a PrimeReact Dropdown, return the accessible names of its options, then
 * toggle the panel shut so a later call finds a single listbox.
 */
export const listDropdownOptions = async (
  user: UserEvent,
  accessibleName: string,
): Promise<string[]> => {
  const container = screen.getByLabelText(accessibleName).closest('[data-pc-name="dropdown"]');
  const trigger = container?.querySelector<HTMLElement>('.p-dropdown-trigger');
  if (!trigger) throw new Error(`listDropdownOptions: no trigger for "${accessibleName}"`);
  await user.click(trigger);
  const listbox = await screen.findByRole('listbox');
  const labels = within(listbox)
    .getAllByRole('option')
    .map((option) => option.getAttribute('aria-label') ?? option.textContent ?? '');
  await user.click(trigger);
  await waitFor(() => expect(screen.queryByRole('listbox')).not.toBeInTheDocument());
  return labels;
};

/**
 * The real `<input>` behind a PrimeReact InputSwitch / InputNumber.
 *
 * Both components copy their `aria-label` onto the visible root element as well as
 * onto the inner input, so `getByLabelText(name)` can match two elements and throw.
 * Picking the `<input>` is what a user types into / toggles.
 */
export const getInputByLabel = (accessibleName: string): HTMLInputElement => {
  const input = screen
    .getAllByLabelText(accessibleName)
    .find((element): element is HTMLInputElement => element instanceof HTMLInputElement);
  if (!input) throw new Error(`getInputByLabel: no <input> labelled "${accessibleName}"`);
  return input;
};

const AUDIT = {
  created_by: 'system',
  created_date: '2024-01-01T00:00:00Z',
  modified_by: 'system',
  modified_date: '2024-01-01T00:00:00Z',
};

/** Seeds the rbac slice as already loaded, with the given resource -> actions grants. */
export const withApiGrants = (
  grants: Record<string, PermissionAction[]>,
): TestPreloadedState => ({
  rbac: {
    menuKeys: [],
    menuPermissions: [],
    apiCodes: [],
    apiResourceActions: grants,
    fieldPermissions: {},
    fieldPermissionStatus: {},
    isLoaded: false,
    isApiLoaded: true,
    isLoading: false,
    isApiLoading: false,
    error: null,
  },
});

export const ALL_WORKFLOW_GRANTS = withApiGrants({
  workflows: ['READ', 'CREATE', 'UPDATE', 'DELETE'],
  approval_matrices: ['READ', 'CREATE', 'UPDATE', 'DELETE'],
});

export const READ_ONLY_GRANTS = withApiGrants({
  workflows: ['READ'],
  approval_matrices: ['READ'],
});

/**
 * A client for hook tests. Unlike `createTestQueryClient` it keeps the default
 * `gcTime`, because a prefetched query with no observer would otherwise be
 * garbage-collected before the test can inspect whether it was invalidated.
 */
export const createHookQueryClient = (): QueryClient =>
  new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });

export const hookWrapper = (queryClient: QueryClient) => {
  const Wrapper = ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  return Wrapper;
};

/** Prefetch a cache entry under `key` so a test can later check `isInvalidated`. */
export const seedQuery = async (queryClient: QueryClient, key: unknown[]): Promise<void> => {
  await queryClient.prefetchQuery({ queryKey: key, queryFn: () => Promise.resolve({}) });
};

// ─── Workflow fixtures ───

export const definition: WorkflowDefinition = {
  id: 7,
  code: 'RETURN_FILING',
  name: 'Return Filing Approval',
  description: 'Approval flow for filed returns',
  entity_type: 'compliance_task',
  version: 3,
  is_active: true,
  ...AUDIT,
};

export const initialStatus: WorkflowStatus = {
  id: 101,
  workflow_definition_id: 7,
  code: 'DRAFT',
  name: 'Draft',
  is_initial: true,
  is_terminal: false,
  sequence: 0,
};

export const middleStatus: WorkflowStatus = {
  id: 102,
  workflow_definition_id: 7,
  code: 'IN_REVIEW',
  name: 'In Review',
  is_initial: false,
  is_terminal: false,
  sequence: 10,
};

export const terminalStatus: WorkflowStatus = {
  id: 103,
  workflow_definition_id: 7,
  code: 'APPROVED',
  name: 'Approved',
  is_initial: false,
  is_terminal: true,
  sequence: 20,
};

export const submitTransition: WorkflowTransition = {
  id: 201,
  workflow_definition_id: 7,
  from_status_id: 101,
  to_status_id: 102,
  action_code: 'SEND_FOR_REVIEW',
  action_type: 'SUBMIT',
  guard_expression: null,
  requires_comment: true,
  auto_execute: false,
  priority: 0,
};

export const detail = (overrides: Partial<WorkflowDefinitionDetail> = {}): WorkflowDefinitionDetail => ({
  definition,
  statuses: [initialStatus, middleStatus, terminalStatus],
  transitions: [submitTransition],
  ...overrides,
});

// ─── Approval matrix fixtures ───

export const matrix: ApprovalMatrix = {
  id: 31,
  code: 'FILING_BY_AMOUNT',
  name: 'Filing approval by amount',
  entity_type: 'compliance_task',
  priority: 5,
  is_active: true,
  rules: [
    {
      id: 1,
      field: 'amount',
      operator: 'GT',
      value: '100000',
      data_type: 'NUMBER',
      logical_group: 'default',
    },
  ],
  assignments: [
    { id: 1, level: 1, assignment_type: 'ROLE', user_id: null, role_id: 901 },
    { id: 2, level: 2, assignment_type: 'USER', user_id: 801, role_id: null },
  ],
  ...AUDIT,
};

export const ROLE_ADMIN_ID = 901;
export const ROLE_REVIEWER_ID = 902;
export const USER_ALICE_ID = 801;
export const USER_BOB_ID = 802;

/** Roles + users lookups that `ApprovalMatrixForm` loads on mount (even while hidden). */
export const mockMatrixFormLookups = (): void =>
  server.use(
    http.get('/api/v1/rbac/roles', () =>
      HttpResponse.json({
        roles: [
          { id: ROLE_ADMIN_ID, code: 'ADMIN', name: 'Admin', is_active: true },
          { id: ROLE_REVIEWER_ID, code: 'REVIEWER', name: 'Reviewer', is_active: true },
          { id: 999, code: 'RETIRED', name: 'Retired', is_active: false },
        ],
        total: 3,
      }),
    ),
    http.get('/api/v1/users', () =>
      HttpResponse.json({
        users: [
          {
            id: USER_ALICE_ID,
            username: 'alice',
            employee_name: 'Alice Anand',
            is_active: true,
            is_blocked: false,
            is_validate_ad: false,
            employee_id: null,
            email: null,
            last_login: null,
            ...AUDIT,
          },
          {
            id: USER_BOB_ID,
            username: 'bob',
            employee_name: null,
            is_active: true,
            is_blocked: false,
            is_validate_ad: false,
            employee_id: null,
            email: null,
            last_login: null,
            ...AUDIT,
          },
        ],
        total: 2,
        skip: 0,
        limit: 500,
      }),
    ),
  );

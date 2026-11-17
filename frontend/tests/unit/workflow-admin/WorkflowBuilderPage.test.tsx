import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { Route, Routes } from 'react-router-dom';
import { describe, expect, it } from 'vitest';

import { WorkflowBuilderPage } from '@features/workflow-admin/pages/WorkflowBuilderPage';

import { server } from '../../mocks/server';
import {
  renderWithProviders,
  screen,
  selectDropdownOption,
  waitFor,
  within,
} from '../../test-utils';

import {
  ALL_WORKFLOW_GRANTS,
  READ_ONLY_GRANTS,
  definition,
  detail,
  getInputByLabel,
  initialStatus,
  middleStatus,
  submitTransition,
  terminalStatus,
  withApiGrants,
} from './fixtures';

type Detail = ReturnType<typeof detail>;

/** Serves the definition detail and counts how many times it has been fetched. */
const mockDetail = (payload: Detail = detail()) => {
  const state = { fetches: 0 };
  server.use(
    http.get('/api/v1/workflow/definitions/7', () => {
      state.fetches += 1;
      return HttpResponse.json(payload);
    }),
  );
  return state;
};

const renderPage = (preloadedState = ALL_WORKFLOW_GRANTS) =>
  renderWithProviders(
    <Routes>
      <Route path="/workflows/:definitionId" element={<WorkflowBuilderPage />} />
      <Route path="/workflows" element={<div>Workflows list route reached</div>} />
    </Routes>,
    { preloadedState, initialEntries: ['/workflows/7'] },
  );

/** Wait for the page to leave its loading state and return the [states, transitions] tables. */
const loadedTables = async () => {
  await screen.findByRole('heading', { name: 'Return Filing Approval' });
  const [states, transitions] = screen.getAllByRole('table');
  if (!states || !transitions) throw new Error('expected the states and transitions tables');
  return { states, transitions };
};

describe('WorkflowBuilderPage', () => {
  describe('loading and failure states', () => {
    it('shows a spinner while the definition loads', async () => {
      mockDetail();
      renderPage();

      expect(screen.getByRole('progressbar')).toBeInTheDocument();
      await screen.findByRole('heading', { name: 'Return Filing Approval' });
      expect(screen.queryByRole('progressbar')).not.toBeInTheDocument();
    });

    it('shows the backend message and a way back when the definition cannot be loaded', async () => {
      const user = userEvent.setup();
      server.use(
        http.get('/api/v1/workflow/definitions/7', () =>
          HttpResponse.json({ message: 'Workflow 7 not found' }, { status: 404 }),
        ),
      );
      renderPage();

      expect(await screen.findByText('Workflow 7 not found')).toBeInTheDocument();
      await user.click(screen.getByRole('button', { name: 'Back to Workflows' }));
      expect(await screen.findByText('Workflows list route reached')).toBeInTheDocument();
    });

    it('falls back to a generic message when the error has no detail', async () => {
      server.use(
        http.get('/api/v1/workflow/definitions/7', () => new HttpResponse(null, { status: 500 })),
      );
      renderPage();

      expect(await screen.findByText('This workflow could not be loaded.')).toBeInTheDocument();
    });

    it('shows the load-failure message without any request when the route has no definition id', () => {
      // No Route wrapper, so `useParams` yields no `definitionId`; an unhandled request would
      // fail the test loudly (onUnhandledRequest: 'error').
      renderWithProviders(<WorkflowBuilderPage />, { preloadedState: ALL_WORKFLOW_GRANTS });

      expect(screen.getByText('This workflow could not be loaded.')).toBeInTheDocument();
    });
  });

  describe('header', () => {
    it('shows the definition name, code, entity type, version and Active tag', async () => {
      mockDetail();
      renderPage();

      expect(
        await screen.findByRole('heading', { name: 'Return Filing Approval' }),
      ).toBeInTheDocument();
      expect(screen.getByText('Active')).toBeInTheDocument();
      expect(screen.getByText(/RETURN_FILING · governs/)).toBeInTheDocument();
      expect(screen.getByText('compliance_task')).toBeInTheDocument();
      expect(screen.getByText(/version\s+3/)).toBeInTheDocument();
    });

    it('shows an Inactive tag for an inactive definition', async () => {
      mockDetail(detail({ definition: { ...definition, is_active: false } }));
      renderPage();

      await screen.findByRole('heading', { name: 'Return Filing Approval' });
      expect(screen.getByText('Inactive')).toBeInTheDocument();
    });

    it('goes back to the workflows list from the arrow button', async () => {
      const user = userEvent.setup();
      mockDetail();
      renderPage();

      await user.click(await screen.findByRole('button', { name: 'Back to workflows' }));

      expect(await screen.findByText('Workflows list route reached')).toBeInTheDocument();
    });
  });

  describe('state-machine health messages', () => {
    it('warns that a workflow with no states cannot be started', async () => {
      mockDetail(detail({ statuses: [], transitions: [] }));
      renderPage();

      await screen.findByRole('heading', { name: 'Return Filing Approval' });
      expect(screen.getByText(/has no initial state, so it cannot be started/)).toBeInTheDocument();
      expect(screen.queryByText(/No terminal state yet/)).not.toBeInTheDocument();
    });

    it('warns when states exist but none is initial', async () => {
      mockDetail(detail({ statuses: [middleStatus, terminalStatus], transitions: [] }));
      renderPage();

      await screen.findByRole('heading', { name: 'Return Filing Approval' });
      expect(screen.getByText(/has no initial state, so it cannot be started/)).toBeInTheDocument();
    });

    it('notes a missing terminal state once an initial state exists', async () => {
      mockDetail(detail({ statuses: [initialStatus, middleStatus], transitions: [] }));
      renderPage();

      await screen.findByRole('heading', { name: 'Return Filing Approval' });
      expect(screen.getByText(/No terminal state yet/)).toBeInTheDocument();
      expect(screen.queryByText(/has no initial state/)).not.toBeInTheDocument();
    });

    it('shows neither message for a complete workflow', async () => {
      mockDetail();
      renderPage();

      await screen.findByRole('heading', { name: 'Return Filing Approval' });
      expect(screen.queryByText(/has no initial state/)).not.toBeInTheDocument();
      expect(screen.queryByText(/No terminal state yet/)).not.toBeInTheDocument();
    });
  });

  describe('tables', () => {
    it('lists every state with its position tag', async () => {
      mockDetail();
      renderPage();

      const { states } = await loadedTables();

      expect(within(states).getByText('Draft')).toBeInTheDocument();
      expect(within(states).getByText('Initial')).toBeInTheDocument();
      expect(within(states).getByText('In Review')).toBeInTheDocument();
      expect(within(states).getByText('Intermediate')).toBeInTheDocument();
      expect(within(states).getByText('Approved')).toBeInTheDocument();
      expect(within(states).getByText('Terminal')).toBeInTheDocument();
    });

    it('lists transitions with resolved state codes, type and comment requirement', async () => {
      mockDetail();
      renderPage();

      const { transitions } = await loadedTables();

      expect(within(transitions).getByText('DRAFT')).toBeInTheDocument();
      expect(within(transitions).getByText('SEND_FOR_REVIEW')).toBeInTheDocument();
      expect(within(transitions).getByText('SUBMIT')).toBeInTheDocument();
      expect(within(transitions).getByText('IN_REVIEW')).toBeInTheDocument();
      expect(within(transitions).getByText('Required')).toBeInTheDocument();
    });

    it('shows "Unknown" for a transition that points at a state not in the definition', async () => {
      mockDetail(
        detail({ transitions: [{ ...submitTransition, id: 202, to_status_id: 99999 }] }),
      );
      renderPage();

      const { transitions } = await loadedTables();

      expect(within(transitions).getByText('Unknown')).toBeInTheDocument();
    });

    it('shows the empty messages when there are no states or transitions', async () => {
      mockDetail(detail({ statuses: [], transitions: [] }));
      renderPage();

      await screen.findByRole('heading', { name: 'Return Filing Approval' });
      expect(screen.getByText('No states defined. Add an initial state to begin.')).toBeVisible();
      expect(
        screen.getByText('No transitions defined. Wire an action between two states.'),
      ).toBeVisible();
    });
  });

  describe('permission gating', () => {
    it('shows every add and row action to a caller with every grant', async () => {
      mockDetail();
      renderPage();

      await loadedTables();
      expect(screen.getByRole('button', { name: 'Add state' })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'Add transition' })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'Edit state Draft' })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'Delete state Draft' })).toBeInTheDocument();
      expect(
        screen.getByRole('button', { name: 'Delete transition SEND_FOR_REVIEW' }),
      ).toBeInTheDocument();
    });

    it('hides every add and row action from a read-only caller', async () => {
      mockDetail();
      renderPage(READ_ONLY_GRANTS);

      await loadedTables();
      expect(screen.queryByRole('button', { name: 'Add state' })).not.toBeInTheDocument();
      expect(screen.queryByRole('button', { name: 'Add transition' })).not.toBeInTheDocument();
      expect(screen.queryByRole('button', { name: /^Edit state / })).not.toBeInTheDocument();
      expect(screen.queryByRole('button', { name: /^Delete state / })).not.toBeInTheDocument();
      expect(screen.queryByRole('button', { name: /^Delete transition / })).not.toBeInTheDocument();
    });

    it('lets UPDATE and DELETE be granted independently', async () => {
      mockDetail();
      renderPage(withApiGrants({ workflows: ['UPDATE'] }));

      await loadedTables();
      expect(screen.getByRole('button', { name: 'Edit state Draft' })).toBeInTheDocument();
      expect(screen.queryByRole('button', { name: /^Delete state / })).not.toBeInTheDocument();
      expect(screen.queryByRole('button', { name: /^Delete transition / })).not.toBeInTheDocument();
    });

    it('disables Add Transition until the workflow has at least two states', async () => {
      mockDetail(detail({ statuses: [initialStatus], transitions: [] }));
      renderPage();

      await screen.findByRole('heading', { name: 'Return Filing Approval' });
      expect(screen.getByRole('button', { name: 'Add transition' })).toBeDisabled();
    });

    it('enables Add Transition once there are two states', async () => {
      mockDetail();
      renderPage();

      await loadedTables();
      expect(screen.getByRole('button', { name: 'Add transition' })).toBeEnabled();
    });
  });

  describe('add state flow', () => {
    it('posts the new state with the suggested next sequence, toasts, closes and refetches', async () => {
      const user = userEvent.setup();
      let body: unknown;
      const counter = mockDetail();
      server.use(
        http.post('/api/v1/workflow/definitions/7/statuses', async ({ request }) => {
          body = await request.json();
          return HttpResponse.json({ ...middleStatus, id: 104, code: 'ESCALATED' });
        }),
      );
      renderPage();
      await loadedTables();
      expect(counter.fetches).toBe(1);

      await user.click(screen.getByRole('button', { name: 'Add state' }));
      // The highest existing sequence is 20, so the suggestion is 20 + 10.
      expect(getInputByLabel('Display order')).toHaveValue('30');
      await user.type(screen.getByLabelText('Code'), 'ESCALATED');
      await user.type(screen.getByLabelText('Name'), 'Escalated');
      await user.click(screen.getByRole('button', { name: 'Add State' }));

      await waitFor(() => expect(screen.getByText("State 'ESCALATED' added")).toBeInTheDocument());
      expect(body).toEqual({
        code: 'ESCALATED',
        name: 'Escalated',
        sequence: 30,
        is_initial: false,
        is_terminal: false,
      });
      await waitFor(() => expect(counter.fetches).toBe(2));
      await waitFor(() =>
        expect(screen.queryByLabelText('Workflow state dialog')).not.toBeInTheDocument(),
      );
    });

    it('suggests sequence 0 for the first state of an empty workflow', async () => {
      const user = userEvent.setup();
      mockDetail(detail({ statuses: [], transitions: [] }));
      renderPage();
      await screen.findByRole('heading', { name: 'Return Filing Approval' });

      await user.click(screen.getByRole('button', { name: 'Add state' }));

      expect(getInputByLabel('Display order')).toHaveValue('0');
    });

    it('shows the backend message and keeps the dialog open when the state is rejected', async () => {
      const user = userEvent.setup();
      mockDetail();
      server.use(
        http.post('/api/v1/workflow/definitions/7/statuses', () =>
          HttpResponse.json(
            { message: 'Workflow already has an initial state' },
            { status: 409 },
          ),
        ),
      );
      renderPage();
      await loadedTables();

      await user.click(screen.getByRole('button', { name: 'Add state' }));
      await user.type(screen.getByLabelText('Code'), 'START');
      await user.type(screen.getByLabelText('Name'), 'Start');
      await user.click(screen.getByRole('button', { name: 'Add State' }));

      await waitFor(() =>
        expect(screen.getByText('Workflow already has an initial state')).toBeInTheDocument(),
      );
      expect(screen.getByLabelText('Workflow state dialog')).toBeInTheDocument();
    });
  });

  describe('edit state flow', () => {
    it('opens the dialog pre-filled and patches the state by its id', async () => {
      const user = userEvent.setup();
      let body: unknown;
      const counter = mockDetail();
      server.use(
        http.patch('/api/v1/workflow/statuses/102', async ({ request }) => {
          body = await request.json();
          return HttpResponse.json({ ...middleStatus, name: 'Under Review' });
        }),
      );
      renderPage();
      await loadedTables();

      await user.click(screen.getByRole('button', { name: 'Edit state In Review' }));
      expect(screen.getByText('Edit State — IN_REVIEW')).toBeInTheDocument();
      expect(screen.getByLabelText('Name')).toHaveValue('In Review');
      await user.clear(screen.getByLabelText('Name'));
      await user.type(screen.getByLabelText('Name'), 'Under Review');
      await user.click(screen.getByRole('button', { name: 'Save Changes' }));

      await waitFor(() =>
        expect(screen.getByText("State 'IN_REVIEW' updated")).toBeInTheDocument(),
      );
      expect(body).toEqual({
        code: 'IN_REVIEW',
        name: 'Under Review',
        sequence: 10,
        is_initial: false,
        is_terminal: false,
      });
      await waitFor(() => expect(counter.fetches).toBe(2));
    });

    it('opens the next "Add State" dialog empty after an edit was closed', async () => {
      const user = userEvent.setup();
      mockDetail();
      renderPage();
      await loadedTables();

      await user.click(screen.getByRole('button', { name: 'Edit state In Review' }));
      await user.click(screen.getByRole('button', { name: 'Cancel' }));
      await user.click(screen.getByRole('button', { name: 'Add state' }));

      expect(screen.getByText('Add State', { selector: '.p-dialog-title' })).toBeInTheDocument();
      expect(screen.getByLabelText('Name')).toHaveValue('');
    });
  });

  describe('delete state flow', () => {
    it('confirms, deletes, toasts and refetches', async () => {
      const user = userEvent.setup();
      let deleted = false;
      const counter = mockDetail();
      server.use(
        http.delete('/api/v1/workflow/statuses/102', () => {
          deleted = true;
          return new HttpResponse(null, { status: 204 });
        }),
      );
      renderPage();
      await loadedTables();

      await user.click(screen.getByRole('button', { name: 'Delete state In Review' }));
      const confirm = await screen.findByRole('dialog', { name: 'Delete state' });
      expect(within(confirm).getByText(/Delete state 'In Review'\?/)).toBeInTheDocument();
      await user.click(within(confirm).getByText('Delete'));

      await waitFor(() =>
        expect(screen.getByText("State 'IN_REVIEW' deleted")).toBeInTheDocument(),
      );
      expect(deleted).toBe(true);
      await waitFor(() => expect(counter.fetches).toBe(2));
    });

    it('shows the backend message when the state is still referenced', async () => {
      const user = userEvent.setup();
      mockDetail();
      server.use(
        http.delete('/api/v1/workflow/statuses/102', () =>
          HttpResponse.json(
            { message: "State 'IN_REVIEW' is used by a transition" },
            { status: 409 },
          ),
        ),
      );
      renderPage();
      await loadedTables();

      await user.click(screen.getByRole('button', { name: 'Delete state In Review' }));
      const confirm = await screen.findByRole('dialog', { name: 'Delete state' });
      await user.click(within(confirm).getByText('Delete'));

      await waitFor(() =>
        expect(screen.getByText("State 'IN_REVIEW' is used by a transition")).toBeInTheDocument(),
      );
    });

    it('does not delete when the confirmation is cancelled', async () => {
      const user = userEvent.setup();
      let deleted = false;
      mockDetail();
      server.use(
        http.delete('/api/v1/workflow/statuses/102', () => {
          deleted = true;
          return new HttpResponse(null, { status: 204 });
        }),
      );
      renderPage();
      await loadedTables();

      await user.click(screen.getByRole('button', { name: 'Delete state In Review' }));
      const confirm = await screen.findByRole('dialog', { name: 'Delete state' });
      await user.click(within(confirm).getByText('Cancel'));

      await waitFor(() =>
        expect(screen.queryByRole('dialog', { name: 'Delete state' })).not.toBeInTheDocument(),
      );
      expect(deleted).toBe(false);
    });
  });

  describe('add transition flow', () => {
    it('posts the wired-up transition, toasts, closes and refetches', async () => {
      const user = userEvent.setup();
      let body: unknown;
      const counter = mockDetail();
      server.use(
        http.post('/api/v1/workflow/definitions/7/transitions', async ({ request }) => {
          body = await request.json();
          return HttpResponse.json({ ...submitTransition, id: 203 });
        }),
      );
      renderPage();
      await loadedTables();

      await user.click(screen.getByRole('button', { name: 'Add transition' }));
      await selectDropdownOption(user, 'Source state', 'In Review (IN_REVIEW)');
      await selectDropdownOption(user, 'Target state', 'Approved (APPROVED)');
      await user.type(screen.getByLabelText('Action Code'), 'SIGN_OFF');
      await selectDropdownOption(user, 'Action type', 'Approve');
      await user.click(screen.getByRole('button', { name: 'Add Transition' }));

      await waitFor(() =>
        expect(screen.getByText("Action 'SIGN_OFF' wired up")).toBeInTheDocument(),
      );
      expect(body).toEqual({
        from_status_id: 102,
        to_status_id: 103,
        action_code: 'SIGN_OFF',
        action_type: 'APPROVE',
        requires_comment: false,
        auto_execute: false,
        priority: 0,
        guard_expression: null,
      });
      await waitFor(() => expect(counter.fetches).toBe(2));
      await waitFor(() =>
        expect(screen.queryByLabelText('Workflow transition dialog')).not.toBeInTheDocument(),
      );
    });

    it('shows the backend message and keeps the dialog open when the transition is rejected', async () => {
      const user = userEvent.setup();
      mockDetail();
      server.use(
        http.post('/api/v1/workflow/definitions/7/transitions', () =>
          HttpResponse.json({ message: 'Transition already exists' }, { status: 409 }),
        ),
      );
      renderPage();
      await loadedTables();

      await user.click(screen.getByRole('button', { name: 'Add transition' }));
      await selectDropdownOption(user, 'Source state', 'Draft (DRAFT)');
      await selectDropdownOption(user, 'Target state', 'In Review (IN_REVIEW)');
      await user.type(screen.getByLabelText('Action Code'), 'SEND_FOR_REVIEW');
      await user.click(screen.getByRole('button', { name: 'Add Transition' }));

      await waitFor(() =>
        expect(screen.getByText('Transition already exists')).toBeInTheDocument(),
      );
      expect(screen.getByLabelText('Workflow transition dialog')).toBeInTheDocument();
    });
  });

  describe('delete transition flow', () => {
    it('confirms, deletes, toasts and refetches', async () => {
      const user = userEvent.setup();
      let deleted = false;
      const counter = mockDetail();
      server.use(
        http.delete('/api/v1/workflow/transitions/201', () => {
          deleted = true;
          return new HttpResponse(null, { status: 204 });
        }),
      );
      renderPage();
      await loadedTables();

      await user.click(screen.getByRole('button', { name: 'Delete transition SEND_FOR_REVIEW' }));
      const confirm = await screen.findByRole('dialog', { name: 'Delete transition' });
      expect(
        within(confirm).getByText("Remove the 'SEND_FOR_REVIEW' transition?"),
      ).toBeInTheDocument();
      await user.click(within(confirm).getByText('Delete'));

      await waitFor(() => expect(screen.getByText('Transition removed')).toBeInTheDocument());
      expect(deleted).toBe(true);
      await waitFor(() => expect(counter.fetches).toBe(2));
    });

    it('shows the backend message when the delete is rejected', async () => {
      const user = userEvent.setup();
      mockDetail();
      server.use(
        http.delete('/api/v1/workflow/transitions/201', () =>
          HttpResponse.json({ message: 'Transition is in use' }, { status: 409 }),
        ),
      );
      renderPage();
      await loadedTables();

      await user.click(screen.getByRole('button', { name: 'Delete transition SEND_FOR_REVIEW' }));
      const confirm = await screen.findByRole('dialog', { name: 'Delete transition' });
      await user.click(within(confirm).getByText('Delete'));

      await waitFor(() => expect(screen.getByText('Transition is in use')).toBeInTheDocument());
    });
  });
});

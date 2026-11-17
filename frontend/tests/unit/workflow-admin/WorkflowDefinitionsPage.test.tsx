import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { Route, Routes } from 'react-router-dom';
import { describe, expect, it } from 'vitest';

import { WorkflowDefinitionsPage } from '@features/workflow-admin/pages/WorkflowDefinitionsPage';

import { server } from '../../mocks/server';
import { renderWithProviders, screen, waitFor, within } from '../../test-utils';

import { ALL_WORKFLOW_GRANTS, READ_ONLY_GRANTS, definition, withApiGrants } from './fixtures';

const inactiveDefinition = {
  ...definition,
  id: 8,
  code: 'LICENCE_RENEWAL',
  name: 'Licence Renewal',
  entity_type: 'licence',
  version: 1,
  is_active: false,
};

const mockList = (definitions = [definition, inactiveDefinition]) =>
  server.use(
    http.get('/api/v1/workflow/definitions', () =>
      HttpResponse.json({ definitions, total: definitions.length, skip: 0, limit: 100 }),
    ),
  );

/** The page plus stub destinations, so navigation can be asserted by what renders. */
const renderPage = (preloadedState = ALL_WORKFLOW_GRANTS) =>
  renderWithProviders(
    <Routes>
      <Route path="/workflows" element={<WorkflowDefinitionsPage />} />
      <Route path="/workflows/:definitionId" element={<div>Builder route reached</div>} />
      <Route path="/approval-matrix" element={<div>Approval matrix route reached</div>} />
    </Routes>,
    { preloadedState, initialEntries: ['/workflows'] },
  );

describe('WorkflowDefinitionsPage', () => {
  describe('rendering', () => {
    it('renders the heading and the fetched definitions with status tags', async () => {
      mockList();
      renderPage();

      expect(screen.getByRole('heading', { name: 'Workflows' })).toBeInTheDocument();
      const table = screen.getByRole('table');
      expect(await within(table).findByText('Return Filing Approval')).toBeInTheDocument();
      expect(within(table).getByText('RETURN_FILING')).toBeInTheDocument();
      expect(within(table).getByText('compliance_task')).toBeInTheDocument();
      expect(within(table).getByText('3')).toBeInTheDocument();
      expect(within(table).getByText('Licence Renewal')).toBeInTheDocument();
      expect(within(table).getByText('Active')).toBeInTheDocument();
      expect(within(table).getByText('Inactive')).toBeInTheDocument();
    });

    it('shows the empty message when there are no workflows', async () => {
      mockList([]);
      renderPage();

      expect(await screen.findByText('No workflows defined yet.')).toBeInTheDocument();
    });

    it('refetches the list when Refresh is clicked', async () => {
      const user = userEvent.setup();
      let calls = 0;
      server.use(
        http.get('/api/v1/workflow/definitions', () => {
          calls += 1;
          return HttpResponse.json({ definitions: [definition], total: 1, skip: 0, limit: 100 });
        }),
      );
      renderPage();
      await screen.findByText('Return Filing Approval');
      expect(calls).toBe(1);

      await user.click(screen.getByRole('button', { name: 'Refresh workflows' }));

      await waitFor(() => expect(calls).toBe(2));
    });
  });

  describe('permission gating', () => {
    it('shows New Workflow and the Edit/Delete row actions to a caller with every grant', async () => {
      mockList();
      renderPage();

      await screen.findByText('Return Filing Approval');
      expect(screen.getByRole('button', { name: 'Create new workflow' })).toBeInTheDocument();
      expect(
        screen.getByRole('button', { name: 'Edit Return Filing Approval' }),
      ).toBeInTheDocument();
      expect(
        screen.getByRole('button', { name: 'Delete Return Filing Approval' }),
      ).toBeInTheDocument();
    });

    it('hides New Workflow, Edit and Delete from a read-only caller but keeps Open builder', async () => {
      mockList();
      renderPage(READ_ONLY_GRANTS);

      await screen.findByText('Return Filing Approval');
      expect(screen.queryByRole('button', { name: 'Create new workflow' })).not.toBeInTheDocument();
      expect(screen.queryByRole('button', { name: /^Edit / })).not.toBeInTheDocument();
      expect(screen.queryByRole('button', { name: /^Delete / })).not.toBeInTheDocument();
      expect(
        screen.getByRole('button', { name: 'Open builder for Return Filing Approval' }),
      ).toBeInTheDocument();
    });

    it('lets UPDATE and DELETE be granted independently', async () => {
      mockList();
      renderPage(withApiGrants({ workflows: ['UPDATE'] }));

      await screen.findByText('Return Filing Approval');
      expect(
        screen.getByRole('button', { name: 'Edit Return Filing Approval' }),
      ).toBeInTheDocument();
      expect(screen.queryByRole('button', { name: /^Delete / })).not.toBeInTheDocument();
    });

    it('hides the Approval Matrix shortcut without approval_matrices READ', async () => {
      mockList();
      renderPage(withApiGrants({ workflows: ['READ', 'CREATE'] }));

      await screen.findByText('Return Filing Approval');
      expect(
        screen.queryByRole('button', { name: 'Go to approval matrix' }),
      ).not.toBeInTheDocument();
    });
  });

  describe('navigation', () => {
    it('opens the builder for the clicked workflow', async () => {
      const user = userEvent.setup();
      mockList();
      renderPage();

      await user.click(
        await screen.findByRole('button', { name: 'Open builder for Return Filing Approval' }),
      );

      expect(await screen.findByText('Builder route reached')).toBeInTheDocument();
    });

    it('goes to the approval matrix page from the shortcut button', async () => {
      const user = userEvent.setup();
      mockList();
      renderPage();

      await user.click(await screen.findByRole('button', { name: 'Go to approval matrix' }));

      expect(await screen.findByText('Approval matrix route reached')).toBeInTheDocument();
    });
  });

  describe('create flow', () => {
    it('creates a workflow end to end: opens the dialog, posts the form and shows a success toast', async () => {
      const user = userEvent.setup();
      let body: unknown;
      mockList([]);
      server.use(
        http.post('/api/v1/workflow/definitions', async ({ request }) => {
          body = await request.json();
          return HttpResponse.json({ ...definition, id: 9, code: 'NEW_FLOW', name: 'New Flow' });
        }),
      );
      renderPage();
      await screen.findByText('No workflows defined yet.');

      await user.click(screen.getByRole('button', { name: 'Create new workflow' }));
      await user.type(screen.getByLabelText('Code'), 'NEW_FLOW');
      await user.type(screen.getByLabelText('Name'), 'New Flow');
      await user.type(screen.getByLabelText('Entity Type'), 'compliance_task');
      await user.click(screen.getByRole('button', { name: 'Create' }));

      await waitFor(() =>
        expect(screen.getByText("Workflow 'NEW_FLOW' created")).toBeInTheDocument(),
      );
      expect(body).toEqual({
        code: 'NEW_FLOW',
        name: 'New Flow',
        entity_type: 'compliance_task',
        description: '',
        is_active: true,
      });
      await waitFor(() =>
        expect(screen.queryByLabelText('Workflow definition dialog')).not.toBeInTheDocument(),
      );
    });

    it('refetches the list after a successful create', async () => {
      const user = userEvent.setup();
      let listCalls = 0;
      server.use(
        http.get('/api/v1/workflow/definitions', () => {
          listCalls += 1;
          return HttpResponse.json({ definitions: [], total: 0, skip: 0, limit: 100 });
        }),
        http.post('/api/v1/workflow/definitions', () => HttpResponse.json(definition)),
      );
      renderPage();
      await screen.findByText('No workflows defined yet.');
      expect(listCalls).toBe(1);

      await user.click(screen.getByRole('button', { name: 'Create new workflow' }));
      await user.type(screen.getByLabelText('Code'), 'NEW_FLOW');
      await user.type(screen.getByLabelText('Name'), 'New Flow');
      await user.type(screen.getByLabelText('Entity Type'), 'task');
      await user.click(screen.getByRole('button', { name: 'Create' }));

      await waitFor(() => expect(listCalls).toBe(2));
    });

    it('shows the backend message and keeps the dialog open when the create is rejected', async () => {
      const user = userEvent.setup();
      mockList([]);
      server.use(
        http.post('/api/v1/workflow/definitions', () =>
          HttpResponse.json({ message: "Workflow 'NEW_FLOW' already exists" }, { status: 409 }),
        ),
      );
      renderPage();
      await screen.findByText('No workflows defined yet.');

      await user.click(screen.getByRole('button', { name: 'Create new workflow' }));
      await user.type(screen.getByLabelText('Code'), 'NEW_FLOW');
      await user.type(screen.getByLabelText('Name'), 'New Flow');
      await user.type(screen.getByLabelText('Entity Type'), 'task');
      await user.click(screen.getByRole('button', { name: 'Create' }));

      await waitFor(() =>
        expect(screen.getByText("Workflow 'NEW_FLOW' already exists")).toBeInTheDocument(),
      );
      expect(screen.getByLabelText('Workflow definition dialog')).toBeInTheDocument();
    });

    it('falls back to a generic message when the error carries no detail', async () => {
      const user = userEvent.setup();
      mockList([]);
      server.use(
        http.post('/api/v1/workflow/definitions', () => new HttpResponse(null, { status: 500 })),
      );
      renderPage();
      await screen.findByText('No workflows defined yet.');

      await user.click(screen.getByRole('button', { name: 'Create new workflow' }));
      await user.type(screen.getByLabelText('Code'), 'NEW_FLOW');
      await user.type(screen.getByLabelText('Name'), 'New Flow');
      await user.type(screen.getByLabelText('Entity Type'), 'task');
      await user.click(screen.getByRole('button', { name: 'Create' }));

      await waitFor(() =>
        expect(screen.getByText('Failed to save the workflow')).toBeInTheDocument(),
      );
    });
  });

  describe('edit flow', () => {
    it('opens the dialog pre-filled and patches without the immutable code', async () => {
      const user = userEvent.setup();
      let body: unknown;
      mockList([definition]);
      server.use(
        http.patch('/api/v1/workflow/definitions/7', async ({ request }) => {
          body = await request.json();
          return HttpResponse.json({ ...definition, name: 'Renamed Flow' });
        }),
      );
      renderPage();

      await user.click(await screen.findByRole('button', { name: 'Edit Return Filing Approval' }));
      expect(screen.getByText('Edit Workflow — RETURN_FILING')).toBeInTheDocument();
      expect(screen.getByLabelText('Name')).toHaveValue('Return Filing Approval');
      await user.clear(screen.getByLabelText('Name'));
      await user.type(screen.getByLabelText('Name'), 'Renamed Flow');
      await user.click(screen.getByRole('button', { name: 'Save Changes' }));

      await waitFor(() =>
        expect(screen.getByText("Workflow 'RETURN_FILING' updated")).toBeInTheDocument(),
      );
      expect(body).toEqual({
        name: 'Renamed Flow',
        entity_type: 'compliance_task',
        description: 'Approval flow for filed returns',
        is_active: true,
      });
      expect(body).not.toHaveProperty('code');
    });

    it('opens the next "New Workflow" dialog empty after an edit was closed', async () => {
      const user = userEvent.setup();
      mockList([definition]);
      renderPage();

      await user.click(await screen.findByRole('button', { name: 'Edit Return Filing Approval' }));
      await user.click(screen.getByRole('button', { name: 'Cancel' }));
      await user.click(screen.getByRole('button', { name: 'Create new workflow' }));

      expect(screen.getByText('New Workflow', { selector: '.p-dialog-title' })).toBeInTheDocument();
      expect(screen.getByLabelText('Name')).toHaveValue('');
      expect(screen.getByLabelText('Code')).toBeEnabled();
    });
  });

  describe('delete flow', () => {
    it('confirms, deletes and shows a success toast', async () => {
      const user = userEvent.setup();
      let deleted = false;
      mockList([definition]);
      server.use(
        http.delete('/api/v1/workflow/definitions/7', () => {
          deleted = true;
          return new HttpResponse(null, { status: 204 });
        }),
      );
      renderPage();

      await user.click(
        await screen.findByRole('button', { name: 'Delete Return Filing Approval' }),
      );
      const confirm = await screen.findByRole('dialog', { name: 'Delete workflow' });
      expect(within(confirm).getByText(/Delete 'Return Filing Approval'\?/)).toBeInTheDocument();
      await user.click(within(confirm).getByText('Delete'));

      await waitFor(() =>
        expect(screen.getByText("Workflow 'RETURN_FILING' deleted")).toBeInTheDocument(),
      );
      expect(deleted).toBe(true);
    });

    it('does not delete anything when the confirmation is cancelled', async () => {
      const user = userEvent.setup();
      let deleted = false;
      mockList([definition]);
      server.use(
        http.delete('/api/v1/workflow/definitions/7', () => {
          deleted = true;
          return new HttpResponse(null, { status: 204 });
        }),
      );
      renderPage();

      await user.click(
        await screen.findByRole('button', { name: 'Delete Return Filing Approval' }),
      );
      const confirm = await screen.findByRole('dialog', { name: 'Delete workflow' });
      await user.click(within(confirm).getByText('Cancel'));

      await waitFor(() =>
        expect(screen.queryByRole('dialog', { name: 'Delete workflow' })).not.toBeInTheDocument(),
      );
      expect(deleted).toBe(false);
    });

    it('shows the backend conflict message when the workflow still has instances', async () => {
      const user = userEvent.setup();
      mockList([definition]);
      server.use(
        http.delete('/api/v1/workflow/definitions/7', () =>
          HttpResponse.json(
            { message: 'Workflow has 3 running instance(s); deactivate it instead' },
            { status: 409 },
          ),
        ),
      );
      renderPage();

      await user.click(
        await screen.findByRole('button', { name: 'Delete Return Filing Approval' }),
      );
      const confirm = await screen.findByRole('dialog', { name: 'Delete workflow' });
      await user.click(within(confirm).getByText('Delete'));

      await waitFor(() =>
        expect(
          screen.getByText('Workflow has 3 running instance(s); deactivate it instead'),
        ).toBeInTheDocument(),
      );
    });
  });
});

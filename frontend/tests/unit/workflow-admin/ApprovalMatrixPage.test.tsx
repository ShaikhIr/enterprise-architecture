import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { Route, Routes } from 'react-router-dom';
import { describe, expect, it } from 'vitest';

import { ApprovalMatrixPage } from '@features/workflow-admin/pages/ApprovalMatrixPage';

import { server } from '../../mocks/server';
import { fireEvent, renderWithProviders, screen, waitFor, within } from '../../test-utils';

import {
  ALL_WORKFLOW_GRANTS,
  READ_ONLY_GRANTS,
  matrix,
  mockMatrixFormLookups,
  withApiGrants,
} from './fixtures';

const matchAllMatrix = {
  ...matrix,
  id: 32,
  code: 'CATCH_ALL',
  name: 'Catch all',
  priority: 99,
  is_active: false,
  rules: [],
  assignments: [],
};

const mockList = (matrices = [matrix, matchAllMatrix]) => {
  mockMatrixFormLookups();
  server.use(
    http.get('/api/v1/workflow/approval-matrices', () =>
      HttpResponse.json({ matrices, total: matrices.length, skip: 0, limit: 100 }),
    ),
  );
};

/** The page plus a stub destination, so navigation can be asserted by what renders. */
const renderPage = (preloadedState = ALL_WORKFLOW_GRANTS) =>
  renderWithProviders(
    <Routes>
      <Route path="/approval-matrix" element={<ApprovalMatrixPage />} />
      <Route path="/workflows" element={<div>Workflows route reached</div>} />
    </Routes>,
    { preloadedState, initialEntries: ['/approval-matrix'] },
  );

const fillCreateForm = async (user: ReturnType<typeof userEvent.setup>) => {
  await user.type(screen.getByLabelText('Code'), 'NEW_MATRIX');
  await user.type(screen.getByLabelText('Name'), 'New matrix');
  await user.type(screen.getByLabelText('Entity Type'), 'compliance_task');
};

describe('ApprovalMatrixPage', () => {
  describe('rendering', () => {
    it('renders the heading and the fetched matrices with their summaries', async () => {
      mockList();
      renderPage();

      expect(screen.getByRole('heading', { name: 'Approval Matrix' })).toBeInTheDocument();
      const table = screen.getByRole('table');
      expect(await within(table).findByText('Filing approval by amount')).toBeInTheDocument();
      expect(within(table).getByText('FILING_BY_AMOUNT')).toBeInTheDocument();
      expect(within(table).getByText('1 condition')).toBeInTheDocument();
      expect(within(table).getByText('2 levels')).toBeInTheDocument();
      expect(within(table).getByText('Active')).toBeInTheDocument();
      // A matrix with no conditions is flagged because it matches every record.
      expect(within(table).getByText('Catch all')).toBeInTheDocument();
      expect(within(table).getByText('Matches all')).toBeInTheDocument();
      expect(within(table).getByText('None')).toBeInTheDocument();
      expect(within(table).getByText('Inactive')).toBeInTheDocument();
    });

    it('shows the empty message when there are no matrices', async () => {
      mockList([]);
      renderPage();

      expect(await screen.findByText('No approval matrices configured yet.')).toBeInTheDocument();
    });

    it('refetches the list when Refresh is clicked', async () => {
      const user = userEvent.setup();
      mockMatrixFormLookups();
      let calls = 0;
      server.use(
        http.get('/api/v1/workflow/approval-matrices', () => {
          calls += 1;
          return HttpResponse.json({ matrices: [matrix], total: 1, skip: 0, limit: 100 });
        }),
      );
      renderPage();
      await screen.findByText('Filing approval by amount');
      expect(calls).toBe(1);

      await user.click(screen.getByRole('button', { name: 'Refresh approval matrices' }));

      await waitFor(() => expect(calls).toBe(2));
    });
  });

  describe('permission gating', () => {
    it('shows New Matrix and the Edit/Delete row actions to a caller with every grant', async () => {
      mockList();
      renderPage();

      await screen.findByText('Filing approval by amount');
      expect(
        screen.getByRole('button', { name: 'Create new approval matrix' }),
      ).toBeInTheDocument();
      expect(
        screen.getByRole('button', { name: 'Edit Filing approval by amount' }),
      ).toBeInTheDocument();
      expect(
        screen.getByRole('button', { name: 'Delete Filing approval by amount' }),
      ).toBeInTheDocument();
    });

    it('hides New Matrix, Edit and Delete from a read-only caller but keeps Preview Routing', async () => {
      mockList();
      renderPage(READ_ONLY_GRANTS);

      await screen.findByText('Filing approval by amount');
      expect(
        screen.queryByRole('button', { name: 'Create new approval matrix' }),
      ).not.toBeInTheDocument();
      expect(screen.queryByRole('button', { name: /^Edit / })).not.toBeInTheDocument();
      expect(screen.queryByRole('button', { name: /^Delete / })).not.toBeInTheDocument();
      expect(
        screen.getByRole('button', { name: 'Preview approval routing' }),
      ).toBeInTheDocument();
    });

    it('lets UPDATE and DELETE be granted independently', async () => {
      mockList();
      renderPage(withApiGrants({ approval_matrices: ['DELETE'] }));

      await screen.findByText('Filing approval by amount');
      expect(screen.queryByRole('button', { name: /^Edit / })).not.toBeInTheDocument();
      expect(
        screen.getByRole('button', { name: 'Delete Filing approval by amount' }),
      ).toBeInTheDocument();
    });

    it('hides the Workflows shortcut without workflows READ', async () => {
      mockList();
      renderPage(withApiGrants({ approval_matrices: ['READ', 'CREATE'] }));

      await screen.findByText('Filing approval by amount');
      expect(screen.queryByRole('button', { name: 'Go to workflows' })).not.toBeInTheDocument();
    });

    it('goes to the workflows page from the shortcut button', async () => {
      const user = userEvent.setup();
      mockList();
      renderPage();

      await user.click(await screen.findByRole('button', { name: 'Go to workflows' }));

      expect(await screen.findByText('Workflows route reached')).toBeInTheDocument();
    });
  });

  describe('create flow', () => {
    it('creates a matrix end to end and shows a success toast', async () => {
      const user = userEvent.setup();
      let body: unknown;
      mockList([]);
      server.use(
        http.post('/api/v1/workflow/approval-matrices', async ({ request }) => {
          body = await request.json();
          return HttpResponse.json({ ...matrix, code: 'NEW_MATRIX', name: 'New matrix' });
        }),
      );
      renderPage();
      await screen.findByText('No approval matrices configured yet.');

      await user.click(screen.getByRole('button', { name: 'Create new approval matrix' }));
      await fillCreateForm(user);
      await user.click(screen.getByRole('button', { name: 'Create' }));

      await waitFor(() =>
        expect(screen.getByText("Matrix 'NEW_MATRIX' created")).toBeInTheDocument(),
      );
      expect(body).toEqual({
        code: 'NEW_MATRIX',
        name: 'New matrix',
        entity_type: 'compliance_task',
        priority: 0,
        is_active: true,
        rules: [],
        assignments: [],
      });
      await waitFor(() =>
        expect(screen.queryByLabelText('Approval matrix dialog')).not.toBeInTheDocument(),
      );
    });

    it('shows the backend message and keeps the dialog open when the create is rejected', async () => {
      const user = userEvent.setup();
      mockList([]);
      server.use(
        http.post('/api/v1/workflow/approval-matrices', () =>
          HttpResponse.json({ message: "Matrix 'NEW_MATRIX' already exists" }, { status: 409 }),
        ),
      );
      renderPage();
      await screen.findByText('No approval matrices configured yet.');

      await user.click(screen.getByRole('button', { name: 'Create new approval matrix' }));
      await fillCreateForm(user);
      await user.click(screen.getByRole('button', { name: 'Create' }));

      await waitFor(() =>
        expect(screen.getByText("Matrix 'NEW_MATRIX' already exists")).toBeInTheDocument(),
      );
      expect(screen.getByLabelText('Approval matrix dialog')).toBeInTheDocument();
    });

    it('falls back to a generic message when the error carries no detail', async () => {
      const user = userEvent.setup();
      mockList([]);
      server.use(
        http.post(
          '/api/v1/workflow/approval-matrices',
          () => new HttpResponse(null, { status: 500 }),
        ),
      );
      renderPage();
      await screen.findByText('No approval matrices configured yet.');

      await user.click(screen.getByRole('button', { name: 'Create new approval matrix' }));
      await fillCreateForm(user);
      await user.click(screen.getByRole('button', { name: 'Create' }));

      await waitFor(() =>
        expect(screen.getByText('Failed to save the approval matrix')).toBeInTheDocument(),
      );
    });
  });

  describe('edit flow', () => {
    it('opens the dialog pre-filled and patches without the immutable code', async () => {
      const user = userEvent.setup();
      let body: unknown;
      mockList([matrix]);
      server.use(
        http.patch('/api/v1/workflow/approval-matrices/31', async ({ request }) => {
          body = await request.json();
          return HttpResponse.json(matrix);
        }),
      );
      renderPage();

      await user.click(await screen.findByRole('button', { name: 'Edit Filing approval by amount' }));
      expect(screen.getByText('Edit Matrix — FILING_BY_AMOUNT')).toBeInTheDocument();
      expect(screen.getByLabelText('Name')).toHaveValue('Filing approval by amount');
      await user.clear(screen.getByLabelText('Name'));
      await user.type(screen.getByLabelText('Name'), 'Renamed matrix');
      await user.click(screen.getByRole('button', { name: 'Save Changes' }));

      await waitFor(() =>
        expect(screen.getByText("Matrix 'FILING_BY_AMOUNT' updated")).toBeInTheDocument(),
      );
      expect(body).not.toHaveProperty('code');
      expect(body).toMatchObject({
        name: 'Renamed matrix',
        entity_type: 'compliance_task',
        priority: 5,
        is_active: true,
        rules: [{ field: 'amount', operator: 'GT', value: '100000', data_type: 'NUMBER' }],
        assignments: [
          { level: 1, assignment_type: 'ROLE', user_id: null, role_id: 901 },
          { level: 2, assignment_type: 'USER', user_id: 801, role_id: null },
        ],
      });
    });

    it('opens the next "New Approval Matrix" dialog empty after an edit was closed', async () => {
      const user = userEvent.setup();
      mockList([matrix]);
      renderPage();

      await user.click(await screen.findByRole('button', { name: 'Edit Filing approval by amount' }));
      await user.click(screen.getByRole('button', { name: 'Cancel' }));
      await user.click(screen.getByRole('button', { name: 'Create new approval matrix' }));

      expect(screen.getByText('New Approval Matrix')).toBeInTheDocument();
      expect(screen.getByLabelText('Name')).toHaveValue('');
      expect(screen.getByLabelText('Code')).toBeEnabled();
    });
  });

  describe('delete flow', () => {
    it('confirms, deletes and shows a success toast', async () => {
      const user = userEvent.setup();
      let deleted = false;
      mockList([matrix]);
      server.use(
        http.delete('/api/v1/workflow/approval-matrices/31', () => {
          deleted = true;
          return new HttpResponse(null, { status: 204 });
        }),
      );
      renderPage();

      await user.click(
        await screen.findByRole('button', { name: 'Delete Filing approval by amount' }),
      );
      const confirm = await screen.findByRole('dialog', { name: 'Delete approval matrix' });
      await user.click(within(confirm).getByText('Delete'));

      await waitFor(() =>
        expect(screen.getByText("Matrix 'FILING_BY_AMOUNT' deleted")).toBeInTheDocument(),
      );
      expect(deleted).toBe(true);
    });

    it('does not delete anything when the confirmation is cancelled', async () => {
      const user = userEvent.setup();
      let deleted = false;
      mockList([matrix]);
      server.use(
        http.delete('/api/v1/workflow/approval-matrices/31', () => {
          deleted = true;
          return new HttpResponse(null, { status: 204 });
        }),
      );
      renderPage();

      await user.click(
        await screen.findByRole('button', { name: 'Delete Filing approval by amount' }),
      );
      const confirm = await screen.findByRole('dialog', { name: 'Delete approval matrix' });
      await user.click(within(confirm).getByText('Cancel'));

      await waitFor(() =>
        expect(
          screen.queryByRole('dialog', { name: 'Delete approval matrix' }),
        ).not.toBeInTheDocument(),
      );
      expect(deleted).toBe(false);
    });

    it('shows the backend message when the delete is rejected', async () => {
      const user = userEvent.setup();
      mockList([matrix]);
      server.use(
        http.delete('/api/v1/workflow/approval-matrices/31', () =>
          HttpResponse.json({ message: 'Matrix is in use by 2 task(s)' }, { status: 409 }),
        ),
      );
      renderPage();

      await user.click(
        await screen.findByRole('button', { name: 'Delete Filing approval by amount' }),
      );
      const confirm = await screen.findByRole('dialog', { name: 'Delete approval matrix' });
      await user.click(within(confirm).getByText('Delete'));

      await waitFor(() =>
        expect(screen.getByText('Matrix is in use by 2 task(s)')).toBeInTheDocument(),
      );
    });
  });

  describe('preview routing', () => {
    const openPreview = async (user: ReturnType<typeof userEvent.setup>) => {
      await user.click(await screen.findByRole('button', { name: 'Preview approval routing' }));
      return screen.findByLabelText('Approval routing preview dialog');
    };

    it('posts the entity type and sample record, then lists the resolved approvers', async () => {
      const user = userEvent.setup();
      let body: unknown;
      mockList([matrix]);
      server.use(
        http.post('/api/v1/workflow/approval-matrices/resolve', async ({ request }) => {
          body = await request.json();
          return HttpResponse.json({
            matched: true,
            matrix,
            levels: [1, 2],
            assignments: matrix.assignments,
          });
        }),
      );
      renderPage();

      const dialog = await openPreview(user);
      await user.type(within(dialog).getByLabelText('Entity Type'), 'compliance_task');
      fireEvent.change(within(dialog).getByLabelText('Sample Record (JSON)'), {
        target: { value: '{"amount": 500000}' },
      });
      await user.click(within(dialog).getByRole('button', { name: 'Resolve' }));

      expect(await within(dialog).findByText('Matched')).toBeInTheDocument();
      expect(body).toEqual({ entity_type: 'compliance_task', entity_data: { amount: 500000 } });
      expect(within(dialog).getByText('priority 5')).toBeInTheDocument();
      expect(within(dialog).getByText('L1')).toBeInTheDocument();
      expect(within(dialog).getByText('L2')).toBeInTheDocument();
    });

    it('shows the no-match warning when nothing matches', async () => {
      const user = userEvent.setup();
      mockList([matrix]);
      server.use(
        http.post('/api/v1/workflow/approval-matrices/resolve', () =>
          HttpResponse.json({ matched: false, matrix: null, levels: [], assignments: [] }),
        ),
      );
      renderPage();

      const dialog = await openPreview(user);
      await user.type(within(dialog).getByLabelText('Entity Type'), 'compliance_task');
      await user.click(within(dialog).getByRole('button', { name: 'Resolve' }));

      expect(
        await within(dialog).findByText(
          'No active matrix matched this record — it would route to nobody.',
        ),
      ).toBeInTheDocument();
    });

    it('shows an error toast when the resolve request fails', async () => {
      const user = userEvent.setup();
      mockList([matrix]);
      server.use(
        http.post('/api/v1/workflow/approval-matrices/resolve', () =>
          HttpResponse.json({ message: 'Unknown entity type' }, { status: 422 }),
        ),
      );
      renderPage();

      const dialog = await openPreview(user);
      await user.type(within(dialog).getByLabelText('Entity Type'), 'compliance_task');
      await user.click(within(dialog).getByRole('button', { name: 'Resolve' }));

      await waitFor(() => expect(screen.getByText('Unknown entity type')).toBeInTheDocument());
    });

    it('clears the previous result when the preview is reopened', async () => {
      const user = userEvent.setup();
      mockList([matrix]);
      server.use(
        http.post('/api/v1/workflow/approval-matrices/resolve', () =>
          HttpResponse.json({ matched: false, matrix: null, levels: [], assignments: [] }),
        ),
      );
      renderPage();

      const dialog = await openPreview(user);
      await user.type(within(dialog).getByLabelText('Entity Type'), 'compliance_task');
      await user.click(within(dialog).getByRole('button', { name: 'Resolve' }));
      await within(dialog).findByText(/No active matrix matched/);
      await user.click(within(dialog).getByText('Close', { selector: '.p-button-label' }));
      await waitFor(() =>
        expect(screen.queryByLabelText('Approval routing preview dialog')).not.toBeInTheDocument(),
      );

      await openPreview(user);

      expect(screen.queryByText(/No active matrix matched/)).not.toBeInTheDocument();
      expect(screen.getByLabelText('Entity Type')).toHaveValue('');
    });
  });
});

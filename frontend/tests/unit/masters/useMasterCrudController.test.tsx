import userEvent from '@testing-library/user-event';
import { ConfirmDialog } from 'primereact/confirmdialog';
import { Toast } from 'primereact/toast';
import { describe, expect, it, vi } from 'vitest';

import { useMasterCrudController } from '@features/masters/hooks/useMasterCrudController';
import type { AuditedRecord } from '@features/masters/models/common';

import { renderWithProviders, screen, waitFor, within } from '../../test-utils';

interface Widget extends AuditedRecord {
  name: string;
}

const widget: Widget = {
  id: '1',
  name: 'Widget One',
  created_by: 'system',
  created_date: '2024-01-01T00:00:00Z',
  modified_by: 'system',
  modified_date: '2024-01-01T00:00:00Z',
};

/**
 * `requestDelete` calls PrimeReact's imperative `confirmDialog()`, which
 * talks to a mounted `<ConfirmDialog />` through `OverlayService` — there is
 * nothing to assert on without one actually in the tree. Same for the toast
 * messages `submit`/`requestDelete` show through `toast.current.show(...)`:
 * only visible with a real `<Toast ref={...} />` mounted. This harness wires
 * both up exactly as `MasterCrudPage` does, so the test exercises the real
 * PrimeReact integration rather than mocking it away.
 */
interface HarnessProps {
  onCreate: (data: { name: string }) => Promise<unknown>;
  onUpdate: (id: string, data: { name: string }) => Promise<unknown>;
  onDelete: (id: string) => Promise<unknown>;
}

const Harness = ({ onCreate, onUpdate, onDelete }: HarnessProps) => {
  const crud = useMasterCrudController<Widget, { name: string }>({
    entityLabel: 'Widget',
    labelOf: (row) => row.name,
    onCreate,
    onUpdate,
    onDelete,
  });

  return (
    <div>
      <Toast ref={crud.toast} />
      <ConfirmDialog />
      <button onClick={crud.openCreate}>Open create</button>
      <button onClick={() => crud.openEdit(widget)}>Open edit</button>
      <button onClick={crud.closeDialog}>Close</button>
      <button onClick={() => crud.requestDelete(widget)}>Delete widget</button>
      <button onClick={() => crud.submit({ name: 'Submitted' })}>Submit</button>
      <div data-testid="dialog-visible">{String(crud.dialogVisible)}</div>
      <div data-testid="editing-id">{crud.editing?.id ?? 'none'}</div>
    </div>
  );
};

const renderHarness = (overrides: Partial<HarnessProps> = {}) =>
  renderWithProviders(
    <Harness
      onCreate={overrides.onCreate ?? vi.fn().mockResolvedValue(undefined)}
      onUpdate={overrides.onUpdate ?? vi.fn().mockResolvedValue(undefined)}
      onDelete={overrides.onDelete ?? vi.fn().mockResolvedValue(undefined)}
    />,
  );

describe('useMasterCrudController', () => {
  it('openCreate shows the dialog with no row being edited', async () => {
    const user = userEvent.setup();
    renderHarness();

    await user.click(screen.getByText('Open create'));

    expect(screen.getByTestId('dialog-visible')).toHaveTextContent('true');
    expect(screen.getByTestId('editing-id')).toHaveTextContent('none');
  });

  it('openEdit shows the dialog with the given row as editing', async () => {
    const user = userEvent.setup();
    renderHarness();

    await user.click(screen.getByText('Open edit'));

    expect(screen.getByTestId('dialog-visible')).toHaveTextContent('true');
    expect(screen.getByTestId('editing-id')).toHaveTextContent('1');
  });

  it('closeDialog hides the dialog and clears the editing row', async () => {
    const user = userEvent.setup();
    renderHarness();
    await user.click(screen.getByText('Open edit'));

    await user.click(screen.getByText('Close'));

    expect(screen.getByTestId('dialog-visible')).toHaveTextContent('false');
    expect(screen.getByTestId('editing-id')).toHaveTextContent('none');
  });

  describe('submit', () => {
    it('calls onCreate and shows a success toast when not editing', async () => {
      const user = userEvent.setup();
      const onCreate = vi.fn().mockResolvedValue(undefined);
      renderHarness({ onCreate });

      await user.click(screen.getByText('Submit'));

      expect(onCreate).toHaveBeenCalledWith({ name: 'Submitted' });
      await waitFor(() => expect(screen.getByText(/Widget created/i)).toBeInTheDocument());
    });

    it('calls onUpdate with the editing row id and shows a success toast', async () => {
      const user = userEvent.setup();
      const onUpdate = vi.fn().mockResolvedValue(undefined);
      renderHarness({ onUpdate });
      await user.click(screen.getByText('Open edit'));

      await user.click(screen.getByText('Submit'));

      expect(onUpdate).toHaveBeenCalledWith('1', { name: 'Submitted' });
      await waitFor(() =>
        expect(screen.getByText(/Widget 'Widget One' updated/i)).toBeInTheDocument(),
      );
    });

    it('closes the dialog after a successful submit', async () => {
      const user = userEvent.setup();
      renderHarness();
      await user.click(screen.getByText('Open create'));

      await user.click(screen.getByText('Submit'));

      await waitFor(() => expect(screen.getByTestId('dialog-visible')).toHaveTextContent('false'));
    });

    it('shows the backend error message and keeps the dialog open on failure', async () => {
      const user = userEvent.setup();
      const onCreate = vi
        .fn()
        .mockRejectedValue({ response: { data: { message: "Widget 'W1' already exists" } } });
      renderHarness({ onCreate });
      await user.click(screen.getByText('Open create'));

      await user.click(screen.getByText('Submit'));

      await waitFor(() =>
        expect(screen.getByText("Widget 'W1' already exists")).toBeInTheDocument(),
      );
      expect(screen.getByTestId('dialog-visible')).toHaveTextContent('true');
    });
  });

  describe('requestDelete', () => {
    it('shows a confirmation naming the row before deleting anything', async () => {
      const user = userEvent.setup();
      const onDelete = vi.fn().mockResolvedValue(undefined);
      renderHarness({ onDelete });

      await user.click(screen.getByText('Delete widget'));

      expect(await screen.findByText(/Delete 'Widget One'\?/)).toBeInTheDocument();
      expect(onDelete).not.toHaveBeenCalled();
    });

    it('calls onDelete and shows a success toast once the confirmation is accepted', async () => {
      const user = userEvent.setup();
      const onDelete = vi.fn().mockResolvedValue(undefined);
      renderHarness({ onDelete });
      await user.click(screen.getByText('Delete widget'));
      const confirmDialog = await screen.findByRole('dialog', { name: 'Delete widget' });

      await user.click(within(confirmDialog).getByText('Delete'));

      await waitFor(() => expect(onDelete).toHaveBeenCalledWith('1'));
      await waitFor(() =>
        expect(screen.getByText("Widget 'Widget One' deleted")).toBeInTheDocument(),
      );
    });

    it('does not call onDelete when the confirmation is cancelled', async () => {
      const user = userEvent.setup();
      const onDelete = vi.fn().mockResolvedValue(undefined);
      renderHarness({ onDelete });
      await user.click(screen.getByText('Delete widget'));
      const confirmDialog = await screen.findByRole('dialog', { name: 'Delete widget' });

      await user.click(within(confirmDialog).getByText('Cancel'));

      expect(onDelete).not.toHaveBeenCalled();
    });

    it('shows the backend error message when the delete is rejected (e.g. still referenced)', async () => {
      const user = userEvent.setup();
      const onDelete = vi
        .fn()
        .mockRejectedValue({ response: { data: { message: '3 state(s) reference it' } } });
      renderHarness({ onDelete });
      await user.click(screen.getByText('Delete widget'));
      const confirmDialog = await screen.findByRole('dialog', { name: 'Delete widget' });

      await user.click(within(confirmDialog).getByText('Delete'));

      await waitFor(() => expect(screen.getByText('3 state(s) reference it')).toBeInTheDocument());
    });
  });
});

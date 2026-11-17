import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { WorkflowDefinitionForm } from '@features/workflow-admin/components/WorkflowDefinitionForm';

import { fireEvent, renderWithProviders, screen, waitFor } from '../../test-utils';

import { definition, getInputByLabel } from './fixtures';

/** `handleSubmit(onSubmit)` also passes the click event, so assert on the data argument only. */
const submittedData = (onSubmit: ReturnType<typeof vi.fn>) =>
  onSubmit.mock.calls[0]?.[0] as Record<string, unknown>;

describe('WorkflowDefinitionForm', () => {
  it('does not render dialog content while not visible', () => {
    renderWithProviders(
      <WorkflowDefinitionForm
        visible={false}
        definition={null}
        onHide={vi.fn()}
        onSubmit={vi.fn()}
      />,
    );

    expect(screen.queryByLabelText('Workflow definition dialog')).not.toBeInTheDocument();
  });

  describe('create mode', () => {
    it('shows the "New Workflow" header, empty fields and an active switch', () => {
      renderWithProviders(
        <WorkflowDefinitionForm visible definition={null} onHide={vi.fn()} onSubmit={vi.fn()} />,
      );

      expect(screen.getByText('New Workflow')).toBeInTheDocument();
      expect(screen.getByLabelText('Code')).toHaveValue('');
      expect(screen.getByLabelText('Code')).toBeEnabled();
      expect(screen.getByLabelText('Name')).toHaveValue('');
      expect(screen.getByLabelText('Entity Type')).toHaveValue('');
      expect(screen.getByLabelText('Description')).toHaveValue('');
      expect(getInputByLabel('Workflow active')).toBeChecked();
      expect(screen.getByRole('button', { name: 'Create' })).toBeInTheDocument();
      expect(screen.queryByText(/Code is fixed after creation/)).not.toBeInTheDocument();
    });

    it('rejects a code shorter than 2 characters', async () => {
      const user = userEvent.setup();
      const onSubmit = vi.fn();
      renderWithProviders(
        <WorkflowDefinitionForm visible definition={null} onHide={vi.fn()} onSubmit={onSubmit} />,
      );

      await user.type(screen.getByLabelText('Code'), 'A');
      await user.type(screen.getByLabelText('Name'), 'Filing');
      await user.type(screen.getByLabelText('Entity Type'), 'task');
      await user.click(screen.getByRole('button', { name: 'Create' }));

      await waitFor(() =>
        expect(screen.getByText('Code must be at least 2 characters')).toBeInTheDocument(),
      );
      expect(onSubmit).not.toHaveBeenCalled();
    });

    it('rejects a lower-case code with the character-set message', async () => {
      const user = userEvent.setup();
      const onSubmit = vi.fn();
      renderWithProviders(
        <WorkflowDefinitionForm visible definition={null} onHide={vi.fn()} onSubmit={onSubmit} />,
      );

      await user.type(screen.getByLabelText('Code'), 'return-filing');
      await user.type(screen.getByLabelText('Name'), 'Filing');
      await user.type(screen.getByLabelText('Entity Type'), 'task');
      await user.click(screen.getByRole('button', { name: 'Create' }));

      await waitFor(() =>
        expect(
          screen.getByText('Use upper case letters, numbers and underscores only'),
        ).toBeInTheDocument(),
      );
      expect(onSubmit).not.toHaveBeenCalled();
    });

    it('rejects a name shorter than 2 characters', async () => {
      const user = userEvent.setup();
      const onSubmit = vi.fn();
      renderWithProviders(
        <WorkflowDefinitionForm visible definition={null} onHide={vi.fn()} onSubmit={onSubmit} />,
      );

      await user.type(screen.getByLabelText('Code'), 'RETURN_FILING');
      await user.type(screen.getByLabelText('Name'), 'F');
      await user.type(screen.getByLabelText('Entity Type'), 'task');
      await user.click(screen.getByRole('button', { name: 'Create' }));

      await waitFor(() =>
        expect(screen.getByText('Name must be at least 2 characters')).toBeInTheDocument(),
      );
      expect(onSubmit).not.toHaveBeenCalled();
    });

    it('rejects an entity type that is too short', async () => {
      const user = userEvent.setup();
      const onSubmit = vi.fn();
      renderWithProviders(
        <WorkflowDefinitionForm visible definition={null} onHide={vi.fn()} onSubmit={onSubmit} />,
      );

      await user.type(screen.getByLabelText('Code'), 'RETURN_FILING');
      await user.type(screen.getByLabelText('Name'), 'Filing');
      await user.type(screen.getByLabelText('Entity Type'), 't');
      await user.click(screen.getByRole('button', { name: 'Create' }));

      await waitFor(() =>
        expect(screen.getByText('Entity type must be at least 2 characters')).toBeInTheDocument(),
      );
      expect(onSubmit).not.toHaveBeenCalled();
    });

    it('rejects an upper-case entity type with the character-set message', async () => {
      const user = userEvent.setup();
      const onSubmit = vi.fn();
      renderWithProviders(
        <WorkflowDefinitionForm visible definition={null} onHide={vi.fn()} onSubmit={onSubmit} />,
      );

      await user.type(screen.getByLabelText('Code'), 'RETURN_FILING');
      await user.type(screen.getByLabelText('Name'), 'Filing');
      await user.type(screen.getByLabelText('Entity Type'), 'Compliance Task');
      await user.click(screen.getByRole('button', { name: 'Create' }));

      await waitFor(() =>
        expect(
          screen.getByText('Use lower case letters, numbers and underscores only'),
        ).toBeInTheDocument(),
      );
      expect(onSubmit).not.toHaveBeenCalled();
    });

    it('rejects a description longer than 2000 characters', async () => {
      const user = userEvent.setup();
      const onSubmit = vi.fn();
      renderWithProviders(
        <WorkflowDefinitionForm visible definition={null} onHide={vi.fn()} onSubmit={onSubmit} />,
      );

      await user.type(screen.getByLabelText('Code'), 'RETURN_FILING');
      await user.type(screen.getByLabelText('Name'), 'Filing');
      await user.type(screen.getByLabelText('Entity Type'), 'task');
      // Typing 2001 characters one by one is needlessly slow; set the value in one event.
      fireEvent.change(screen.getByLabelText('Description'), {
        target: { value: 'x'.repeat(2001) },
      });
      await user.click(screen.getByRole('button', { name: 'Create' }));

      await waitFor(() =>
        expect(document.getElementById('wf-description-error')).toBeInTheDocument(),
      );
      expect(onSubmit).not.toHaveBeenCalled();
    });

    it('submits the entered values with is_active defaulting to true', async () => {
      const user = userEvent.setup();
      const onSubmit = vi.fn();
      renderWithProviders(
        <WorkflowDefinitionForm visible definition={null} onHide={vi.fn()} onSubmit={onSubmit} />,
      );

      await user.type(screen.getByLabelText('Code'), 'RETURN_FILING');
      await user.type(screen.getByLabelText('Name'), 'Return Filing Approval');
      await user.type(screen.getByLabelText('Entity Type'), 'compliance_task');
      await user.type(screen.getByLabelText('Description'), 'Approval flow');
      await user.click(screen.getByRole('button', { name: 'Create' }));

      await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
      expect(submittedData(onSubmit)).toEqual({
        code: 'RETURN_FILING',
        name: 'Return Filing Approval',
        entity_type: 'compliance_task',
        description: 'Approval flow',
        is_active: true,
      });
    });

    it('submits an empty description as an empty string, not null', async () => {
      const user = userEvent.setup();
      const onSubmit = vi.fn();
      renderWithProviders(
        <WorkflowDefinitionForm visible definition={null} onHide={vi.fn()} onSubmit={onSubmit} />,
      );

      await user.type(screen.getByLabelText('Code'), 'RETURN_FILING');
      await user.type(screen.getByLabelText('Name'), 'Filing');
      await user.type(screen.getByLabelText('Entity Type'), 'task');
      await user.click(screen.getByRole('button', { name: 'Create' }));

      await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
      expect(submittedData(onSubmit).description).toBe('');
    });

    it('submits is_active false after the switch is turned off', async () => {
      const user = userEvent.setup();
      const onSubmit = vi.fn();
      renderWithProviders(
        <WorkflowDefinitionForm visible definition={null} onHide={vi.fn()} onSubmit={onSubmit} />,
      );

      await user.type(screen.getByLabelText('Code'), 'RETURN_FILING');
      await user.type(screen.getByLabelText('Name'), 'Filing');
      await user.type(screen.getByLabelText('Entity Type'), 'task');
      await user.click(getInputByLabel('Workflow active'));
      await user.click(screen.getByRole('button', { name: 'Create' }));

      await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
      expect(submittedData(onSubmit).is_active).toBe(false);
    });
  });

  describe('edit mode', () => {
    it('shows the edit header and pre-fills every field from the row', () => {
      renderWithProviders(
        <WorkflowDefinitionForm
          visible
          definition={{ ...definition, is_active: false }}
          onHide={vi.fn()}
          onSubmit={vi.fn()}
        />,
      );

      expect(screen.getByText('Edit Workflow — RETURN_FILING')).toBeInTheDocument();
      expect(screen.getByLabelText('Code')).toHaveValue('RETURN_FILING');
      expect(screen.getByLabelText('Name')).toHaveValue('Return Filing Approval');
      expect(screen.getByLabelText('Entity Type')).toHaveValue('compliance_task');
      expect(screen.getByLabelText('Description')).toHaveValue('Approval flow for filed returns');
      expect(getInputByLabel('Workflow active')).not.toBeChecked();
    });

    it('locks the code field and explains why', () => {
      renderWithProviders(
        <WorkflowDefinitionForm
          visible
          definition={definition}
          onHide={vi.fn()}
          onSubmit={vi.fn()}
        />,
      );

      expect(screen.getByLabelText('Code')).toBeDisabled();
      expect(screen.getByText(/Code is fixed after creation/)).toBeInTheDocument();
    });

    it('uses the "Save Changes" button and submits the unchanged row values', async () => {
      const user = userEvent.setup();
      const onSubmit = vi.fn();
      renderWithProviders(
        <WorkflowDefinitionForm
          visible
          definition={definition}
          onHide={vi.fn()}
          onSubmit={onSubmit}
        />,
      );

      expect(screen.queryByRole('button', { name: 'Create' })).not.toBeInTheDocument();
      await user.click(screen.getByRole('button', { name: 'Save Changes' }));

      await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
      expect(submittedData(onSubmit)).toEqual({
        code: 'RETURN_FILING',
        name: 'Return Filing Approval',
        entity_type: 'compliance_task',
        description: 'Approval flow for filed returns',
        is_active: true,
      });
    });

    it('submits an edited name', async () => {
      const user = userEvent.setup();
      const onSubmit = vi.fn();
      renderWithProviders(
        <WorkflowDefinitionForm
          visible
          definition={definition}
          onHide={vi.fn()}
          onSubmit={onSubmit}
        />,
      );

      await user.clear(screen.getByLabelText('Name'));
      await user.type(screen.getByLabelText('Name'), 'Renamed Flow');
      await user.click(screen.getByRole('button', { name: 'Save Changes' }));

      await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
      expect(submittedData(onSubmit).name).toBe('Renamed Flow');
    });
  });

  describe('resetting', () => {
    it('clears the fields when the dialog switches from edit to create', () => {
      const { rerender } = renderWithProviders(
        <WorkflowDefinitionForm
          visible
          definition={definition}
          onHide={vi.fn()}
          onSubmit={vi.fn()}
        />,
      );
      expect(screen.getByLabelText('Name')).toHaveValue('Return Filing Approval');

      rerender(
        <WorkflowDefinitionForm visible definition={null} onHide={vi.fn()} onSubmit={vi.fn()} />,
      );

      expect(screen.getByText('New Workflow')).toBeInTheDocument();
      expect(screen.getByLabelText('Name')).toHaveValue('');
      expect(screen.getByLabelText('Code')).toHaveValue('');
      expect(screen.getByLabelText('Code')).toBeEnabled();
    });

    it('does not show previously typed values after the dialog is closed and reopened', async () => {
      const user = userEvent.setup();
      const { rerender } = renderWithProviders(
        <WorkflowDefinitionForm visible definition={null} onHide={vi.fn()} onSubmit={vi.fn()} />,
      );
      await user.type(screen.getByLabelText('Name'), 'Leftover');

      rerender(
        <WorkflowDefinitionForm
          visible={false}
          definition={null}
          onHide={vi.fn()}
          onSubmit={vi.fn()}
        />,
      );
      rerender(
        <WorkflowDefinitionForm visible definition={null} onHide={vi.fn()} onSubmit={vi.fn()} />,
      );

      expect(screen.getByLabelText('Name')).toHaveValue('');
    });
  });

  it('calls onHide when Cancel is clicked, without calling onSubmit', async () => {
    const user = userEvent.setup();
    const onHide = vi.fn();
    const onSubmit = vi.fn();
    renderWithProviders(
      <WorkflowDefinitionForm visible definition={null} onHide={onHide} onSubmit={onSubmit} />,
    );

    await user.click(screen.getByRole('button', { name: 'Cancel' }));

    expect(onHide).toHaveBeenCalledTimes(1);
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('disables the action button while loading', () => {
    renderWithProviders(
      <WorkflowDefinitionForm
        visible
        definition={null}
        loading
        onHide={vi.fn()}
        onSubmit={vi.fn()}
      />,
    );

    expect(screen.getByRole('button', { name: 'Create' })).toHaveClass('p-disabled');
  });
});

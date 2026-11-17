import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { WorkflowTransitionForm } from '@features/workflow-admin/components/WorkflowTransitionForm';

import {
  getDropdownLabel,
  getValidationError,
  renderWithProviders,
  screen,
  selectDropdownOption,
  waitFor,
} from '../../test-utils';

import {
  getInputByLabel,
  initialStatus,
  listDropdownOptions,
  middleStatus,
  terminalStatus,
} from './fixtures';

const DRAFT = 'Draft (DRAFT)';
const IN_REVIEW = 'In Review (IN_REVIEW)';
const APPROVED = 'Approved (APPROVED)';

const allStatuses = [initialStatus, middleStatus, terminalStatus];

/** `handleSubmit(submit)` also passes the click event, so assert on the data argument only. */
const submittedData = (onSubmit: ReturnType<typeof vi.fn>) =>
  onSubmit.mock.calls[0]?.[0] as Record<string, unknown>;

describe('WorkflowTransitionForm', () => {
  it('does not render dialog content while not visible', () => {
    renderWithProviders(
      <WorkflowTransitionForm
        visible={false}
        statuses={allStatuses}
        onHide={vi.fn()}
        onSubmit={vi.fn()}
      />,
    );

    expect(screen.queryByLabelText('Workflow transition dialog')).not.toBeInTheDocument();
  });

  it('shows the "Add Transition" header and defaults', () => {
    renderWithProviders(
      <WorkflowTransitionForm
        visible
        statuses={allStatuses}
        onHide={vi.fn()}
        onSubmit={vi.fn()}
      />,
    );

    expect(screen.getByText('Add Transition', { selector: '.p-dialog-title' })).toBeInTheDocument();
    expect(screen.getByLabelText('Action Code')).toHaveValue('');
    expect(getDropdownLabel('Action type')).toBe('Custom (no approval effect)');
    expect(getInputByLabel('Transition priority')).toHaveValue('0');
    expect(getInputByLabel('Requires comment')).not.toBeChecked();
    expect(getInputByLabel('Auto execute')).not.toBeChecked();
    expect(screen.getByText(/No effect on approvals/)).toBeInTheDocument();
  });

  describe('state pickers', () => {
    it('excludes terminal states from the source options', async () => {
      const user = userEvent.setup();
      renderWithProviders(
        <WorkflowTransitionForm
          visible
          statuses={allStatuses}
          onHide={vi.fn()}
          onSubmit={vi.fn()}
        />,
      );

      const options = await listDropdownOptions(user, 'Source state');

      expect(options).toEqual([DRAFT, IN_REVIEW]);
    });

    it('offers every state as a target until a source is chosen', async () => {
      const user = userEvent.setup();
      renderWithProviders(
        <WorkflowTransitionForm
          visible
          statuses={allStatuses}
          onHide={vi.fn()}
          onSubmit={vi.fn()}
        />,
      );

      const options = await listDropdownOptions(user, 'Target state');

      expect(options).toEqual([DRAFT, IN_REVIEW, APPROVED]);
    });

    it('removes the chosen source from the target options (cascade)', async () => {
      const user = userEvent.setup();
      renderWithProviders(
        <WorkflowTransitionForm
          visible
          statuses={allStatuses}
          onHide={vi.fn()}
          onSubmit={vi.fn()}
        />,
      );

      await selectDropdownOption(user, 'Source state', IN_REVIEW);
      const options = await listDropdownOptions(user, 'Target state');

      expect(options).toEqual([DRAFT, APPROVED]);
    });

    it('warns when fewer than two states exist', () => {
      renderWithProviders(
        <WorkflowTransitionForm
          visible
          statuses={[initialStatus]}
          onHide={vi.fn()}
          onSubmit={vi.fn()}
        />,
      );

      expect(
        screen.getByText('Add at least two states before wiring a transition.'),
      ).toBeInTheDocument();
    });

    it('disables the action button when every state is terminal (no possible source)', () => {
      renderWithProviders(
        <WorkflowTransitionForm
          visible
          statuses={[terminalStatus, { ...terminalStatus, id: 104, code: 'REJECTED' }]}
          onHide={vi.fn()}
          onSubmit={vi.fn()}
        />,
      );

      expect(screen.getByRole('button', { name: 'Add Transition' })).toBeDisabled();
    });

    it('does not warn when at least two states exist', () => {
      renderWithProviders(
        <WorkflowTransitionForm
          visible
          statuses={allStatuses}
          onHide={vi.fn()}
          onSubmit={vi.fn()}
        />,
      );

      expect(screen.queryByText(/Add at least two states/)).not.toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'Add Transition' })).toBeEnabled();
    });
  });

  describe('action type', () => {
    it('updates the effect hint when the action type changes', async () => {
      const user = userEvent.setup();
      renderWithProviders(
        <WorkflowTransitionForm
          visible
          statuses={allStatuses}
          onHide={vi.fn()}
          onSubmit={vi.fn()}
        />,
      );

      await selectDropdownOption(user, 'Action type', 'Approve');

      expect(getDropdownLabel('Action type')).toBe('Approve');
      expect(screen.getByText(/Settles this level, opens the next/)).toBeInTheDocument();
      expect(screen.queryByText(/No effect on approvals/)).not.toBeInTheDocument();
    });
  });

  describe('validation', () => {
    it('requires a source state, a target state and an action code', async () => {
      const user = userEvent.setup();
      const onSubmit = vi.fn();
      renderWithProviders(
        <WorkflowTransitionForm
          visible
          statuses={allStatuses}
          onHide={vi.fn()}
          onSubmit={onSubmit}
        />,
      );

      await user.click(screen.getByRole('button', { name: 'Add Transition' }));

      await waitFor(() => expect(getValidationError('Select a source state')).toBeInTheDocument());
      expect(getValidationError('Select a target state')).toBeInTheDocument();
      expect(getValidationError('Action code must be at least 2 characters')).toBeInTheDocument();
      expect(onSubmit).not.toHaveBeenCalled();
    });

    it('rejects a lower-case action code with the character-set message', async () => {
      const user = userEvent.setup();
      const onSubmit = vi.fn();
      renderWithProviders(
        <WorkflowTransitionForm
          visible
          statuses={allStatuses}
          onHide={vi.fn()}
          onSubmit={onSubmit}
        />,
      );

      await selectDropdownOption(user, 'Source state', DRAFT);
      await selectDropdownOption(user, 'Target state', IN_REVIEW);
      await user.type(screen.getByLabelText('Action Code'), 'send for review');
      await user.click(screen.getByRole('button', { name: 'Add Transition' }));

      await waitFor(() =>
        expect(
          getValidationError('Use upper case letters, numbers and underscores only'),
        ).toBeInTheDocument(),
      );
      expect(onSubmit).not.toHaveBeenCalled();
    });

    it('rejects a single-character action code', async () => {
      const user = userEvent.setup();
      const onSubmit = vi.fn();
      renderWithProviders(
        <WorkflowTransitionForm
          visible
          statuses={allStatuses}
          onHide={vi.fn()}
          onSubmit={onSubmit}
        />,
      );

      await selectDropdownOption(user, 'Source state', DRAFT);
      await selectDropdownOption(user, 'Target state', IN_REVIEW);
      await user.type(screen.getByLabelText('Action Code'), 'A');
      await user.click(screen.getByRole('button', { name: 'Add Transition' }));

      await waitFor(() =>
        expect(getValidationError('Action code must be at least 2 characters')).toBeInTheDocument(),
      );
      expect(onSubmit).not.toHaveBeenCalled();
    });
  });

  describe('submitting', () => {
    it('submits the defaults with a null guard expression', async () => {
      const user = userEvent.setup();
      const onSubmit = vi.fn();
      renderWithProviders(
        <WorkflowTransitionForm
          visible
          statuses={allStatuses}
          onHide={vi.fn()}
          onSubmit={onSubmit}
        />,
      );

      await selectDropdownOption(user, 'Source state', DRAFT);
      await selectDropdownOption(user, 'Target state', IN_REVIEW);
      await user.type(screen.getByLabelText('Action Code'), 'SEND_FOR_REVIEW');
      await user.click(screen.getByRole('button', { name: 'Add Transition' }));

      await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
      expect(submittedData(onSubmit)).toEqual({
        from_status_id: initialStatus.id,
        to_status_id: middleStatus.id,
        action_code: 'SEND_FOR_REVIEW',
        action_type: 'CUSTOM',
        requires_comment: false,
        auto_execute: false,
        priority: 0,
        guard_expression: null,
      });
    });

    it('submits a chosen action type and both switches turned on', async () => {
      const user = userEvent.setup();
      const onSubmit = vi.fn();
      renderWithProviders(
        <WorkflowTransitionForm
          visible
          statuses={allStatuses}
          onHide={vi.fn()}
          onSubmit={onSubmit}
        />,
      );

      await selectDropdownOption(user, 'Source state', IN_REVIEW);
      await selectDropdownOption(user, 'Target state', APPROVED);
      await user.type(screen.getByLabelText('Action Code'), 'SIGN_OFF');
      await selectDropdownOption(user, 'Action type', 'Approve');
      await user.click(getInputByLabel('Requires comment'));
      await user.click(getInputByLabel('Auto execute'));
      await user.click(screen.getByRole('button', { name: 'Add Transition' }));

      await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
      expect(submittedData(onSubmit)).toEqual({
        from_status_id: middleStatus.id,
        to_status_id: terminalStatus.id,
        action_code: 'SIGN_OFF',
        action_type: 'APPROVE',
        requires_comment: true,
        auto_execute: true,
        priority: 0,
        guard_expression: null,
      });
    });

    it('submits a typed priority', async () => {
      const user = userEvent.setup();
      const onSubmit = vi.fn();
      renderWithProviders(
        <WorkflowTransitionForm
          visible
          statuses={allStatuses}
          onHide={vi.fn()}
          onSubmit={onSubmit}
        />,
      );

      await selectDropdownOption(user, 'Source state', DRAFT);
      await selectDropdownOption(user, 'Target state', IN_REVIEW);
      await user.type(screen.getByLabelText('Action Code'), 'GO');
      const priority = getInputByLabel('Transition priority');
      await user.clear(priority);
      await user.type(priority, '15');
      await user.click(screen.getByRole('button', { name: 'Add Transition' }));

      await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
      expect(submittedData(onSubmit).priority).toBe(15);
    });
  });

  describe('resetting', () => {
    it('clears every field when the dialog is closed and reopened', async () => {
      const user = userEvent.setup();
      const props = { statuses: allStatuses, onHide: vi.fn(), onSubmit: vi.fn() };
      const { rerender } = renderWithProviders(<WorkflowTransitionForm visible {...props} />);
      await selectDropdownOption(user, 'Source state', DRAFT);
      await user.type(screen.getByLabelText('Action Code'), 'LEFTOVER');
      await selectDropdownOption(user, 'Action type', 'Reject');

      rerender(<WorkflowTransitionForm visible={false} {...props} />);
      rerender(<WorkflowTransitionForm visible {...props} />);

      expect(screen.getByLabelText('Action Code')).toHaveValue('');
      expect(getDropdownLabel('Action type')).toBe('Custom (no approval effect)');
      // A reset source re-opens the full target list (nothing is excluded).
      const options = await listDropdownOptions(user, 'Target state');
      expect(options).toEqual([DRAFT, IN_REVIEW, APPROVED]);
    });
  });

  it('calls onHide when Cancel is clicked, without calling onSubmit', async () => {
    const user = userEvent.setup();
    const onHide = vi.fn();
    const onSubmit = vi.fn();
    renderWithProviders(
      <WorkflowTransitionForm visible statuses={allStatuses} onHide={onHide} onSubmit={onSubmit} />,
    );

    await user.click(screen.getByRole('button', { name: 'Cancel' }));

    expect(onHide).toHaveBeenCalledTimes(1);
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('disables the action button while loading', () => {
    renderWithProviders(
      <WorkflowTransitionForm
        visible
        statuses={allStatuses}
        loading
        onHide={vi.fn()}
        onSubmit={vi.fn()}
      />,
    );

    expect(screen.getByRole('button', { name: 'Add Transition' })).toHaveClass('p-disabled');
  });
});

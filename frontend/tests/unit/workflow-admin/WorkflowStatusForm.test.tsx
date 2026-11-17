import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { WorkflowStatusForm } from '@features/workflow-admin/components/WorkflowStatusForm';

import {
  getDropdownLabel,
  renderWithProviders,
  screen,
  selectDropdownOption,
  waitFor,
} from '../../test-utils';

import { getInputByLabel, initialStatus, middleStatus, terminalStatus } from './fixtures';

const INITIAL_OPTION = 'Initial — workflows start here';
const INTERMEDIATE_OPTION = 'Intermediate — in progress';
const TERMINAL_OPTION = 'Terminal — workflow ends here';

/** `handleSubmit(submit)` also passes the click event, so assert on the data argument only. */
const submittedData = (onSubmit: ReturnType<typeof vi.fn>) =>
  onSubmit.mock.calls[0]?.[0] as Record<string, unknown>;

describe('WorkflowStatusForm', () => {
  it('does not render dialog content while not visible', () => {
    renderWithProviders(
      <WorkflowStatusForm visible={false} status={null} onHide={vi.fn()} onSubmit={vi.fn()} />,
    );

    expect(screen.queryByLabelText('Workflow state dialog')).not.toBeInTheDocument();
  });

  describe('create mode', () => {
    it('shows the "Add State" header with empty fields, Intermediate position and the suggested sequence', () => {
      renderWithProviders(
        <WorkflowStatusForm
          visible
          status={null}
          nextSequence={30}
          onHide={vi.fn()}
          onSubmit={vi.fn()}
        />,
      );

      expect(screen.getByLabelText('Code')).toHaveValue('');
      expect(screen.getByLabelText('Name')).toHaveValue('');
      expect(getDropdownLabel('State position')).toBe(INTERMEDIATE_OPTION);
      expect(getInputByLabel('Display order')).toHaveValue('30');
      expect(screen.getByRole('button', { name: 'Add State' })).toBeInTheDocument();
    });

    it('defaults the sequence to 0 when no suggestion is passed', () => {
      renderWithProviders(
        <WorkflowStatusForm visible status={null} onHide={vi.fn()} onSubmit={vi.fn()} />,
      );

      expect(getInputByLabel('Display order')).toHaveValue('0');
    });

    it('follows a changed nextSequence suggestion while the dialog is open', () => {
      const { rerender } = renderWithProviders(
        <WorkflowStatusForm
          visible
          status={null}
          nextSequence={10}
          onHide={vi.fn()}
          onSubmit={vi.fn()}
        />,
      );

      rerender(
        <WorkflowStatusForm
          visible
          status={null}
          nextSequence={40}
          onHide={vi.fn()}
          onSubmit={vi.fn()}
        />,
      );

      expect(getInputByLabel('Display order')).toHaveValue('40');
    });

    it('rejects a code shorter than 2 characters', async () => {
      const user = userEvent.setup();
      const onSubmit = vi.fn();
      renderWithProviders(
        <WorkflowStatusForm visible status={null} onHide={vi.fn()} onSubmit={onSubmit} />,
      );

      await user.type(screen.getByLabelText('Code'), 'A');
      await user.type(screen.getByLabelText('Name'), 'Draft');
      await user.click(screen.getByRole('button', { name: 'Add State' }));

      await waitFor(() =>
        expect(screen.getByText('Code must be at least 2 characters')).toBeInTheDocument(),
      );
      expect(onSubmit).not.toHaveBeenCalled();
    });

    it('rejects a lower-case code with the character-set message', async () => {
      const user = userEvent.setup();
      const onSubmit = vi.fn();
      renderWithProviders(
        <WorkflowStatusForm visible status={null} onHide={vi.fn()} onSubmit={onSubmit} />,
      );

      await user.type(screen.getByLabelText('Code'), 'in review');
      await user.type(screen.getByLabelText('Name'), 'In Review');
      await user.click(screen.getByRole('button', { name: 'Add State' }));

      await waitFor(() =>
        expect(
          screen.getByText('Use upper case letters, numbers and underscores only'),
        ).toBeInTheDocument(),
      );
      expect(onSubmit).not.toHaveBeenCalled();
    });

    it('rejects a blank name', async () => {
      const user = userEvent.setup();
      const onSubmit = vi.fn();
      renderWithProviders(
        <WorkflowStatusForm visible status={null} onHide={vi.fn()} onSubmit={onSubmit} />,
      );

      await user.type(screen.getByLabelText('Code'), 'DRAFT');
      await user.click(screen.getByRole('button', { name: 'Add State' }));

      await waitFor(() => expect(screen.getByText('Name is required')).toBeInTheDocument());
      expect(onSubmit).not.toHaveBeenCalled();
    });

    it('maps the default Intermediate position to is_initial=false, is_terminal=false', async () => {
      const user = userEvent.setup();
      const onSubmit = vi.fn();
      renderWithProviders(
        <WorkflowStatusForm
          visible
          status={null}
          nextSequence={20}
          onHide={vi.fn()}
          onSubmit={onSubmit}
        />,
      );

      await user.type(screen.getByLabelText('Code'), 'IN_REVIEW');
      await user.type(screen.getByLabelText('Name'), 'In Review');
      await user.click(screen.getByRole('button', { name: 'Add State' }));

      await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
      expect(submittedData(onSubmit)).toEqual({
        code: 'IN_REVIEW',
        name: 'In Review',
        sequence: 20,
        is_initial: false,
        is_terminal: false,
      });
    });

    it('maps the Initial position to is_initial=true only', async () => {
      const user = userEvent.setup();
      const onSubmit = vi.fn();
      renderWithProviders(
        <WorkflowStatusForm visible status={null} onHide={vi.fn()} onSubmit={onSubmit} />,
      );

      await user.type(screen.getByLabelText('Code'), 'DRAFT');
      await user.type(screen.getByLabelText('Name'), 'Draft');
      await selectDropdownOption(user, 'State position', INITIAL_OPTION);
      expect(getDropdownLabel('State position')).toBe(INITIAL_OPTION);
      await user.click(screen.getByRole('button', { name: 'Add State' }));

      await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
      expect(submittedData(onSubmit)).toMatchObject({ is_initial: true, is_terminal: false });
    });

    it('maps the Terminal position to is_terminal=true only', async () => {
      const user = userEvent.setup();
      const onSubmit = vi.fn();
      renderWithProviders(
        <WorkflowStatusForm visible status={null} onHide={vi.fn()} onSubmit={onSubmit} />,
      );

      await user.type(screen.getByLabelText('Code'), 'APPROVED');
      await user.type(screen.getByLabelText('Name'), 'Approved');
      await selectDropdownOption(user, 'State position', TERMINAL_OPTION);
      await user.click(screen.getByRole('button', { name: 'Add State' }));

      await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
      expect(submittedData(onSubmit)).toMatchObject({ is_initial: false, is_terminal: true });
    });

    it('never submits a state that is both initial and terminal', async () => {
      const user = userEvent.setup();
      const onSubmit = vi.fn();
      renderWithProviders(
        <WorkflowStatusForm visible status={null} onHide={vi.fn()} onSubmit={onSubmit} />,
      );

      await user.type(screen.getByLabelText('Code'), 'ODD');
      await user.type(screen.getByLabelText('Name'), 'Odd');
      await selectDropdownOption(user, 'State position', INITIAL_OPTION);
      await selectDropdownOption(user, 'State position', TERMINAL_OPTION);
      await user.click(screen.getByRole('button', { name: 'Add State' }));

      await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
      const data = submittedData(onSubmit);
      expect(data.is_initial && data.is_terminal).toBe(false);
      expect(data.is_terminal).toBe(true);
    });
  });

  describe('edit mode', () => {
    it('shows the edit header, uses "Save Changes" and pre-fills the row', () => {
      renderWithProviders(
        <WorkflowStatusForm visible status={middleStatus} onHide={vi.fn()} onSubmit={vi.fn()} />,
      );

      expect(screen.getByText('Edit State — IN_REVIEW')).toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'Save Changes' })).toBeInTheDocument();
      expect(screen.queryByRole('button', { name: 'Add State' })).not.toBeInTheDocument();
      expect(screen.getByLabelText('Code')).toHaveValue('IN_REVIEW');
      expect(screen.getByLabelText('Name')).toHaveValue('In Review');
      expect(getInputByLabel('Display order')).toHaveValue('10');
    });

    it.each([
      [initialStatus, INITIAL_OPTION],
      [middleStatus, INTERMEDIATE_OPTION],
      [terminalStatus, TERMINAL_OPTION],
    ])('derives the position from the row flags (%#)', (status, expectedLabel) => {
      renderWithProviders(
        <WorkflowStatusForm visible status={status} onHide={vi.fn()} onSubmit={vi.fn()} />,
      );

      expect(getDropdownLabel('State position')).toBe(expectedLabel);
    });

    it('ignores the nextSequence suggestion and keeps the row’s own sequence', () => {
      renderWithProviders(
        <WorkflowStatusForm
          visible
          status={middleStatus}
          nextSequence={999}
          onHide={vi.fn()}
          onSubmit={vi.fn()}
        />,
      );

      expect(getInputByLabel('Display order')).toHaveValue('10');
    });

    it('round-trips a terminal row back to is_terminal=true on submit', async () => {
      const user = userEvent.setup();
      const onSubmit = vi.fn();
      renderWithProviders(
        <WorkflowStatusForm visible status={terminalStatus} onHide={vi.fn()} onSubmit={onSubmit} />,
      );

      await user.click(screen.getByRole('button', { name: 'Save Changes' }));

      await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
      expect(submittedData(onSubmit)).toEqual({
        code: 'APPROVED',
        name: 'Approved',
        sequence: 20,
        is_initial: false,
        is_terminal: true,
      });
    });

    it('submits a changed name', async () => {
      const user = userEvent.setup();
      const onSubmit = vi.fn();
      renderWithProviders(
        <WorkflowStatusForm visible status={middleStatus} onHide={vi.fn()} onSubmit={onSubmit} />,
      );

      await user.clear(screen.getByLabelText('Name'));
      await user.type(screen.getByLabelText('Name'), 'Under Review');
      await user.click(screen.getByRole('button', { name: 'Save Changes' }));

      await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
      expect(submittedData(onSubmit)).toMatchObject({ name: 'Under Review', code: 'IN_REVIEW' });
    });
  });

  describe('resetting', () => {
    it('clears the fields when the dialog switches from edit to create', () => {
      const { rerender } = renderWithProviders(
        <WorkflowStatusForm
          visible
          status={middleStatus}
          nextSequence={50}
          onHide={vi.fn()}
          onSubmit={vi.fn()}
        />,
      );
      expect(screen.getByLabelText('Name')).toHaveValue('In Review');

      rerender(
        <WorkflowStatusForm
          visible
          status={null}
          nextSequence={50}
          onHide={vi.fn()}
          onSubmit={vi.fn()}
        />,
      );

      expect(screen.getByText('Add State', { selector: '.p-dialog-title' })).toBeInTheDocument();
      expect(screen.getByLabelText('Name')).toHaveValue('');
      expect(screen.getByLabelText('Code')).toHaveValue('');
      expect(getDropdownLabel('State position')).toBe(INTERMEDIATE_OPTION);
      expect(getInputByLabel('Display order')).toHaveValue('50');
    });

    it('does not show previously typed values after the dialog is closed and reopened', async () => {
      const user = userEvent.setup();
      const { rerender } = renderWithProviders(
        <WorkflowStatusForm visible status={null} onHide={vi.fn()} onSubmit={vi.fn()} />,
      );
      await user.type(screen.getByLabelText('Name'), 'Leftover');

      rerender(
        <WorkflowStatusForm visible={false} status={null} onHide={vi.fn()} onSubmit={vi.fn()} />,
      );
      rerender(<WorkflowStatusForm visible status={null} onHide={vi.fn()} onSubmit={vi.fn()} />);

      expect(screen.getByLabelText('Name')).toHaveValue('');
    });
  });

  it('calls onHide when Cancel is clicked, without calling onSubmit', async () => {
    const user = userEvent.setup();
    const onHide = vi.fn();
    const onSubmit = vi.fn();
    renderWithProviders(
      <WorkflowStatusForm visible status={null} onHide={onHide} onSubmit={onSubmit} />,
    );

    await user.click(screen.getByRole('button', { name: 'Cancel' }));

    expect(onHide).toHaveBeenCalledTimes(1);
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('disables the action button while loading', () => {
    renderWithProviders(
      <WorkflowStatusForm visible status={null} loading onHide={vi.fn()} onSubmit={vi.fn()} />,
    );

    expect(screen.getByRole('button', { name: 'Add State' })).toHaveClass('p-disabled');
  });
});

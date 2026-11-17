import type { ComponentProps } from 'react';

import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { ApprovalMatrixResolveDialog } from '@features/workflow-admin/components/ApprovalMatrixResolveDialog';
import type { ApprovalResolveResponse } from '@features/workflow-admin/models/ApprovalMatrix';

import { fireEvent, renderWithProviders, screen, waitFor, within } from '../../test-utils';

import { matrix } from './fixtures';

const matchedResult: ApprovalResolveResponse = {
  matched: true,
  matrix,
  levels: [1, 2],
  assignments: matrix.assignments,
};

const renderDialog = (
  props: Partial<ComponentProps<typeof ApprovalMatrixResolveDialog>> = {},
) => {
  const onHide = vi.fn();
  const onResolve = vi.fn();
  const view = renderWithProviders(
    <ApprovalMatrixResolveDialog visible onHide={onHide} onResolve={onResolve} {...props} />,
  );
  return { onHide, onResolve, ...view };
};

const setPayload = (value: string) =>
  fireEvent.change(screen.getByLabelText('Sample Record (JSON)'), { target: { value } });

describe('ApprovalMatrixResolveDialog', () => {
  it('does not render dialog content while not visible', () => {
    renderDialog({ visible: false });

    expect(screen.queryByLabelText('Approval routing preview dialog')).not.toBeInTheDocument();
  });

  it('opens with an empty entity type and the sample JSON record', () => {
    renderDialog();

    expect(screen.getByText('Preview Approval Routing')).toBeInTheDocument();
    expect(screen.getByLabelText('Entity Type')).toHaveValue('');
    const payload = screen.getByLabelText('Sample Record (JSON)') as HTMLTextAreaElement;
    expect(JSON.parse(payload.value)).toEqual({ amount: 250000, state: { code: 'MH' } });
  });

  describe('Resolve button', () => {
    it('is disabled until the entity type has at least 2 non-blank characters', async () => {
      const user = userEvent.setup();
      renderDialog();
      const resolve = screen.getByRole('button', { name: 'Resolve' });
      expect(resolve).toBeDisabled();

      await user.type(screen.getByLabelText('Entity Type'), 'a');
      expect(resolve).toBeDisabled();

      await user.clear(screen.getByLabelText('Entity Type'));
      await user.type(screen.getByLabelText('Entity Type'), '   ');
      expect(resolve).toBeDisabled();

      await user.clear(screen.getByLabelText('Entity Type'));
      await user.type(screen.getByLabelText('Entity Type'), 'ab');
      expect(resolve).toBeEnabled();
    });

    it('calls onResolve with the trimmed entity type and the parsed sample record', async () => {
      const user = userEvent.setup();
      const { onResolve } = renderDialog();

      await user.type(screen.getByLabelText('Entity Type'), '  compliance_task  ');
      await user.click(screen.getByRole('button', { name: 'Resolve' }));

      expect(onResolve).toHaveBeenCalledTimes(1);
      expect(onResolve).toHaveBeenCalledWith('compliance_task', {
        amount: 250000,
        state: { code: 'MH' },
      });
    });

    it('sends an edited record', async () => {
      const user = userEvent.setup();
      const { onResolve } = renderDialog();

      await user.type(screen.getByLabelText('Entity Type'), 'compliance_task');
      setPayload('{"amount": 5}');
      await user.click(screen.getByRole('button', { name: 'Resolve' }));

      expect(onResolve).toHaveBeenCalledWith('compliance_task', { amount: 5 });
    });
  });

  describe('sample record validation', () => {
    it('reports invalid JSON and does not call onResolve', async () => {
      const user = userEvent.setup();
      const { onResolve } = renderDialog();

      await user.type(screen.getByLabelText('Entity Type'), 'compliance_task');
      setPayload('{not json');
      await user.click(screen.getByRole('button', { name: 'Resolve' }));

      expect(screen.getByText('Sample record must be valid JSON.')).toBeInTheDocument();
      expect(screen.getByLabelText('Sample Record (JSON)')).toHaveClass('p-invalid');
      expect(onResolve).not.toHaveBeenCalled();
    });

    it.each([
      ['an array', '[1, 2]'],
      ['a string', '"hello"'],
      ['a number', '42'],
      ['null', 'null'],
    ])('rejects %s as not a JSON object', async (_label, text) => {
      const user = userEvent.setup();
      const { onResolve } = renderDialog();

      await user.type(screen.getByLabelText('Entity Type'), 'compliance_task');
      setPayload(text);
      await user.click(screen.getByRole('button', { name: 'Resolve' }));

      expect(screen.getByText('Sample record must be a JSON object.')).toBeInTheDocument();
      expect(onResolve).not.toHaveBeenCalled();
    });

    it('clears the error once a valid record is resolved', async () => {
      const user = userEvent.setup();
      const { onResolve } = renderDialog();
      await user.type(screen.getByLabelText('Entity Type'), 'compliance_task');
      setPayload('oops');
      await user.click(screen.getByRole('button', { name: 'Resolve' }));
      expect(screen.getByText('Sample record must be valid JSON.')).toBeInTheDocument();

      setPayload('{"a": 1}');
      await user.click(screen.getByRole('button', { name: 'Resolve' }));

      expect(screen.queryByText('Sample record must be valid JSON.')).not.toBeInTheDocument();
      expect(onResolve).toHaveBeenCalledWith('compliance_task', { a: 1 });
    });
  });

  describe('result display', () => {
    it('shows nothing about a result before one exists', () => {
      renderDialog({ result: null });

      expect(screen.queryByText('Matched')).not.toBeInTheDocument();
      expect(screen.queryByText(/No active matrix matched/)).not.toBeInTheDocument();
    });

    it('warns when no matrix matched', () => {
      renderDialog({ result: { matched: false, matrix: null, levels: [], assignments: [] } });

      expect(
        screen.getByText('No active matrix matched this record — it would route to nobody.'),
      ).toBeInTheDocument();
      expect(screen.queryByText('Matched')).not.toBeInTheDocument();
    });

    it('shows the winning matrix and a row per approver level', () => {
      renderDialog({ result: matchedResult });

      expect(screen.getByText('Matched')).toBeInTheDocument();
      expect(screen.getByText('Filing approval by amount')).toBeInTheDocument();
      expect(screen.getByText('(FILING_BY_AMOUNT)')).toBeInTheDocument();
      expect(screen.getByText('priority 5')).toBeInTheDocument();

      const table = screen.getByRole('table');
      const rows = within(table).getAllByRole('row').slice(1);
      expect(rows).toHaveLength(2);
      const [roleRow, userRow] = rows;
      if (!roleRow || !userRow) throw new Error('expected two approver rows');
      expect(within(roleRow).getByText('L1')).toBeInTheDocument();
      expect(within(roleRow).getByText('ROLE')).toBeInTheDocument();
      expect(within(roleRow).getByText('901')).toBeInTheDocument();
      expect(within(userRow).getByText('L2')).toBeInTheDocument();
      expect(within(userRow).getByText('USER')).toBeInTheDocument();
      expect(within(userRow).getByText('801')).toBeInTheDocument();
    });

    it('shows a dash for an assignment with neither a role nor a user', () => {
      renderDialog({
        result: {
          ...matchedResult,
          assignments: [{ id: 9, level: 1, assignment_type: 'ROLE', user_id: null, role_id: null }],
        },
      });

      expect(within(screen.getByRole('table')).getByText('—')).toBeInTheDocument();
    });

    it('says so when the matched matrix defines no approval levels', () => {
      renderDialog({ result: { ...matchedResult, assignments: [] } });

      expect(screen.getByText('Matrix matched but defines no approval levels.')).toBeInTheDocument();
    });
  });

  describe('resetting', () => {
    it('clears the entity type, record and error when the dialog is reopened', async () => {
      const user = userEvent.setup();
      const props = { onHide: vi.fn(), onResolve: vi.fn() };
      const { rerender } = renderWithProviders(<ApprovalMatrixResolveDialog visible {...props} />);
      await user.type(screen.getByLabelText('Entity Type'), 'compliance_task');
      setPayload('oops');
      await user.click(screen.getByRole('button', { name: 'Resolve' }));
      expect(screen.getByText('Sample record must be valid JSON.')).toBeInTheDocument();

      rerender(<ApprovalMatrixResolveDialog visible={false} {...props} />);
      rerender(<ApprovalMatrixResolveDialog visible {...props} />);

      await waitFor(() => expect(screen.getByLabelText('Entity Type')).toHaveValue(''));
      expect(screen.queryByText('Sample record must be valid JSON.')).not.toBeInTheDocument();
      const payload = screen.getByLabelText('Sample Record (JSON)') as HTMLTextAreaElement;
      expect(JSON.parse(payload.value)).toEqual({ amount: 250000, state: { code: 'MH' } });
    });
  });

  it('calls onHide when Close is clicked', async () => {
    const user = userEvent.setup();
    const { onHide, onResolve } = renderDialog();

    // The dialog's own header X is also named Close, so click the footer button by its label.
    await user.click(screen.getByText('Close', { selector: '.p-button-label' }));

    expect(onHide).toHaveBeenCalledTimes(1);
    expect(onResolve).not.toHaveBeenCalled();
  });

  it('shows a loading state on the Resolve button while a request is in flight', async () => {
    const user = userEvent.setup();
    renderDialog({ loading: true });
    await user.type(screen.getByLabelText('Entity Type'), 'compliance_task');

    expect(screen.getByRole('button', { name: 'Resolve' })).toHaveClass('p-disabled');
  });
});

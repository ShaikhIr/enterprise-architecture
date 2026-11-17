import type { ComponentProps } from 'react';

import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { ApprovalMatrixForm } from '@features/workflow-admin/components/ApprovalMatrixForm';

import {
  getDropdownLabel,
  getValidationError,
  renderWithProviders,
  screen,
  selectDropdownOption,
  waitFor,
} from '../../test-utils';

import {
  ROLE_ADMIN_ID,
  ROLE_REVIEWER_ID,
  USER_ALICE_ID,
  getInputByLabel,
  listDropdownOptions,
  matrix,
  mockMatrixFormLookups,
} from './fixtures';

type FormProps = ComponentProps<typeof ApprovalMatrixForm>;
type User = ReturnType<typeof userEvent.setup>;

const ADMIN = 'Admin (ADMIN)';
const REVIEWER = 'Reviewer (REVIEWER)';
const ALICE = 'alice — Alice Anand';
const BOB = 'bob';

const renderForm = (props: Partial<FormProps> = {}) => {
  mockMatrixFormLookups();
  const onSubmit = vi.fn();
  const onHide = vi.fn();
  const view = renderWithProviders(
    <ApprovalMatrixForm visible matrix={null} onHide={onHide} onSubmit={onSubmit} {...props} />,
  );
  return { onSubmit, onHide, ...view };
};

/** `handleSubmit(onSubmit)` also passes the click event, so assert on the data argument only. */
const submittedData = (onSubmit: ReturnType<typeof vi.fn>) =>
  onSubmit.mock.calls[0]?.[0] as Record<string, unknown>;

const fillBasics = async (user: User, code = 'FILING_BY_AMOUNT') => {
  await user.type(screen.getByLabelText('Code'), code);
  await user.type(screen.getByLabelText('Name'), 'Filing approval by amount');
  await user.type(screen.getByLabelText('Entity Type'), 'compliance_task');
};

const clickSave = (user: User) => user.click(screen.getByRole('button', { name: 'Create' }));

const waitForRoles = (row: number) =>
  waitFor(() =>
    expect(getDropdownLabel(`Role for level row ${row}`)).not.toBe('Loading roles...'),
  );

const addLevel = async (user: User) => {
  await user.click(screen.getByRole('button', { name: 'Add Level' }));
};

const addCondition = async (user: User) => {
  await user.click(screen.getByRole('button', { name: 'Add Condition' }));
};

describe('ApprovalMatrixForm', () => {
  it('does not render dialog content while not visible', () => {
    renderForm({ visible: false });

    expect(screen.queryByLabelText('Approval matrix dialog')).not.toBeInTheDocument();
  });

  describe('create mode', () => {
    it('shows the "New Approval Matrix" header with empty fields and empty-state hints', () => {
      renderForm();

      expect(screen.getByText('New Approval Matrix')).toBeInTheDocument();
      expect(screen.getByLabelText('Code')).toHaveValue('');
      expect(screen.getByLabelText('Code')).toBeEnabled();
      expect(screen.getByLabelText('Name')).toHaveValue('');
      expect(screen.getByLabelText('Entity Type')).toHaveValue('');
      expect(getInputByLabel('Matrix priority')).toHaveValue('0');
      expect(getInputByLabel('Matrix active')).toBeChecked();
      expect(
        screen.getByText('No conditions — this matrix will match every record of its entity type.'),
      ).toBeInTheDocument();
      expect(screen.getByText('No approval levels defined yet.')).toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'Create' })).toBeInTheDocument();
      expect(screen.queryByText(/Saving replaces the stored conditions/)).not.toBeInTheDocument();
    });

    describe('basic validation', () => {
      it('rejects a code shorter than 2 characters', async () => {
        const user = userEvent.setup();
        const { onSubmit } = renderForm();

        await fillBasics(user, 'A');
        await clickSave(user);

        await waitFor(() =>
          expect(screen.getByText('Code must be at least 2 characters')).toBeInTheDocument(),
        );
        expect(onSubmit).not.toHaveBeenCalled();
      });

      it('rejects a lower-case code with the character-set message', async () => {
        const user = userEvent.setup();
        const { onSubmit } = renderForm();

        await fillBasics(user, 'filing-by-amount');
        await clickSave(user);

        await waitFor(() =>
          expect(
            screen.getByText('Use upper case letters, numbers and underscores only'),
          ).toBeInTheDocument(),
        );
        expect(onSubmit).not.toHaveBeenCalled();
      });

      it('rejects a name shorter than 2 characters', async () => {
        const user = userEvent.setup();
        const { onSubmit } = renderForm();

        await user.type(screen.getByLabelText('Code'), 'FILING');
        await user.type(screen.getByLabelText('Name'), 'F');
        await user.type(screen.getByLabelText('Entity Type'), 'compliance_task');
        await clickSave(user);

        await waitFor(() =>
          expect(screen.getByText('Name must be at least 2 characters')).toBeInTheDocument(),
        );
        expect(onSubmit).not.toHaveBeenCalled();
      });

      it('rejects an entity type that is too short', async () => {
        const user = userEvent.setup();
        const { onSubmit } = renderForm();

        await user.type(screen.getByLabelText('Code'), 'FILING');
        await user.type(screen.getByLabelText('Name'), 'Filing');
        await user.type(screen.getByLabelText('Entity Type'), 't');
        await clickSave(user);

        await waitFor(() =>
          expect(screen.getByText('Entity type must be at least 2 characters')).toBeInTheDocument(),
        );
        expect(onSubmit).not.toHaveBeenCalled();
      });

      it('rejects an upper-case entity type with the character-set message', async () => {
        const user = userEvent.setup();
        const { onSubmit } = renderForm();

        await user.type(screen.getByLabelText('Code'), 'FILING');
        await user.type(screen.getByLabelText('Name'), 'Filing');
        await user.type(screen.getByLabelText('Entity Type'), 'Compliance Task');
        await clickSave(user);

        await waitFor(() =>
          expect(
            screen.getByText('Use lower case letters, numbers and underscores only'),
          ).toBeInTheDocument(),
        );
        expect(onSubmit).not.toHaveBeenCalled();
      });
    });

    describe('conditions', () => {
      it('adds a condition row with the default operator, data type and group', async () => {
        const user = userEvent.setup();
        renderForm();

        await addCondition(user);

        expect(screen.getByLabelText('Condition 1 field')).toHaveValue('');
        expect(getDropdownLabel('Condition 1 operator')).toBe('equals');
        expect(screen.getByLabelText('Condition 1 value')).toHaveValue('');
        expect(getDropdownLabel('Condition 1 data type')).toBe('String');
        expect(screen.getByLabelText('Condition 1 group')).toHaveValue('default');
        expect(screen.queryByText(/No conditions — this matrix will match every/)).toBeNull();
      });

      it('requires a field and a value on every condition', async () => {
        const user = userEvent.setup();
        const { onSubmit } = renderForm();

        await fillBasics(user);
        await addCondition(user);
        await clickSave(user);

        await waitFor(() => expect(getValidationError('Field is required')).toBeInTheDocument());
        expect(getValidationError('Value is required')).toBeInTheDocument();
        expect(onSubmit).not.toHaveBeenCalled();
      });

      it('does not submit a condition whose group has been cleared', async () => {
        const user = userEvent.setup();
        const { onSubmit } = renderForm();

        await fillBasics(user);
        await addCondition(user);
        await user.type(screen.getByLabelText('Condition 1 field'), 'amount');
        await user.type(screen.getByLabelText('Condition 1 value'), '5');
        await user.clear(screen.getByLabelText('Condition 1 group'));
        await clickSave(user);

        // Give validation time to run before asserting the negative.
        await waitFor(() => expect(screen.getByLabelText('Condition 1 group')).toHaveValue(''));
        expect(onSubmit).not.toHaveBeenCalled();
      });

      // Suspected src bug: `ruleSchema.logical_group` is `.min(1)` with no message and the
      // row renders no error element for it, so a blank group blocks submit silently while
      // the field and value get visible messages. The expectation below is the correct
      // behaviour; `it.fails` flips to a hard failure once the form shows an error.
      it.fails('shows a validation message when a condition group is blank', async () => {
        const user = userEvent.setup();
        renderForm();

        await fillBasics(user);
        await addCondition(user);
        await user.type(screen.getByLabelText('Condition 1 field'), 'amount');
        await user.type(screen.getByLabelText('Condition 1 value'), '5');
        await user.clear(screen.getByLabelText('Condition 1 group'));
        await clickSave(user);

        // Every other field is valid at this point, so any `.p-error` must be about the group.
        await waitFor(() => expect(document.querySelector('.p-error')).toBeInTheDocument());
      });

      it('removes only the condition whose trash button was clicked', async () => {
        const user = userEvent.setup();
        renderForm();

        await addCondition(user);
        await addCondition(user);
        await user.type(screen.getByLabelText('Condition 1 field'), 'amount');
        await user.type(screen.getByLabelText('Condition 2 field'), 'state.code');

        await user.click(screen.getByRole('button', { name: 'Remove condition 1' }));

        expect(screen.queryByLabelText('Condition 2 field')).not.toBeInTheDocument();
        expect(screen.getByLabelText('Condition 1 field')).toHaveValue('state.code');
      });

      it('shows the match-everything hint again after the last condition is removed', async () => {
        const user = userEvent.setup();
        renderForm();

        await addCondition(user);
        await user.click(screen.getByRole('button', { name: 'Remove condition 1' }));

        expect(
          screen.getByText(
            'No conditions — this matrix will match every record of its entity type.',
          ),
        ).toBeInTheDocument();
      });
    });

    describe('approval levels', () => {
      it('adds a Role level numbered 1 with the roles dropdown, excluding inactive roles', async () => {
        const user = userEvent.setup();
        renderForm();

        await addLevel(user);
        await waitForRoles(1);

        expect(getInputByLabel('Level number for row 1')).toHaveValue('1');
        expect(getDropdownLabel('Assignment type for row 1')).toBe('Role');
        expect(getDropdownLabel('Role for level row 1')).toBe('Select a role');
        expect(screen.queryByText('No approval levels defined yet.')).not.toBeInTheDocument();

        expect(await listDropdownOptions(user, 'Role for level row 1')).toEqual([ADMIN, REVIEWER]);
      });

      it('numbers a new level one above the highest existing level', async () => {
        const user = userEvent.setup();
        renderForm();

        await addLevel(user);
        await addLevel(user);
        await addLevel(user);

        expect(getInputByLabel('Level number for row 1')).toHaveValue('1');
        expect(getInputByLabel('Level number for row 2')).toHaveValue('2');
        expect(getInputByLabel('Level number for row 3')).toHaveValue('3');
        expect(screen.getByText('Chain:')).toBeInTheDocument();
        for (const tag of ['L1', 'L2', 'L3']) {
          expect(screen.getByText(tag)).toBeInTheDocument();
        }
      });

      it('requires a role for a Role level', async () => {
        const user = userEvent.setup();
        const { onSubmit } = renderForm();

        await fillBasics(user);
        await addLevel(user);
        await waitForRoles(1);
        await clickSave(user);

        await waitFor(() => expect(getValidationError('Select a role')).toBeInTheDocument());
        expect(onSubmit).not.toHaveBeenCalled();
      });

      it('requires a user for a User level', async () => {
        const user = userEvent.setup();
        const { onSubmit } = renderForm();

        await fillBasics(user);
        await addLevel(user);
        await waitForRoles(1);
        await selectDropdownOption(user, 'Assignment type for row 1', 'User');
        await clickSave(user);

        await waitFor(() => expect(getValidationError('Select a user')).toBeInTheDocument());
        expect(onSubmit).not.toHaveBeenCalled();
      });

      it('switches the target picker to users when the type changes, and labels users by name', async () => {
        const user = userEvent.setup();
        renderForm();

        await addLevel(user);
        await waitForRoles(1);
        await selectDropdownOption(user, 'Assignment type for row 1', 'User');

        expect(screen.queryByLabelText('Role for level row 1')).not.toBeInTheDocument();
        await waitFor(() =>
          expect(getDropdownLabel('User for level row 1')).toBe('Select a user'),
        );
        expect(getDropdownLabel('Assignment type for row 1')).toBe('User');
      });

      it('clears a previously chosen role when the type is switched to User and back', async () => {
        const user = userEvent.setup();
        renderForm();

        await addLevel(user);
        await waitForRoles(1);
        await selectDropdownOption(user, 'Role for level row 1', ADMIN);
        expect(getDropdownLabel('Role for level row 1')).toBe(ADMIN);

        await selectDropdownOption(user, 'Assignment type for row 1', 'User');
        await selectDropdownOption(user, 'Assignment type for row 1', 'Role');

        await waitFor(() =>
          expect(getDropdownLabel('Role for level row 1')).toBe('Select a role'),
        );
      });

      it('keeps the level number when the type is switched', async () => {
        const user = userEvent.setup();
        renderForm();

        await addLevel(user);
        await addLevel(user);
        await selectDropdownOption(user, 'Assignment type for row 2', 'User');

        expect(getInputByLabel('Level number for row 2')).toHaveValue('2');
      });

      it('removes only the level whose trash button was clicked and updates the chain', async () => {
        const user = userEvent.setup();
        renderForm();

        await addLevel(user);
        await addLevel(user);
        expect(screen.getByText('L2')).toBeInTheDocument();

        await user.click(screen.getByRole('button', { name: 'Remove level row 2' }));

        expect(screen.queryByLabelText('Level number for row 2')).not.toBeInTheDocument();
        expect(screen.getByText('L1')).toBeInTheDocument();
        expect(screen.queryByText('L2')).not.toBeInTheDocument();
      });

      it('shows the warning again after the last level is removed', async () => {
        const user = userEvent.setup();
        renderForm();

        await addLevel(user);
        await user.click(screen.getByRole('button', { name: 'Remove level row 1' }));

        expect(screen.getByText('No approval levels defined yet.')).toBeInTheDocument();
        expect(screen.queryByText('Chain:')).not.toBeInTheDocument();
      });
    });

    describe('submitting', () => {
      it('submits the basics with empty rule and level sets', async () => {
        const user = userEvent.setup();
        const { onSubmit } = renderForm();

        await fillBasics(user);
        await clickSave(user);

        await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
        expect(submittedData(onSubmit)).toEqual({
          code: 'FILING_BY_AMOUNT',
          name: 'Filing approval by amount',
          entity_type: 'compliance_task',
          priority: 0,
          is_active: true,
          rules: [],
          assignments: [],
        });
      });

      it('submits is_active false after the switch is turned off', async () => {
        const user = userEvent.setup();
        const { onSubmit } = renderForm();

        await fillBasics(user);
        await user.click(getInputByLabel('Matrix active'));
        await clickSave(user);

        await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
        expect(submittedData(onSubmit).is_active).toBe(false);
      });

      it('submits a typed priority', async () => {
        const user = userEvent.setup();
        const { onSubmit } = renderForm();

        await fillBasics(user);
        const priority = getInputByLabel('Matrix priority');
        await user.clear(priority);
        await user.type(priority, '12');
        await clickSave(user);

        await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
        expect(submittedData(onSubmit).priority).toBe(12);
      });

      it('submits a full matrix: a condition with a chosen operator/type and a role level', async () => {
        const user = userEvent.setup();
        const { onSubmit } = renderForm();

        await fillBasics(user);
        await addCondition(user);
        await user.type(screen.getByLabelText('Condition 1 field'), 'amount');
        await selectDropdownOption(user, 'Condition 1 operator', 'is greater than');
        await user.type(screen.getByLabelText('Condition 1 value'), '100000');
        await selectDropdownOption(user, 'Condition 1 data type', 'Number');
        await addLevel(user);
        await waitForRoles(1);
        await selectDropdownOption(user, 'Role for level row 1', ADMIN);
        await clickSave(user);

        await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
        expect(submittedData(onSubmit)).toEqual({
          code: 'FILING_BY_AMOUNT',
          name: 'Filing approval by amount',
          entity_type: 'compliance_task',
          priority: 0,
          is_active: true,
          rules: [
            {
              field: 'amount',
              operator: 'GT',
              value: '100000',
              data_type: 'NUMBER',
              logical_group: 'default',
            },
          ],
          assignments: [
            { level: 1, assignment_type: 'ROLE', user_id: null, role_id: ROLE_ADMIN_ID },
          ],
        });
      });

      it('submits a user level with role_id null, labelling users by employee name or username', async () => {
        const user = userEvent.setup();
        const { onSubmit } = renderForm();

        await fillBasics(user);
        await addLevel(user);
        await waitForRoles(1);
        await selectDropdownOption(user, 'Assignment type for row 1', 'User');
        await waitFor(() =>
          expect(getDropdownLabel('User for level row 1')).not.toBe('Loading users...'),
        );
        await selectDropdownOption(user, 'User for level row 1', BOB);
        expect(getDropdownLabel('User for level row 1')).toBe(BOB);
        await selectDropdownOption(user, 'User for level row 1', ALICE);
        await clickSave(user);

        await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
        expect(submittedData(onSubmit).assignments).toEqual([
          { level: 1, assignment_type: 'USER', user_id: USER_ALICE_ID, role_id: null },
        ]);
      });

      it('submits several levels in row order', async () => {
        const user = userEvent.setup();
        const { onSubmit } = renderForm();

        await fillBasics(user);
        await addLevel(user);
        await addLevel(user);
        await waitForRoles(1);
        await selectDropdownOption(user, 'Role for level row 1', ADMIN);
        await selectDropdownOption(user, 'Role for level row 2', REVIEWER);
        await clickSave(user);

        await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
        expect(submittedData(onSubmit).assignments).toEqual([
          { level: 1, assignment_type: 'ROLE', user_id: null, role_id: ROLE_ADMIN_ID },
          { level: 2, assignment_type: 'ROLE', user_id: null, role_id: ROLE_REVIEWER_ID },
        ]);
      });
    });
  });

  describe('edit mode', () => {
    it('shows the edit header, locks the code, warns about replacement and uses "Save Changes"', () => {
      renderForm({ matrix });

      expect(screen.getByText('Edit Matrix — FILING_BY_AMOUNT')).toBeInTheDocument();
      expect(screen.getByLabelText('Code')).toHaveValue('FILING_BY_AMOUNT');
      expect(screen.getByLabelText('Code')).toBeDisabled();
      expect(
        screen.getByText(
          'Saving replaces the stored conditions and levels with what is shown here.',
        ),
      ).toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'Save Changes' })).toBeInTheDocument();
      expect(screen.queryByRole('button', { name: 'Create' })).not.toBeInTheDocument();
    });

    it('pre-fills basics, conditions and levels from the matrix', async () => {
      renderForm({ matrix });

      expect(screen.getByLabelText('Name')).toHaveValue('Filing approval by amount');
      expect(screen.getByLabelText('Entity Type')).toHaveValue('compliance_task');
      expect(getInputByLabel('Matrix priority')).toHaveValue('5');
      expect(getInputByLabel('Matrix active')).toBeChecked();

      expect(screen.getByLabelText('Condition 1 field')).toHaveValue('amount');
      expect(getDropdownLabel('Condition 1 operator')).toBe('is greater than');
      expect(screen.getByLabelText('Condition 1 value')).toHaveValue('100000');
      expect(getDropdownLabel('Condition 1 data type')).toBe('Number');
      expect(screen.getByLabelText('Condition 1 group')).toHaveValue('default');

      expect(getInputByLabel('Level number for row 1')).toHaveValue('1');
      expect(getInputByLabel('Level number for row 2')).toHaveValue('2');
      expect(getDropdownLabel('Assignment type for row 1')).toBe('Role');
      expect(getDropdownLabel('Assignment type for row 2')).toBe('User');
      await waitFor(() => expect(getDropdownLabel('Role for level row 1')).toBe(ADMIN));
      await waitFor(() => expect(getDropdownLabel('User for level row 2')).toBe(ALICE));
    });

    it('lists each distinct level once in the chain', () => {
      renderForm({
        matrix: {
          ...matrix,
          assignments: [
            { id: 1, level: 1, assignment_type: 'ROLE', user_id: null, role_id: ROLE_ADMIN_ID },
            { id: 2, level: 1, assignment_type: 'ROLE', user_id: null, role_id: ROLE_REVIEWER_ID },
            { id: 3, level: 3, assignment_type: 'USER', user_id: USER_ALICE_ID, role_id: null },
          ],
        },
      });

      expect(screen.getAllByText('L1')).toHaveLength(1);
      expect(screen.getByText('L3')).toBeInTheDocument();
      expect(screen.queryByText('L2')).not.toBeInTheDocument();
    });

    it('submits the unchanged matrix with ids stripped from rules and levels', async () => {
      const user = userEvent.setup();
      const { onSubmit } = renderForm({ matrix });

      await user.click(screen.getByRole('button', { name: 'Save Changes' }));

      await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
      expect(submittedData(onSubmit)).toEqual({
        code: 'FILING_BY_AMOUNT',
        name: 'Filing approval by amount',
        entity_type: 'compliance_task',
        priority: 5,
        is_active: true,
        rules: [
          {
            field: 'amount',
            operator: 'GT',
            value: '100000',
            data_type: 'NUMBER',
            logical_group: 'default',
          },
        ],
        assignments: [
          { level: 1, assignment_type: 'ROLE', user_id: null, role_id: ROLE_ADMIN_ID },
          { level: 2, assignment_type: 'USER', user_id: USER_ALICE_ID, role_id: null },
        ],
      });
    });

    it('submits an edited name and a removed condition', async () => {
      const user = userEvent.setup();
      const { onSubmit } = renderForm({ matrix });

      await user.clear(screen.getByLabelText('Name'));
      await user.type(screen.getByLabelText('Name'), 'Renamed matrix');
      await user.click(screen.getByRole('button', { name: 'Remove condition 1' }));
      await user.click(screen.getByRole('button', { name: 'Save Changes' }));

      await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
      expect(submittedData(onSubmit)).toMatchObject({ name: 'Renamed matrix', rules: [] });
    });
  });

  describe('resetting', () => {
    it('clears basics, conditions and levels when the dialog switches from edit to create', () => {
      const onHide = vi.fn();
      const onSubmit = vi.fn();
      mockMatrixFormLookups();
      const { rerender } = renderWithProviders(
        <ApprovalMatrixForm visible matrix={matrix} onHide={onHide} onSubmit={onSubmit} />,
      );
      expect(screen.getByLabelText('Condition 1 field')).toHaveValue('amount');

      rerender(<ApprovalMatrixForm visible matrix={null} onHide={onHide} onSubmit={onSubmit} />);

      expect(screen.getByText('New Approval Matrix')).toBeInTheDocument();
      expect(screen.getByLabelText('Code')).toHaveValue('');
      expect(screen.getByLabelText('Code')).toBeEnabled();
      expect(screen.getByLabelText('Name')).toHaveValue('');
      expect(getInputByLabel('Matrix priority')).toHaveValue('0');
      expect(screen.queryByLabelText('Condition 1 field')).not.toBeInTheDocument();
      expect(screen.queryByLabelText('Level number for row 1')).not.toBeInTheDocument();
      expect(screen.getByText('No approval levels defined yet.')).toBeInTheDocument();
    });

    it('does not show previously added rows after the dialog is closed and reopened', async () => {
      const user = userEvent.setup();
      const onHide = vi.fn();
      const onSubmit = vi.fn();
      mockMatrixFormLookups();
      const { rerender } = renderWithProviders(
        <ApprovalMatrixForm visible matrix={null} onHide={onHide} onSubmit={onSubmit} />,
      );
      await addCondition(user);
      await addLevel(user);

      rerender(
        <ApprovalMatrixForm visible={false} matrix={null} onHide={onHide} onSubmit={onSubmit} />,
      );
      rerender(<ApprovalMatrixForm visible matrix={null} onHide={onHide} onSubmit={onSubmit} />);

      expect(screen.queryByLabelText('Condition 1 field')).not.toBeInTheDocument();
      expect(screen.queryByLabelText('Level number for row 1')).not.toBeInTheDocument();
    });
  });

  it('calls onHide when Cancel is clicked, without calling onSubmit', async () => {
    const user = userEvent.setup();
    const { onHide, onSubmit } = renderForm();

    await user.click(screen.getByRole('button', { name: 'Cancel' }));

    expect(onHide).toHaveBeenCalledTimes(1);
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('disables the action button while loading', () => {
    renderForm({ loading: true });

    expect(screen.getByRole('button', { name: 'Create' })).toHaveClass('p-disabled');
  });
});

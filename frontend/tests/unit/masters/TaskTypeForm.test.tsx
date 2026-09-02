import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { TaskTypeForm } from '@features/masters/components/TaskTypeForm';

import { renderWithProviders, screen, waitFor } from '../../test-utils';

/**
 * TaskType is the flattest master — no dropdowns, no dependent hierarchy.
 * The one thing specific to it is code normalisation: spaces are collapsed
 * to underscores in addition to the trim+upper-case every master form does,
 * so "return filing" becomes "RETURN_FILING" rather than being rejected.
 */
describe('TaskTypeForm', () => {
  it('normalises a code with spaces to upper snake case on submit', async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    renderWithProviders(
      <TaskTypeForm visible taskType={null} onHide={vi.fn()} onSubmit={onSubmit} />,
    );

    await user.type(screen.getByLabelText('Code'), 'return filing');
    await user.type(screen.getByLabelText('Name'), 'Return Filing');
    await user.click(screen.getByRole('button', { name: 'Create' }));

    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({ code: 'RETURN_FILING', name: 'Return Filing' }),
    );
  });

  it('collapses multiple consecutive spaces into a single underscore', async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    renderWithProviders(
      <TaskTypeForm visible taskType={null} onHide={vi.fn()} onSubmit={onSubmit} />,
    );

    await user.type(screen.getByLabelText('Code'), 'return   filing');
    await user.type(screen.getByLabelText('Name'), 'Return Filing');
    await user.click(screen.getByRole('button', { name: 'Create' }));

    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({ code: 'RETURN_FILING' }));
  });

  it('pre-fills the form with the row being edited', () => {
    renderWithProviders(
      <TaskTypeForm
        visible
        taskType={{
          id: 1,
          code: 'RETURN_FILING',
          name: 'Return Filing',
          description: 'Periodic statutory filing',
          is_active: true,
          created_by: 'system',
          created_date: '2024-01-01T00:00:00Z',
          modified_by: 'system',
          modified_date: '2024-01-01T00:00:00Z',
        }}
        onHide={vi.fn()}
        onSubmit={vi.fn()}
      />,
    );

    expect(screen.getByText('Edit Task Type — RETURN_FILING')).toBeInTheDocument();
    expect(screen.getByLabelText('Code')).toHaveValue('RETURN_FILING');
    expect(screen.getByLabelText('Description')).toHaveValue('Periodic statutory filing');
  });
});

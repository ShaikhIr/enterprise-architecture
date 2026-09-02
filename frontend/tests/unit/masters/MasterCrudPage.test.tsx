import { useRef } from 'react';

import userEvent from '@testing-library/user-event';
import { Column } from 'primereact/column';
import type { Toast } from 'primereact/toast';
import { describe, expect, it, vi } from 'vitest';

import { MasterCrudPage } from '@features/masters/components/MasterCrudPage';
import type { AuditedRecord } from '@features/masters/models/common';

import { renderWithProviders, screen, within } from '../../test-utils';

interface Widget extends AuditedRecord {
  code: string;
  name: string;
}

const rows: Widget[] = [
  {
    id: 1,
    code: 'W1',
    name: 'Widget One',
    created_by: 'system',
    created_date: '2024-01-01T00:00:00Z',
    modified_by: 'system',
    modified_date: '2024-01-01T00:00:00Z',
  },
];

/** A thin wrapper so `toastRef` (a hook value) can be supplied inside a component. */
const Harness = ({
  canCreate,
  columns,
  rows: rowsOverride = rows,
  onRefresh = vi.fn(),
  emptyMessage = 'No widgets',
}: {
  canCreate: boolean;
  columns: React.ReactNode;
  rows?: Widget[];
  onRefresh?: () => void;
  emptyMessage?: string;
}) => {
  const toastRef = useRef<Toast | null>(null);
  return (
    <MasterCrudPage<Widget>
      title="Widgets"
      subtitle="Test widgets"
      newLabel="New Widget"
      rows={rowsOverride}
      loading={false}
      onRefresh={onRefresh}
      onNew={vi.fn()}
      canCreate={canCreate}
      columns={columns}
      emptyMessage={emptyMessage}
      toastRef={toastRef}
    />
  );
};

describe('MasterCrudPage', () => {
  it('renders the title, subtitle, and empty message chrome', () => {
    renderWithProviders(
      <Harness
        canCreate
        columns={
          <>
            <Column field="code" header="Code" />
          </>
        }
      />,
    );

    expect(screen.getByText('Widgets')).toBeInTheDocument();
    expect(screen.getByText('Test widgets')).toBeInTheDocument();
  });

  it('flattens a fragment of columns into real DataTable headers', () => {
    renderWithProviders(
      <Harness
        canCreate
        columns={
          <>
            <Column field="code" header="Code" />
            <Column field="name" header="Name" />
          </>
        }
      />,
    );

    const table = screen.getByRole('table');
    expect(within(table).getByText('Code')).toBeInTheDocument();
    expect(within(table).getByText('Name')).toBeInTheDocument();
    expect(within(table).getByText('W1')).toBeInTheDocument();
    expect(within(table).getByText('Widget One')).toBeInTheDocument();
  });

  it('drops a conditional column that evaluates to false, keeping the rest', () => {
    // A variable, not a literal `false`: this stands in for a real caller's
    // `{someCondition && <Column />}` (e.g. `canModifyRows`), which ESLint's
    // no-constant-binary-expression rule would otherwise (correctly) flag a
    // literal boolean for.
    const showNameColumn = false;
    renderWithProviders(
      <Harness
        canCreate
        columns={
          <>
            <Column field="code" header="Code" />
            {showNameColumn && <Column field="name" header="Name" />}
            <Column field="name" header="Actions" />
          </>
        }
      />,
    );

    const table = screen.getByRole('table');
    expect(within(table).queryByText('Name')).not.toBeInTheDocument();
    expect(within(table).getByText('Actions')).toBeInTheDocument();
  });

  it('flattens nested fragments (a conditional column set wrapped in its own fragment)', () => {
    const showNameColumn = true;
    renderWithProviders(
      <Harness
        canCreate
        columns={
          <>
            <Column field="code" header="Code" />
            {showNameColumn && (
              <>
                <Column field="name" header="Name" />
              </>
            )}
          </>
        }
      />,
    );

    const table = screen.getByRole('table');
    expect(within(table).getByText('Code')).toBeInTheDocument();
    expect(within(table).getByText('Name')).toBeInTheDocument();
  });

  it('shows the New button when canCreate is true and hides it when false', () => {
    const { rerender } = renderWithProviders(
      <Harness canCreate columns={<Column field="code" header="Code" />} />,
    );
    expect(screen.getByRole('button', { name: 'New Widget' })).toBeInTheDocument();

    rerender(<Harness canCreate={false} columns={<Column field="code" header="Code" />} />);
    expect(screen.queryByRole('button', { name: 'New Widget' })).not.toBeInTheDocument();
  });

  it('calls onRefresh when the Refresh button is clicked', async () => {
    const user = userEvent.setup();
    const onRefresh = vi.fn();
    renderWithProviders(
      <Harness canCreate onRefresh={onRefresh} columns={<Column field="code" header="Code" />} />,
    );

    await user.click(screen.getByRole('button', { name: /refresh widgets/i }));

    expect(onRefresh).toHaveBeenCalledTimes(1);
  });

  it('shows the empty message when there are no rows', () => {
    renderWithProviders(
      <Harness
        canCreate
        rows={[]}
        emptyMessage="No widgets defined yet."
        columns={<Column field="code" header="Code" />}
      />,
    );

    expect(screen.getByText('No widgets defined yet.')).toBeInTheDocument();
  });
});

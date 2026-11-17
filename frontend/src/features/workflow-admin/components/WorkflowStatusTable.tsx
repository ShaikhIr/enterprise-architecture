/**
 * States of one workflow definition.
 * The tag column reads the initial/terminal flags rather than showing two
 * booleans, because a state is exactly one of the three positions.
 */

import { Button } from 'primereact/button';
import { Column } from 'primereact/column';
import { DataTable } from 'primereact/datatable';
import { Tag } from 'primereact/tag';

import type { WorkflowStatus } from '../models/Workflow';

interface WorkflowStatusTableProps {
  statuses: WorkflowStatus[];
  loading?: boolean;
  /** Whether the caller holds workflows.UPDATE. */
  canUpdate: boolean;
  /** Whether the caller holds workflows.DELETE. */
  canDelete: boolean;
  onEdit: (status: WorkflowStatus) => void;
  onDelete: (status: WorkflowStatus) => void;
}

export const WorkflowStatusTable = ({
  statuses,
  loading,
  canUpdate,
  canDelete,
  onEdit,
  onDelete,
}: WorkflowStatusTableProps) => {
  const positionBodyTemplate = (row: WorkflowStatus) => {
    if (row.is_initial) return <Tag value="Initial" severity="info" />;
    if (row.is_terminal) return <Tag value="Terminal" severity="danger" />;
    return <Tag value="Intermediate" severity="success" />;
  };

  const actionsBodyTemplate = (row: WorkflowStatus) => (
    <div className="flex gap-1">
      {canUpdate && (
        <Button
          icon="pi pi-pencil"
          rounded
          outlined
          severity="info"
          size="small"
          onClick={() => onEdit(row)}
          tooltip="Edit"
          tooltipOptions={{ position: 'top' }}
          aria-label={`Edit state ${row.name}`}
        />
      )}
      {canDelete && (
        <Button
          icon="pi pi-trash"
          rounded
          outlined
          severity="danger"
          size="small"
          onClick={() => onDelete(row)}
          tooltip="Delete"
          tooltipOptions={{ position: 'top' }}
          aria-label={`Delete state ${row.name}`}
        />
      )}
    </div>
  );

  return (
    <DataTable
      value={statuses}
      loading={loading}
      stripedRows
      showGridlines
      size="small"
      emptyMessage="No states defined. Add an initial state to begin."
      aria-label="Workflow states table"
    >
      <Column field="sequence" header="#" sortable style={{ width: '4rem' }} />
      <Column field="code" header="Code" sortable />
      <Column field="name" header="Name" sortable />
      <Column header="Position" body={positionBodyTemplate} style={{ width: '9rem' }} />
      <Column header="Actions" body={actionsBodyTemplate} style={{ width: '7rem' }} />
    </DataTable>
  );
};

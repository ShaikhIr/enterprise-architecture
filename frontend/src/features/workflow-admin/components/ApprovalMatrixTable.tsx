/**
 * Approval matrices table.
 * Rule and level counts are summarised rather than listed — the detail belongs in
 * the edit dialog, and a row that unrolls a whole rule set is unreadable.
 */

import { useState } from 'react';

import { FilterMatchMode } from 'primereact/api';
import { Button } from 'primereact/button';
import { Column } from 'primereact/column';
import { DataTable, type DataTableFilterMeta } from 'primereact/datatable';
import { Tag } from 'primereact/tag';

import type { ApprovalMatrix } from '../models/ApprovalMatrix';

interface ApprovalMatrixTableProps {
  matrices: ApprovalMatrix[];
  loading: boolean;
  /** Whether the caller holds approval_matrices.UPDATE. */
  canUpdate: boolean;
  /** Whether the caller holds approval_matrices.DELETE. */
  canDelete: boolean;
  onEdit: (matrix: ApprovalMatrix) => void;
  onDelete: (matrix: ApprovalMatrix) => void;
}

const defaultFilters: DataTableFilterMeta = {
  code: { value: null, matchMode: FilterMatchMode.CONTAINS },
  name: { value: null, matchMode: FilterMatchMode.CONTAINS },
  entity_type: { value: null, matchMode: FilterMatchMode.CONTAINS },
};

const plural = (count: number, noun: string) => `${count} ${noun}${count === 1 ? '' : 's'}`;

export const ApprovalMatrixTable = ({
  matrices,
  loading,
  canUpdate,
  canDelete,
  onEdit,
  onDelete,
}: ApprovalMatrixTableProps) => {
  const [filters, setFilters] = useState<DataTableFilterMeta>(defaultFilters);

  const rulesBodyTemplate = (row: ApprovalMatrix) =>
    row.rules.length === 0 ? (
      <Tag value="Matches all" severity="warning" />
    ) : (
      <span>{plural(row.rules.length, 'condition')}</span>
    );

  const levelsBodyTemplate = (row: ApprovalMatrix) => {
    const levels = new Set(row.assignments.map((a) => a.level));
    return levels.size === 0 ? (
      <span className="text-600">None</span>
    ) : (
      <span>{plural(levels.size, 'level')}</span>
    );
  };

  const statusBodyTemplate = (row: ApprovalMatrix) => (
    <Tag
      value={row.is_active ? 'Active' : 'Inactive'}
      severity={row.is_active ? 'success' : 'warning'}
    />
  );

  const actionsBodyTemplate = (row: ApprovalMatrix) => (
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
          aria-label={`Edit ${row.name}`}
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
          aria-label={`Delete ${row.name}`}
        />
      )}
    </div>
  );

  return (
    <DataTable
      value={matrices}
      loading={loading}
      paginator
      rows={10}
      rowsPerPageOptions={[5, 10, 25, 50]}
      stripedRows
      showGridlines
      emptyMessage="No approval matrices configured yet."
      filters={filters}
      filterDisplay="row"
      onFilter={(e) => setFilters(e.filters)}
      aria-label="Approval matrices table"
    >
      <Column field="code" header="Code" sortable filter filterPlaceholder="Search..." />
      <Column field="name" header="Name" sortable filter filterPlaceholder="Search..." />
      <Column
        field="entity_type"
        header="Entity Type"
        sortable
        filter
        filterPlaceholder="Search..."
      />
      <Column field="priority" header="Priority" sortable style={{ width: '7rem' }} />
      <Column header="Conditions" body={rulesBodyTemplate} style={{ width: '9rem' }} />
      <Column header="Levels" body={levelsBodyTemplate} style={{ width: '7rem' }} />
      <Column header="Status" body={statusBodyTemplate} style={{ width: '7rem' }} />
      <Column header="Actions" body={actionsBodyTemplate} style={{ width: '7rem' }} />
    </DataTable>
  );
};

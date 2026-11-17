/**
 * Workflow definitions table.
 * Row actions open the builder, edit the definition, or delete it.
 */

import { useState } from 'react';

import { FilterMatchMode } from 'primereact/api';
import { Button } from 'primereact/button';
import { Column } from 'primereact/column';
import { DataTable, type DataTableFilterMeta } from 'primereact/datatable';
import { Tag } from 'primereact/tag';

import type { WorkflowDefinition } from '../models/Workflow';

interface WorkflowDefinitionTableProps {
  definitions: WorkflowDefinition[];
  loading: boolean;
  /** Whether the caller holds workflows.UPDATE. */
  canUpdate: boolean;
  /** Whether the caller holds workflows.DELETE. */
  canDelete: boolean;
  onConfigure: (definition: WorkflowDefinition) => void;
  onEdit: (definition: WorkflowDefinition) => void;
  onDelete: (definition: WorkflowDefinition) => void;
}

const defaultFilters: DataTableFilterMeta = {
  code: { value: null, matchMode: FilterMatchMode.CONTAINS },
  name: { value: null, matchMode: FilterMatchMode.CONTAINS },
  entity_type: { value: null, matchMode: FilterMatchMode.CONTAINS },
};

export const WorkflowDefinitionTable = ({
  definitions,
  loading,
  canUpdate,
  canDelete,
  onConfigure,
  onEdit,
  onDelete,
}: WorkflowDefinitionTableProps) => {
  const [filters, setFilters] = useState<DataTableFilterMeta>(defaultFilters);

  const statusBodyTemplate = (row: WorkflowDefinition) => (
    <Tag
      value={row.is_active ? 'Active' : 'Inactive'}
      severity={row.is_active ? 'success' : 'warning'}
    />
  );

  const actionsBodyTemplate = (row: WorkflowDefinition) => (
    <div className="flex gap-1">
      <Button
        icon="pi pi-sitemap"
        rounded
        outlined
        severity="secondary"
        size="small"
        onClick={() => onConfigure(row)}
        tooltip="Open builder"
        tooltipOptions={{ position: 'top' }}
        aria-label={`Open builder for ${row.name}`}
      />
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
      value={definitions}
      loading={loading}
      paginator
      rows={10}
      rowsPerPageOptions={[5, 10, 25, 50]}
      stripedRows
      showGridlines
      emptyMessage="No workflows defined yet."
      filters={filters}
      filterDisplay="row"
      onFilter={(e) => setFilters(e.filters)}
      aria-label="Workflow definitions table"
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
      <Column field="version" header="Version" style={{ width: '6rem' }} />
      <Column header="Status" body={statusBodyTemplate} style={{ width: '7rem' }} />
      <Column header="Actions" body={actionsBodyTemplate} style={{ width: '9rem' }} />
    </DataTable>
  );
};

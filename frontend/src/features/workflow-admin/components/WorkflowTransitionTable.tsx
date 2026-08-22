/**
 * Transitions of one workflow definition, rendered as `from -> action -> to`.
 * State ids are resolved to codes through the lookup passed in, so the table
 * needs no extra fetch of its own.
 */

import { Button } from 'primereact/button';
import { Column } from 'primereact/column';
import { DataTable } from 'primereact/datatable';
import { Tag } from 'primereact/tag';

import type { WorkflowActionType, WorkflowStatus, WorkflowTransition } from '../models/Workflow';

/**
 * Colour tracks the effect on the approval chain, not the wording: the three
 * types that tear a chain down read as destructive.
 */
const CHAIN_EFFECT_SEVERITY: Record<
  WorkflowActionType,
  'success' | 'info' | 'warning' | 'danger' | null
> = {
  SUBMIT: 'info',
  APPROVE: 'success',
  REJECT: 'danger',
  REFER_BACK: 'warning',
  CANCEL: 'danger',
  CLOSE: null,
  ESCALATE: 'warning',
  CUSTOM: null,
};

interface WorkflowTransitionTableProps {
  transitions: WorkflowTransition[];
  statuses: WorkflowStatus[];
  loading?: boolean;
  /** Whether the caller holds workflows.DELETE. */
  canDelete: boolean;
  onDelete: (transition: WorkflowTransition) => void;
}

export const WorkflowTransitionTable = ({
  transitions,
  statuses,
  loading,
  canDelete,
  onDelete,
}: WorkflowTransitionTableProps) => {
  const byId = new Map(statuses.map((status) => [status.id, status]));

  const stateTag = (statusId: string, terminalStyling: boolean) => {
    const status = byId.get(statusId);
    if (!status) return <span className="text-600">Unknown</span>;
    return (
      <Tag
        value={status.code}
        severity={terminalStyling && status.is_terminal ? 'danger' : 'info'}
      />
    );
  };

  const actionsBodyTemplate = (row: WorkflowTransition) =>
    canDelete ? (
      <Button
        icon="pi pi-trash"
        rounded
        outlined
        severity="danger"
        size="small"
        onClick={() => onDelete(row)}
        tooltip="Delete"
        tooltipOptions={{ position: 'top' }}
        aria-label={`Delete transition ${row.action_code}`}
      />
    ) : null;

  return (
    <DataTable
      value={transitions}
      loading={loading}
      stripedRows
      showGridlines
      size="small"
      emptyMessage="No transitions defined. Wire an action between two states."
      aria-label="Workflow transitions table"
    >
      <Column
        header="From"
        body={(row: WorkflowTransition) => stateTag(row.from_status_id, false)}
        style={{ width: '11rem' }}
      />
      <Column field="action_code" header="Action" sortable />
      <Column
        header="Type"
        body={(row: WorkflowTransition) =>
          row.action_type === 'CUSTOM' ? (
            <span className="text-600">—</span>
          ) : (
            <Tag value={row.action_type} severity={CHAIN_EFFECT_SEVERITY[row.action_type]} />
          )
        }
        sortable
        field="action_type"
        style={{ width: '9rem' }}
      />
      <Column
        header="To"
        body={(row: WorkflowTransition) => stateTag(row.to_status_id, true)}
        style={{ width: '11rem' }}
      />
      <Column
        header="Comment"
        body={(row: WorkflowTransition) => (row.requires_comment ? 'Required' : '—')}
        style={{ width: '8rem' }}
      />
      <Column field="priority" header="Priority" sortable style={{ width: '7rem' }} />
      <Column header="" body={actionsBodyTemplate} style={{ width: '5rem' }} />
    </DataTable>
  );
};

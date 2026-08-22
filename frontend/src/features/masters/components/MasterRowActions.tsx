/**
 * Edit and delete row actions, using the rounded outlined icon buttons the UI
 * standard prescribes for row-level actions.
 */

import { Button } from 'primereact/button';

interface MasterRowActionsProps {
  /** Row name, used for the accessible labels. */
  label: string;
  /** Whether the caller holds UPDATE on this resource. */
  canUpdate: boolean;
  /** Whether the caller holds DELETE on this resource. */
  canDelete: boolean;
  onEdit: () => void;
  onDelete: () => void;
}

export const MasterRowActions = ({
  label,
  canUpdate,
  canDelete,
  onEdit,
  onDelete,
}: MasterRowActionsProps) => (
  <div className="flex gap-1">
    {canUpdate && (
      <Button
        icon="pi pi-pencil"
        rounded
        outlined
        severity="info"
        size="small"
        onClick={onEdit}
        tooltip="Edit"
        tooltipOptions={{ position: 'top' }}
        aria-label={`Edit ${label}`}
      />
    )}
    {canDelete && (
      <Button
        icon="pi pi-trash"
        rounded
        outlined
        severity="danger"
        size="small"
        onClick={onDelete}
        tooltip="Delete"
        tooltipOptions={{ position: 'top' }}
        aria-label={`Delete ${label}`}
      />
    )}
  </div>
);

/**
 * User data table component.
 * Displays all users in a PrimeReact DataTable with status badges.
 */

import { DataTable } from 'primereact/datatable';
import { Column } from 'primereact/column';
import { Tag } from 'primereact/tag';
import { Button } from 'primereact/button';
import type { User } from '../models/User';

interface UserTableProps {
  users: User[];
  loading: boolean;
  onEdit: (user: User) => void;
}

export const UserTable = ({ users, loading, onEdit }: UserTableProps) => {
  const statusBodyTemplate = (rowData: User) => {
    if (rowData.is_blocked) {
      return <Tag value="Blocked" severity="danger" />;
    }
    return rowData.is_active ? (
      <Tag value="Active" severity="success" />
    ) : (
      <Tag value="Inactive" severity="warning" />
    );
  };

  const roleBodyTemplate = (rowData: User) => {
    const severityMap: Record<string, 'info' | 'success' | 'warning'> = {
      ADMIN: 'info',
      MANAGER: 'warning',
      USER: 'success',
    };
    return <Tag value={rowData.role} severity={severityMap[rowData.role] || 'info'} />;
  };

  const actionsBodyTemplate = (rowData: User) => {
    return (
      <Button
        icon="pi pi-pencil"
        rounded
        outlined
        severity="info"
        size="small"
        onClick={() => onEdit(rowData)}
        aria-label={`Edit user ${rowData.username}`}
        tooltip="Edit"
        tooltipOptions={{ position: 'top' }}
      />
    );
  };

  const dateBodyTemplate = (rowData: User) => {
    return new Date(rowData.created_date).toLocaleDateString();
  };

  return (
    <DataTable
      value={users}
      loading={loading}
      paginator
      rows={10}
      rowsPerPageOptions={[5, 10, 25, 50]}
      stripedRows
      showGridlines
      emptyMessage="No users found."
      aria-label="Users table"
    >
      <Column field="username" header="Username" sortable />
      <Column field="role" header="Role" body={roleBodyTemplate} sortable />
      <Column header="Status" body={statusBodyTemplate} />
      <Column field="created_by" header="Created By" />
      <Column header="Created Date" body={dateBodyTemplate} sortable />
      <Column header="Actions" body={actionsBodyTemplate} style={{ width: '5rem' }} />
    </DataTable>
  );
};

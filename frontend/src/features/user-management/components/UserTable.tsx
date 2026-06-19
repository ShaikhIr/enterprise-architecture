/**
 * User data table component.
 * Displays all users in a PrimeReact DataTable with status badges.
 * Roles button opens a tree popup showing assigned roles and permissions.
 */

import { useState } from 'react';
import { DataTable } from 'primereact/datatable';
import { Column } from 'primereact/column';
import { Tag } from 'primereact/tag';
import { Button } from 'primereact/button';
import { Dialog } from 'primereact/dialog';
import { Tree } from 'primereact/tree';
import type { TreeNode } from 'primereact/treenode';
import { userApi } from '../api/userApi';
import type { User, UserRole } from '../models/User';

interface UserTableProps {
  users: User[];
  loading: boolean;
  onEdit: (user: User) => void;
}

export const UserTable = ({ users, loading, onEdit }: UserTableProps) => {
  const [rolesDialogVisible, setRolesDialogVisible] = useState(false);
  const [rolesDialogUser, setRolesDialogUser] = useState<string>('');
  const [rolesTreeData, setRolesTreeData] = useState<TreeNode[]>([]);
  const [rolesLoading, setRolesLoading] = useState(false);

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

  const handleViewRoles = async (user: User) => {
    setRolesDialogUser(user.username);
    setRolesDialogVisible(true);
    setRolesLoading(true);

    try {
      const data = await userApi.getUserRoles(user.id);
      const treeNodes: TreeNode[] = data.roles.map((role: UserRole) => ({
        key: role.id,
        label: `${role.name} (${role.code})`,
        icon: 'pi pi-shield',
        children: role.permissions.map((perm) => ({
          key: `${role.id}-${perm.code}`,
          label: perm.name,
          icon: perm.scope === 'MENU' ? 'pi pi-bars' : perm.scope === 'API' ? 'pi pi-server' : 'pi pi-eye',
          data: `${perm.scope} | ${perm.resource} | ${perm.action}`,
        })),
      }));
      setRolesTreeData(treeNodes);
    } catch {
      setRolesTreeData([{ key: 'error', label: 'Failed to load roles', icon: 'pi pi-exclamation-triangle' }]);
    } finally {
      setRolesLoading(false);
    }
  };

  const actionsBodyTemplate = (rowData: User) => {
    return (
      <div className="flex gap-2">
        <Button
          icon="pi pi-shield"
          rounded
          outlined
          severity="warning"
          size="small"
          onClick={() => handleViewRoles(rowData)}
          aria-label={`View roles for ${rowData.username}`}
          tooltip="View Roles"
          tooltipOptions={{ position: 'top' }}
        />
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
      </div>
    );
  };

  const dateBodyTemplate = (rowData: User) => {
    return new Date(rowData.created_date).toLocaleDateString();
  };

  return (
    <>
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
        <Column header="Status" body={statusBodyTemplate} />
        <Column field="created_by" header="Created By" />
        <Column header="Created Date" body={dateBodyTemplate} sortable />
        <Column header="Actions" body={actionsBodyTemplate} style={{ width: '8rem' }} />
      </DataTable>

      {/* Roles Tree Dialog */}
      <Dialog
        header={`Roles — ${rolesDialogUser}`}
        visible={rolesDialogVisible}
        onHide={() => setRolesDialogVisible(false)}
        style={{ width: '550px' }}
        modal
        aria-label="User roles dialog"
      >
        {rolesLoading ? (
          <div className="flex align-items-center justify-content-center p-4">
            <i className="pi pi-spin pi-spinner text-2xl" />
            <span className="ml-2">Loading roles...</span>
          </div>
        ) : rolesTreeData.length === 0 ? (
          <p className="text-600 p-3">No roles assigned to this user.</p>
        ) : (
          <Tree
            value={rolesTreeData}
            className="w-full"
            aria-label="Assigned roles tree"
          />
        )}
      </Dialog>
    </>
  );
};

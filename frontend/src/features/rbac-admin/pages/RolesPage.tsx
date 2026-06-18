/**
 * RBAC Roles Management page.
 * Lists roles, their permissions, and allows granting/revoking.
 */

import { useEffect, useRef, useState } from 'react';
import { Button } from 'primereact/button';
import { Column } from 'primereact/column';
import { DataTable } from 'primereact/datatable';
import { Dialog } from 'primereact/dialog';
import { InputText } from 'primereact/inputtext';
import { InputTextarea } from 'primereact/inputtextarea';
import { MultiSelect } from 'primereact/multiselect';
import { Tag } from 'primereact/tag';
import { Toast } from 'primereact/toast';
import { Toolbar } from 'primereact/toolbar';
import { rbacAdminApi } from '../api/rbacAdminApi';
import type { CreateRoleRequest, Permission, Role } from '../models/rbac-admin.types';

export const RolesPage = () => {
  const toast = useRef<Toast>(null);
  const [roles, setRoles] = useState<Role[]>([]);
  const [permissions, setPermissions] = useState<Permission[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreateDialog, setShowCreateDialog] = useState(false);
  const [showPermissionsDialog, setShowPermissionsDialog] = useState(false);
  const [selectedRole, setSelectedRole] = useState<Role | null>(null);
  const [selectedPermissions, setSelectedPermissions] = useState<string[]>([]);
  const [createForm, setCreateForm] = useState<CreateRoleRequest>({
    code: '',
    name: '',
    description: '',
  });

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    setLoading(true);
    try {
      const [rolesData, permsData] = await Promise.all([
        rbacAdminApi.listRoles(),
        rbacAdminApi.listPermissions(),
      ]);
      setRoles(rolesData.roles);
      setPermissions(permsData);
    } catch (error: any) {
      toast.current?.show({
        severity: 'error',
        summary: 'Error',
        detail: error.response?.data?.detail || 'Failed to load RBAC data',
        life: 5000,
      });
    } finally {
      setLoading(false);
    }
  };

  const handleCreateRole = async () => {
    try {
      await rbacAdminApi.createRole(createForm);
      setShowCreateDialog(false);
      setCreateForm({ code: '', name: '', description: '' });
      toast.current?.show({
        severity: 'success',
        summary: 'Success',
        detail: `Role '${createForm.code}' created`,
        life: 3000,
      });
      loadData();
    } catch (error: any) {
      toast.current?.show({
        severity: 'error',
        summary: 'Error',
        detail: error.response?.data?.detail || 'Failed to create role',
        life: 5000,
      });
    }
  };

  const openPermissionsDialog = (role: Role) => {
    setSelectedRole(role);
    setSelectedPermissions(role.permissions.map((p) => p.id));
    setShowPermissionsDialog(true);
  };

  const handleSavePermissions = async () => {
    if (!selectedRole) return;

    const currentPermIds = new Set(selectedRole.permissions.map((p) => p.id));
    const newPermIds = new Set(selectedPermissions);

    // Permissions to grant (in new but not in current)
    const toGrant = [...newPermIds].filter((id) => !currentPermIds.has(id));
    // Permissions to revoke (in current but not in new)
    const toRevoke = [...currentPermIds].filter((id) => !newPermIds.has(id));

    try {
      for (const permId of toGrant) {
        await rbacAdminApi.grantPermission({
          role_id: selectedRole.id,
          permission_id: permId,
        });
      }
      for (const permId of toRevoke) {
        await rbacAdminApi.revokePermission({
          role_id: selectedRole.id,
          permission_id: permId,
        });
      }
      setShowPermissionsDialog(false);
      toast.current?.show({
        severity: 'success',
        summary: 'Success',
        detail: `Permissions updated for '${selectedRole.code}'`,
        life: 3000,
      });
      loadData();
    } catch (error: any) {
      toast.current?.show({
        severity: 'error',
        summary: 'Error',
        detail: error.response?.data?.detail || 'Failed to update permissions',
        life: 5000,
      });
    }
  };

  // ─── Column Templates ───

  const statusTemplate = (role: Role) => (
    <Tag
      value={role.is_active ? 'Active' : 'Inactive'}
      severity={role.is_active ? 'success' : 'danger'}
    />
  );

  const typeTemplate = (role: Role) => (
    <Tag
      value={role.is_system ? 'System' : 'Custom'}
      severity={role.is_system ? 'info' : 'warning'}
    />
  );

  const permissionsCountTemplate = (role: Role) => (
    <span className="font-semibold">{role.permissions.length}</span>
  );

  const scopeTemplate = (perm: Permission) => {
    const severity = perm.scope === 'MENU' ? 'info' : perm.scope === 'API' ? 'warning' : 'danger';
    return <Tag value={perm.scope} severity={severity} />;
  };

  const actionsTemplate = (role: Role) => (
    <div className="flex gap-2">
      <Button
        icon="pi pi-shield"
        rounded
        outlined
        severity="info"
        size="small"
        tooltip="Manage Permissions"
        tooltipOptions={{ position: 'top' }}
        onClick={() => openPermissionsDialog(role)}
        aria-label={`Manage permissions for ${role.name}`}
      />
    </div>
  );

  // ─── Toolbar ───

  const leftToolbar = () => (
    <div className="flex gap-2">
      <Button
        label="New Role"
        icon="pi pi-plus"
        onClick={() => setShowCreateDialog(true)}
        aria-label="Create new role"
      />
      <Button
        label="Refresh"
        icon="pi pi-refresh"
        severity="secondary"
        outlined
        onClick={loadData}
        aria-label="Refresh roles list"
      />
    </div>
  );

  return (
    <div className="p-4">
      <Toast ref={toast} />

      {/* Header */}
      <div className="mb-4">
        <h2 className="text-2xl font-semibold text-900 m-0">Roles & Permissions</h2>
        <p className="text-600 mt-1 mb-0">Manage roles, assign permissions, and configure access control</p>
      </div>

      <div className="surface-card p-4 border-round shadow-1">
        <Toolbar className="mb-4" start={leftToolbar} />

        <DataTable
          value={roles}
          loading={loading}
          stripedRows
          paginator
          rows={10}
          emptyMessage="No roles found"
          tableStyle={{ minWidth: '50rem' }}
        >
          <Column field="code" header="Code" sortable style={{ width: '10%' }} />
          <Column field="name" header="Name" sortable style={{ width: '20%' }} />
          <Column field="description" header="Description" style={{ width: '25%' }} />
          <Column header="Type" body={typeTemplate} style={{ width: '10%' }} />
          <Column header="Status" body={statusTemplate} style={{ width: '10%' }} />
          <Column header="Permissions" body={permissionsCountTemplate} style={{ width: '10%' }} />
          <Column header="Actions" body={actionsTemplate} style={{ width: '15%' }} />
        </DataTable>
      </div>

      {/* ─── Create Role Dialog ─── */}
      <Dialog
        header="Create New Role"
        visible={showCreateDialog}
        style={{ width: '450px' }}
        modal
        onHide={() => setShowCreateDialog(false)}
        footer={
          <div className="flex justify-content-end gap-2">
            <Button
              label="Cancel"
              icon="pi pi-times"
              severity="secondary"
              text
              onClick={() => setShowCreateDialog(false)}
            />
            <Button
              label="Create"
              icon="pi pi-check"
              onClick={handleCreateRole}
              disabled={!createForm.code || !createForm.name}
            />
          </div>
        }
      >
        <div className="flex flex-column gap-3 mt-2">
          <div className="flex flex-column gap-2">
            <label htmlFor="role-code" className="font-medium">Code</label>
            <InputText
              id="role-code"
              value={createForm.code}
              onChange={(e) => setCreateForm({ ...createForm, code: e.target.value.toUpperCase() })}
              placeholder="e.g. SUPERVISOR"
            />
          </div>
          <div className="flex flex-column gap-2">
            <label htmlFor="role-name" className="font-medium">Name</label>
            <InputText
              id="role-name"
              value={createForm.name}
              onChange={(e) => setCreateForm({ ...createForm, name: e.target.value })}
              placeholder="e.g. Supervisor"
            />
          </div>
          <div className="flex flex-column gap-2">
            <label htmlFor="role-desc" className="font-medium">Description</label>
            <InputTextarea
              id="role-desc"
              value={createForm.description}
              onChange={(e) => setCreateForm({ ...createForm, description: e.target.value })}
              rows={3}
              placeholder="What this role is for..."
            />
          </div>
        </div>
      </Dialog>

      {/* ─── Manage Permissions Dialog ─── */}
      <Dialog
        header={`Permissions — ${selectedRole?.name || ''}`}
        visible={showPermissionsDialog}
        style={{ width: '700px' }}
        modal
        onHide={() => setShowPermissionsDialog(false)}
        footer={
          <div className="flex justify-content-end gap-2">
            <Button
              label="Cancel"
              icon="pi pi-times"
              severity="secondary"
              text
              onClick={() => setShowPermissionsDialog(false)}
            />
            <Button
              label="Save Changes"
              icon="pi pi-check"
              onClick={handleSavePermissions}
            />
          </div>
        }
      >
        <div className="flex flex-column gap-3 mt-2">
          <p className="text-600 m-0">
            Select the permissions to assign to this role. Changes are audit-logged.
          </p>
          <MultiSelect
            value={selectedPermissions}
            options={permissions.map((p) => ({
              label: `${p.code} (${p.scope})`,
              value: p.id,
              scope: p.scope,
            }))}
            onChange={(e) => setSelectedPermissions(e.value)}
            placeholder="Select permissions"
            display="chip"
            filter
            className="w-full"
            maxSelectedLabels={5}
            aria-label="Select permissions for role"
          />

          {/* Current permissions table */}
          {selectedRole && selectedRole.permissions.length > 0 && (
            <div className="mt-3">
              <h4 className="text-sm font-semibold text-600 mb-2">
                Currently Assigned ({selectedRole.permissions.length})
              </h4>
              <DataTable
                value={selectedRole.permissions}
                size="small"
                scrollable
                scrollHeight="250px"
              >
                <Column field="code" header="Code" style={{ width: '30%' }} />
                <Column field="name" header="Name" style={{ width: '30%' }} />
                <Column header="Scope" body={scopeTemplate} style={{ width: '15%' }} />
                <Column field="resource" header="Resource" style={{ width: '25%' }} />
              </DataTable>
            </div>
          )}
        </div>
      </Dialog>
    </div>
  );
};

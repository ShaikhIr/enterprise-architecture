/**
 * User Management page.
 * Lists all users and provides create/edit functionality.
 */

import { useState } from 'react';
import { Button } from 'primereact/button';
import { Toast } from 'primereact/toast';
import { useRef } from 'react';
import { UserTable } from '../components/UserTable';
import { UserForm } from '../components/UserForm';
import { useUsers, useCreateUser } from '../hooks/useUsers';
import type { User, CreateUserRequest } from '../models/User';

export const UserListPage = () => {
  const [showCreateDialog, setShowCreateDialog] = useState(false);
  const toast = useRef<Toast>(null);

  const { data, isLoading } = useUsers();
  const createUserMutation = useCreateUser();

  const handleCreateUser = async (formData: CreateUserRequest) => {
    try {
      await createUserMutation.mutateAsync(formData);
      setShowCreateDialog(false);
      toast.current?.show({
        severity: 'success',
        summary: 'Success',
        detail: `User '${formData.username}' created successfully`,
        life: 3000,
      });
    } catch (error: any) {
      const detail = error.response?.data?.detail || 'Failed to create user';
      toast.current?.show({
        severity: 'error',
        summary: 'Error',
        detail,
        life: 5000,
      });
    }
  };

  const handleEditUser = (user: User) => {
    // Navigate to edit or open edit dialog
    toast.current?.show({
      severity: 'info',
      summary: 'Edit',
      detail: `Editing user: ${user.username}`,
      life: 2000,
    });
  };

  return (
    <div className="p-4">
      <Toast ref={toast} />

      {/* Header */}
      <div className="flex align-items-center justify-content-between mb-4">
        <div>
          <h2 className="text-2xl font-semibold text-900 m-0">User Management</h2>
          <p className="text-600 mt-1 mb-0">Manage application users and roles</p>
        </div>
        <Button
          label="New User"
          icon="pi pi-plus"
          onClick={() => setShowCreateDialog(true)}
          aria-label="Create new user"
        />
      </div>

      {/* Data Table */}
      <div className="surface-card p-4 border-round shadow-1">
        <UserTable
          users={data?.users || []}
          loading={isLoading}
          onEdit={handleEditUser}
        />
      </div>

      {/* Create User Dialog */}
      <UserForm
        visible={showCreateDialog}
        onHide={() => setShowCreateDialog(false)}
        onSubmit={handleCreateUser}
        loading={createUserMutation.isPending}
      />
    </div>
  );
};

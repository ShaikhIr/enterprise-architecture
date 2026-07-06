/**
 * Edit User Dialog.
 * Allows editing user profile fields, entity assignment, active/blocked status,
 * AD validation toggle, single role assignment, and optional password change.
 *
 * Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7, 10.8, 10.9, 10.10
 */

import { useEffect, useState } from 'react';
import { useForm, Controller } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { InputText } from 'primereact/inputtext';
import { Password } from 'primereact/password';
import { Dropdown } from 'primereact/dropdown';
import { InputSwitch } from 'primereact/inputswitch';
import { Button } from 'primereact/button';
import { Dialog } from 'primereact/dialog';
import { ConfirmDialog, confirmDialog } from 'primereact/confirmdialog';
import { useQueryClient } from '@tanstack/react-query';
import { useRoles } from '../hooks/useRoles';
import { useEntityDropdown } from '@features/masters/hooks/useEntities';
import { userApi } from '../api/userApi';
import type { User, UpdateUserRequest } from '../models/User';

const editUserSchema = z.object({
  email: z.string().email('Must be a valid email').max(254).optional().or(z.literal('')),
  first_name: z.string().min(1, 'First name is required').max(100),
  last_name: z.string().min(1, 'Last name is required').max(100),
  entity_id: z.string().optional().or(z.literal('')),
  is_active: z.boolean(),
  is_blocked: z.boolean(),
  is_validate_ad: z.boolean(),
  role_id: z.string().nullable(),
  password: z.string().optional().or(z.literal('')),
});

type EditUserFormData = z.infer<typeof editUserSchema>;

interface EditUserDialogProps {
  visible: boolean;
  user: User | null;
  onHide: () => void;
  onSubmit: (userId: string, data: UpdateUserRequest) => void;
  loading?: boolean;
}

export const EditUserDialog = ({ visible, user, onHide, onSubmit, loading }: EditUserDialogProps) => {
  const { roleOptions, loading: rolesLoading } = useRoles();
  const [loadingUserRole, setLoadingUserRole] = useState(false);
  const queryClient = useQueryClient();

  const { data: entityDropdown, isLoading: entitiesLoading } = useEntityDropdown();

  const entityOptions = (entityDropdown ?? []).map((item) => ({
    label: item.label,
    value: item.id,
  }));

  const {
    register,
    handleSubmit,
    control,
    reset,
    setValue,
    watch,
    formState: { errors },
  } = useForm<EditUserFormData>({
    resolver: zodResolver(editUserSchema),
    defaultValues: {
      email: '',
      first_name: '',
      last_name: '',
      entity_id: '',
      is_active: true,
      is_blocked: false,
      is_validate_ad: false,
      role_id: null,
      password: '',
    },
  });

  const isValidateAd = watch('is_validate_ad');
  const isActive = watch('is_active');

  // Reset form and load user's current role and details when dialog opens
  useEffect(() => {
    if (user && visible) {
      // Invalidate the entity dropdown cache so entities created via employee
      // import (e.g. from group_company) are visible immediately
      queryClient.invalidateQueries({ queryKey: ['entities', 'dropdown'] });

      // Set initial values from the basic user object
      reset({
        email: user.email ?? '',
        first_name: '',
        last_name: '',
        entity_id: '',
        is_active: user.is_active,
        is_blocked: user.is_blocked,
        is_validate_ad: user.is_validate_ad,
        role_id: null,
        password: '',
      });

      // Fetch full user details (first_name, last_name, entity_id are in user_details table)
      userApi.getUserDetails(user.id)
        .then((details) => {
          setValue('first_name', details.first_name ?? '');
          setValue('last_name', details.last_name ?? '');
          setValue('email', details.email ?? user.email ?? '');
          // entity_id is a UUID string from the API; set to '' if null so the
          // dropdown shows as unselected (empty string is the "no entity" sentinel)
          setValue('entity_id', details.entity_id ? String(details.entity_id) : '');
        })
        .catch(() => {
          // If details fetch fails, fields remain empty — user can still edit
        });

      // Fetch user's current role assignment
      setLoadingUserRole(true);
      userApi.getUserRoles(user.id)
        .then((data) => {
          const firstRole = data.roles[0];
          if (firstRole) {
            setValue('role_id', firstRole.id);
          }
        })
        .catch(() => {})
        .finally(() => setLoadingUserRole(false));
    }
  }, [user, visible, reset, setValue]);

  const handleDeactivationConfirm = (callback: () => void) => {
    confirmDialog({
      message: 'Deactivating this user will prevent them from logging in. Are you sure?',
      header: 'Confirm Deactivation',
      icon: 'pi pi-exclamation-triangle',
      acceptClassName: 'p-button-danger',
      accept: callback,
    });
  };

  const handleFormSubmit = (data: EditUserFormData) => {
    if (!user) return;

    const submitData = () => {
      const request: UpdateUserRequest = {
        is_active: data.is_active,
        is_blocked: data.is_blocked,
        is_validate_ad: data.is_validate_ad,
        // role_ids is a list — wrap single role_id, or send empty array to clear
        role_ids: data.role_id ? [data.role_id] : [],
        email: data.email || undefined,
        first_name: data.first_name || undefined,
        last_name: data.last_name || undefined,
        // Pass the UUID string when selected; omit the field entirely when blank
        // (empty string from showClear → don't send, to avoid Pydantic UUID parse error)
        ...(data.entity_id ? { entity_id: data.entity_id } : {}),
        // Backend field is change_password, not password
        change_password: (!data.is_validate_ad && data.password && data.password.length > 0)
          ? data.password
          : undefined,
      };
      onSubmit(user.id, request);
    };

    // Show confirmation when deactivating (was active, now inactive)
    if (user.is_active && !data.is_active) {
      handleDeactivationConfirm(submitData);
    } else {
      submitData();
    }
  };

  const footer = (
    <div className="flex justify-content-end gap-2">
      <Button
        label="Cancel"
        icon="pi pi-times"
        severity="secondary"
        outlined
        onClick={onHide}
      />
      <Button
        label="Save"
        icon="pi pi-check"
        loading={loading}
        onClick={handleSubmit(handleFormSubmit)}
      />
    </div>
  );

  return (
    <>
      <ConfirmDialog />
      <Dialog
        header={`Edit User: ${user?.username || ''}`}
        visible={visible}
        onHide={onHide}
        style={{ width: '500px' }}
        footer={footer}
        modal
        aria-label="Edit user dialog"
      >
        <form className="flex flex-column gap-4 pt-3">
          {/* Employee ID (read-only) */}
          <div className="flex flex-column gap-2">
            <label className="font-medium">Employee ID</label>
            <span className="text-900 font-semibold">{user?.employee_id || '—'}</span>
          </div>

          {/* Username (read-only) */}
          <div className="flex flex-column gap-2">
            <label className="font-medium">Username</label>
            <span className="text-900 font-semibold">{user?.username}</span>
          </div>

          {/* Email */}
          <div className="flex flex-column gap-2">
            <label htmlFor="edit-email" className="font-medium">Email</label>
            <InputText
              id="edit-email"
              {...register('email')}
              placeholder="Enter email"
              className={errors.email ? 'p-invalid' : ''}
              aria-describedby="edit-email-error"
            />
            {errors.email && (
              <small id="edit-email-error" className="p-error">{errors.email.message}</small>
            )}
          </div>

          {/* First Name (required) */}
          <div className="flex flex-column gap-2">
            <label htmlFor="edit-first-name" className="font-medium">First Name *</label>
            <InputText
              id="edit-first-name"
              {...register('first_name')}
              placeholder="Enter first name"
              className={errors.first_name ? 'p-invalid' : ''}
              aria-describedby="edit-first-name-error"
            />
            {errors.first_name && (
              <small id="edit-first-name-error" className="p-error">{errors.first_name.message}</small>
            )}
          </div>

          {/* Last Name (required) */}
          <div className="flex flex-column gap-2">
            <label htmlFor="edit-last-name" className="font-medium">Last Name *</label>
            <InputText
              id="edit-last-name"
              {...register('last_name')}
              placeholder="Enter last name"
              className={errors.last_name ? 'p-invalid' : ''}
              aria-describedby="edit-last-name-error"
            />
            {errors.last_name && (
              <small id="edit-last-name-error" className="p-error">{errors.last_name.message}</small>
            )}
          </div>

          {/* Entity Dropdown */}
          <div className="flex flex-column gap-2">
            <label htmlFor="edit-entity" className="font-medium">Entity</label>
            <Controller
              name="entity_id"
              control={control}
              render={({ field }) => (
                <Dropdown
                  id="edit-entity"
                  value={field.value}
                  options={entityOptions}
                  onChange={(e) => field.onChange(e.value)}
                  placeholder={entitiesLoading ? 'Loading entities...' : 'Select an entity'}
                  disabled={entitiesLoading}
                  className="w-full"
                  showClear
                  filter
                  aria-label="Select entity"
                />
              )}
            />
          </div>

          {/* Role Assignment */}
          <div className="flex flex-column gap-2">
            <label htmlFor="edit-role" className="font-medium">Role</label>
            <Controller
              name="role_id"
              control={control}
              render={({ field }) => (
                <Dropdown
                  id="edit-role"
                  value={field.value}
                  options={roleOptions}
                  onChange={(e) => field.onChange(e.value)}
                  placeholder={rolesLoading || loadingUserRole ? 'Loading...' : 'Select a role'}
                  disabled={rolesLoading || loadingUserRole}
                  className="w-full"
                  aria-label="Assign role"
                />
              )}
            />
          </div>

          {/* Active toggle with deactivation warning */}
          <div className="flex align-items-center gap-3">
            <Controller
              name="is_active"
              control={control}
              render={({ field }) => (
                <InputSwitch
                  id="edit-active"
                  checked={field.value}
                  onChange={(e) => field.onChange(e.value)}
                  aria-label="Active status"
                />
              )}
            />
            <label htmlFor="edit-active" className="font-medium cursor-pointer">Active</label>
            {!isActive && user?.is_active && (
              <small className="text-orange-500">User will be deactivated on save</small>
            )}
          </div>

          {/* Blocked */}
          <div className="flex align-items-center gap-3">
            <Controller
              name="is_blocked"
              control={control}
              render={({ field }) => (
                <InputSwitch
                  id="edit-blocked"
                  checked={field.value}
                  onChange={(e) => field.onChange(e.value)}
                  aria-label="Blocked status"
                />
              )}
            />
            <label htmlFor="edit-blocked" className="font-medium cursor-pointer">Blocked</label>
          </div>

          {/* Validate with AD */}
          <div className="flex align-items-center gap-3">
            <Controller
              name="is_validate_ad"
              control={control}
              render={({ field }) => (
                <InputSwitch
                  id="edit-validate-ad"
                  checked={field.value}
                  onChange={(e) => field.onChange(e.value)}
                  aria-label="Validate with AD"
                />
              )}
            />
            <label htmlFor="edit-validate-ad" className="font-medium cursor-pointer">
              Validate with AD
            </label>
          </div>

          {/* Change Password (optional, hidden when AD is enabled) */}
          {!isValidateAd && (
            <div className="flex flex-column gap-2">
              <label htmlFor="edit-password" className="font-medium">Change Password</label>
              <Controller
                name="password"
                control={control}
                render={({ field }) => (
                  <Password
                    id="edit-password"
                    value={field.value ?? ''}
                    onChange={(e) => field.onChange(e.target.value)}
                    placeholder="Leave blank to keep current"
                    toggleMask
                    className={errors.password ? 'p-invalid' : ''}
                    inputClassName="w-full"
                    aria-describedby="edit-password-error"
                  />
                )}
              />
              {errors.password && (
                <small id="edit-password-error" className="p-error">{errors.password.message}</small>
              )}
              <small className="text-500">Min 8 characters. Leave blank to keep current password.</small>
            </div>
          )}
        </form>
      </Dialog>
    </>
  );
};

export { editUserSchema };

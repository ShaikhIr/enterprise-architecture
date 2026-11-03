/**
 * Edit User Dialog.
 * Allows editing active/blocked status, AD validation, and single role assignment.
 */

import { useEffect, useState } from 'react';

import { zodResolver } from '@hookform/resolvers/zod';
import { Button } from 'primereact/button';
import { Dialog } from 'primereact/dialog';
import { Dropdown } from 'primereact/dropdown';
import { InputSwitch } from 'primereact/inputswitch';
import { InputText } from 'primereact/inputtext';
import { Message } from 'primereact/message';
import { Password } from 'primereact/password';
import { Tag } from 'primereact/tag';
import { useForm, Controller, useWatch } from 'react-hook-form';
import { z } from 'zod';

import { useValidateCredentials } from '@features/service-menu/hooks/useEmployeeAD';

import { extractApiError } from '@shared/utils/apiError';

import { userApi } from '../api/userApi';
import { useRoles } from '../hooks/useRoles';
import type { User, UpdateUserRequest } from '../models/User';

const editUserSchema = z.object({
  is_active: z.boolean(),
  is_blocked: z.boolean(),
  is_validate_ad: z.boolean(),
  role_id: z.number().int().positive().nullable(),
});

type EditUserFormData = z.infer<typeof editUserSchema>;

interface EditUserDialogProps {
  visible: boolean;
  user: User | null;
  onHide: () => void;
  onSubmit: (userId: number, data: UpdateUserRequest) => void;
  loading?: boolean;
}

export const EditUserDialog = ({
  visible,
  user,
  onHide,
  onSubmit,
  loading,
}: EditUserDialogProps) => {
  const { roleOptions, loading: rolesLoading } = useRoles();
  const [loadingUserRole, setLoadingUserRole] = useState(false);

  // Local state for the AD credential check (independent of the form fields).
  const [validateEmployeeId, setValidateEmployeeId] = useState('');
  const [validatePassword, setValidatePassword] = useState('');
  const [validateError, setValidateError] = useState<string | null>(null);
  const validateMutation = useValidateCredentials();

  const { handleSubmit, control, reset, setValue } = useForm<EditUserFormData>({
    resolver: zodResolver(editUserSchema),
    defaultValues: {
      is_active: true,
      is_blocked: false,
      is_validate_ad: true,
      role_id: null,
    },
  });

  // Only validate against AD while the switch is on — mirrors the backend login
  // branch that calls the Darwin AD service only when is_validate_ad is true.
  const isValidateAd = useWatch({ control, name: 'is_validate_ad' });

  // Reset form and load user's current role when dialog opens
  useEffect(() => {
    if (user && visible) {
      reset({
        is_active: user.is_active,
        is_blocked: user.is_blocked,
        is_validate_ad: user.is_validate_ad,
        role_id: null,
      });

      // Seed the AD check with the user's employee id and clear any prior result.
      setValidateEmployeeId(user.employee_id ?? '');
      setValidatePassword('');
      setValidateError(null);
      validateMutation.reset();

      // Fetch user's current role assignment
      setLoadingUserRole(true);
      userApi
        .getUserRoles(user.id)
        .then((data) => {
          if (data.roles.length > 0) {
            setValue('role_id', data.roles[0]!.id);
          }
        })
        .catch(() => {})
        .finally(() => setLoadingUserRole(false));
    }
    // validateMutation is a stable TanStack mutation handle; excluded to avoid re-running on every render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user, visible, reset, setValue]);

  const handleValidateAd = async () => {
    setValidateError(null);
    try {
      await validateMutation.mutateAsync({
        employee_id: validateEmployeeId.trim(),
        password: validatePassword,
      });
    } catch (error) {
      setValidateError(extractApiError(error, 'Failed to validate AD credentials'));
    }
  };

  const handleFormSubmit = (data: EditUserFormData) => {
    if (!user) return;
    onSubmit(user.id, {
      is_active: data.is_active,
      is_blocked: data.is_blocked,
      is_validate_ad: data.is_validate_ad,
      role_id: data.role_id,
    });
  };

  const footer = (
    <div className="flex justify-content-end gap-2">
      <Button label="Cancel" icon="pi pi-times" severity="secondary" outlined onClick={onHide} />
      <Button
        label="Save"
        icon="pi pi-check"
        loading={loading}
        onClick={handleSubmit(handleFormSubmit)}
      />
    </div>
  );

  return (
    <Dialog
      header={`Edit User: ${user?.username || ''}`}
      visible={visible}
      onHide={onHide}
      style={{ width: '450px' }}
      footer={footer}
      modal
      aria-label="Edit user dialog"
    >
      <form className="flex flex-column gap-4 pt-3">
        {/* Username (read-only) */}
        <div className="flex flex-column gap-2">
          <label className="font-medium">Username</label>
          <span className="text-900 font-semibold">{user?.username}</span>
        </div>

        {/* Role Assignment */}
        <div className="flex flex-column gap-2">
          <label htmlFor="edit-role" className="font-medium">
            Role
          </label>
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

        {/* Active */}
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
          <label htmlFor="edit-active" className="font-medium cursor-pointer">
            Active
          </label>
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
          <label htmlFor="edit-blocked" className="font-medium cursor-pointer">
            Blocked
          </label>
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

        {/* AD credential check — only relevant while "Validate with AD" is on */}
        {isValidateAd && (
          <div className="flex flex-column gap-3 surface-100 border-round p-3">
            <span className="font-medium text-700">Validate AD credentials</span>

            <div className="flex flex-column gap-2">
              <label htmlFor="validate-employee-id" className="text-sm text-600">
                Employee ID
              </label>
              <InputText
                id="validate-employee-id"
                value={validateEmployeeId}
                onChange={(e) => setValidateEmployeeId(e.target.value)}
                placeholder="e.g. 93300040"
                className="w-full"
                aria-label="Employee ID to validate"
              />
            </div>

            <div className="flex flex-column gap-2">
              <label htmlFor="validate-password" className="text-sm text-600">
                Password
              </label>
              <Password
                id="validate-password"
                value={validatePassword}
                onChange={(e) => setValidatePassword(e.target.value)}
                placeholder="Enter password"
                feedback={false}
                toggleMask
                className="w-full"
                inputClassName="w-full"
                aria-label="Password to validate"
              />
            </div>

            <Button
              type="button"
              label="Validate AD"
              icon="pi pi-shield"
              severity="info"
              outlined
              loading={validateMutation.isPending}
              disabled={!validateEmployeeId.trim() || !validatePassword}
              onClick={handleValidateAd}
              aria-label="Validate AD credentials"
            />

            {validateMutation.data && !validateError && (
              <Tag
                value={
                  validateMutation.data.is_valid_user ? 'Valid AD user' : 'Invalid AD credentials'
                }
                severity={validateMutation.data.is_valid_user ? 'success' : 'danger'}
                icon={validateMutation.data.is_valid_user ? 'pi pi-check' : 'pi pi-times'}
              />
            )}

            {validateError && <Message severity="error" text={validateError} />}
          </div>
        )}
      </form>
    </Dialog>
  );
};

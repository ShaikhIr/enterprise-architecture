/**
 * Edit User Dialog.
 * Allows editing active/blocked status and AD validation flag.
 */

import { useEffect } from 'react';
import { useForm, Controller } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { InputSwitch } from 'primereact/inputswitch';
import { Button } from 'primereact/button';
import { Dialog } from 'primereact/dialog';
import type { User, UpdateUserRequest } from '../models/User';

const editUserSchema = z.object({
  is_active: z.boolean(),
  is_blocked: z.boolean(),
  is_validate_ad: z.boolean(),
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
  const {
    handleSubmit,
    control,
    reset,
  } = useForm<EditUserFormData>({
    resolver: zodResolver(editUserSchema),
    defaultValues: {
      is_active: true,
      is_blocked: false,
      is_validate_ad: true,
    },
  });

  // Reset form when user changes
  useEffect(() => {
    if (user) {
      reset({
        is_active: user.is_active,
        is_blocked: user.is_blocked,
        is_validate_ad: user.is_validate_ad,
      });
    }
  }, [user, reset]);

  const handleFormSubmit = (data: EditUserFormData) => {
    if (!user) return;
    onSubmit(user.id, data);
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
          <label htmlFor="edit-active" className="font-medium cursor-pointer">Active</label>
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
          <small className="text-600">
            Login via Darwin AD when enabled
          </small>
        </div>
      </form>
    </Dialog>
  );
};

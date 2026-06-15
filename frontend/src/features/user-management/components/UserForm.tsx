/**
 * User create/edit form component.
 * Uses React Hook Form + Zod + PrimeReact.
 */

import { useForm, Controller } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { InputText } from 'primereact/inputtext';
import { Password } from 'primereact/password';
import { Dropdown } from 'primereact/dropdown';
import { Button } from 'primereact/button';
import { Dialog } from 'primereact/dialog';
import type { User } from '../models/User';

const createUserSchema = z.object({
  username: z.string().min(3, 'Username must be at least 3 characters').max(255),
  password: z.string().min(8, 'Password must be at least 8 characters').max(128),
  role: z.enum(['ADMIN', 'MANAGER', 'USER']),
});

type CreateUserFormData = z.infer<typeof createUserSchema>;

interface UserFormProps {
  visible: boolean;
  onHide: () => void;
  onSubmit: (data: CreateUserFormData) => void;
  loading?: boolean;
}

const roleOptions = [
  { label: 'Admin', value: 'ADMIN' },
  { label: 'Manager', value: 'MANAGER' },
  { label: 'User', value: 'USER' },
];

export const UserForm = ({ visible, onHide, onSubmit, loading }: UserFormProps) => {
  const {
    register,
    handleSubmit,
    control,
    reset,
    formState: { errors },
  } = useForm<CreateUserFormData>({
    resolver: zodResolver(createUserSchema),
    defaultValues: { role: 'USER' },
  });

  const handleFormSubmit = (data: CreateUserFormData) => {
    onSubmit(data);
    reset();
  };

  const footer = (
    <div className="flex justify-content-end gap-2">
      <Button
        label="Cancel"
        icon="pi pi-times"
        severity="secondary"
        outlined
        onClick={() => { reset(); onHide(); }}
      />
      <Button
        label="Create"
        icon="pi pi-check"
        loading={loading}
        onClick={handleSubmit(handleFormSubmit)}
      />
    </div>
  );

  return (
    <Dialog
      header="Create New User"
      visible={visible}
      onHide={() => { reset(); onHide(); }}
      style={{ width: '450px' }}
      footer={footer}
      modal
      aria-label="Create user dialog"
    >
      <form className="flex flex-column gap-4 pt-3">
        <div className="flex flex-column gap-2">
          <label htmlFor="new-username" className="font-medium">
            Username
          </label>
          <InputText
            id="new-username"
            {...register('username')}
            placeholder="Enter username"
            className={errors.username ? 'p-invalid' : ''}
            aria-describedby="new-username-error"
          />
          {errors.username && (
            <small id="new-username-error" className="p-error">
              {errors.username.message}
            </small>
          )}
        </div>

        <div className="flex flex-column gap-2">
          <label htmlFor="new-password" className="font-medium">
            Password
          </label>
          <Controller
            name="password"
            control={control}
            render={({ field }) => (
              <Password
                id="new-password"
                {...field}
                placeholder="Enter password"
                toggleMask
                className={errors.password ? 'p-invalid' : ''}
                inputClassName="w-full"
                aria-describedby="new-password-error"
              />
            )}
          />
          {errors.password && (
            <small id="new-password-error" className="p-error">
              {errors.password.message}
            </small>
          )}
        </div>

        <div className="flex flex-column gap-2">
          <label htmlFor="new-role" className="font-medium">
            Role
          </label>
          <Controller
            name="role"
            control={control}
            render={({ field }) => (
              <Dropdown
                id="new-role"
                {...field}
                options={roleOptions}
                placeholder="Select role"
                className={errors.role ? 'p-invalid' : ''}
                aria-label="User role"
              />
            )}
          />
          {errors.role && (
            <small className="p-error">{errors.role.message}</small>
          )}
        </div>
      </form>
    </Dialog>
  );
};

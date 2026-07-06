/**
 * User create form component.
 * Includes single role assignment via Dropdown, Entity dropdown,
 * conditional password field based on AD validation toggle.
 *
 * Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7, 10.8, 10.9, 10.10
 */

import { useForm, Controller } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { InputText } from 'primereact/inputtext';
import { Password } from 'primereact/password';
import { Dropdown } from 'primereact/dropdown';
import { InputSwitch } from 'primereact/inputswitch';
import { Button } from 'primereact/button';
import { Dialog } from 'primereact/dialog';
import { useRoles } from '../hooks/useRoles';
import { useEntityDropdown } from '@features/masters/hooks/useEntities';
import type { CreateUserRequest } from '../models/User';

const createUserSchema = z.object({
  employee_id: z.string().min(1, 'Employee ID is required'),
  username: z.string().min(3, 'Username must be at least 3 characters').max(255),
  email: z.string().email('Must be a valid email').max(254).optional().or(z.literal('')),
  first_name: z.string().max(100).optional().or(z.literal('')),
  last_name: z.string().max(100).optional().or(z.literal('')),
  password: z.string().optional().or(z.literal('')),
  is_validate_ad: z.boolean(),
  role_id: z.string().min(1, 'Role is required'),
  entity_id: z.string().optional().or(z.literal('')),
});

export type CreateUserFormData = z.infer<typeof createUserSchema>;

interface UserFormProps {
  visible: boolean;
  onHide: () => void;
  onSubmit: (data: CreateUserRequest) => void;
  loading?: boolean;
}

export const UserForm = ({ visible, onHide, onSubmit, loading }: UserFormProps) => {
  const { roleOptions, loading: rolesLoading } = useRoles();
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
    watch,
    formState: { errors },
  } = useForm<CreateUserFormData>({
    resolver: zodResolver(createUserSchema),
    defaultValues: {
      employee_id: '',
      username: '',
      email: '',
      first_name: '',
      last_name: '',
      password: '',
      is_validate_ad: false,
      role_id: '',
      entity_id: '',
    },
  });

  const isValidateAd = watch('is_validate_ad');

  const handleFormSubmit = (data: CreateUserFormData) => {
    const request: CreateUserRequest = {
      employee_id: data.employee_id,
      username: data.username,
      is_validate_ad: data.is_validate_ad,
      role_id: data.role_id || null,
      email: data.email || undefined,
      first_name: data.first_name || undefined,
      last_name: data.last_name || undefined,
      entity_id: data.entity_id || undefined,
      password: data.is_validate_ad ? undefined : data.password,
    };
    onSubmit(request);
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
      style={{ width: '500px' }}
      footer={footer}
      modal
      aria-label="Create user dialog"
    >
      <form className="flex flex-column gap-4 pt-3">
        {/* Employee ID (required) */}
        <div className="flex flex-column gap-2">
          <label htmlFor="new-employee-id" className="font-medium">Employee ID *</label>
          <InputText
            id="new-employee-id"
            {...register('employee_id')}
            placeholder="Enter employee ID"
            className={errors.employee_id ? 'p-invalid' : ''}
            aria-describedby="new-employee-id-error"
          />
          {errors.employee_id && (
            <small id="new-employee-id-error" className="p-error">{errors.employee_id.message}</small>
          )}
        </div>

        {/* Username */}
        <div className="flex flex-column gap-2">
          <label htmlFor="new-username" className="font-medium">Username *</label>
          <InputText
            id="new-username"
            {...register('username')}
            placeholder="Enter username"
            className={errors.username ? 'p-invalid' : ''}
            aria-describedby="new-username-error"
          />
          {errors.username && (
            <small id="new-username-error" className="p-error">{errors.username.message}</small>
          )}
        </div>

        {/* Email */}
        <div className="flex flex-column gap-2">
          <label htmlFor="new-email" className="font-medium">Email</label>
          <InputText
            id="new-email"
            {...register('email')}
            placeholder="Enter email"
            className={errors.email ? 'p-invalid' : ''}
            aria-describedby="new-email-error"
          />
          {errors.email && (
            <small id="new-email-error" className="p-error">{errors.email.message}</small>
          )}
        </div>

        {/* First Name */}
        <div className="flex flex-column gap-2">
          <label htmlFor="new-first-name" className="font-medium">First Name</label>
          <InputText
            id="new-first-name"
            {...register('first_name')}
            placeholder="Enter first name"
          />
        </div>

        {/* Last Name */}
        <div className="flex flex-column gap-2">
          <label htmlFor="new-last-name" className="font-medium">Last Name</label>
          <InputText
            id="new-last-name"
            {...register('last_name')}
            placeholder="Enter last name"
          />
        </div>

        {/* Entity Dropdown */}
        <div className="flex flex-column gap-2">
          <label htmlFor="new-entity" className="font-medium">Entity</label>
          <Controller
            name="entity_id"
            control={control}
            render={({ field }) => (
              <Dropdown
                id="new-entity"
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
          <label htmlFor="new-role" className="font-medium">Role *</label>
          <Controller
            name="role_id"
            control={control}
            render={({ field }) => (
              <Dropdown
                id="new-role"
                value={field.value}
                options={roleOptions}
                onChange={(e) => field.onChange(e.value)}
                placeholder={rolesLoading ? 'Loading roles...' : 'Select a role'}
                disabled={rolesLoading}
                className={`w-full ${errors.role_id ? 'p-invalid' : ''}`}
                aria-label="Assign role"
              />
            )}
          />
          {errors.role_id && (
            <small className="p-error">{errors.role_id.message}</small>
          )}
        </div>

        {/* Validate with AD toggle */}
        <div className="flex align-items-center gap-3">
          <Controller
            name="is_validate_ad"
            control={control}
            render={({ field }) => (
              <InputSwitch
                id="new-validate-ad"
                checked={field.value}
                onChange={(e) => field.onChange(e.value)}
                aria-label="Validate with AD"
              />
            )}
          />
          <label htmlFor="new-validate-ad" className="font-medium cursor-pointer">
            Validate with AD
          </label>
        </div>

        {/* Password (conditional: only shown when AD validation is disabled) */}
        {!isValidateAd && (
          <div className="flex flex-column gap-2">
            <label htmlFor="new-password" className="font-medium">Password *</label>
            <Controller
              name="password"
              control={control}
              render={({ field }) => (
                <Password
                  id="new-password"
                  value={field.value ?? ''}
                  onChange={(e) => field.onChange(e.target.value)}
                  placeholder="Enter password (min 8 characters)"
                  toggleMask
                  className={errors.password ? 'p-invalid' : ''}
                  inputClassName="w-full"
                  aria-describedby="new-password-error"
                />
              )}
            />
            {errors.password && (
              <small id="new-password-error" className="p-error">{errors.password.message}</small>
            )}
          </div>
        )}
      </form>
    </Dialog>
  );
};

export { createUserSchema };

/**
 * Create / edit dialog for a category of law.
 *
 * State is optional, and leaving it empty is meaningful: it marks the category as
 * country-wide rather than belonging to one state. The picker therefore offers an
 * explicit "country-wide" choice instead of relying on the user clearing it.
 */

import { useEffect } from 'react';

import { zodResolver } from '@hookform/resolvers/zod';
import { Button } from 'primereact/button';
import { Dialog } from 'primereact/dialog';
import { Dropdown } from 'primereact/dropdown';
import { InputSwitch } from 'primereact/inputswitch';
import { InputText } from 'primereact/inputtext';
import { InputTextarea } from 'primereact/inputtextarea';
import { Controller, useForm } from 'react-hook-form';
import { z } from 'zod';

import { useStateLookup } from '../hooks/useStates';
import type { CategoryOfLaw, CreateCategoryOfLawRequest } from '../models/CategoryOfLaw';

/** Sentinel for the "country-wide" option: null, since the field carries no state. */
const COUNTRY_WIDE = null;

const schema = z.object({
  code: z
    .string()
    .min(2, 'Code must be at least 2 characters')
    .max(50, 'Code must be at most 50 characters'),
  name: z.string().min(1, 'Name is required').max(255),
  description: z.string().max(2000),
  state_id: z.number().int().positive().nullable(),
  is_active: z.boolean(),
});

type FormData = z.infer<typeof schema>;

const EMPTY: FormData = {
  code: '',
  name: '',
  description: '',
  state_id: COUNTRY_WIDE,
  is_active: true,
};

interface CategoryOfLawFormProps {
  visible: boolean;
  category: CategoryOfLaw | null;
  saving?: boolean;
  onHide: () => void;
  onSubmit: (data: CreateCategoryOfLawRequest) => void;
}

export const CategoryOfLawForm = ({
  visible,
  category,
  saving,
  onHide,
  onSubmit,
}: CategoryOfLawFormProps) => {
  const isEdit = Boolean(category);
  const states = useStateLookup();

  const stateOptions = [
    { label: 'Country-wide (no state)', value: COUNTRY_WIDE as number | null },
    ...states.options,
  ];

  const {
    register,
    handleSubmit,
    control,
    reset,
    formState: { errors },
  } = useForm<FormData>({ resolver: zodResolver(schema), defaultValues: EMPTY });

  useEffect(() => {
    if (!visible) return;
    reset(
      category
        ? {
            code: category.code,
            name: category.name,
            description: category.description,
            state_id: category.state_id ?? COUNTRY_WIDE,
            is_active: category.is_active,
          }
        : EMPTY,
    );
  }, [visible, category, reset]);

  const close = () => {
    reset(EMPTY);
    onHide();
  };

  const submit = (data: FormData) => {
    onSubmit({
      code: data.code.trim().toUpperCase(),
      name: data.name.trim(),
      description: data.description.trim(),
      state_id: data.state_id,
      is_active: data.is_active,
    });
  };

  return (
    <Dialog
      header={isEdit ? `Edit Category — ${category?.code}` : 'New Category of Law'}
      visible={visible}
      onHide={close}
      style={{ width: '450px' }}
      modal
      aria-label="Category of law dialog"
      footer={
        <div className="flex justify-content-end gap-2">
          <Button label="Cancel" icon="pi pi-times" severity="secondary" outlined onClick={close} />
          <Button
            label={isEdit ? 'Save Changes' : 'Create'}
            icon="pi pi-check"
            loading={saving}
            onClick={handleSubmit(submit)}
          />
        </div>
      }
    >
      <form className="flex flex-column gap-4 pt-3">
        <div className="flex flex-column gap-2">
          <label htmlFor="category-code" className="font-medium">
            Code
          </label>
          <InputText
            id="category-code"
            {...register('code')}
            placeholder="e.g. LABOUR"
            className={errors.code ? 'p-invalid' : ''}
            aria-describedby="category-code-error"
          />
          {errors.code && (
            <small id="category-code-error" className="p-error">
              {errors.code.message}
            </small>
          )}
        </div>

        <div className="flex flex-column gap-2">
          <label htmlFor="category-name" className="font-medium">
            Name
          </label>
          <InputText
            id="category-name"
            {...register('name')}
            placeholder="e.g. Labour Law"
            className={errors.name ? 'p-invalid' : ''}
            aria-describedby="category-name-error"
          />
          {errors.name && (
            <small id="category-name-error" className="p-error">
              {errors.name.message}
            </small>
          )}
        </div>

        <div className="flex flex-column gap-2">
          <label htmlFor="category-state" className="font-medium">
            State
          </label>
          <Controller
            name="state_id"
            control={control}
            render={({ field }) => (
              <Dropdown
                id="category-state"
                value={field.value}
                options={stateOptions}
                onChange={(e) => field.onChange(e.value ?? COUNTRY_WIDE)}
                showClear
                filter
                className="w-full"
                aria-label="Owning state"
              />
            )}
          />
          <small className="text-600">
            Leave as country-wide for a category that is not state-specific.
          </small>
        </div>

        <div className="flex flex-column gap-2">
          <label htmlFor="category-description" className="font-medium">
            Description
          </label>
          <InputTextarea
            id="category-description"
            {...register('description')}
            rows={3}
            autoResize
          />
        </div>

        <div className="flex align-items-center gap-3">
          <Controller
            name="is_active"
            control={control}
            render={({ field }) => (
              <InputSwitch
                id="category-active"
                checked={field.value}
                onChange={(e) => field.onChange(e.value)}
                aria-label="Category active"
              />
            )}
          />
          <label htmlFor="category-active" className="font-medium cursor-pointer">
            Active
          </label>
        </div>
      </form>
    </Dialog>
  );
};

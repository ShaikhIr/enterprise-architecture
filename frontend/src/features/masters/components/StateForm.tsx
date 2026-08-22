/**
 * Create / edit dialog for a state.
 *
 * Country is required and offered from active countries only. A state cannot be
 * created before its country exists, so the picker being empty is a real signal
 * rather than a loading glitch — hence the explicit hint.
 */

import { useEffect } from 'react';

import { zodResolver } from '@hookform/resolvers/zod';
import { Button } from 'primereact/button';
import { Dialog } from 'primereact/dialog';
import { Dropdown } from 'primereact/dropdown';
import { InputSwitch } from 'primereact/inputswitch';
import { InputText } from 'primereact/inputtext';
import { Controller, useForm } from 'react-hook-form';
import { z } from 'zod';

import { useCountryLookup } from '../hooks/useCountries';
import type { CreateStateRequest, State } from '../models/State';

const schema = z.object({
  code: z
    .string()
    .min(2, 'Code must be at least 2 characters')
    .max(20, 'Code must be at most 20 characters'),
  name: z.string().min(1, 'Name is required').max(255),
  country_id: z.string().uuid('Select a country'),
  is_union_territory: z.boolean(),
  is_active: z.boolean(),
});

type FormData = z.infer<typeof schema>;

const EMPTY: FormData = {
  code: '',
  name: '',
  country_id: '',
  is_union_territory: false,
  is_active: true,
};

interface StateFormProps {
  visible: boolean;
  state: State | null;
  saving?: boolean;
  onHide: () => void;
  onSubmit: (data: CreateStateRequest) => void;
}

export const StateForm = ({ visible, state, saving, onHide, onSubmit }: StateFormProps) => {
  const isEdit = Boolean(state);
  const countries = useCountryLookup();

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
      state
        ? {
            code: state.code,
            name: state.name,
            country_id: state.country_id,
            is_union_territory: state.is_union_territory,
            is_active: state.is_active,
          }
        : EMPTY,
    );
  }, [visible, state, reset]);

  const close = () => {
    reset(EMPTY);
    onHide();
  };

  const submit = (data: FormData) => {
    onSubmit({
      code: data.code.trim().toUpperCase(),
      name: data.name.trim(),
      country_id: data.country_id,
      is_union_territory: data.is_union_territory,
      is_active: data.is_active,
    });
  };

  return (
    <Dialog
      header={isEdit ? `Edit State — ${state?.code}` : 'New State'}
      visible={visible}
      onHide={close}
      style={{ width: '450px' }}
      modal
      aria-label="State dialog"
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
          <label htmlFor="state-country" className="font-medium">
            Country
          </label>
          <Controller
            name="country_id"
            control={control}
            render={({ field }) => (
              <Dropdown
                id="state-country"
                value={field.value}
                options={countries.options}
                onChange={(e) => field.onChange(e.value)}
                placeholder={countries.loading ? 'Loading countries...' : 'Select a country'}
                disabled={countries.loading}
                filter
                className={`w-full ${errors.country_id ? 'p-invalid' : ''}`}
                aria-label="Owning country"
              />
            )}
          />
          {!countries.loading && countries.options.length === 0 && (
            <small className="text-600">No active countries — add a country first.</small>
          )}
          {errors.country_id && <small className="p-error">{errors.country_id.message}</small>}
        </div>

        <div className="flex flex-column gap-2">
          <label htmlFor="state-code" className="font-medium">
            Code
          </label>
          <InputText
            id="state-code"
            {...register('code')}
            placeholder="e.g. IN-MH"
            className={errors.code ? 'p-invalid' : ''}
            aria-describedby="state-code-error"
          />
          {errors.code && (
            <small id="state-code-error" className="p-error">
              {errors.code.message}
            </small>
          )}
        </div>

        <div className="flex flex-column gap-2">
          <label htmlFor="state-name" className="font-medium">
            Name
          </label>
          <InputText
            id="state-name"
            {...register('name')}
            placeholder="e.g. Maharashtra"
            className={errors.name ? 'p-invalid' : ''}
            aria-describedby="state-name-error"
          />
          {errors.name && (
            <small id="state-name-error" className="p-error">
              {errors.name.message}
            </small>
          )}
        </div>

        <div className="flex align-items-center gap-3">
          <Controller
            name="is_union_territory"
            control={control}
            render={({ field }) => (
              <InputSwitch
                id="state-ut"
                checked={field.value}
                onChange={(e) => field.onChange(e.value)}
                aria-label="Union territory"
              />
            )}
          />
          <label htmlFor="state-ut" className="font-medium cursor-pointer">
            Union territory
          </label>
        </div>

        <div className="flex align-items-center gap-3">
          <Controller
            name="is_active"
            control={control}
            render={({ field }) => (
              <InputSwitch
                id="state-active"
                checked={field.value}
                onChange={(e) => field.onChange(e.value)}
                aria-label="State active"
              />
            )}
          />
          <label htmlFor="state-active" className="font-medium cursor-pointer">
            Active
          </label>
        </div>
      </form>
    </Dialog>
  );
};

/**
 * Create / edit dialog for a country.
 *
 * The optional code fields are upper-cased on the way in to match the backend
 * validators, so the same country cannot be entered as both "ind" and "IND".
 * Empty strings are sent as null rather than "", because the backend treats those
 * columns as nullable and "" would be a value.
 */

import { useEffect } from 'react';

import { zodResolver } from '@hookform/resolvers/zod';
import { Button } from 'primereact/button';
import { Dialog } from 'primereact/dialog';
import { InputSwitch } from 'primereact/inputswitch';
import { InputText } from 'primereact/inputtext';
import { Controller, useForm } from 'react-hook-form';
import { z } from 'zod';

import type { Country, CreateCountryRequest } from '../models/Country';

const schema = z.object({
  code: z
    .string()
    .min(2, 'Code must be at least 2 characters')
    .max(10, 'Code must be at most 10 characters'),
  name: z.string().min(1, 'Name is required').max(255),
  iso3_code: z.string().max(10).optional(),
  dial_code: z.string().max(10).optional(),
  currency_code: z.string().max(10).optional(),
  is_active: z.boolean(),
});

type FormData = z.infer<typeof schema>;

const EMPTY: FormData = {
  code: '',
  name: '',
  iso3_code: '',
  dial_code: '',
  currency_code: '',
  is_active: true,
};

/** Optional text fields go to the API as null, not as an empty string. */
const orNull = (value?: string): string | null => {
  const trimmed = value?.trim();
  return trimmed ? trimmed : null;
};

interface CountryFormProps {
  visible: boolean;
  country: Country | null;
  saving?: boolean;
  onHide: () => void;
  onSubmit: (data: CreateCountryRequest) => void;
}

export const CountryForm = ({ visible, country, saving, onHide, onSubmit }: CountryFormProps) => {
  const isEdit = Boolean(country);

  const {
    register,
    handleSubmit,
    control,
    reset,
    formState: { errors },
  } = useForm<FormData>({ resolver: zodResolver(schema), defaultValues: EMPTY });

  // Reset on open so a reused dialog never shows the previous row's values.
  useEffect(() => {
    if (!visible) return;
    reset(
      country
        ? {
            code: country.code,
            name: country.name,
            iso3_code: country.iso3_code ?? '',
            dial_code: country.dial_code ?? '',
            currency_code: country.currency_code ?? '',
            is_active: country.is_active,
          }
        : EMPTY,
    );
  }, [visible, country, reset]);

  const close = () => {
    reset(EMPTY);
    onHide();
  };

  const submit = (data: FormData) => {
    onSubmit({
      code: data.code.trim().toUpperCase(),
      name: data.name.trim(),
      iso3_code: orNull(data.iso3_code)?.toUpperCase() ?? null,
      dial_code: orNull(data.dial_code),
      currency_code: orNull(data.currency_code)?.toUpperCase() ?? null,
      is_active: data.is_active,
    });
  };

  return (
    <Dialog
      header={isEdit ? `Edit Country — ${country?.code}` : 'New Country'}
      visible={visible}
      onHide={close}
      style={{ width: '450px' }}
      modal
      aria-label="Country dialog"
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
          <label htmlFor="country-code" className="font-medium">
            Code
          </label>
          <InputText
            id="country-code"
            {...register('code')}
            placeholder="e.g. IN"
            className={errors.code ? 'p-invalid' : ''}
            aria-describedby="country-code-error"
          />
          <small className="text-600">ISO 3166-1 alpha-2, upper case.</small>
          {errors.code && (
            <small id="country-code-error" className="p-error">
              {errors.code.message}
            </small>
          )}
        </div>

        <div className="flex flex-column gap-2">
          <label htmlFor="country-name" className="font-medium">
            Name
          </label>
          <InputText
            id="country-name"
            {...register('name')}
            placeholder="e.g. India"
            className={errors.name ? 'p-invalid' : ''}
            aria-describedby="country-name-error"
          />
          {errors.name && (
            <small id="country-name-error" className="p-error">
              {errors.name.message}
            </small>
          )}
        </div>

        <div className="grid">
          <div className="col-4 flex flex-column gap-2">
            <label htmlFor="country-iso3" className="font-medium">
              ISO3
            </label>
            <InputText id="country-iso3" {...register('iso3_code')} placeholder="IND" />
          </div>
          <div className="col-4 flex flex-column gap-2">
            <label htmlFor="country-dial" className="font-medium">
              Dial
            </label>
            <InputText id="country-dial" {...register('dial_code')} placeholder="+91" />
          </div>
          <div className="col-4 flex flex-column gap-2">
            <label htmlFor="country-currency" className="font-medium">
              Currency
            </label>
            <InputText id="country-currency" {...register('currency_code')} placeholder="INR" />
          </div>
        </div>

        <div className="flex align-items-center gap-3">
          <Controller
            name="is_active"
            control={control}
            render={({ field }) => (
              <InputSwitch
                id="country-active"
                checked={field.value}
                onChange={(e) => field.onChange(e.value)}
                aria-label="Country active"
              />
            )}
          />
          <label htmlFor="country-active" className="font-medium cursor-pointer">
            Active
          </label>
        </div>
      </form>
    </Dialog>
  );
};

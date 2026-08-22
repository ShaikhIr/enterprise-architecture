/**
 * Create / edit dialog for a legislation.
 *
 * Country and category are required; state is optional and empty means central
 * legislation. The state picker is narrowed to the chosen country, so a
 * Maharashtra state cannot be attached to a UK legislation.
 */

import { useEffect } from 'react';

import { zodResolver } from '@hookform/resolvers/zod';
import { Button } from 'primereact/button';
import { Calendar } from 'primereact/calendar';
import { Dialog } from 'primereact/dialog';
import { Dropdown } from 'primereact/dropdown';
import { InputSwitch } from 'primereact/inputswitch';
import { InputText } from 'primereact/inputtext';
import { InputTextarea } from 'primereact/inputtextarea';
import { Controller, useForm, useWatch } from 'react-hook-form';
import { z } from 'zod';

import { useCategoryOfLawLookup } from '../hooks/useCategoriesOfLaw';
import { useCountryLookup } from '../hooks/useCountries';
import { useStateLookup } from '../hooks/useStates';
import type { CreateLegislationRequest, Legislation } from '../models/Legislation';
import { fromIsoDate, toIsoDate } from '../utils/isoDate';

/** Sentinel for "central"; a Dropdown cannot hold null as a value. */
const CENTRAL = '';

const schema = z.object({
  code: z
    .string()
    .min(2, 'Code must be at least 2 characters')
    .max(50, 'Code must be at most 50 characters'),
  name: z.string().min(1, 'Name is required').max(500),
  description: z.string().max(4000),
  category_of_law_id: z.string().uuid('Select a category of law'),
  country_id: z.string().uuid('Select a country'),
  state_id: z.string(),
  legislation_number: z.string().max(100),
  effective_date: z.date().nullable(),
  is_active: z.boolean(),
});

type FormData = z.infer<typeof schema>;

const EMPTY: FormData = {
  code: '',
  name: '',
  description: '',
  category_of_law_id: '',
  country_id: '',
  state_id: CENTRAL,
  legislation_number: '',
  effective_date: null,
  is_active: true,
};

interface LegislationFormProps {
  visible: boolean;
  legislation: Legislation | null;
  saving?: boolean;
  onHide: () => void;
  onSubmit: (data: CreateLegislationRequest) => void;
}

export const LegislationForm = ({
  visible,
  legislation,
  saving,
  onHide,
  onSubmit,
}: LegislationFormProps) => {
  const isEdit = Boolean(legislation);
  const countries = useCountryLookup();
  const categories = useCategoryOfLawLookup();

  const {
    register,
    handleSubmit,
    control,
    reset,
    formState: { errors },
  } = useForm<FormData>({ resolver: zodResolver(schema), defaultValues: EMPTY });

  const countryId = useWatch({ control, name: 'country_id' });
  const states = useStateLookup(countryId || undefined);

  const stateOptions = [{ label: 'Central (no state)', value: CENTRAL }, ...states.options];

  useEffect(() => {
    if (!visible) return;
    reset(
      legislation
        ? {
            code: legislation.code,
            name: legislation.name,
            description: legislation.description,
            category_of_law_id: legislation.category_of_law_id,
            country_id: legislation.country_id,
            state_id: legislation.state_id ?? CENTRAL,
            legislation_number: legislation.legislation_number ?? '',
            effective_date: fromIsoDate(legislation.effective_date),
            is_active: legislation.is_active,
          }
        : EMPTY,
    );
  }, [visible, legislation, reset]);

  const close = () => {
    reset(EMPTY);
    onHide();
  };

  const submit = (data: FormData) => {
    onSubmit({
      code: data.code.trim().toUpperCase(),
      name: data.name.trim(),
      description: data.description.trim(),
      category_of_law_id: data.category_of_law_id,
      country_id: data.country_id,
      state_id: data.state_id === CENTRAL ? null : data.state_id,
      legislation_number: data.legislation_number.trim() || null,
      effective_date: toIsoDate(data.effective_date),
      is_active: data.is_active,
    });
  };

  return (
    <Dialog
      header={isEdit ? `Edit Legislation — ${legislation?.code}` : 'New Legislation'}
      visible={visible}
      onHide={close}
      style={{ width: '700px' }}
      breakpoints={{ '960px': '95vw' }}
      modal
      aria-label="Legislation dialog"
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
        <div className="grid">
          <div className="col-12 md:col-6 flex flex-column gap-2">
            <label htmlFor="legislation-country" className="font-medium">
              Country
            </label>
            <Controller
              name="country_id"
              control={control}
              render={({ field }) => (
                <Dropdown
                  id="legislation-country"
                  value={field.value}
                  options={countries.options}
                  onChange={(e) => field.onChange(e.value)}
                  placeholder={countries.loading ? 'Loading...' : 'Select a country'}
                  disabled={countries.loading}
                  filter
                  className={`w-full ${errors.country_id ? 'p-invalid' : ''}`}
                  aria-label="Owning country"
                />
              )}
            />
            {errors.country_id && <small className="p-error">{errors.country_id.message}</small>}
          </div>

          <div className="col-12 md:col-6 flex flex-column gap-2">
            <label htmlFor="legislation-state" className="font-medium">
              State
            </label>
            <Controller
              name="state_id"
              control={control}
              render={({ field }) => (
                <Dropdown
                  id="legislation-state"
                  value={field.value}
                  options={stateOptions}
                  onChange={(e) => field.onChange(e.value ?? CENTRAL)}
                  filter
                  className="w-full"
                  aria-label="Owning state"
                />
              )}
            />
            <small className="text-600">Central when no state applies.</small>
          </div>

          <div className="col-12 flex flex-column gap-2">
            <label htmlFor="legislation-category" className="font-medium">
              Category of Law
            </label>
            <Controller
              name="category_of_law_id"
              control={control}
              render={({ field }) => (
                <Dropdown
                  id="legislation-category"
                  value={field.value}
                  options={categories.options}
                  onChange={(e) => field.onChange(e.value)}
                  placeholder={categories.loading ? 'Loading...' : 'Select a category'}
                  disabled={categories.loading}
                  filter
                  className={`w-full ${errors.category_of_law_id ? 'p-invalid' : ''}`}
                  aria-label="Category of law"
                />
              )}
            />
            {!categories.loading && categories.options.length === 0 && (
              <small className="text-600">
                No active categories — add a category of law first.
              </small>
            )}
            {errors.category_of_law_id && (
              <small className="p-error">{errors.category_of_law_id.message}</small>
            )}
          </div>

          <div className="col-12 md:col-6 flex flex-column gap-2">
            <label htmlFor="legislation-code" className="font-medium">
              Code
            </label>
            <InputText
              id="legislation-code"
              {...register('code')}
              placeholder="e.g. IN-FACT-1948"
              className={errors.code ? 'p-invalid' : ''}
            />
            {errors.code && <small className="p-error">{errors.code.message}</small>}
          </div>

          <div className="col-12 md:col-6 flex flex-column gap-2">
            <label htmlFor="legislation-number" className="font-medium">
              Legislation Number
            </label>
            <InputText
              id="legislation-number"
              {...register('legislation_number')}
              placeholder="e.g. Act No. 63 of 1948"
            />
          </div>

          <div className="col-12 flex flex-column gap-2">
            <label htmlFor="legislation-name" className="font-medium">
              Name
            </label>
            <InputText
              id="legislation-name"
              {...register('name')}
              placeholder="e.g. The Factories Act, 1948"
              className={errors.name ? 'p-invalid' : ''}
            />
            {errors.name && <small className="p-error">{errors.name.message}</small>}
          </div>

          <div className="col-12 md:col-6 flex flex-column gap-2">
            <label htmlFor="legislation-effective" className="font-medium">
              Effective Date
            </label>
            <Controller
              name="effective_date"
              control={control}
              render={({ field }) => (
                <Calendar
                  id="legislation-effective"
                  value={field.value}
                  onChange={(e) => field.onChange(e.value ?? null)}
                  dateFormat="dd-mm-yy"
                  showIcon
                  showButtonBar
                  className="w-full"
                  aria-label="Effective date"
                />
              )}
            />
          </div>

          <div className="col-12 md:col-6 flex flex-column gap-2">
            <label htmlFor="legislation-active" className="font-medium">
              Active
            </label>
            <Controller
              name="is_active"
              control={control}
              render={({ field }) => (
                <InputSwitch
                  id="legislation-active"
                  checked={field.value}
                  onChange={(e) => field.onChange(e.value)}
                  aria-label="Legislation active"
                />
              )}
            />
          </div>

          <div className="col-12 flex flex-column gap-2">
            <label htmlFor="legislation-description" className="font-medium">
              Description
            </label>
            <InputTextarea
              id="legislation-description"
              {...register('description')}
              rows={3}
              autoResize
            />
          </div>
        </div>
      </form>
    </Dialog>
  );
};

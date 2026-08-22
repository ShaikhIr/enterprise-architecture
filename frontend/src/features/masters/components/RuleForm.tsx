/**
 * Create / edit dialog for a rule.
 *
 * Legislation and country are required; state is optional and empty means the rule
 * is central. The state picker is narrowed to the chosen country for the same
 * reason as on the legislation form.
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

import { useCountryLookup } from '../hooks/useCountries';
import { useLegislationLookup } from '../hooks/useLegislations';
import { useStateLookup } from '../hooks/useStates';
import type { CreateRuleRequest, Rule } from '../models/Rule';
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
  legislation_id: z.string().uuid('Select a legislation'),
  country_id: z.string().uuid('Select a country'),
  state_id: z.string(),
  rule_number: z.string().max(100),
  effective_date: z.date().nullable(),
  is_active: z.boolean(),
});

type FormData = z.infer<typeof schema>;

const EMPTY: FormData = {
  code: '',
  name: '',
  description: '',
  legislation_id: '',
  country_id: '',
  state_id: CENTRAL,
  rule_number: '',
  effective_date: null,
  is_active: true,
};

interface RuleFormProps {
  visible: boolean;
  rule: Rule | null;
  saving?: boolean;
  onHide: () => void;
  onSubmit: (data: CreateRuleRequest) => void;
}

export const RuleForm = ({ visible, rule, saving, onHide, onSubmit }: RuleFormProps) => {
  const isEdit = Boolean(rule);
  const countries = useCountryLookup();
  const legislations = useLegislationLookup();

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
      rule
        ? {
            code: rule.code,
            name: rule.name,
            description: rule.description,
            legislation_id: rule.legislation_id,
            country_id: rule.country_id,
            state_id: rule.state_id ?? CENTRAL,
            rule_number: rule.rule_number ?? '',
            effective_date: fromIsoDate(rule.effective_date),
            is_active: rule.is_active,
          }
        : EMPTY,
    );
  }, [visible, rule, reset]);

  const close = () => {
    reset(EMPTY);
    onHide();
  };

  const submit = (data: FormData) => {
    onSubmit({
      code: data.code.trim().toUpperCase(),
      name: data.name.trim(),
      description: data.description.trim(),
      legislation_id: data.legislation_id,
      country_id: data.country_id,
      state_id: data.state_id === CENTRAL ? null : data.state_id,
      rule_number: data.rule_number.trim() || null,
      effective_date: toIsoDate(data.effective_date),
      is_active: data.is_active,
    });
  };

  return (
    <Dialog
      header={isEdit ? `Edit Rule — ${rule?.code}` : 'New Rule'}
      visible={visible}
      onHide={close}
      style={{ width: '700px' }}
      breakpoints={{ '960px': '95vw' }}
      modal
      aria-label="Rule dialog"
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
          <div className="col-12 flex flex-column gap-2">
            <label htmlFor="rule-legislation" className="font-medium">
              Legislation
            </label>
            <Controller
              name="legislation_id"
              control={control}
              render={({ field }) => (
                <Dropdown
                  id="rule-legislation"
                  value={field.value}
                  options={legislations.options}
                  onChange={(e) => field.onChange(e.value)}
                  placeholder={legislations.loading ? 'Loading...' : 'Select a legislation'}
                  disabled={legislations.loading}
                  filter
                  className={`w-full ${errors.legislation_id ? 'p-invalid' : ''}`}
                  aria-label="Parent legislation"
                />
              )}
            />
            {!legislations.loading && legislations.options.length === 0 && (
              <small className="text-600">No active legislations — add a legislation first.</small>
            )}
            {errors.legislation_id && (
              <small className="p-error">{errors.legislation_id.message}</small>
            )}
          </div>

          <div className="col-12 md:col-6 flex flex-column gap-2">
            <label htmlFor="rule-country" className="font-medium">
              Country
            </label>
            <Controller
              name="country_id"
              control={control}
              render={({ field }) => (
                <Dropdown
                  id="rule-country"
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
            <label htmlFor="rule-state" className="font-medium">
              State
            </label>
            <Controller
              name="state_id"
              control={control}
              render={({ field }) => (
                <Dropdown
                  id="rule-state"
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

          <div className="col-12 md:col-6 flex flex-column gap-2">
            <label htmlFor="rule-code" className="font-medium">
              Code
            </label>
            <InputText
              id="rule-code"
              {...register('code')}
              placeholder="e.g. IN-FACT-1948-R5"
              className={errors.code ? 'p-invalid' : ''}
            />
            {errors.code && <small className="p-error">{errors.code.message}</small>}
          </div>

          <div className="col-12 md:col-6 flex flex-column gap-2">
            <label htmlFor="rule-number" className="font-medium">
              Rule Number
            </label>
            <InputText id="rule-number" {...register('rule_number')} placeholder="e.g. Rule 5(2)" />
          </div>

          <div className="col-12 flex flex-column gap-2">
            <label htmlFor="rule-name" className="font-medium">
              Name
            </label>
            <InputText
              id="rule-name"
              {...register('name')}
              placeholder="e.g. Maintenance of health register"
              className={errors.name ? 'p-invalid' : ''}
            />
            {errors.name && <small className="p-error">{errors.name.message}</small>}
          </div>

          <div className="col-12 md:col-6 flex flex-column gap-2">
            <label htmlFor="rule-effective" className="font-medium">
              Effective Date
            </label>
            <Controller
              name="effective_date"
              control={control}
              render={({ field }) => (
                <Calendar
                  id="rule-effective"
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
            <label htmlFor="rule-active" className="font-medium">
              Active
            </label>
            <Controller
              name="is_active"
              control={control}
              render={({ field }) => (
                <InputSwitch
                  id="rule-active"
                  checked={field.value}
                  onChange={(e) => field.onChange(e.value)}
                  aria-label="Rule active"
                />
              )}
            />
          </div>

          <div className="col-12 flex flex-column gap-2">
            <label htmlFor="rule-description" className="font-medium">
              Description
            </label>
            <InputTextarea id="rule-description" {...register('description')} rows={3} autoResize />
          </div>
        </div>
      </form>
    </Dialog>
  );
};

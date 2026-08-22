/**
 * Add-transition dialog.
 *
 * Source states exclude terminal ones and the target excludes the chosen source,
 * mirroring the two rules the backend enforces — so the impossible options are
 * never offered rather than rejected after submit.
 */

import { useEffect, useMemo } from 'react';

import { zodResolver } from '@hookform/resolvers/zod';
import { Button } from 'primereact/button';
import { Dialog } from 'primereact/dialog';
import { Dropdown } from 'primereact/dropdown';
import { InputNumber } from 'primereact/inputnumber';
import { InputSwitch } from 'primereact/inputswitch';
import { InputText } from 'primereact/inputtext';
import { Message } from 'primereact/message';
import { Controller, useForm, useWatch } from 'react-hook-form';
import { z } from 'zod';

import {
  WORKFLOW_ACTION_TYPES,
  WORKFLOW_ACTION_TYPE_EFFECTS,
  type CreateWorkflowTransitionRequest,
  type WorkflowStatus,
} from '../models/Workflow';

const ACTION_TYPE_LABELS: Record<(typeof WORKFLOW_ACTION_TYPES)[number], string> = {
  SUBMIT: 'Submit',
  APPROVE: 'Approve',
  REJECT: 'Reject',
  REFER_BACK: 'Refer back',
  CANCEL: 'Cancel',
  CLOSE: 'Close',
  ESCALATE: 'Escalate',
  CUSTOM: 'Custom (no approval effect)',
};

const actionTypeOptions = WORKFLOW_ACTION_TYPES.map((value) => ({
  label: ACTION_TYPE_LABELS[value],
  value,
}));

const transitionSchema = z.object({
  from_status_id: z.string().uuid('Select a source state'),
  to_status_id: z.string().uuid('Select a target state'),
  action_code: z
    .string()
    .min(2, 'Action code must be at least 2 characters')
    .max(50)
    .regex(/^[A-Z0-9_]+$/, 'Use upper case letters, numbers and underscores only'),
  action_type: z.enum(WORKFLOW_ACTION_TYPES),
  requires_comment: z.boolean(),
  auto_execute: z.boolean(),
  priority: z.number().int().min(0).max(999),
});

type TransitionFormData = z.infer<typeof transitionSchema>;

const EMPTY: TransitionFormData = {
  from_status_id: '',
  to_status_id: '',
  action_code: '',
  action_type: 'CUSTOM',
  requires_comment: false,
  auto_execute: false,
  priority: 0,
};

interface WorkflowTransitionFormProps {
  visible: boolean;
  statuses: WorkflowStatus[];
  loading?: boolean;
  onHide: () => void;
  onSubmit: (data: CreateWorkflowTransitionRequest) => void;
}

export const WorkflowTransitionForm = ({
  visible,
  statuses,
  loading,
  onHide,
  onSubmit,
}: WorkflowTransitionFormProps) => {
  const {
    register,
    handleSubmit,
    control,
    reset,
    formState: { errors },
  } = useForm<TransitionFormData>({
    resolver: zodResolver(transitionSchema),
    defaultValues: EMPTY,
  });

  const fromStatusId = useWatch({ control, name: 'from_status_id' });
  const actionType = useWatch({ control, name: 'action_type' });

  useEffect(() => {
    if (visible) reset(EMPTY);
  }, [visible, reset]);

  const label = (status: WorkflowStatus) => `${status.name} (${status.code})`;

  const sourceOptions = useMemo(
    () =>
      statuses
        .filter((status) => !status.is_terminal)
        .map((status) => ({ label: label(status), value: status.id })),
    [statuses],
  );

  const targetOptions = useMemo(
    () =>
      statuses
        .filter((status) => status.id !== fromStatusId)
        .map((status) => ({ label: label(status), value: status.id })),
    [statuses, fromStatusId],
  );

  const close = () => {
    reset(EMPTY);
    onHide();
  };

  const submit = (data: TransitionFormData) => {
    onSubmit({ ...data, guard_expression: null });
  };

  const footer = (
    <div className="flex justify-content-end gap-2">
      <Button label="Cancel" icon="pi pi-times" severity="secondary" outlined onClick={close} />
      <Button
        label="Add Transition"
        icon="pi pi-check"
        loading={loading}
        disabled={sourceOptions.length === 0}
        onClick={handleSubmit(submit)}
      />
    </div>
  );

  return (
    <Dialog
      header="Add Transition"
      visible={visible}
      onHide={close}
      style={{ width: '480px' }}
      footer={footer}
      modal
      aria-label="Workflow transition dialog"
    >
      <form className="flex flex-column gap-4 pt-3">
        {statuses.length < 2 && (
          <Message severity="warn" text="Add at least two states before wiring a transition." />
        )}

        <div className="flex flex-column gap-2">
          <label htmlFor="tr-from" className="font-medium">
            From State
          </label>
          <Controller
            name="from_status_id"
            control={control}
            render={({ field }) => (
              <Dropdown
                id="tr-from"
                value={field.value}
                options={sourceOptions}
                onChange={(e) => field.onChange(e.value)}
                placeholder="Select the source state"
                className={`w-full ${errors.from_status_id ? 'p-invalid' : ''}`}
                aria-label="Source state"
              />
            )}
          />
          <small className="text-600">Terminal states are excluded — nothing leaves them.</small>
          {errors.from_status_id && (
            <small className="p-error">{errors.from_status_id.message}</small>
          )}
        </div>

        <div className="flex flex-column gap-2">
          <label htmlFor="tr-action" className="font-medium">
            Action Code
          </label>
          <InputText
            id="tr-action"
            {...register('action_code')}
            placeholder="e.g. APPROVE, REJECT, SUBMIT"
            className={errors.action_code ? 'p-invalid' : ''}
            aria-describedby="tr-action-error"
          />
          {errors.action_code && (
            <small id="tr-action-error" className="p-error">
              {errors.action_code.message}
            </small>
          )}
        </div>

        <div className="flex flex-column gap-2">
          <label htmlFor="tr-action-type" className="font-medium">
            Action Type
          </label>
          <Controller
            name="action_type"
            control={control}
            render={({ field }) => (
              <Dropdown
                id="tr-action-type"
                value={field.value}
                options={actionTypeOptions}
                onChange={(e) => field.onChange(e.value)}
                className="w-full"
                aria-label="Action type"
              />
            )}
          />
          <small className="text-600">
            {WORKFLOW_ACTION_TYPE_EFFECTS[actionType]} — the action code above is a label; this is
            what drives the approval chain.
          </small>
        </div>

        <div className="flex flex-column gap-2">
          <label htmlFor="tr-to" className="font-medium">
            To State
          </label>
          <Controller
            name="to_status_id"
            control={control}
            render={({ field }) => (
              <Dropdown
                id="tr-to"
                value={field.value}
                options={targetOptions}
                onChange={(e) => field.onChange(e.value)}
                placeholder="Select the target state"
                className={`w-full ${errors.to_status_id ? 'p-invalid' : ''}`}
                aria-label="Target state"
              />
            )}
          />
          {errors.to_status_id && <small className="p-error">{errors.to_status_id.message}</small>}
        </div>

        <div className="flex flex-column gap-2">
          <label htmlFor="tr-priority" className="font-medium">
            Priority
          </label>
          <Controller
            name="priority"
            control={control}
            render={({ field }) => (
              <InputNumber
                id="tr-priority"
                value={field.value}
                onValueChange={(e) => field.onChange(e.value ?? 0)}
                min={0}
                max={999}
                showButtons
                aria-label="Transition priority"
              />
            )}
          />
          <small className="text-600">Lower values are offered first.</small>
        </div>

        <div className="flex align-items-center gap-3">
          <Controller
            name="requires_comment"
            control={control}
            render={({ field }) => (
              <InputSwitch
                id="tr-requires-comment"
                checked={field.value}
                onChange={(e) => field.onChange(e.value)}
                aria-label="Requires comment"
              />
            )}
          />
          <label htmlFor="tr-requires-comment" className="font-medium cursor-pointer">
            Requires a comment
          </label>
        </div>

        <div className="flex align-items-center gap-3">
          <Controller
            name="auto_execute"
            control={control}
            render={({ field }) => (
              <InputSwitch
                id="tr-auto-execute"
                checked={field.value}
                onChange={(e) => field.onChange(e.value)}
                aria-label="Auto execute"
              />
            )}
          />
          <label htmlFor="tr-auto-execute" className="font-medium cursor-pointer">
            Auto-execute when reached
          </label>
        </div>
      </form>
    </Dialog>
  );
};

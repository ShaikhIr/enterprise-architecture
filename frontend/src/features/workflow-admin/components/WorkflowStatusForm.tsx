/**
 * Create / edit dialog for one workflow state.
 *
 * Position is a single three-way choice rather than two switches: the backend
 * rejects a state that is both initial and terminal, so offering that
 * combination at all would only produce a 409.
 */

import { useEffect } from 'react';

import { zodResolver } from '@hookform/resolvers/zod';
import { Button } from 'primereact/button';
import { Dialog } from 'primereact/dialog';
import { Dropdown } from 'primereact/dropdown';
import { InputNumber } from 'primereact/inputnumber';
import { InputText } from 'primereact/inputtext';
import { Controller, useForm } from 'react-hook-form';
import { z } from 'zod';

import type { CreateWorkflowStatusRequest, WorkflowStatus } from '../models/Workflow';

type StatePosition = 'INITIAL' | 'INTERMEDIATE' | 'TERMINAL';

const POSITION_OPTIONS: { label: string; value: StatePosition }[] = [
  { label: 'Initial — workflows start here', value: 'INITIAL' },
  { label: 'Intermediate — in progress', value: 'INTERMEDIATE' },
  { label: 'Terminal — workflow ends here', value: 'TERMINAL' },
];

const statusSchema = z.object({
  code: z
    .string()
    .min(2, 'Code must be at least 2 characters')
    .max(50)
    .regex(/^[A-Z0-9_]+$/, 'Use upper case letters, numbers and underscores only'),
  name: z.string().min(1, 'Name is required').max(255),
  position: z.enum(['INITIAL', 'INTERMEDIATE', 'TERMINAL']),
  sequence: z.number().int().min(0).max(999),
});

type StatusFormData = z.infer<typeof statusSchema>;

const EMPTY: StatusFormData = {
  code: '',
  name: '',
  position: 'INTERMEDIATE',
  sequence: 0,
};

const toPosition = (status: WorkflowStatus): StatePosition => {
  if (status.is_initial) return 'INITIAL';
  if (status.is_terminal) return 'TERMINAL';
  return 'INTERMEDIATE';
};

interface WorkflowStatusFormProps {
  visible: boolean;
  status?: WorkflowStatus | null;
  loading?: boolean;
  nextSequence?: number;
  onHide: () => void;
  onSubmit: (data: CreateWorkflowStatusRequest) => void;
}

export const WorkflowStatusForm = ({
  visible,
  status,
  loading,
  nextSequence = 0,
  onHide,
  onSubmit,
}: WorkflowStatusFormProps) => {
  const isEdit = Boolean(status);

  const {
    register,
    handleSubmit,
    control,
    reset,
    formState: { errors },
  } = useForm<StatusFormData>({
    resolver: zodResolver(statusSchema),
    defaultValues: EMPTY,
  });

  useEffect(() => {
    if (!visible) return;
    reset(
      status
        ? {
            code: status.code,
            name: status.name,
            position: toPosition(status),
            sequence: status.sequence,
          }
        : { ...EMPTY, sequence: nextSequence },
    );
  }, [visible, status, nextSequence, reset]);

  const close = () => {
    reset(EMPTY);
    onHide();
  };

  const submit = (data: StatusFormData) => {
    onSubmit({
      code: data.code,
      name: data.name,
      sequence: data.sequence,
      is_initial: data.position === 'INITIAL',
      is_terminal: data.position === 'TERMINAL',
    });
  };

  const footer = (
    <div className="flex justify-content-end gap-2">
      <Button label="Cancel" icon="pi pi-times" severity="secondary" outlined onClick={close} />
      <Button
        label={isEdit ? 'Save Changes' : 'Add State'}
        icon="pi pi-check"
        loading={loading}
        onClick={handleSubmit(submit)}
      />
    </div>
  );

  return (
    <Dialog
      header={isEdit ? `Edit State — ${status?.code}` : 'Add State'}
      visible={visible}
      onHide={close}
      style={{ width: '440px' }}
      footer={footer}
      modal
      aria-label="Workflow state dialog"
    >
      <form className="flex flex-column gap-4 pt-3">
        <div className="flex flex-column gap-2">
          <label htmlFor="state-code" className="font-medium">
            Code
          </label>
          <InputText
            id="state-code"
            {...register('code')}
            placeholder="e.g. PENDING_REVIEW"
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
            placeholder="e.g. Pending Review"
            className={errors.name ? 'p-invalid' : ''}
            aria-describedby="state-name-error"
          />
          {errors.name && (
            <small id="state-name-error" className="p-error">
              {errors.name.message}
            </small>
          )}
        </div>

        <div className="flex flex-column gap-2">
          <label htmlFor="state-position" className="font-medium">
            Position
          </label>
          <Controller
            name="position"
            control={control}
            render={({ field }) => (
              <Dropdown
                id="state-position"
                value={field.value}
                options={POSITION_OPTIONS}
                onChange={(e) => field.onChange(e.value)}
                className="w-full"
                aria-label="State position"
              />
            )}
          />
          <small className="text-600">
            A workflow has exactly one initial state and any number of terminal ones.
          </small>
        </div>

        <div className="flex flex-column gap-2">
          <label htmlFor="state-sequence" className="font-medium">
            Sequence
          </label>
          <Controller
            name="sequence"
            control={control}
            render={({ field }) => (
              <InputNumber
                id="state-sequence"
                value={field.value}
                onValueChange={(e) => field.onChange(e.value ?? 0)}
                min={0}
                max={999}
                showButtons
                aria-label="Display order"
              />
            )}
          />
          <small className="text-600">Display order only; it does not affect routing.</small>
        </div>
      </form>
    </Dialog>
  );
};

/**
 * Create / edit dialog for a task type.
 *
 * Codes are normalised to upper snake case to match the backend validator, so
 * "return filing" and "Return_Filing" cannot both exist.
 */

import { useEffect } from 'react';

import { zodResolver } from '@hookform/resolvers/zod';
import { Button } from 'primereact/button';
import { Dialog } from 'primereact/dialog';
import { InputSwitch } from 'primereact/inputswitch';
import { InputText } from 'primereact/inputtext';
import { InputTextarea } from 'primereact/inputtextarea';
import { Controller, useForm } from 'react-hook-form';
import { z } from 'zod';

import type { CreateTaskTypeRequest, TaskType } from '../models/TaskType';

const schema = z.object({
  code: z
    .string()
    .min(2, 'Code must be at least 2 characters')
    .max(50, 'Code must be at most 50 characters'),
  name: z.string().min(1, 'Name is required').max(255),
  description: z.string().max(2000),
  is_active: z.boolean(),
});

type FormData = z.infer<typeof schema>;

const EMPTY: FormData = { code: '', name: '', description: '', is_active: true };

interface TaskTypeFormProps {
  visible: boolean;
  taskType: TaskType | null;
  saving?: boolean;
  onHide: () => void;
  onSubmit: (data: CreateTaskTypeRequest) => void;
}

export const TaskTypeForm = ({
  visible,
  taskType,
  saving,
  onHide,
  onSubmit,
}: TaskTypeFormProps) => {
  const isEdit = Boolean(taskType);

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
      taskType
        ? {
            code: taskType.code,
            name: taskType.name,
            description: taskType.description,
            is_active: taskType.is_active,
          }
        : EMPTY,
    );
  }, [visible, taskType, reset]);

  const close = () => {
    reset(EMPTY);
    onHide();
  };

  const submit = (data: FormData) => {
    onSubmit({
      code: data.code.trim().toUpperCase().replace(/\s+/g, '_'),
      name: data.name.trim(),
      description: data.description.trim(),
      is_active: data.is_active,
    });
  };

  return (
    <Dialog
      header={isEdit ? `Edit Task Type — ${taskType?.code}` : 'New Task Type'}
      visible={visible}
      onHide={close}
      style={{ width: '450px' }}
      modal
      aria-label="Task type dialog"
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
          <label htmlFor="task-type-code" className="font-medium">
            Code
          </label>
          <InputText
            id="task-type-code"
            {...register('code')}
            placeholder="e.g. RETURN_FILING"
            className={errors.code ? 'p-invalid' : ''}
            aria-describedby="task-type-code-error"
          />
          {errors.code && (
            <small id="task-type-code-error" className="p-error">
              {errors.code.message}
            </small>
          )}
        </div>

        <div className="flex flex-column gap-2">
          <label htmlFor="task-type-name" className="font-medium">
            Name
          </label>
          <InputText
            id="task-type-name"
            {...register('name')}
            placeholder="e.g. Return Filing"
            className={errors.name ? 'p-invalid' : ''}
            aria-describedby="task-type-name-error"
          />
          {errors.name && (
            <small id="task-type-name-error" className="p-error">
              {errors.name.message}
            </small>
          )}
        </div>

        <div className="flex flex-column gap-2">
          <label htmlFor="task-type-description" className="font-medium">
            Description
          </label>
          <InputTextarea
            id="task-type-description"
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
                id="task-type-active"
                checked={field.value}
                onChange={(e) => field.onChange(e.value)}
                aria-label="Task type active"
              />
            )}
          />
          <label htmlFor="task-type-active" className="font-medium cursor-pointer">
            Active
          </label>
        </div>
      </form>
    </Dialog>
  );
};

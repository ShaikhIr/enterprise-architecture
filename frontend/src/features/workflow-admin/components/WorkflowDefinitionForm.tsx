/**
 * Create / edit dialog for a workflow definition.
 *
 * One component serves both modes: `definition` being set switches it to edit,
 * where `code` is locked because it is the key business modules start workflows
 * by, and changing it would silently break their calls.
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

import type { CreateWorkflowDefinitionRequest, WorkflowDefinition } from '../models/Workflow';

const definitionSchema = z.object({
  code: z
    .string()
    .min(2, 'Code must be at least 2 characters')
    .max(100)
    .regex(/^[A-Z0-9_]+$/, 'Use upper case letters, numbers and underscores only'),
  name: z.string().min(2, 'Name must be at least 2 characters').max(255),
  entity_type: z
    .string()
    .min(2, 'Entity type must be at least 2 characters')
    .max(100)
    .regex(/^[a-z0-9_]+$/, 'Use lower case letters, numbers and underscores only'),
  description: z.string().max(2000),
  is_active: z.boolean(),
});

type DefinitionFormData = z.infer<typeof definitionSchema>;

const EMPTY: DefinitionFormData = {
  code: '',
  name: '',
  entity_type: '',
  description: '',
  is_active: true,
};

interface WorkflowDefinitionFormProps {
  visible: boolean;
  definition?: WorkflowDefinition | null;
  loading?: boolean;
  onHide: () => void;
  onSubmit: (data: CreateWorkflowDefinitionRequest) => void;
}

export const WorkflowDefinitionForm = ({
  visible,
  definition,
  loading,
  onHide,
  onSubmit,
}: WorkflowDefinitionFormProps) => {
  const isEdit = Boolean(definition);

  const {
    register,
    handleSubmit,
    control,
    reset,
    formState: { errors },
  } = useForm<DefinitionFormData>({
    resolver: zodResolver(definitionSchema),
    defaultValues: EMPTY,
  });

  // Reset on open so a reused dialog never shows the previous row's values.
  useEffect(() => {
    if (!visible) return;
    reset(
      definition
        ? {
            code: definition.code,
            name: definition.name,
            entity_type: definition.entity_type,
            description: definition.description,
            is_active: definition.is_active,
          }
        : EMPTY,
    );
  }, [visible, definition, reset]);

  const close = () => {
    reset(EMPTY);
    onHide();
  };

  const footer = (
    <div className="flex justify-content-end gap-2">
      <Button label="Cancel" icon="pi pi-times" severity="secondary" outlined onClick={close} />
      <Button
        label={isEdit ? 'Save Changes' : 'Create'}
        icon="pi pi-check"
        loading={loading}
        onClick={handleSubmit(onSubmit)}
      />
    </div>
  );

  return (
    <Dialog
      header={isEdit ? `Edit Workflow — ${definition?.code}` : 'New Workflow'}
      visible={visible}
      onHide={close}
      style={{ width: '480px' }}
      footer={footer}
      modal
      aria-label="Workflow definition dialog"
    >
      <form className="flex flex-column gap-4 pt-3">
        <div className="flex flex-column gap-2">
          <label htmlFor="wf-code" className="font-medium">
            Code
          </label>
          <InputText
            id="wf-code"
            {...register('code')}
            placeholder="e.g. RETURN_FILING"
            disabled={isEdit}
            className={errors.code ? 'p-invalid' : ''}
            aria-describedby="wf-code-error"
          />
          {isEdit && (
            <small className="text-600">
              Code is fixed after creation — business modules start workflows by it.
            </small>
          )}
          {errors.code && (
            <small id="wf-code-error" className="p-error">
              {errors.code.message}
            </small>
          )}
        </div>

        <div className="flex flex-column gap-2">
          <label htmlFor="wf-name" className="font-medium">
            Name
          </label>
          <InputText
            id="wf-name"
            {...register('name')}
            placeholder="e.g. Return Filing Approval"
            className={errors.name ? 'p-invalid' : ''}
            aria-describedby="wf-name-error"
          />
          {errors.name && (
            <small id="wf-name-error" className="p-error">
              {errors.name.message}
            </small>
          )}
        </div>

        <div className="flex flex-column gap-2">
          <label htmlFor="wf-entity-type" className="font-medium">
            Entity Type
          </label>
          <InputText
            id="wf-entity-type"
            {...register('entity_type')}
            placeholder="e.g. compliance_task"
            className={errors.entity_type ? 'p-invalid' : ''}
            aria-describedby="wf-entity-type-error"
          />
          <small className="text-600">
            The record type this workflow governs. Approval matrices are matched on the same value.
          </small>
          {errors.entity_type && (
            <small id="wf-entity-type-error" className="p-error">
              {errors.entity_type.message}
            </small>
          )}
        </div>

        <div className="flex flex-column gap-2">
          <label htmlFor="wf-description" className="font-medium">
            Description
          </label>
          <InputTextarea
            id="wf-description"
            {...register('description')}
            rows={3}
            autoResize
            aria-describedby="wf-description-error"
          />
          {errors.description && (
            <small id="wf-description-error" className="p-error">
              {errors.description.message}
            </small>
          )}
        </div>

        <div className="flex align-items-center gap-3">
          <Controller
            name="is_active"
            control={control}
            render={({ field }) => (
              <InputSwitch
                id="wf-is-active"
                checked={field.value}
                onChange={(e) => field.onChange(e.value)}
                aria-label="Workflow active"
              />
            )}
          />
          <label htmlFor="wf-is-active" className="font-medium cursor-pointer">
            Active
          </label>
        </div>
      </form>
    </Dialog>
  );
};

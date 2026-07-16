/**
 * Entity Form Dialog.
 * Create/Edit dialog for Entity Master records.
 * Uses React Hook Form + Zod for validation, handles 409/422 server errors.
 *
 * Requirements: 2.4, 2.5, 2.6, 2.7, 2.8, 2.10, 14.5, 14.6
 */

import { useEffect, useState } from 'react';
import { useForm, Controller } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { Dialog } from 'primereact/dialog';
import { Button } from 'primereact/button';
import { InputText } from 'primereact/inputtext';
import { Dropdown } from 'primereact/dropdown';
import { RadioButton } from 'primereact/radiobutton';
import { entityCreateSchema, type EntityCreateFormData } from '../schemas/entitySchema';
import { mapBackendErrors } from '../utils/errorUtils';
import { workflowApi, type WorkflowDefinition } from '@features/workflow-admin/api/workflowApi';
import type { Entity } from '../models/entity';

interface EntityFormDialogProps {
  visible: boolean;
  onHide: () => void;
  entity: Entity | null; // null = create mode, Entity = edit mode
  onSubmit: (data: EntityCreateFormData) => Promise<void>;
  loading: boolean;
}

export const EntityFormDialog = ({
  visible,
  onHide,
  entity,
  onSubmit,
  loading,
}: EntityFormDialogProps) => {
  const isEditMode = entity !== null;

  const [workflowOptions, setWorkflowOptions] = useState<{ label: string; value: string }[]>([]);

  useEffect(() => {
    workflowApi.listDefinitions().then((res) => {
      const defs = res.definitions || [];
      setWorkflowOptions(
        defs.filter((d) => d.is_active).map((d) => ({ label: `${d.name} (${d.code})`, value: d.id }))
      );
    }).catch(() => {});
  }, []);

  const {
    register,
    handleSubmit,
    reset,
    setError,
    control,
    formState: { errors },
  } = useForm<EntityCreateFormData>({
    resolver: zodResolver(entityCreateSchema),
    defaultValues: {
      entity_name: '',
      short_code: '',
      company_code: '',
      is_active: true,
      workflow_definition_id: '',
    },
  });

  // Pre-populate form when editing
  useEffect(() => {
    if (visible) {
      if (entity) {
        reset({
          entity_name: entity.entity_name,
          short_code: entity.short_code ?? '',
          company_code: entity.company_code ?? '',
          is_active: entity.is_active,
          workflow_definition_id: entity.workflow_definition_id ?? '',
        });
      } else {
        reset({
          entity_name: '',
          short_code: '',
          company_code: '',
          is_active: true,
          workflow_definition_id: '',
        });
      }
    }
  }, [visible, entity, reset]);

  const onFormSubmit = async (data: EntityCreateFormData) => {
    try {
      await onSubmit(data);
    } catch (error: any) {
      const status = error?.response?.status;
      if (status === 422) {
        mapBackendErrors(error, setError);
      }
      // 409 and other errors are handled by the parent (EntityListPage)
      throw error;
    }
  };

  const footer = (
    <div className="flex justify-content-end gap-2">
      <Button
        label="Cancel"
        icon="pi pi-times"
        severity="secondary"
        outlined
        onClick={onHide}
        type="button"
      />
      <Button
        label={isEditMode ? 'Update' : 'Create'}
        icon="pi pi-check"
        onClick={handleSubmit(onFormSubmit)}
        loading={loading}
        type="submit"
      />
    </div>
  );

  return (
    <Dialog
      header={isEditMode ? 'Edit Entity' : 'New Entity'}
      visible={visible}
      onHide={onHide}
      style={{ width: '500px' }}
      footer={footer}
      modal
      aria-label={isEditMode ? 'Edit entity dialog' : 'Create entity dialog'}
    >
      <form className="flex flex-column gap-4 pt-2" onSubmit={handleSubmit(onFormSubmit)}>
        {/* Entity Name (required) */}
        <div className="flex flex-column gap-2">
          <label htmlFor="entity_name" className="font-medium">
            Entity Name <span className="text-red-500">*</span>
          </label>
          <InputText
            id="entity_name"
            {...register('entity_name')}
            placeholder="Enter entity name"
            className={errors.entity_name ? 'p-invalid' : ''}
            aria-invalid={!!errors.entity_name}
            aria-describedby="entity_name-error"
          />
          {errors.entity_name && (
            <small id="entity_name-error" className="p-error">
              {errors.entity_name.message}
            </small>
          )}
        </div>

        {/* Short Code (optional) */}
        <div className="flex flex-column gap-2">
          <label htmlFor="short_code" className="font-medium">
            Short Code
          </label>
          <InputText
            id="short_code"
            {...register('short_code')}
            placeholder="e.g. EMC"
            className={errors.short_code ? 'p-invalid' : ''}
            aria-invalid={!!errors.short_code}
            aria-describedby="short_code-error"
          />
          {errors.short_code && (
            <small id="short_code-error" className="p-error">
              {errors.short_code.message}
            </small>
          )}
        </div>

        {/* Company Code (optional) */}
        <div className="flex flex-column gap-2">
          <label htmlFor="company_code" className="font-medium">
            Company Code
          </label>
          <InputText
            id="company_code"
            {...register('company_code')}
            placeholder="e.g. 1000"
            className={errors.company_code ? 'p-invalid' : ''}
            aria-invalid={!!errors.company_code}
            aria-describedby="company_code-error"
          />
          {errors.company_code && (
            <small id="company_code-error" className="p-error">
              {errors.company_code.message}
            </small>
          )}
        </div>

        {/* Approval Workflow */}
        <div className="flex flex-column gap-2">
          <label htmlFor="workflow_definition_id" className="font-medium">
            Approval Workflow
          </label>
          <Controller
            name="workflow_definition_id"
            control={control}
            render={({ field }) => (
              <Dropdown
                id="workflow_definition_id"
                value={field.value}
                options={workflowOptions}
                onChange={(e) => field.onChange(e.value)}
                placeholder="Select approval workflow..."
                filter
                showClear
                className="w-full"
                aria-label="Approval Workflow"
              />
            )}
          />
        </div>

        {/* Status — Active / Inactive radio buttons (edit mode only) */}
        {isEditMode && (
          <div className="flex flex-column gap-2">
            <label className="font-medium">Status</label>
            <Controller
              name="is_active"
              control={control}
              render={({ field }) => (
                <div className="flex gap-4">
                  <div className="flex align-items-center gap-2">
                    <RadioButton inputId="ent_active" value={true} checked={field.value === true} onChange={() => field.onChange(true)} />
                    <label htmlFor="ent_active" className="cursor-pointer" style={{ color: 'var(--color-success)', fontWeight: 500 }}>Active</label>
                  </div>
                  <div className="flex align-items-center gap-2">
                    <RadioButton inputId="ent_inactive" value={false} checked={field.value === false} onChange={() => field.onChange(false)} />
                    <label htmlFor="ent_inactive" className="cursor-pointer" style={{ color: 'var(--color-error)', fontWeight: 500 }}>Inactive</label>
                  </div>
                </div>
              )}
            />
          </div>
        )}
      </form>
    </Dialog>
  );
};

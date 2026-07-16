/**
 * ClaimActionDialog — reusable dialog for Approve / Refer Back / Reject workflow actions.
 * Requires non-empty remarks (per Req 7.5).
 */
import { useEffect } from 'react';
import { useForm, Controller } from 'react-hook-form';
import { Dialog } from 'primereact/dialog';
import { InputTextarea } from 'primereact/inputtextarea';
import { Button } from 'primereact/button';
import { classNames } from 'primereact/utils';

export type WorkflowActionType = 'approve' | 'referBack' | 'reject';

interface ClaimActionDialogProps {
  visible: boolean;
  action: WorkflowActionType;
  onHide: () => void;
  onConfirm: (remarks: string) => void;
  loading?: boolean;
}

const ACTION_CONFIG: Record<
  WorkflowActionType,
  { label: string; icon: string; severity?: 'success' | 'danger' | 'warning' }
> = {
  approve:   { label: 'Approve',    icon: 'pi pi-check',      severity: 'success' },
  referBack: { label: 'Refer Back', icon: 'pi pi-arrow-left', severity: 'warning' },
  reject:    { label: 'Reject',     icon: 'pi pi-times',      severity: 'danger' },
};

export const ClaimActionDialog = ({
  visible,
  action,
  onHide,
  onConfirm,
  loading = false,
}: ClaimActionDialogProps) => {
  const {
    control,
    handleSubmit,
    reset,
    watch,
    formState: { errors },
  } = useForm<{ remarks: string }>({
    defaultValues: { remarks: '' },
  });

  const remarks = watch('remarks');

  useEffect(() => {
    if (visible) reset({ remarks: '' });
  }, [visible, reset]);

  const config = ACTION_CONFIG[action];

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
        label={config.label}
        icon={config.icon}
        severity={config.severity}
        onClick={handleSubmit((data) => onConfirm(data.remarks))}
        loading={loading}
        disabled={!remarks?.trim()}
        type="button"
      />
    </div>
  );

  return (
    <Dialog
      header={config.label}
      visible={visible}
      onHide={onHide}
      style={{ width: '480px' }}
      footer={footer}
      modal
      aria-label={`${config.label} claim dialog`}
    >
      <div className="flex flex-column gap-3 pt-2">
        <div className="flex flex-column gap-1">
          <label htmlFor="remarks" className="font-medium">
            Remarks <span className="text-red-500">*</span>
          </label>
          <Controller
            name="remarks"
            control={control}
            rules={{ required: 'Remarks are required' }}
            render={({ field }) => (
              <InputTextarea
                id="remarks"
                {...field}
                rows={4}
                autoResize
                className={classNames({ 'p-invalid': errors.remarks })}
                placeholder="Enter your remarks..."
                aria-label="Remarks"
              />
            )}
          />
          {errors.remarks && (
            <small className="p-error">{errors.remarks.message}</small>
          )}
        </div>
      </div>
    </Dialog>
  );
};

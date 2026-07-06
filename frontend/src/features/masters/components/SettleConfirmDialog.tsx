/**
 * SettleConfirmDialog — Simple confirmation dialog for marking an invoice as Settled.
 * On confirm, calls useMarkSettled mutation.
 *
 * Requirements: 9.8
 */

import { Dialog } from 'primereact/dialog';
import { Button } from 'primereact/button';

interface SettleConfirmDialogProps {
  visible: boolean;
  onHide: () => void;
  onConfirm: () => void;
  loading?: boolean;
}

export const SettleConfirmDialog = ({
  visible,
  onHide,
  onConfirm,
  loading = false,
}: SettleConfirmDialogProps) => {
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
        label="Mark Settled"
        icon="pi pi-check"
        severity="success"
        onClick={onConfirm}
        loading={loading}
        type="button"
      />
    </div>
  );

  return (
    <Dialog
      header="Confirm Settlement"
      visible={visible}
      onHide={onHide}
      style={{ width: '450px' }}
      footer={footer}
      modal
      aria-label="Settle invoice confirmation dialog"
    >
      <div className="flex align-items-center gap-3 pt-2">
        <i className="pi pi-question-circle text-4xl text-blue-500" />
        <p className="m-0 line-height-3">
          Are you sure you want to mark this invoice as Settled?
        </p>
      </div>
    </Dialog>
  );
};

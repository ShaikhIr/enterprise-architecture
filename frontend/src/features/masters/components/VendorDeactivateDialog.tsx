/**
 * VendorDeactivateDialog — Confirmation dialog for vendor deactivation.
 * Warns that deactivation will block portal access and claim submissions.
 *
 * Requirements: 3.9, 3.10
 */

import { Dialog } from 'primereact/dialog';
import { Button } from 'primereact/button';

interface VendorDeactivateDialogProps {
  visible: boolean;
  onHide: () => void;
  onConfirm: () => void;
  vendorName?: string;
  loading?: boolean;
}

export const VendorDeactivateDialog = ({
  visible,
  onHide,
  onConfirm,
  vendorName,
  loading = false,
}: VendorDeactivateDialogProps) => {
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
        label="Deactivate"
        icon="pi pi-ban"
        severity="danger"
        onClick={onConfirm}
        loading={loading}
        type="button"
      />
    </div>
  );

  return (
    <Dialog
      header="Confirm Deactivation"
      visible={visible}
      onHide={onHide}
      style={{ width: '450px' }}
      footer={footer}
      modal
      aria-label="Vendor deactivation confirmation dialog"
    >
      <div className="flex align-items-center gap-3 pt-2">
        <i className="pi pi-exclamation-triangle text-4xl text-orange-500" />
        <div>
          {vendorName && (
            <p className="font-semibold mb-2">Vendor: {vendorName}</p>
          )}
          <p className="m-0 line-height-3">
            Deactivating this vendor will block their portal access and claim submissions.
          </p>
        </div>
      </div>
    </Dialog>
  );
};

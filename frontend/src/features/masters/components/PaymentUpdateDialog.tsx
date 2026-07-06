/**
 * PaymentUpdateDialog — Dialog for updating invoice payment details.
 * Fields: Payment Clearing Date (Calendar), SAP Clearing Document No (InputText).
 * On submit, calls useUpdatePayment mutation.
 *
 * Requirements: 9.6, 9.7
 */

import { useEffect } from 'react';
import { useForm, Controller } from 'react-hook-form';
import { Dialog } from 'primereact/dialog';
import { InputText } from 'primereact/inputtext';
import { Calendar } from 'primereact/calendar';
import { Button } from 'primereact/button';
import { classNames } from 'primereact/utils';

interface PaymentUpdateFormData {
  payment_clearing_date: string;
  sap_clearing_doc_no: string;
}

interface PaymentUpdateDialogProps {
  visible: boolean;
  onHide: () => void;
  onSubmit: (data: PaymentUpdateFormData) => void;
  loading?: boolean;
}

export const PaymentUpdateDialog = ({
  visible,
  onHide,
  onSubmit,
  loading = false,
}: PaymentUpdateDialogProps) => {
  const {
    control,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<PaymentUpdateFormData>({
    defaultValues: {
      payment_clearing_date: '',
      sap_clearing_doc_no: '',
    },
  });

  useEffect(() => {
    if (visible) {
      reset({
        payment_clearing_date: '',
        sap_clearing_doc_no: '',
      });
    }
  }, [visible, reset]);

  const handleFormSubmit = (data: PaymentUpdateFormData) => {
    onSubmit(data);
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
        label="Update Payment"
        icon="pi pi-check"
        onClick={handleSubmit(handleFormSubmit)}
        loading={loading}
        type="button"
      />
    </div>
  );

  return (
    <Dialog
      header="Update Payment"
      visible={visible}
      onHide={onHide}
      style={{ width: '450px' }}
      footer={footer}
      modal
      aria-label="Update payment dialog"
    >
      <form className="flex flex-column gap-3 pt-2" onSubmit={handleSubmit(handleFormSubmit)}>
        {/* Payment Clearing Date */}
        <div className="flex flex-column gap-1">
          <label htmlFor="payment_clearing_date" className="font-medium">
            Payment Clearing Date <span className="text-red-500">*</span>
          </label>
          <Controller
            name="payment_clearing_date"
            control={control}
            rules={{ required: 'This field is required' }}
            render={({ field }) => (
              <Calendar
                id="payment_clearing_date"
                value={field.value ? new Date(field.value) : null}
                onChange={(e) => {
                  const date = e.value as Date | null;
                  field.onChange(date ? date.toISOString().split('T')[0] : '');
                }}
                dateFormat="yy-mm-dd"
                showIcon
                className={classNames({ 'p-invalid': errors.payment_clearing_date })}
                aria-label="Payment Clearing Date"
              />
            )}
          />
          {errors.payment_clearing_date && (
            <small className="p-error">{errors.payment_clearing_date.message}</small>
          )}
        </div>

        {/* SAP Clearing Document No */}
        <div className="flex flex-column gap-1">
          <label htmlFor="sap_clearing_doc_no" className="font-medium">
            SAP Clearing Document No
          </label>
          <Controller
            name="sap_clearing_doc_no"
            control={control}
            render={({ field }) => (
              <InputText
                id="sap_clearing_doc_no"
                {...field}
                aria-label="SAP Clearing Document Number"
              />
            )}
          />
        </div>
      </form>
    </Dialog>
  );
};

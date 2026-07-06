/**
 * CustomerFormDialog — Create/Edit dialog for Customer Master.
 * Uses React Hook Form + Zod resolver with customerCreateSchema.
 * Includes Customer Type dropdown (PrimeReact Dropdown).
 * Pre-populates fields when in edit mode.
 *
 * Requirements: 4.1, 4.2, 4.3, 4.5
 */

import { useEffect } from 'react';
import { useForm, Controller } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { Dialog } from 'primereact/dialog';
import { InputText } from 'primereact/inputtext';
import { InputTextarea } from 'primereact/inputtextarea';
import { RadioButton } from 'primereact/radiobutton';
import { Button } from 'primereact/button';
import { classNames } from 'primereact/utils';
import { customerCreateSchema, type CustomerCreateFormData } from '../schemas/customerSchema';
import type { Customer } from '../models/customer';

interface CustomerFormDialogProps {
  visible: boolean;
  onHide: () => void;
  onSubmit: (data: CustomerCreateFormData) => void;
  customer?: Customer | null;
  loading?: boolean;
}

export const CustomerFormDialog = ({
  visible,
  onHide,
  onSubmit,
  customer,
  loading = false,
}: CustomerFormDialogProps) => {
  const isEditMode = !!customer;

  const {
    control,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<CustomerCreateFormData>({
    resolver: zodResolver(customerCreateSchema),
    defaultValues: {
      customer_code: '',
      customer_name: '',
      address: '',
      gstn_number: '',
      contact_person: '',
      contact_number: '',
      contact_email: '',
      status: 'Active' as const,
    },
  });

  useEffect(() => {
    if (visible) {
      if (customer) {
        reset({
          customer_code: customer.customer_code,
          customer_name: customer.customer_name,
          address: customer.address ?? '',
          gstn_number: customer.gstn_number ?? '',
          contact_person: customer.contact_person ?? '',
          contact_number: customer.contact_number ?? '',
          contact_email: customer.contact_email ?? '',
          status: customer.status,
        });
      } else {
        reset({
          customer_code: '',
          customer_name: '',
          address: '',
          gstn_number: '',
          contact_person: '',
          contact_number: '',
          contact_email: '',
          status: 'Active',
        });
      }
    }
  }, [visible, customer, reset]);

  const handleFormSubmit = (data: CustomerCreateFormData) => {
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
        label={isEditMode ? 'Update' : 'Create'}
        icon="pi pi-check"
        onClick={handleSubmit(handleFormSubmit)}
        loading={loading}
        type="button"
      />
    </div>
  );

  return (
    <Dialog
      header={isEditMode ? 'Edit Customer' : 'New Customer'}
      visible={visible}
      onHide={onHide}
      style={{ width: '650px' }}
      footer={footer}
      modal
      aria-label={isEditMode ? 'Edit customer dialog' : 'Create customer dialog'}
    >
      <form className="flex flex-column gap-3 pt-2" onSubmit={handleSubmit(handleFormSubmit)}>
        {/* Customer Code */}
        <div className="flex flex-column gap-1">
          <label htmlFor="customer_code" className="font-medium">
            Customer Code <span className="text-red-500">*</span>
          </label>
          <Controller
            name="customer_code"
            control={control}
            render={({ field }) => (
              <InputText
                id="customer_code"
                {...field}
                placeholder="e.g. CUST001"
                className={classNames({ 'p-invalid': errors.customer_code })}
                aria-label="Customer Code"
              />
            )}
          />
          {errors.customer_code && (
            <small className="p-error">{errors.customer_code.message}</small>
          )}
        </div>

        {/* Customer Name */}
        <div className="flex flex-column gap-1">
          <label htmlFor="customer_name" className="font-medium">
            Customer Name <span className="text-red-500">*</span>
          </label>
          <Controller
            name="customer_name"
            control={control}
            render={({ field }) => (
              <InputText
                id="customer_name"
                {...field}
                placeholder="Enter customer name"
                className={classNames({ 'p-invalid': errors.customer_name })}
                aria-label="Customer Name"
              />
            )}
          />
          {errors.customer_name && (
            <small className="p-error">{errors.customer_name.message}</small>
          )}
        </div>

        {/* Address */}
        <div className="flex flex-column gap-1">
          <label htmlFor="address" className="font-medium">Address</label>
          <Controller
            name="address"
            control={control}
            render={({ field }) => (
              <InputTextarea
                id="address"
                {...field}
                rows={2}
                placeholder="Enter full address"
                className={classNames({ 'p-invalid': errors.address })}
                aria-label="Address"
              />
            )}
          />
          {errors.address && (
            <small className="p-error">{errors.address.message}</small>
          )}
        </div>

        {/* GSTN Number */}
        <div className="flex flex-column gap-1">
          <label htmlFor="gstn_number" className="font-medium">GSTN Number</label>
          <Controller
            name="gstn_number"
            control={control}
            render={({ field }) => (
              <InputText
                id="gstn_number"
                {...field}
                placeholder="15 uppercase alphanumeric"
                className={classNames({ 'p-invalid': errors.gstn_number })}
                aria-label="GSTN Number"
              />
            )}
          />
          {errors.gstn_number && (
            <small className="p-error">{errors.gstn_number.message}</small>
          )}
        </div>

        {/* Contact Person */}
        <div className="flex flex-column gap-1">
          <label htmlFor="contact_person" className="font-medium">Contact Person</label>
          <Controller
            name="contact_person"
            control={control}
            render={({ field }) => (
              <InputText
                id="contact_person"
                {...field}
                placeholder="Enter contact person name"
                className={classNames({ 'p-invalid': errors.contact_person })}
                aria-label="Contact Person"
              />
            )}
          />
          {errors.contact_person && (
            <small className="p-error">{errors.contact_person.message}</small>
          )}
        </div>

        {/* Contact Number */}
        <div className="flex flex-column gap-1">
          <label htmlFor="contact_number" className="font-medium">Contact Number</label>
          <Controller
            name="contact_number"
            control={control}
            render={({ field }) => (
              <InputText
                id="contact_number"
                {...field}
                placeholder="e.g. +91 98765 43210"
                className={classNames({ 'p-invalid': errors.contact_number })}
                aria-label="Contact Number"
              />
            )}
          />
          {errors.contact_number && (
            <small className="p-error">{errors.contact_number.message}</small>
          )}
        </div>

        {/* Contact Email */}
        <div className="flex flex-column gap-1">
          <label htmlFor="contact_email" className="font-medium">Contact Email</label>
          <Controller
            name="contact_email"
            control={control}
            render={({ field }) => (
              <InputText
                id="contact_email"
                {...field}
                placeholder="contact@example.com"
                className={classNames({ 'p-invalid': errors.contact_email })}
                aria-label="Contact Email"
              />
            )}
          />
          {errors.contact_email && (
            <small className="p-error">{errors.contact_email.message}</small>
          )}
        </div>

        {/* Status — Active / Inactive radio buttons (edit mode only) */}
        {isEditMode && (
          <div className="flex flex-column gap-1">
            <label className="font-medium">Status</label>
            <Controller
              name="status"
              control={control}
              render={({ field }) => (
                <div className="flex gap-4">
                  <div className="flex align-items-center gap-2">
                    <RadioButton
                      inputId="cust_status_active"
                      value="Active"
                      checked={field.value === 'Active'}
                      onChange={() => field.onChange('Active')}
                    />
                    <label htmlFor="cust_status_active" className="cursor-pointer" style={{ color: 'var(--color-success)', fontWeight: 500 }}>Active</label>
                  </div>
                  <div className="flex align-items-center gap-2">
                    <RadioButton
                      inputId="cust_status_inactive"
                      value="Inactive"
                      checked={field.value === 'Inactive'}
                      onChange={() => field.onChange('Inactive')}
                    />
                    <label htmlFor="cust_status_inactive" className="cursor-pointer" style={{ color: 'var(--color-error)', fontWeight: 500 }}>Inactive</label>
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

export type { CustomerFormDialogProps };

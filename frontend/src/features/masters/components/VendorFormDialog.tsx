/**
 * VendorFormDialog — Create/Edit dialog for Vendor Master.
 * Uses React Hook Form + Zod resolver with vendorCreateSchema.
 * Pre-populates fields when in edit mode.
 *
 * Requirements: 3.3, 3.4, 3.7
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
import { vendorCreateSchema, type VendorCreateFormData } from '../schemas/vendorSchema';
import type { Vendor } from '../models/vendor';

interface VendorFormDialogProps {
  visible: boolean;
  onHide: () => void;
  onSubmit: (data: VendorCreateFormData) => void;
  vendor?: Vendor | null;
  loading?: boolean;
}

export const VendorFormDialog = ({
  visible,
  onHide,
  onSubmit,
  vendor,
  loading = false,
}: VendorFormDialogProps) => {
  const isEditMode = !!vendor;

  const {
    control,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<VendorCreateFormData>({
    resolver: zodResolver(vendorCreateSchema),
    defaultValues: {
      vendor_code: '',
      vendor_name: '',
      vendor_email: '',
      vendor_contact: '',
      vendor_address: '',
      city: '',
      gstn_number: '',
      pan_number: '',
      bank_account_no: '',
      bank_ifsc: '',
      bank_name: '',
    },
  });

  useEffect(() => {
    if (visible) {
      if (vendor) {
        reset({
          vendor_code: vendor.vendor_code,
          vendor_name: vendor.vendor_name,
          vendor_email: vendor.vendor_email,
          vendor_contact: vendor.vendor_contact ?? '',
          vendor_address: vendor.vendor_address ?? '',
          city: vendor.city ?? '',
          gstn_number: vendor.gstn_number ?? '',
          pan_number: vendor.pan_number ?? '',
          bank_account_no: vendor.bank_account_no ?? '',
          bank_ifsc: vendor.bank_ifsc ?? '',
          bank_name: vendor.bank_name ?? '',
          status: vendor.status,
        });
      } else {
        reset({
          vendor_code: '',
          vendor_name: '',
          vendor_email: '',
          vendor_contact: '',
          vendor_address: '',
          city: '',
          gstn_number: '',
          pan_number: '',
          bank_account_no: '',
          bank_ifsc: '',
          bank_name: '',
          status: 'Active',
        });
      }
    }
  }, [visible, vendor, reset]);

  const handleFormSubmit = (data: VendorCreateFormData) => {
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
      header={isEditMode ? 'Edit Vendor' : 'New Vendor'}
      visible={visible}
      onHide={onHide}
      style={{ width: '650px' }}
      footer={footer}
      modal
      aria-label={isEditMode ? 'Edit vendor dialog' : 'Create vendor dialog'}
    >
      <form className="flex flex-column gap-3 pt-2" onSubmit={handleSubmit(handleFormSubmit)}>
        {/* Vendor Code */}
        <div className="flex flex-column gap-1">
          <label htmlFor="vendor_code" className="font-medium">
            Vendor Code <span className="text-red-500">*</span>
          </label>
          <Controller
            name="vendor_code"
            control={control}
            render={({ field }) => (
              <InputText
                id="vendor_code"
                {...field}
                placeholder="e.g. VND001"
                className={classNames({ 'p-invalid': errors.vendor_code })}
                aria-label="Vendor Code"
              />
            )}
          />
          {errors.vendor_code && (
            <small className="p-error">{errors.vendor_code.message}</small>
          )}
        </div>

        {/* Vendor Name */}
        <div className="flex flex-column gap-1">
          <label htmlFor="vendor_name" className="font-medium">
            Vendor Name <span className="text-red-500">*</span>
          </label>
          <Controller
            name="vendor_name"
            control={control}
            render={({ field }) => (
              <InputText
                id="vendor_name"
                {...field}
                placeholder="Enter vendor name"
                className={classNames({ 'p-invalid': errors.vendor_name })}
                aria-label="Vendor Name"
              />
            )}
          />
          {errors.vendor_name && (
            <small className="p-error">{errors.vendor_name.message}</small>
          )}
        </div>

        {/* Vendor Email */}
        <div className="flex flex-column gap-1">
          <label htmlFor="vendor_email" className="font-medium">
            Vendor Email <span className="text-red-500">*</span>
          </label>
          <Controller
            name="vendor_email"
            control={control}
            render={({ field }) => (
              <InputText
                id="vendor_email"
                {...field}
                placeholder="vendor@example.com"
                className={classNames({ 'p-invalid': errors.vendor_email })}
                aria-label="Vendor Email"
              />
            )}
          />
          {errors.vendor_email && (
            <small className="p-error">{errors.vendor_email.message}</small>
          )}
        </div>

        {/* Vendor Contact */}
        <div className="flex flex-column gap-1">
          <label htmlFor="vendor_contact" className="font-medium">Vendor Contact</label>
          <Controller
            name="vendor_contact"
            control={control}
            render={({ field }) => (
              <InputText
                id="vendor_contact"
                {...field}
                placeholder="e.g. +91 98765 43210"
                className={classNames({ 'p-invalid': errors.vendor_contact })}
                aria-label="Vendor Contact"
              />
            )}
          />
          {errors.vendor_contact && (
            <small className="p-error">{errors.vendor_contact.message}</small>
          )}
        </div>

        {/* Vendor Address */}
        <div className="flex flex-column gap-1">
          <label htmlFor="vendor_address" className="font-medium">Vendor Address</label>
          <Controller
            name="vendor_address"
            control={control}
            render={({ field }) => (
              <InputTextarea
                id="vendor_address"
                {...field}
                rows={2}
                placeholder="Enter full address"
                className={classNames({ 'p-invalid': errors.vendor_address })}
                aria-label="Vendor Address"
              />
            )}
          />
          {errors.vendor_address && (
            <small className="p-error">{errors.vendor_address.message}</small>
          )}
        </div>

        {/* City */}
        <div className="flex flex-column gap-1">
          <label htmlFor="city" className="font-medium">City</label>
          <Controller
            name="city"
            control={control}
            render={({ field }) => (
              <InputText
                id="city"
                {...field}
                placeholder="Enter city"
                className={classNames({ 'p-invalid': errors.city })}
                aria-label="City"
              />
            )}
          />
          {errors.city && (
            <small className="p-error">{errors.city.message}</small>
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

        {/* PAN Number */}
        <div className="flex flex-column gap-1">
          <label htmlFor="pan_number" className="font-medium">PAN Number</label>
          <Controller
            name="pan_number"
            control={control}
            render={({ field }) => (
              <InputText
                id="pan_number"
                {...field}
                placeholder="e.g. ABCDE1234F"
                className={classNames({ 'p-invalid': errors.pan_number })}
                aria-label="PAN Number"
              />
            )}
          />
          {errors.pan_number && (
            <small className="p-error">{errors.pan_number.message}</small>
          )}
        </div>

        {/* Bank Account No */}
        <div className="flex flex-column gap-1">
          <label htmlFor="bank_account_no" className="font-medium">Bank Account No</label>
          <Controller
            name="bank_account_no"
            control={control}
            render={({ field }) => (
              <InputText
                id="bank_account_no"
                {...field}
                placeholder="Enter bank account number"
                className={classNames({ 'p-invalid': errors.bank_account_no })}
                aria-label="Bank Account No"
              />
            )}
          />
          {errors.bank_account_no && (
            <small className="p-error">{errors.bank_account_no.message}</small>
          )}
        </div>

        {/* Bank IFSC */}
        <div className="flex flex-column gap-1">
          <label htmlFor="bank_ifsc" className="font-medium">Bank IFSC</label>
          <Controller
            name="bank_ifsc"
            control={control}
            render={({ field }) => (
              <InputText
                id="bank_ifsc"
                {...field}
                placeholder="e.g. HDFC0001234"
                className={classNames({ 'p-invalid': errors.bank_ifsc })}
                aria-label="Bank IFSC"
              />
            )}
          />
          {errors.bank_ifsc && (
            <small className="p-error">{errors.bank_ifsc.message}</small>
          )}
        </div>

        {/* Bank Name */}
        <div className="flex flex-column gap-1">
          <label htmlFor="bank_name" className="font-medium">Bank Name</label>
          <Controller
            name="bank_name"
            control={control}
            render={({ field }) => (
              <InputText
                id="bank_name"
                {...field}
                placeholder="e.g. HDFC Bank"
                className={classNames({ 'p-invalid': errors.bank_name })}
                aria-label="Bank Name"
              />
            )}
          />
          {errors.bank_name && (
            <small className="p-error">{errors.bank_name.message}</small>
          )}
        </div>

        {/* Status — Active / Inactive radio buttons (edit mode only) */}
        {isEditMode && (
          <div className="flex flex-column gap-2">
            <label className="font-medium">Status</label>
            <Controller
              name="status"
              control={control}
              render={({ field }) => (
                <div className="flex gap-4">
                  <div className="flex align-items-center gap-2">
                    <RadioButton
                      inputId="status_active"
                      value="Active"
                      checked={field.value === 'Active'}
                      onChange={() => field.onChange('Active')}
                      aria-label="Active"
                    />
                    <label htmlFor="status_active" className="cursor-pointer" style={{ color: 'var(--color-success)', fontWeight: 500 }}>
                      Active
                    </label>
                  </div>
                  <div className="flex align-items-center gap-2">
                    <RadioButton
                      inputId="status_inactive"
                      value="Inactive"
                      checked={field.value === 'Inactive'}
                      onChange={() => field.onChange('Inactive')}
                      aria-label="Inactive"
                    />
                    <label htmlFor="status_inactive" className="cursor-pointer" style={{ color: 'var(--color-error)', fontWeight: 500 }}>
                      Inactive
                    </label>
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

/** Expose the setError type for external use (422 mapping) */
export type { VendorFormDialogProps };

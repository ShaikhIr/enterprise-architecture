/**
 * MappingFormDialog — Create/Edit dialog for Vendor–Customer Mapping.
 *
 * Create mode: Vendor and Customer dropdowns + Validity From/To date pickers.
 * Edit mode: Vendor and Customer displayed as read-only, only dates editable.
 *
 * Uses React Hook Form + Zod resolver with mappingCreateSchema / mappingUpdateSchema.
 * Dropdown data sourced from useVendors and useCustomers hooks.
 *
 * Requirements: 8.4, 8.5, 8.7, 8.8, 12.1
 */

import { useEffect } from 'react';
import { useForm, Controller } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { Dialog } from 'primereact/dialog';
import { Button } from 'primereact/button';
import { Dropdown } from 'primereact/dropdown';
import { Calendar } from 'primereact/calendar';
import { InputText } from 'primereact/inputtext';
import {
  mappingCreateSchema,
  mappingUpdateSchema,
  type MappingCreateFormData,
  type MappingUpdateFormData,
} from '../schemas/mappingSchema';
import { mapBackendErrors } from '../utils/errorUtils';
import { useVendors } from '../hooks/useVendors';
import { useCustomers } from '../hooks/useCustomers';
import type { VendorCustomerMapping } from '../models/mapping';

interface MappingFormDialogProps {
  visible: boolean;
  onHide: () => void;
  onSubmit: (data: MappingCreateFormData | MappingUpdateFormData) => Promise<void>;
  mapping?: VendorCustomerMapping | null;
  loading?: boolean;
}

export const MappingFormDialog = ({
  visible,
  onHide,
  onSubmit,
  mapping,
  loading = false,
}: MappingFormDialogProps) => {
  const isEditMode = !!mapping;

  // Fetch vendors for dropdown (create mode)
  const { data: vendorsData } = useVendors({ skip: 0, limit: 1000 });

  // Fetch customers for dropdown (create mode)
  const { data: customersData } = useCustomers({ skip: 0, limit: 1000 });

  const vendorOptions = (vendorsData?.items ?? []).map((v) => ({
    label: `${v.vendor_code} - ${v.vendor_name}`,
    value: v.id,
  }));

  const customerOptions = (customersData?.items ?? []).map((c) => ({
    label: `${c.customer_code} - ${c.customer_name}`,
    value: c.id,
  }));

  // Use different schemas for create vs edit
  const {
    handleSubmit,
    reset,
    setError,
    control,
    formState: { errors },
  } = useForm<MappingCreateFormData>({
    resolver: zodResolver(isEditMode ? mappingUpdateSchema : mappingCreateSchema),
    defaultValues: {
      vendor_id: '',
      customer_id: '',
      validity_from: '',
      validity_to: '',
    },
  });

  // Pre-populate form
  useEffect(() => {
    if (visible) {
      if (mapping) {
        // Edit mode — pre-fill dates, vendor/customer IDs (for schema pass-through)
        reset({
          vendor_id: mapping.vendor_id,
          customer_id: mapping.customer_id,
          validity_from: mapping.validity_from,
          validity_to: mapping.validity_to,
        });
      } else {
        reset({
          vendor_id: '',
          customer_id: '',
          validity_from: '',
          validity_to: '',
        });
      }
    }
  }, [visible, mapping, reset]);

  const onFormSubmit = async (data: MappingCreateFormData) => {
    try {
      if (isEditMode) {
        // Only send date fields for update
        const updateData: MappingUpdateFormData = {
          validity_from: data.validity_from,
          validity_to: data.validity_to,
        };
        await onSubmit(updateData);
      } else {
        await onSubmit(data);
      }
    } catch (error: any) {
      const status = error?.response?.status;
      if (status === 422) {
        mapBackendErrors(error, setError);
      }
      // 409 and other errors are handled by the parent (MappingListPage)
    }
  };

  /**
   * Convert ISO date string to Date object for Calendar component.
   */
  const parseDate = (dateStr: string | undefined): Date | null => {
    if (!dateStr) return null;
    const d = new Date(dateStr);
    return isNaN(d.getTime()) ? null : d;
  };

  /**
   * Convert Date object to ISO date string (YYYY-MM-DD).
   */
  const formatDate = (date: Date | null | undefined): string => {
    if (!date) return '';
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
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
      header={isEditMode ? 'Edit Mapping' : 'New Mapping'}
      visible={visible}
      onHide={onHide}
      style={{ width: '550px' }}
      footer={footer}
      modal
      aria-label={isEditMode ? 'Edit mapping dialog' : 'Create mapping dialog'}
    >
      <form className="flex flex-column gap-4 pt-2" onSubmit={handleSubmit(onFormSubmit)}>
        {/* Vendor (dropdown in create, read-only in edit) */}
        <div className="flex flex-column gap-2">
          <label htmlFor="vendor_id" className="font-medium">
            Vendor <span className="text-red-500">*</span>
          </label>
          {isEditMode ? (
            <InputText
              id="vendor_id_display"
              value={mapping?.vendor_name ?? ''}
              disabled
              aria-label="Vendor (read-only)"
            />
          ) : (
            <Controller
              name="vendor_id"
              control={control}
              render={({ field }) => (
                <Dropdown
                  id="vendor_id"
                  value={field.value}
                  onChange={(e) => field.onChange(e.value)}
                  options={vendorOptions}
                  optionLabel="label"
                  optionValue="value"
                  placeholder="Select Vendor"
                  filter
                  className={errors.vendor_id ? 'p-invalid w-full' : 'w-full'}
                  aria-invalid={!!errors.vendor_id}
                  aria-describedby="vendor_id-error"
                />
              )}
            />
          )}
          {errors.vendor_id && (
            <small id="vendor_id-error" className="p-error">
              {errors.vendor_id.message}
            </small>
          )}
        </div>

        {/* Customer (dropdown in create, read-only in edit) */}
        <div className="flex flex-column gap-2">
          <label htmlFor="customer_id" className="font-medium">
            Customer <span className="text-red-500">*</span>
          </label>
          {isEditMode ? (
            <InputText
              id="customer_id_display"
              value={mapping?.customer_name ?? ''}
              disabled
              aria-label="Customer (read-only)"
            />
          ) : (
            <Controller
              name="customer_id"
              control={control}
              render={({ field }) => (
                <Dropdown
                  id="customer_id"
                  value={field.value}
                  onChange={(e) => field.onChange(e.value)}
                  options={customerOptions}
                  optionLabel="label"
                  optionValue="value"
                  placeholder="Select Customer"
                  filter
                  className={errors.customer_id ? 'p-invalid w-full' : 'w-full'}
                  aria-invalid={!!errors.customer_id}
                  aria-describedby="customer_id-error"
                />
              )}
            />
          )}
          {errors.customer_id && (
            <small id="customer_id-error" className="p-error">
              {errors.customer_id.message}
            </small>
          )}
        </div>

        {/* Validity From (date picker) */}
        <div className="flex flex-column gap-2">
          <label htmlFor="validity_from" className="font-medium">
            Validity From <span className="text-red-500">*</span>
          </label>
          <Controller
            name="validity_from"
            control={control}
            render={({ field }) => (
              <Calendar
                id="validity_from"
                value={parseDate(field.value)}
                onChange={(e) => field.onChange(formatDate(e.value as Date | null))}
                dateFormat="yy-mm-dd"
                showIcon
                className={errors.validity_from ? 'p-invalid w-full' : 'w-full'}
                aria-invalid={!!errors.validity_from}
                aria-describedby="validity_from-error"
                placeholder="Select date"
              />
            )}
          />
          {errors.validity_from && (
            <small id="validity_from-error" className="p-error">
              {errors.validity_from.message}
            </small>
          )}
        </div>

        {/* Validity To (date picker) */}
        <div className="flex flex-column gap-2">
          <label htmlFor="validity_to" className="font-medium">
            Validity To <span className="text-red-500">*</span>
          </label>
          <Controller
            name="validity_to"
            control={control}
            render={({ field }) => (
              <Calendar
                id="validity_to"
                value={parseDate(field.value)}
                onChange={(e) => field.onChange(formatDate(e.value as Date | null))}
                dateFormat="yy-mm-dd"
                showIcon
                className={errors.validity_to ? 'p-invalid w-full' : 'w-full'}
                aria-invalid={!!errors.validity_to}
                aria-describedby="validity_to-error"
                placeholder="Select date"
              />
            )}
          />
          {errors.validity_to && (
            <small id="validity_to-error" className="p-error">
              {errors.validity_to.message}
            </small>
          )}
        </div>
      </form>
    </Dialog>
  );
};

export type { MappingFormDialogProps };

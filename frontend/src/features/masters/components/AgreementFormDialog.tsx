/**
 * Agreement Form Dialog.
 * Create/Edit dialog for Agreement Master records.
 * Uses React Hook Form + Zod for validation.
 * Vendor dropdown populated with active vendors.
 * Product Detail dropdown populated with active product details.
 * Includes file upload for agreement document (PDF/JPEG/PNG, max 10 MB).
 * Shows CommissionSlabInfo panel within the form.
 *
 * Requirements: 7.4, 7.5, 7.9, 12.1, 12.5
 */

import { useEffect, useRef } from 'react';
import { useForm, Controller } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { Dialog } from 'primereact/dialog';
import { Button } from 'primereact/button';
import { InputNumber } from 'primereact/inputnumber';
import { Dropdown } from 'primereact/dropdown';
import { Calendar } from 'primereact/calendar';
import { FileUpload, type FileUploadHandlerEvent } from 'primereact/fileupload';
import { agreementCreateSchema, type AgreementCreateFormData } from '../schemas/agreementSchema';
import { mapBackendErrors } from '../utils/errorUtils';
import { useVendors } from '../hooks/useVendors';
import { useProductMasters } from '../hooks/useProductMasters';
import { CommissionSlabInfo } from './CommissionSlabInfo';
import type { Agreement } from '../models/agreement';

interface AgreementFormDialogProps {
  visible: boolean;
  onHide: () => void;
  agreement: Agreement | null; // null = create mode, Agreement = edit mode
  onSubmit: (data: AgreementCreateFormData) => Promise<void>;
  loading: boolean;
}

export const AgreementFormDialog = ({
  visible,
  onHide,
  agreement,
  onSubmit,
  loading,
}: AgreementFormDialogProps) => {
  const isEditMode = agreement !== null;
  const fileUploadRef = useRef<FileUpload>(null);

  const {
    handleSubmit,
    reset,
    setError,
    control,
    setValue,
    formState: { errors },
  } = useForm<AgreementCreateFormData>({
    resolver: zodResolver(agreementCreateSchema),
    defaultValues: {
      vendor_id: '',
      product_master_id: '',
      from_date: '',
      to_date: '',
      slab_in_days: 1,
      reduction_percent: 0,
      max_commission_percent: 0,
      min_commission_percent: 0,
      credit_days: 0,
      agreement_document: undefined,
    },
  });

  // Fetch active vendors for dropdown
  const { data: vendorsData } = useVendors({ skip: 0, limit: 1000 });
  const vendorOptions = (vendorsData?.items ?? []).map((v) => ({
    label: `${v.vendor_code} - ${v.vendor_name}`,
    value: v.id,
  }));

  // Fetch active product masters for dropdown
  const { data: productDetailsData } = useProductMasters({ skip: 0, limit: 1000 });
  const productDetailOptions = (productDetailsData?.items ?? []).map((pd) => ({
    label: `${pd.child_code} - ${pd.product_name}`,
    value: pd.id,
  }));

  // Pre-populate form when editing
  useEffect(() => {
    if (visible) {
      if (agreement) {
        reset({
          vendor_id: agreement.vendor_id,
          product_master_id: agreement.product_master_id,
          from_date: agreement.from_date,
          to_date: agreement.to_date,
          slab_in_days: agreement.slab_in_days,
          reduction_percent: agreement.reduction_percent,
          max_commission_percent: agreement.max_commission_percent,
          min_commission_percent: agreement.min_commission_percent,
          credit_days: agreement.credit_days,
          agreement_document: undefined,
        });
      } else {
        reset({
          vendor_id: '',
          product_master_id: '',
          from_date: '',
          to_date: '',
          slab_in_days: 1,
          reduction_percent: 0,
          max_commission_percent: 0,
          min_commission_percent: 0,
          credit_days: 0,
          agreement_document: undefined,
        });
      }
      // Clear file upload state
      fileUploadRef.current?.clear();
    }
  }, [visible, agreement, reset]);

  const handleFileSelect = (e: FileUploadHandlerEvent) => {
    const file = e.files?.[0];
    if (file) {
      setValue('agreement_document', file, { shouldValidate: true });
    }
  };

  const onFormSubmit = async (data: AgreementCreateFormData) => {
    try {
      await onSubmit(data);
    } catch (error: any) {
      const status = error?.response?.status;
      if (status === 422) {
        mapBackendErrors(error, setError);
      }
    }
  };

  /**
   * InputNumber fires onValueChange with e.value = null when cleared.
   * This helper converts null → the provided fallback so Zod never receives null.
   */
  const handleNumberChange = (onChange: (v: number) => void, fallback = 0) =>
    (e: { value: number | null | undefined }) =>
      onChange(e.value ?? fallback);

  const parseDate = (dateStr: string): Date | null => {
    if (!dateStr) return null;
    const d = new Date(dateStr);
    return isNaN(d.getTime()) ? null : d;
  };

  const formatDate = (date: Date | null): string => {
    if (!date) return '';
    return date.toISOString().split('T')[0] ?? '';
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
      header={isEditMode ? 'Edit Agreement' : 'New Agreement'}
      visible={visible}
      onHide={onHide}
      style={{ width: '700px' }}
      footer={footer}
      modal
      aria-label={isEditMode ? 'Edit agreement dialog' : 'Create agreement dialog'}
    >
      <form className="flex flex-column gap-4 pt-2" onSubmit={handleSubmit(onFormSubmit)}>
        {/* Commission Slab Info */}
        <CommissionSlabInfo />

        {/* Vendor (required dropdown) */}
        <div className="flex flex-column gap-2">
          <label htmlFor="vendor_id" className="font-medium">
            Vendor <span className="text-red-500">*</span>
          </label>
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
          {errors.vendor_id && (
            <small id="vendor_id-error" className="p-error">
              {errors.vendor_id.message}
            </small>
          )}
        </div>

        {/* Product Detail (required dropdown) */}
        <div className="flex flex-column gap-2">
          <label htmlFor="product_master_id" className="font-medium">
            Product Detail <span className="text-red-500">*</span>
          </label>
          <Controller
            name="product_master_id"
            control={control}
            render={({ field }) => (
              <Dropdown
                id="product_master_id"
                value={field.value}
                onChange={(e) => field.onChange(e.value)}
                options={productDetailOptions}
                optionLabel="label"
                optionValue="value"
                placeholder="Select Product Detail"
                filter
                className={errors.product_master_id ? 'p-invalid w-full' : 'w-full'}
                aria-invalid={!!errors.product_master_id}
                aria-describedby="product_master_id-error"
              />
            )}
          />
          {errors.product_master_id && (
            <small id="product_master_id-error" className="p-error">
              {errors.product_master_id.message}
            </small>
          )}
        </div>

        {/* Date fields row */}
        <div className="grid">
          {/* From Date */}
          <div className="col-6">
            <div className="flex flex-column gap-2">
              <label htmlFor="from_date" className="font-medium">
                From Date <span className="text-red-500">*</span>
              </label>
              <Controller
                name="from_date"
                control={control}
                render={({ field }) => (
                  <Calendar
                    id="from_date"
                    value={parseDate(field.value)}
                    onChange={(e) => field.onChange(formatDate(e.value as Date | null))}
                    dateFormat="yy-mm-dd"
                    showIcon
                    className={errors.from_date ? 'p-invalid w-full' : 'w-full'}
                    aria-invalid={!!errors.from_date}
                    aria-describedby="from_date-error"
                  />
                )}
              />
              {errors.from_date && (
                <small id="from_date-error" className="p-error">
                  {errors.from_date.message}
                </small>
              )}
            </div>
          </div>

          {/* To Date */}
          <div className="col-6">
            <div className="flex flex-column gap-2">
              <label htmlFor="to_date" className="font-medium">
                To Date <span className="text-red-500">*</span>
              </label>
              <Controller
                name="to_date"
                control={control}
                render={({ field }) => (
                  <Calendar
                    id="to_date"
                    value={parseDate(field.value)}
                    onChange={(e) => field.onChange(formatDate(e.value as Date | null))}
                    dateFormat="yy-mm-dd"
                    showIcon
                    className={errors.to_date ? 'p-invalid w-full' : 'w-full'}
                    aria-invalid={!!errors.to_date}
                    aria-describedby="to_date-error"
                  />
                )}
              />
              {errors.to_date && (
                <small id="to_date-error" className="p-error">
                  {errors.to_date.message}
                </small>
              )}
            </div>
          </div>
        </div>

        {/* Slab in Days and Reduction % row */}
        <div className="grid">
          <div className="col-6">
            <div className="flex flex-column gap-2">
              <label htmlFor="slab_in_days" className="font-medium">
                Slab in Days <span className="text-red-500">*</span>
              </label>
              <Controller
                name="slab_in_days"
                control={control}
                render={({ field }) => (
                  <InputNumber
                    id="slab_in_days"
                    value={field.value ?? null}
                    onValueChange={handleNumberChange(field.onChange, 1)}
                    min={1}
                    useGrouping={false}
                    className={errors.slab_in_days ? 'p-invalid w-full' : 'w-full'}
                    aria-invalid={!!errors.slab_in_days}
                    aria-describedby="slab_in_days-error"
                  />
                )}
              />
              {errors.slab_in_days && (
                <small id="slab_in_days-error" className="p-error">
                  {errors.slab_in_days.message}
                </small>
              )}
            </div>
          </div>

          <div className="col-6">
            <div className="flex flex-column gap-2">
              <label htmlFor="reduction_percent" className="font-medium">
                Reduction % <span className="text-red-500">*</span>
              </label>
              <Controller
                name="reduction_percent"
                control={control}
                render={({ field }) => (
                  <InputNumber
                    id="reduction_percent"
                    value={field.value ?? null}
                    onValueChange={handleNumberChange(field.onChange, 0)}
                    mode="decimal"
                    minFractionDigits={0}
                    maxFractionDigits={2}
                    min={0}
                    max={100}
                    suffix="%"
                    className={errors.reduction_percent ? 'p-invalid w-full' : 'w-full'}
                    aria-invalid={!!errors.reduction_percent}
                    aria-describedby="reduction_percent-error"
                  />
                )}
              />
              {errors.reduction_percent && (
                <small id="reduction_percent-error" className="p-error">
                  {errors.reduction_percent.message}
                </small>
              )}
            </div>
          </div>
        </div>

        {/* Max Commission % and Min Commission % row */}
        <div className="grid">
          <div className="col-6">
            <div className="flex flex-column gap-2">
              <label htmlFor="max_commission_percent" className="font-medium">
                Max Commission % <span className="text-red-500">*</span>
              </label>
              <Controller
                name="max_commission_percent"
                control={control}
                render={({ field }) => (
                  <InputNumber
                    id="max_commission_percent"
                    value={field.value ?? null}
                    onValueChange={handleNumberChange(field.onChange, 0)}
                    mode="decimal"
                    minFractionDigits={0}
                    maxFractionDigits={2}
                    min={0}
                    max={100}
                    suffix="%"
                    className={errors.max_commission_percent ? 'p-invalid w-full' : 'w-full'}
                    aria-invalid={!!errors.max_commission_percent}
                    aria-describedby="max_commission_percent-error"
                  />
                )}
              />
              {errors.max_commission_percent && (
                <small id="max_commission_percent-error" className="p-error">
                  {errors.max_commission_percent.message}
                </small>
              )}
            </div>
          </div>

          <div className="col-6">
            <div className="flex flex-column gap-2">
              <label htmlFor="min_commission_percent" className="font-medium">
                Min Commission % <span className="text-red-500">*</span>
              </label>
              <Controller
                name="min_commission_percent"
                control={control}
                render={({ field }) => (
                  <InputNumber
                    id="min_commission_percent"
                    value={field.value ?? null}
                    onValueChange={handleNumberChange(field.onChange, 0)}
                    mode="decimal"
                    minFractionDigits={0}
                    maxFractionDigits={2}
                    min={0}
                    max={100}
                    suffix="%"
                    className={errors.min_commission_percent ? 'p-invalid w-full' : 'w-full'}
                    aria-invalid={!!errors.min_commission_percent}
                    aria-describedby="min_commission_percent-error"
                  />
                )}
              />
              {errors.min_commission_percent && (
                <small id="min_commission_percent-error" className="p-error">
                  {errors.min_commission_percent.message}
                </small>
              )}
            </div>
          </div>
        </div>

        {/* Credit Days */}
        <div className="flex flex-column gap-2">
          <label htmlFor="credit_days" className="font-medium">
            Credit Days <span className="text-red-500">*</span>
          </label>
          <Controller
            name="credit_days"
            control={control}
            render={({ field }) => (
              <InputNumber
                id="credit_days"
                value={field.value ?? null}
                onValueChange={handleNumberChange(field.onChange, 0)}
                min={0}
                useGrouping={false}
                className={errors.credit_days ? 'p-invalid w-full' : 'w-full'}
                aria-invalid={!!errors.credit_days}
                aria-describedby="credit_days-error"
              />
            )}
          />
          {errors.credit_days && (
            <small id="credit_days-error" className="p-error">
              {errors.credit_days.message}
            </small>
          )}
        </div>

        {/* Agreement Document (optional file upload) */}
        <div className="flex flex-column gap-2">
          <label className="font-medium">
            Agreement Document <span className="text-500">(optional, PDF/JPEG/PNG, max 10 MB)</span>
          </label>
          <FileUpload
            ref={fileUploadRef}
            mode="basic"
            accept=".pdf,.jpeg,.jpg,.png"
            maxFileSize={10 * 1024 * 1024}
            customUpload
            uploadHandler={handleFileSelect}
            auto
            chooseLabel="Choose File"
            className={errors.agreement_document ? 'p-invalid' : ''}
            aria-label="Upload agreement document"
          />
          {errors.agreement_document && (
            <small className="p-error">
              {(errors.agreement_document as any).message}
            </small>
          )}
        </div>
      </form>
    </Dialog>
  );
};

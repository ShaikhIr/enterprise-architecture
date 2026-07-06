/**
 * Agreement Renewal Dialog.
 * Renewal dialog for existing Agreement records.
 * Vendor and Product Detail are shown as read-only from the original agreement.
 * The user sets new From Date, To Date, Slab in Days, Reduction %, Max/Min Commission %, Credit Days.
 * Uses React Hook Form + Zod for validation.
 *
 * Requirements: 7.7, 7.8, 7.9
 */

import { useEffect, useRef } from 'react';
import { useForm, Controller } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { Dialog } from 'primereact/dialog';
import { Button } from 'primereact/button';
import { InputText } from 'primereact/inputtext';
import { InputNumber } from 'primereact/inputnumber';
import { Calendar } from 'primereact/calendar';
import { FileUpload, type FileUploadHandlerEvent } from 'primereact/fileupload';
import { agreementCreateSchema, type AgreementCreateFormData } from '../schemas/agreementSchema';
import { mapBackendErrors } from '../utils/errorUtils';
import { CommissionSlabInfo } from './CommissionSlabInfo';
import type { Agreement } from '../models/agreement';

interface AgreementRenewalDialogProps {
  visible: boolean;
  onHide: () => void;
  agreement: Agreement | null; // The active agreement being renewed
  onSubmit: (data: AgreementCreateFormData) => Promise<void>;
  loading: boolean;
}

export const AgreementRenewalDialog = ({
  visible,
  onHide,
  agreement,
  onSubmit,
  loading,
}: AgreementRenewalDialogProps) => {
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
      product_detail_id: '',
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

  // Pre-populate form with original agreement data (vendor/product read-only)
  useEffect(() => {
    if (visible && agreement) {
      reset({
        vendor_id: agreement.vendor_id,
        product_detail_id: agreement.product_detail_id,
        from_date: '',
        to_date: '',
        slab_in_days: agreement.slab_in_days,
        reduction_percent: agreement.reduction_percent,
        max_commission_percent: agreement.max_commission_percent,
        min_commission_percent: agreement.min_commission_percent,
        credit_days: agreement.credit_days,
        agreement_document: undefined,
      });
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
        label="Renew"
        icon="pi pi-refresh"
        onClick={handleSubmit(onFormSubmit)}
        loading={loading}
        type="submit"
      />
    </div>
  );

  return (
    <Dialog
      header="Renew Agreement"
      visible={visible}
      onHide={onHide}
      style={{ width: '700px' }}
      footer={footer}
      modal
      aria-label="Renew agreement dialog"
    >
      <form className="flex flex-column gap-4 pt-2" onSubmit={handleSubmit(onFormSubmit)}>
        {/* Commission Slab Info */}
        <CommissionSlabInfo />

        {/* Vendor (read-only) */}
        <div className="flex flex-column gap-2">
          <label htmlFor="renewal_vendor" className="font-medium">
            Vendor
          </label>
          <InputText
            id="renewal_vendor"
            value={agreement ? `${agreement.vendor_name}` : ''}
            disabled
            className="w-full"
            aria-label="Vendor (read-only)"
          />
        </div>

        {/* Product Detail (read-only) */}
        <div className="flex flex-column gap-2">
          <label htmlFor="renewal_product_detail" className="font-medium">
            Product Detail
          </label>
          <InputText
            id="renewal_product_detail"
            value={agreement ? `${agreement.product_detail_child_code} - ${agreement.product_detail_name}` : ''}
            disabled
            className="w-full"
            aria-label="Product Detail (read-only)"
          />
        </div>

        {/* Date fields row */}
        <div className="grid">
          {/* From Date */}
          <div className="col-6">
            <div className="flex flex-column gap-2">
              <label htmlFor="renewal_from_date" className="font-medium">
                From Date <span className="text-red-500">*</span>
              </label>
              <Controller
                name="from_date"
                control={control}
                render={({ field }) => (
                  <Calendar
                    id="renewal_from_date"
                    value={parseDate(field.value)}
                    onChange={(e) => field.onChange(formatDate(e.value as Date | null))}
                    dateFormat="yy-mm-dd"
                    showIcon
                    className={errors.from_date ? 'p-invalid w-full' : 'w-full'}
                    aria-invalid={!!errors.from_date}
                    aria-describedby="renewal_from_date-error"
                  />
                )}
              />
              {errors.from_date && (
                <small id="renewal_from_date-error" className="p-error">
                  {errors.from_date.message}
                </small>
              )}
            </div>
          </div>

          {/* To Date */}
          <div className="col-6">
            <div className="flex flex-column gap-2">
              <label htmlFor="renewal_to_date" className="font-medium">
                To Date <span className="text-red-500">*</span>
              </label>
              <Controller
                name="to_date"
                control={control}
                render={({ field }) => (
                  <Calendar
                    id="renewal_to_date"
                    value={parseDate(field.value)}
                    onChange={(e) => field.onChange(formatDate(e.value as Date | null))}
                    dateFormat="yy-mm-dd"
                    showIcon
                    className={errors.to_date ? 'p-invalid w-full' : 'w-full'}
                    aria-invalid={!!errors.to_date}
                    aria-describedby="renewal_to_date-error"
                  />
                )}
              />
              {errors.to_date && (
                <small id="renewal_to_date-error" className="p-error">
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
              <label htmlFor="renewal_slab_in_days" className="font-medium">
                Slab in Days <span className="text-red-500">*</span>
              </label>
              <Controller
                name="slab_in_days"
                control={control}
                render={({ field }) => (
                  <InputNumber
                    id="renewal_slab_in_days"
                    value={field.value ?? null}
                    onValueChange={(e) => field.onChange(e.value ?? undefined)}
                    min={1}
                    useGrouping={false}
                    className={errors.slab_in_days ? 'p-invalid w-full' : 'w-full'}
                    aria-invalid={!!errors.slab_in_days}
                    aria-describedby="renewal_slab_in_days-error"
                  />
                )}
              />
              {errors.slab_in_days && (
                <small id="renewal_slab_in_days-error" className="p-error">
                  {errors.slab_in_days.message}
                </small>
              )}
            </div>
          </div>

          <div className="col-6">
            <div className="flex flex-column gap-2">
              <label htmlFor="renewal_reduction_percent" className="font-medium">
                Reduction % <span className="text-red-500">*</span>
              </label>
              <Controller
                name="reduction_percent"
                control={control}
                render={({ field }) => (
                  <InputNumber
                    id="renewal_reduction_percent"
                    value={field.value ?? null}
                    onValueChange={(e) => field.onChange(e.value ?? undefined)}
                    mode="decimal"
                    minFractionDigits={0}
                    maxFractionDigits={2}
                    min={0}
                    max={100}
                    suffix="%"
                    className={errors.reduction_percent ? 'p-invalid w-full' : 'w-full'}
                    aria-invalid={!!errors.reduction_percent}
                    aria-describedby="renewal_reduction_percent-error"
                  />
                )}
              />
              {errors.reduction_percent && (
                <small id="renewal_reduction_percent-error" className="p-error">
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
              <label htmlFor="renewal_max_commission_percent" className="font-medium">
                Max Commission % <span className="text-red-500">*</span>
              </label>
              <Controller
                name="max_commission_percent"
                control={control}
                render={({ field }) => (
                  <InputNumber
                    id="renewal_max_commission_percent"
                    value={field.value ?? null}
                    onValueChange={(e) => field.onChange(e.value ?? undefined)}
                    mode="decimal"
                    minFractionDigits={0}
                    maxFractionDigits={2}
                    min={0}
                    max={100}
                    suffix="%"
                    className={errors.max_commission_percent ? 'p-invalid w-full' : 'w-full'}
                    aria-invalid={!!errors.max_commission_percent}
                    aria-describedby="renewal_max_commission_percent-error"
                  />
                )}
              />
              {errors.max_commission_percent && (
                <small id="renewal_max_commission_percent-error" className="p-error">
                  {errors.max_commission_percent.message}
                </small>
              )}
            </div>
          </div>

          <div className="col-6">
            <div className="flex flex-column gap-2">
              <label htmlFor="renewal_min_commission_percent" className="font-medium">
                Min Commission % <span className="text-red-500">*</span>
              </label>
              <Controller
                name="min_commission_percent"
                control={control}
                render={({ field }) => (
                  <InputNumber
                    id="renewal_min_commission_percent"
                    value={field.value ?? null}
                    onValueChange={(e) => field.onChange(e.value ?? undefined)}
                    mode="decimal"
                    minFractionDigits={0}
                    maxFractionDigits={2}
                    min={0}
                    max={100}
                    suffix="%"
                    className={errors.min_commission_percent ? 'p-invalid w-full' : 'w-full'}
                    aria-invalid={!!errors.min_commission_percent}
                    aria-describedby="renewal_min_commission_percent-error"
                  />
                )}
              />
              {errors.min_commission_percent && (
                <small id="renewal_min_commission_percent-error" className="p-error">
                  {errors.min_commission_percent.message}
                </small>
              )}
            </div>
          </div>
        </div>

        {/* Credit Days */}
        <div className="flex flex-column gap-2">
          <label htmlFor="renewal_credit_days" className="font-medium">
            Credit Days <span className="text-red-500">*</span>
          </label>
          <Controller
            name="credit_days"
            control={control}
            render={({ field }) => (
              <InputNumber
                id="renewal_credit_days"
                value={field.value ?? null}
                onValueChange={(e) => field.onChange(e.value ?? undefined)}
                min={0}
                useGrouping={false}
                className={errors.credit_days ? 'p-invalid w-full' : 'w-full'}
                aria-invalid={!!errors.credit_days}
                aria-describedby="renewal_credit_days-error"
              />
            )}
          />
          {errors.credit_days && (
            <small id="renewal_credit_days-error" className="p-error">
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

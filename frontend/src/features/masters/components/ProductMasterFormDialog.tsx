/**
 * Product Master Form Dialog.
 * Create/Edit dialog for the merged Product Master records.
 * Carries both base-product identity fields (basic_material_code, product_name)
 * and SKU/variant fields (child_code, hsn_code, etc.).
 * Uses React Hook Form + Zod for validation.
 * Child Code is read-only in edit mode.
 */

import { useEffect } from 'react';
import { useForm, Controller } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { Dialog } from 'primereact/dialog';
import { Button } from 'primereact/button';
import { InputText } from 'primereact/inputtext';
import { InputNumber } from 'primereact/inputnumber';
import { RadioButton } from 'primereact/radiobutton';
import { productMasterCreateSchema, type ProductMasterCreateFormData } from '../schemas/productMasterSchema';
import { mapBackendErrors } from '../utils/errorUtils';
import type { ProductMaster } from '../models/productMaster';

interface ProductMasterFormDialogProps {
  visible: boolean;
  onHide: () => void;
  productMaster: ProductMaster | null; // null = create mode
  onSubmit: (data: ProductMasterCreateFormData) => Promise<void>;
  loading: boolean;
}

export const ProductMasterFormDialog = ({
  visible,
  onHide,
  productMaster,
  onSubmit,
  loading,
}: ProductMasterFormDialogProps) => {
  const isEditMode = productMaster !== null;

  const {
    register,
    handleSubmit,
    reset,
    setError,
    control,
    formState: { errors },
  } = useForm<ProductMasterCreateFormData>({
    resolver: zodResolver(productMasterCreateSchema),
    defaultValues: {
      basic_material_code: '',
      product_name: '',
      child_code: '',
      variant_description: '',
      hsn_code: '',
      pack_size: '',
      unit_of_measure: '',
      mrp: undefined,
      rate: undefined,
      gst_percent: undefined,
      status: 'Active',
    },
  });

  useEffect(() => {
    if (visible) {
      if (productMaster) {
        reset({
          basic_material_code: productMaster.basic_material_code,
          product_name: productMaster.product_name,
          child_code: productMaster.child_code,
          variant_description: productMaster.variant_description ?? '',
          hsn_code: productMaster.hsn_code ?? '',
          pack_size: productMaster.pack_size ?? '',
          unit_of_measure: productMaster.unit_of_measure ?? '',
          mrp: productMaster.mrp ?? undefined,
          rate: productMaster.rate ?? undefined,
          gst_percent: productMaster.gst_percent ?? undefined,
          status: productMaster.status,
        });
      } else {
        reset({
          basic_material_code: '',
          product_name: '',
          child_code: '',
          variant_description: '',
          hsn_code: '',
          pack_size: '',
          unit_of_measure: '',
          mrp: undefined,
          rate: undefined,
          gst_percent: undefined,
          status: 'Active',
        });
      }
    }
  }, [visible, productMaster, reset]);

  const onFormSubmit = async (data: ProductMasterCreateFormData) => {
    try {
      await onSubmit(data);
    } catch (error: any) {
      if (error?.response?.status === 422) {
        mapBackendErrors(error, setError);
      }
    }
  };

  const footer = (
    <div className="flex justify-content-end gap-2">
      <Button label="Cancel" icon="pi pi-times" severity="secondary" outlined onClick={onHide} type="button" />
      <Button label={isEditMode ? 'Update' : 'Create'} icon="pi pi-check" onClick={handleSubmit(onFormSubmit)} loading={loading} type="submit" />
    </div>
  );

  return (
    <Dialog
      header={isEditMode ? 'Edit Product Master' : 'New Product Master'}
      visible={visible}
      onHide={onHide}
      style={{ width: '600px' }}
      footer={footer}
      modal
      aria-label={isEditMode ? 'Edit product master dialog' : 'Create product master dialog'}
    >
      <form className="flex flex-column gap-4 pt-2" onSubmit={handleSubmit(onFormSubmit)}>

        {/* Basic Material Code (required) */}
        <div className="flex flex-column gap-2">
          <label htmlFor="basic_material_code" className="font-medium">
            Basic Material Code <span className="text-red-500">*</span>
          </label>
          <InputText
            id="basic_material_code"
            {...register('basic_material_code')}
            className={errors.basic_material_code ? 'p-invalid' : ''}
            aria-invalid={!!errors.basic_material_code}
            aria-describedby="basic_material_code-error"
          />
          {errors.basic_material_code && (
            <small id="basic_material_code-error" className="p-error">{errors.basic_material_code.message}</small>
          )}
        </div>

        {/* Product Name (required) */}
        <div className="flex flex-column gap-2">
          <label htmlFor="product_name" className="font-medium">
            Product Name <span className="text-red-500">*</span>
          </label>
          <InputText
            id="product_name"
            {...register('product_name')}
            className={errors.product_name ? 'p-invalid' : ''}
            aria-invalid={!!errors.product_name}
            aria-describedby="product_name-error"
          />
          {errors.product_name && (
            <small id="product_name-error" className="p-error">{errors.product_name.message}</small>
          )}
        </div>

        {/* Child Code (required, read-only on edit) */}
        <div className="flex flex-column gap-2">
          <label htmlFor="child_code" className="font-medium">
            Child Code <span className="text-red-500">*</span>
          </label>
          <InputText
            id="child_code"
            {...register('child_code')}
            disabled={isEditMode}
            className={errors.child_code ? 'p-invalid' : ''}
            aria-invalid={!!errors.child_code}
            aria-describedby="child_code-error"
          />
          {errors.child_code && (
            <small id="child_code-error" className="p-error">{errors.child_code.message}</small>
          )}
        </div>

        {/* Variant Description (optional) */}
        <div className="flex flex-column gap-2">
          <label htmlFor="variant_description" className="font-medium">Variant Description</label>
          <InputText
            id="variant_description"
            {...register('variant_description')}
            className={errors.variant_description ? 'p-invalid' : ''}
            aria-invalid={!!errors.variant_description}
            aria-describedby="variant_description-error"
          />
          {errors.variant_description && (
            <small id="variant_description-error" className="p-error">{errors.variant_description.message}</small>
          )}
        </div>

        {/* HSN Code (optional) */}
        <div className="flex flex-column gap-2">
          <label htmlFor="hsn_code" className="font-medium">HSN Code</label>
          <InputText
            id="hsn_code"
            {...register('hsn_code')}
            className={errors.hsn_code ? 'p-invalid' : ''}
            aria-invalid={!!errors.hsn_code}
            aria-describedby="hsn_code-error"
          />
          {errors.hsn_code && (
            <small id="hsn_code-error" className="p-error">{errors.hsn_code.message}</small>
          )}
        </div>

        {/* Pack Size (optional) */}
        <div className="flex flex-column gap-2">
          <label htmlFor="pack_size" className="font-medium">Pack Size</label>
          <InputText
            id="pack_size"
            {...register('pack_size')}
            className={errors.pack_size ? 'p-invalid' : ''}
            aria-invalid={!!errors.pack_size}
            aria-describedby="pack_size-error"
          />
          {errors.pack_size && (
            <small id="pack_size-error" className="p-error">{errors.pack_size.message}</small>
          )}
        </div>

        {/* Unit of Measure (optional) */}
        <div className="flex flex-column gap-2">
          <label htmlFor="unit_of_measure" className="font-medium">Unit of Measure</label>
          <InputText
            id="unit_of_measure"
            {...register('unit_of_measure')}
            className={errors.unit_of_measure ? 'p-invalid' : ''}
            aria-invalid={!!errors.unit_of_measure}
            aria-describedby="unit_of_measure-error"
          />
          {errors.unit_of_measure && (
            <small id="unit_of_measure-error" className="p-error">{errors.unit_of_measure.message}</small>
          )}
        </div>

        {/* MRP (numeric, optional) */}
        <div className="flex flex-column gap-2">
          <label htmlFor="mrp" className="font-medium">MRP</label>
          <Controller
            name="mrp"
            control={control}
            render={({ field }) => (
              <InputNumber
                id="mrp"
                value={field.value ?? null}
                onValueChange={(e) => field.onChange(e.value ?? undefined)}
                mode="decimal"
                minFractionDigits={0}
                maxFractionDigits={2}
                min={0}
                max={999999999.99}
                className={errors.mrp ? 'p-invalid w-full' : 'w-full'}
                aria-invalid={!!errors.mrp}
                aria-describedby="mrp-error"
              />
            )}
          />
          {errors.mrp && <small id="mrp-error" className="p-error">{errors.mrp.message}</small>}
        </div>

        {/* Rate (numeric, optional) */}
        <div className="flex flex-column gap-2">
          <label htmlFor="rate" className="font-medium">Rate</label>
          <Controller
            name="rate"
            control={control}
            render={({ field }) => (
              <InputNumber
                id="rate"
                value={field.value ?? null}
                onValueChange={(e) => field.onChange(e.value ?? undefined)}
                mode="decimal"
                minFractionDigits={0}
                maxFractionDigits={2}
                min={0}
                max={999999999.99}
                className={errors.rate ? 'p-invalid w-full' : 'w-full'}
                aria-invalid={!!errors.rate}
                aria-describedby="rate-error"
              />
            )}
          />
          {errors.rate && <small id="rate-error" className="p-error">{errors.rate.message}</small>}
        </div>

        {/* GST % (numeric, optional) */}
        <div className="flex flex-column gap-2">
          <label htmlFor="gst_percent" className="font-medium">GST %</label>
          <Controller
            name="gst_percent"
            control={control}
            render={({ field }) => (
              <InputNumber
                id="gst_percent"
                value={field.value ?? null}
                onValueChange={(e) => field.onChange(e.value ?? undefined)}
                mode="decimal"
                minFractionDigits={0}
                maxFractionDigits={2}
                min={0}
                max={100}
                suffix="%"
                className={errors.gst_percent ? 'p-invalid w-full' : 'w-full'}
                aria-invalid={!!errors.gst_percent}
                aria-describedby="gst_percent-error"
              />
            )}
          />
          {errors.gst_percent && <small id="gst_percent-error" className="p-error">{errors.gst_percent.message}</small>}
        </div>

        {/* Status (edit mode only) */}
        {isEditMode && (
          <div className="flex flex-column gap-2">
            <label className="font-medium">Status</label>
            <Controller
              name="status"
              control={control}
              render={({ field }) => (
                <div className="flex gap-4">
                  <div className="flex align-items-center gap-2">
                    <RadioButton inputId="pm_status_active" value="Active" checked={field.value === 'Active'} onChange={() => field.onChange('Active')} />
                    <label htmlFor="pm_status_active" className="cursor-pointer" style={{ color: 'var(--color-success)', fontWeight: 500 }}>Active</label>
                  </div>
                  <div className="flex align-items-center gap-2">
                    <RadioButton inputId="pm_status_inactive" value="Inactive" checked={field.value === 'Inactive'} onChange={() => field.onChange('Inactive')} />
                    <label htmlFor="pm_status_inactive" className="cursor-pointer" style={{ color: 'var(--color-error)', fontWeight: 500 }}>Inactive</label>
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

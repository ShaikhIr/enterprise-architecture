/**
 * InvoiceLineItems — Dynamic line items section for invoice creation form.
 * Each line includes: Product Detail dropdown, Quantity, Line Amount, VAT/GST Amount.
 * Supports add/remove operations.
 *
 * Requirements: 9.3, 9.5
 */

import { useFieldArray, Controller, type Control, type FieldErrors } from 'react-hook-form';
import { Dropdown } from 'primereact/dropdown';
import { InputNumber } from 'primereact/inputnumber';
import { Button } from 'primereact/button';
import { classNames } from 'primereact/utils';
import { useProductMasters } from '../hooks/useProductMasters';
import type { InvoiceCreateFormData } from '../schemas/invoiceSchema';

interface InvoiceLineItemsProps {
  control: Control<InvoiceCreateFormData>;
  errors: FieldErrors<InvoiceCreateFormData>;
}

export const InvoiceLineItems = ({ control, errors }: InvoiceLineItemsProps) => {
  const { fields, append, remove } = useFieldArray({
    control,
    name: 'lines',
  });

  // Fetch product masters for dropdown (load all for selection)
  const { data: productDetailData, isLoading: loadingProducts } = useProductMasters({
    skip: 0,
    limit: 500,
  });

  const productOptions = (productDetailData?.items ?? []).map((pd) => ({
    label: `${pd.child_code} - ${pd.variant_description ?? pd.product_name}`,
    value: pd.id,
  }));

  const handleAddLine = () => {
    append({ product_detail_id: '', quantity: undefined, line_amount: undefined, vat_gst_amount: undefined });
  };

  return (
    <div className="flex flex-column gap-3">
      <div className="flex align-items-center justify-content-between">
        <label className="font-medium text-lg">Line Items</label>
        <Button
          type="button"
          label="Add Line"
          icon="pi pi-plus"
          size="small"
          outlined
          onClick={handleAddLine}
          aria-label="Add line item"
        />
      </div>

      {errors.lines && !Array.isArray(errors.lines) && (
        <small className="p-error">{errors.lines.message}</small>
      )}

      {fields.map((field, index) => (
        /* #7 – Use a CSS grid so all columns sit on the same row without overlap */
        <div
          key={field.id}
          style={{
            display: 'grid',
            gridTemplateColumns: '1fr 110px 140px 140px 44px',
            gap: '8px',
            alignItems: 'end',
            padding: '12px',
            background: 'var(--color-neutral-50)',
            borderRadius: 'var(--radius-md)',
            border: '1px solid var(--color-neutral-200)',
          }}
        >
          {/* Product Detail */}
          <div className="flex flex-column gap-1">
            <label className="font-medium text-sm">
              Product Detail <span className="text-red-500">*</span>
            </label>
            <Controller
              name={`lines.${index}.product_detail_id`}
              control={control}
              render={({ field: f }) => (
                <Dropdown
                  id={`line_product_${index}`}
                  value={f.value}
                  onChange={(e) => f.onChange(e.value)}
                  options={productOptions}
                  placeholder="Select product..."
                  filter
                  filterPlaceholder="Search products..."
                  loading={loadingProducts}
                  className={classNames('w-full', { 'p-invalid': errors.lines?.[index]?.product_detail_id })}
                  aria-label={`Line ${index + 1} Product Detail`}
                />
              )}
            />
            {errors.lines?.[index]?.product_detail_id && (
              <small className="p-error">{errors.lines[index]?.product_detail_id?.message}</small>
            )}
          </div>

          {/* Quantity */}
          <div className="flex flex-column gap-1">
            <label className="font-medium text-sm">Quantity</label>
            <Controller
              name={`lines.${index}.quantity`}
              control={control}
              render={({ field: f }) => (
                <InputNumber
                  id={`line_quantity_${index}`}
                  value={f.value ?? null}
                  onValueChange={(e) => f.onChange(e.value)}
                  min={0}
                  placeholder="0"
                  className={classNames({ 'p-invalid': errors.lines?.[index]?.quantity })}
                  aria-label={`Line ${index + 1} Quantity`}
                />
              )}
            />
          </div>

          {/* Line Amount */}
          <div className="flex flex-column gap-1">
            <label className="font-medium text-sm">Line Amount</label>
            <Controller
              name={`lines.${index}.line_amount`}
              control={control}
              render={({ field: f }) => (
                <InputNumber
                  id={`line_amount_${index}`}
                  value={f.value ?? null}
                  onValueChange={(e) => f.onChange(e.value)}
                  mode="decimal"
                  minFractionDigits={2}
                  maxFractionDigits={2}
                  placeholder="0.00"
                  className={classNames({ 'p-invalid': errors.lines?.[index]?.line_amount })}
                  aria-label={`Line ${index + 1} Line Amount`}
                />
              )}
            />
          </div>

          {/* VAT/GST Amount */}
          <div className="flex flex-column gap-1">
            <label className="font-medium text-sm">VAT/GST Amount</label>
            <Controller
              name={`lines.${index}.vat_gst_amount`}
              control={control}
              render={({ field: f }) => (
                <InputNumber
                  id={`line_vat_${index}`}
                  value={f.value ?? null}
                  onValueChange={(e) => f.onChange(e.value)}
                  mode="decimal"
                  minFractionDigits={2}
                  maxFractionDigits={2}
                  placeholder="0.00"
                  className={classNames({ 'p-invalid': errors.lines?.[index]?.vat_gst_amount })}
                  aria-label={`Line ${index + 1} VAT/GST Amount`}
                />
              )}
            />
          </div>

          {/* Remove button — #8: clear danger color, labelled tooltip */}
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', paddingTop: '20px' }}>
            <Button
              type="button"
              icon="pi pi-minus-circle"
              severity="danger"
              text
              rounded
              onClick={() => remove(index)}
              disabled={fields.length <= 1}
              aria-label={`Remove line item ${index + 1}`}
              tooltip="Remove line"
              tooltipOptions={{ position: 'top' }}
              style={{ color: '#dc2626', opacity: fields.length <= 1 ? 0.4 : 1 }}
            />
          </div>
        </div>
      ))}

      {fields.length === 0 && (
        <div className="text-center text-500 py-3 surface-50 border-round">
          No line items added. Click "Add Line" to add one.
        </div>
      )}
    </div>
  );
};

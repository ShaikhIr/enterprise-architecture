/**
 * InvoiceForm — Creation form for Invoice Master.
 * Header fields: Invoice Number, Invoice Date, Vendor, Customer, Bill Amount excl. GST,
 * Bill Amount incl. Tax, Amount Deducted, TDS Value.
 * Uses React Hook Form + Zod (invoiceCreateSchema) and includes InvoiceLineItems as child.
 *
 * Requirements: 9.1, 9.2, 9.3, 9.4, 9.5
 */

import { useEffect } from 'react';
import { useForm, Controller } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { Dialog } from 'primereact/dialog';
import { InputText } from 'primereact/inputtext';
import { InputNumber } from 'primereact/inputnumber';
import { Calendar } from 'primereact/calendar';
import { Dropdown } from 'primereact/dropdown';
import { Button } from 'primereact/button';
import { classNames } from 'primereact/utils';
import { invoiceCreateSchema, type InvoiceCreateFormData } from '../schemas/invoiceSchema';
import { useVendors } from '../hooks/useVendors';
import { useCustomers } from '../hooks/useCustomers';
import { useEntityDropdown } from '../hooks/useEntities';
import { InvoiceLineItems } from './InvoiceLineItems';

interface InvoiceFormProps {
  visible: boolean;
  onHide: () => void;
  onSubmit: (data: InvoiceCreateFormData) => void;
  loading?: boolean;
}

export const InvoiceForm = ({
  visible,
  onHide,
  onSubmit,
  loading = false,
}: InvoiceFormProps) => {
  const {
    control,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<InvoiceCreateFormData>({
    resolver: zodResolver(invoiceCreateSchema),
    defaultValues: {
      invoice_number: '',
      invoice_date: '',
      vendor_id: '',
      customer_id: '',
      entity_id: '',
      bill_amount_excl_gst: undefined as unknown as number,
      bill_amount_incl_tax: undefined,
      amount_deducted: 0,
      tds_value: 0,
      lines: [{ product_master_id: '', quantity: undefined, line_amount: undefined, vat_gst_amount: undefined }],
    },
  });

  // Fetch vendors and customers for dropdowns
  const { data: vendorData, isLoading: loadingVendors } = useVendors({ skip: 0, limit: 500 });
  const { data: customerData, isLoading: loadingCustomers } = useCustomers({ skip: 0, limit: 500 });
  const { data: entityDropdown, isLoading: loadingEntities } = useEntityDropdown();

  const vendorOptions = (vendorData?.items ?? []).map((v) => ({
    label: `${v.vendor_code} - ${v.vendor_name}`,
    value: v.id,
  }));

  const customerOptions = (customerData?.items ?? []).map((c) => ({
    label: `${c.customer_code} - ${c.customer_name}`,
    value: c.id,
  }));

  const entityOptions = (entityDropdown ?? []).map((item) => ({
    label: item.label,
    value: item.id,
  }));

  useEffect(() => {
    if (visible) {
      reset({
        invoice_number: '',
        invoice_date: '',
        vendor_id: '',
        customer_id: '',
        entity_id: '',
        bill_amount_excl_gst: undefined as unknown as number,
        bill_amount_incl_tax: undefined,
        amount_deducted: 0,
        tds_value: 0,
        lines: [{ product_master_id: '', quantity: undefined, line_amount: undefined, vat_gst_amount: undefined }],
      });
    }
  }, [visible, reset]);

  const handleFormSubmit = (data: InvoiceCreateFormData) => {
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
        label="Create"
        icon="pi pi-check"
        onClick={handleSubmit(handleFormSubmit)}
        loading={loading}
        type="button"
      />
    </div>
  );

  return (
    <Dialog
      header="New Invoice"
      visible={visible}
      onHide={onHide}
      style={{ width: '800px' }}
      footer={footer}
      modal
      aria-label="Create invoice dialog"
    >
      <form className="flex flex-column gap-3 pt-2" onSubmit={handleSubmit(handleFormSubmit)}>
        <div className="grid">
          {/* Invoice Number */}
          <div className="col-12 md:col-6 flex flex-column gap-1">
            <label htmlFor="invoice_number" className="font-medium">
              Invoice Number <span className="text-red-500">*</span>
            </label>
            <Controller
              name="invoice_number"
              control={control}
              render={({ field }) => (
                <InputText
                  id="invoice_number"
                  {...field}
                  placeholder="e.g. INV-2024-001"
                  className={classNames({ 'p-invalid': errors.invoice_number })}
                  aria-label="Invoice Number"
                />
              )}
            />
            {errors.invoice_number && (
              <small className="p-error">{errors.invoice_number.message}</small>
            )}
          </div>

          {/* Invoice Date */}
          <div className="col-12 md:col-6 flex flex-column gap-1">
            <label htmlFor="invoice_date" className="font-medium">
              Invoice Date <span className="text-red-500">*</span>
            </label>
            <Controller
              name="invoice_date"
              control={control}
              render={({ field }) => (
                <Calendar
                  id="invoice_date"
                  value={field.value ? new Date(field.value) : null}
                  onChange={(e) => {
                    const date = e.value as Date | null;
                    field.onChange(date ? date.toISOString().split('T')[0] : '');
                  }}
                  dateFormat="yy-mm-dd"
                  showIcon
                  className={classNames({ 'p-invalid': errors.invoice_date })}
                  aria-label="Invoice Date"
                />
              )}
            />
            {errors.invoice_date && (
              <small className="p-error">{errors.invoice_date.message}</small>
            )}
          </div>

          {/* Vendor */}
          <div className="col-12 md:col-6 flex flex-column gap-1">
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
                  placeholder="Select vendor..."
                  filter
                  filterPlaceholder="Search vendors..."
                  loading={loadingVendors}
                  className={classNames('w-full', { 'p-invalid': errors.vendor_id })}
                  aria-label="Vendor"
                />
              )}
            />
            {errors.vendor_id && (
              <small className="p-error">{errors.vendor_id.message}</small>
            )}
          </div>

          {/* Customer */}
          <div className="col-12 md:col-6 flex flex-column gap-1">
            <label htmlFor="customer_id" className="font-medium">
              Customer <span className="text-red-500">*</span>
            </label>
            <Controller
              name="customer_id"
              control={control}
              render={({ field }) => (
                <Dropdown
                  id="customer_id"
                  value={field.value}
                  onChange={(e) => field.onChange(e.value)}
                  options={customerOptions}
                  placeholder="Select customer..."
                  filter
                  filterPlaceholder="Search customers..."
                  loading={loadingCustomers}
                  className={classNames('w-full', { 'p-invalid': errors.customer_id })}
                  aria-label="Customer"
                />
              )}
            />
            {errors.customer_id && (
              <small className="p-error">{errors.customer_id.message}</small>
            )}
          </div>

          {/* Company / Entity */}
          <div className="col-12 md:col-6 flex flex-column gap-1">
            <label htmlFor="entity_id" className="font-medium">
              Company <span className="text-red-500">*</span>
            </label>
            <Controller
              name="entity_id"
              control={control}
              render={({ field }) => (
                <Dropdown
                  id="entity_id"
                  value={field.value}
                  onChange={(e) => field.onChange(e.value)}
                  options={entityOptions}
                  placeholder={loadingEntities ? 'Loading...' : 'Select company...'}
                  filter
                  filterPlaceholder="Search companies..."
                  loading={loadingEntities}
                  className={classNames('w-full', { 'p-invalid': errors.entity_id })}
                  aria-label="Company"
                />
              )}
            />
            {errors.entity_id && (
              <small className="p-error">{errors.entity_id.message}</small>
            )}
          </div>

          {/* Bill Amount excl. GST */}
          <div className="col-12 md:col-6 flex flex-column gap-1">
            <label htmlFor="bill_amount_excl_gst" className="font-medium">
              Bill Amount excl. GST <span className="text-red-500">*</span>
            </label>
            <Controller
              name="bill_amount_excl_gst"
              control={control}
              render={({ field }) => (
                <InputNumber
                  id="bill_amount_excl_gst"
                  value={field.value ?? null}
                  onValueChange={(e) => field.onChange(e.value)}
                  mode="decimal"
                  minFractionDigits={2}
                  maxFractionDigits={2}
                  className={classNames({ 'p-invalid': errors.bill_amount_excl_gst })}
                  aria-label="Bill Amount excluding GST"
                />
              )}
            />
            {errors.bill_amount_excl_gst && (
              <small className="p-error">{errors.bill_amount_excl_gst.message}</small>
            )}
          </div>

          {/* Bill Amount incl. Tax */}
          <div className="col-12 md:col-6 flex flex-column gap-1">
            <label htmlFor="bill_amount_incl_tax" className="font-medium">
              Bill Amount incl. Tax
            </label>
            <Controller
              name="bill_amount_incl_tax"
              control={control}
              render={({ field }) => (
                <InputNumber
                  id="bill_amount_incl_tax"
                  value={field.value ?? null}
                  onValueChange={(e) => field.onChange(e.value)}
                  mode="decimal"
                  minFractionDigits={2}
                  maxFractionDigits={2}
                  aria-label="Bill Amount including Tax"
                />
              )}
            />
          </div>

          {/* Amount Deducted */}
          <div className="col-12 md:col-6 flex flex-column gap-1">
            <label htmlFor="amount_deducted" className="font-medium">Amount Deducted</label>
            <Controller
              name="amount_deducted"
              control={control}
              render={({ field }) => (
                <InputNumber
                  id="amount_deducted"
                  value={field.value ?? 0}
                  onValueChange={(e) => field.onChange(e.value ?? 0)}
                  mode="decimal"
                  minFractionDigits={2}
                  maxFractionDigits={2}
                  aria-label="Amount Deducted"
                />
              )}
            />
          </div>

          {/* TDS Value */}
          <div className="col-12 md:col-6 flex flex-column gap-1">
            <label htmlFor="tds_value" className="font-medium">TDS Value</label>
            <Controller
              name="tds_value"
              control={control}
              render={({ field }) => (
                <InputNumber
                  id="tds_value"
                  value={field.value ?? 0}
                  onValueChange={(e) => field.onChange(e.value ?? 0)}
                  mode="decimal"
                  minFractionDigits={2}
                  maxFractionDigits={2}
                  aria-label="TDS Value"
                />
              )}
            />
          </div>
        </div>

        {/* Line Items */}
        <InvoiceLineItems control={control} errors={errors} />
      </form>
    </Dialog>
  );
};

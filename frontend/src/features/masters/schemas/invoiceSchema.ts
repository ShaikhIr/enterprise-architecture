import { z } from 'zod';

const invoiceLineSchema = z.object({
  product_detail_id: z.string().min(1, 'Product is required'),
  quantity: z.number().optional(),
  line_amount: z.number().optional(),
  vat_gst_amount: z.number().optional(),
});

export const invoiceCreateSchema = z.object({
  invoice_number: z.string().min(1, 'This field is required'),
  invoice_date: z.string().min(1, 'This field is required'),
  vendor_id: z.string().min(1, 'Vendor is required'),
  customer_id: z.string().min(1, 'Customer is required'),
  bill_amount_excl_gst: z.number().positive('Must be a positive number'),
  bill_amount_incl_tax: z.number().optional(),
  amount_deducted: z.number().optional(),
  tds_value: z.number().optional(),
  lines: z.array(invoiceLineSchema).min(1, 'At least one line item is required'),
});

export type InvoiceCreateFormData = z.infer<typeof invoiceCreateSchema>;

import { z } from 'zod';

export const vendorCreateSchema = z.object({
  vendor_code: z.string().min(1, 'This field is required').max(50),
  vendor_name: z.string().min(1, 'This field is required').max(200),
  vendor_email: z.string().min(1, 'This field is required').email('Must be a valid email').max(254),
  vendor_contact: z.string().max(20).optional().or(z.literal('')),
  vendor_address: z.string().optional().or(z.literal('')),
  city: z.string().max(100).optional().or(z.literal('')),
  gstn_number: z.string().regex(/^[A-Z0-9]{15}$/, 'Must be 15 alphanumeric characters').optional().or(z.literal('')),
  pan_number: z.string().max(10).optional().or(z.literal('')),
  bank_account_no: z.string().max(30).optional().or(z.literal('')),
  bank_ifsc: z.string().max(11).optional().or(z.literal('')),
  bank_name: z.string().max(100).optional().or(z.literal('')),
  status: z.enum(['Active', 'Inactive']).optional(),
});

export type VendorCreateFormData = z.infer<typeof vendorCreateSchema>;

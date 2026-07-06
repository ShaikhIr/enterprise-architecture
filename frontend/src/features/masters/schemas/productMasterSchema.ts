import { z } from 'zod';

export const productMasterCreateSchema = z.object({
  basic_material_code: z.string().min(1, 'This field is required').max(50),
  product_name: z.string().min(1, 'This field is required').max(255),
  child_code: z.string().min(1, 'This field is required').max(50),
  variant_description: z.string().max(200).optional().or(z.literal('')),
  hsn_code: z.string().max(20).optional().or(z.literal('')),
  pack_size: z.string().max(50).optional().or(z.literal('')),
  unit_of_measure: z.string().max(20).optional().or(z.literal('')),
  mrp: z.number().min(0).max(999999999.99).optional().or(z.literal(undefined)),
  rate: z.number().min(0).max(999999999.99).optional().or(z.literal(undefined)),
  gst_percent: z.number().min(0).max(100).optional().or(z.literal(undefined)),
  status: z.enum(['Active', 'Inactive']).optional(),
});

export type ProductMasterCreateFormData = z.infer<typeof productMasterCreateSchema>;

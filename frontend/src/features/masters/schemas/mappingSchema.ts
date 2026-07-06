import { z } from 'zod';

export const mappingCreateSchema = z.object({
  vendor_id: z.string().min(1, 'This field is required'),
  customer_id: z.string().min(1, 'This field is required'),
  validity_from: z.string().min(1, 'This field is required'),
  validity_to: z.string().min(1, 'This field is required'),
}).refine((data) => data.validity_from <= data.validity_to, {
  message: 'Validity From must be on or before Validity To',
  path: ['validity_to'],
});

export type MappingCreateFormData = z.infer<typeof mappingCreateSchema>;

export const mappingUpdateSchema = z.object({
  validity_from: z.string().min(1, 'This field is required'),
  validity_to: z.string().min(1, 'This field is required'),
}).refine((data) => data.validity_from <= data.validity_to, {
  message: 'Validity From must be on or before Validity To',
  path: ['validity_to'],
});

export type MappingUpdateFormData = z.infer<typeof mappingUpdateSchema>;

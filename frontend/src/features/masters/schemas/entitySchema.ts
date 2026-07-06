import { z } from 'zod';

export const entityCreateSchema = z.object({
  entity_name: z.string().min(1, 'This field is required').max(255),
  short_code: z.string().max(50).optional().or(z.literal('')),
  company_code: z.string().max(50).optional().or(z.literal('')),
  is_active: z.boolean().optional(),
});

export type EntityCreateFormData = z.infer<typeof entityCreateSchema>;

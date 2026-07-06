import { z } from 'zod';

export const customerCreateSchema = z.object({
  customer_code: z.string().min(1, 'This field is required').max(50),
  customer_name: z.string().min(1, 'This field is required').max(255),
  address: z.string().optional().or(z.literal('')),
  gstn_number: z.string().regex(/^[A-Z0-9]{15}$/, 'Must be 15 alphanumeric characters').optional().or(z.literal('')),
  contact_person: z.string().max(100).optional().or(z.literal('')),
  contact_number: z.string().max(20).optional().or(z.literal('')),
  contact_email: z.string().email('Must be a valid email').max(255).optional().or(z.literal('')),
  status: z.enum(['Active', 'Inactive']).optional(),
});

export type CustomerCreateFormData = z.infer<typeof customerCreateSchema>;

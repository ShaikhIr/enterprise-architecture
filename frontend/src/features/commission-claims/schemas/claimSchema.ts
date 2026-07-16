import { z } from 'zod';

export const addLineSchema = z.object({
  invoice_id: z.string().uuid('Please select a valid invoice'),
  due_date_override: z.string().nullable().optional(),
  ld_charges: z.number().min(0).default(0),
  retention_amount: z.number().min(0).default(0),
  remarks: z.string().default(''),
});

export const workflowActionSchema = z.object({
  remarks: z.string().min(1, 'Remarks are required'),
});

export const sapBookingSchema = z.object({
  sap_p2p_booking_reference: z.string().min(1, 'SAP booking reference is required'),
});

export const misFilterSchema = z.object({
  vendor_id: z.string().uuid().nullable().optional(),
  claim_number: z.string().nullable().optional(),
  start_date: z.string().nullable().optional(),
  end_date: z.string().nullable().optional(),
});

export type AddLineFormData = z.infer<typeof addLineSchema>;
export type WorkflowActionFormData = z.infer<typeof workflowActionSchema>;
export type SAPBookingFormData = z.infer<typeof sapBookingSchema>;
export type MISFilterFormData = z.infer<typeof misFilterSchema>;

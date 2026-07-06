import { z } from 'zod';

const MAX_FILE_SIZE = 10 * 1024 * 1024; // 10 MB
const ACCEPTED_FILE_TYPES = ['application/pdf', 'image/jpeg', 'image/png'];

/**
 * Coerce a value that may arrive as a numeric string from the backend API
 * (FastAPI serialises Decimal fields as strings, e.g. "5.00") into a JS number,
 * then apply the numeric rules. This prevents Zod's z.number() from rejecting
 * pre-populated edit-mode values that come back from the server as strings.
 */
const numericField = z.union([z.string(), z.number()]).transform((v) => {
  const n = typeof v === 'string' ? parseFloat(v) : v;
  return isNaN(n) ? 0 : n;
});

export const agreementCreateSchema = z.object({
  vendor_id: z.string().min(1, 'This field is required'),
  product_detail_id: z.string().min(1, 'This field is required'),
  from_date: z.string().min(1, 'This field is required'),
  to_date: z.string().min(1, 'This field is required'),
  slab_in_days: numericField
    .pipe(z.number().int('Must be a whole number').min(1, 'Must be at least 1')),
  reduction_percent: numericField
    .pipe(z.number().min(0, 'Must be at least 0').max(100, 'Must be at most 100')),
  max_commission_percent: numericField
    .pipe(z.number().min(0, 'Must be at least 0').max(100, 'Must be at most 100')),
  min_commission_percent: numericField
    .pipe(z.number().min(0, 'Must be at least 0').max(100, 'Must be at most 100')),
  credit_days: numericField
    .pipe(z.number().int('Must be a whole number').min(0, 'Must be at least 0')),
  agreement_document: z
    .instanceof(File)
    .refine((file) => file.size <= MAX_FILE_SIZE, 'File size must not exceed 10 MB')
    .refine(
      (file) => ACCEPTED_FILE_TYPES.includes(file.type),
      'Only PDF, JPEG, and PNG files are accepted',
    )
    .optional(),
}).refine((data) => data.from_date <= data.to_date, {
  message: 'From Date must be on or before To Date',
  path: ['to_date'],
}).refine((data) => data.min_commission_percent <= data.max_commission_percent, {
  message: 'Min Commission must be ≤ Max Commission',
  path: ['min_commission_percent'],
});

export type AgreementCreateFormData = z.infer<typeof agreementCreateSchema>;

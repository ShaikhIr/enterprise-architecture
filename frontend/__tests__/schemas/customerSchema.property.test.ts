/**
 * Customer Schema — Property-Based Tests
 *
 * Uses Vitest + fast-check to verify universal correctness invariants
 * for the customerCreateSchema Zod validation.
 *
 * **Validates: Requirements 4.4**
 */

import * as fc from 'fast-check';
import { describe, it, expect } from 'vitest';
import { customerCreateSchema } from '../../src/features/masters/schemas/customerSchema';

const CUSTOMER_TYPES = ['Government Medical Corporation', 'Hospital', 'Pharmacy', 'Institution', 'Other'] as const;

const ALPHANUM_UPPER = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'.split('');
const ALPHANUM_LOWER = 'abcdefghijklmnopqrstuvwxyz0123456789'.split('');
const ALPHA_LOWER = 'abcdefghijklmnopqrstuvwxyz'.split('');

/**
 * Arbitraries for generating valid field values
 */
const validCustomerCode = fc.string({ minLength: 1, maxLength: 50 }).filter((s) => s.trim().length > 0);
const validCustomerName = fc.string({ minLength: 1, maxLength: 255 }).filter((s) => s.trim().length > 0);
const validGstn = fc.array(fc.constantFrom(...ALPHANUM_UPPER), { minLength: 15, maxLength: 15 }).map((arr) => arr.join(''));
const validEmail = fc.tuple(
  fc.array(fc.constantFrom(...ALPHANUM_LOWER), { minLength: 1, maxLength: 20 }).map((a) => a.join('')),
  fc.array(fc.constantFrom(...ALPHA_LOWER), { minLength: 2, maxLength: 10 }).map((a) => a.join('')),
).map(([local, domain]) => `${local}@${domain}.com`);
const validContactPerson = fc.string({ minLength: 0, maxLength: 100 });
const validContactNumber = fc.string({ minLength: 0, maxLength: 20 });
const validCustomerType = fc.constantFrom(...CUSTOMER_TYPES);

describe('Customer Schema — Property Tests', () => {
  /**
   * Property 4: Customer schema validation — code, GSTN, and email constraints
   *
   * For any string inputs for Customer create form fields, the Zod schema SHALL
   * accept the input if and only if: customer_code is non-empty and ≤ 50 characters,
   * customer_name is non-empty and ≤ 255 characters, gstn_number (if provided) matches
   * `[A-Z0-9]{15}`, contact_email (if provided) is valid email format and ≤ 255 characters,
   * contact_number (if provided) is ≤ 20 characters, and contact_person (if provided) is
   * ≤ 100 characters.
   *
   * **Validates: Requirements 4.4**
   */

  it('accepts valid customer data with all optional fields provided', () => {
    fc.assert(
      fc.property(
        validCustomerCode,
        validCustomerName,
        validCustomerType,
        validGstn,
        validEmail,
        validContactPerson,
        validContactNumber,
        (code, name, type, gstn, email, person, number) => {
          const data = {
            customer_code: code,
            customer_name: name,
            customer_type: type,
            gstn_number: gstn,
            contact_email: email,
            contact_person: person,
            contact_number: number,
          };
          const result = customerCreateSchema.safeParse(data);
          expect(result.success).toBe(true);
        },
      ),
      { numRuns: 100 },
    );
  });

  it('accepts valid customer data with optional fields as empty strings', () => {
    fc.assert(
      fc.property(validCustomerCode, validCustomerName, (code, name) => {
        const data = {
          customer_code: code,
          customer_name: name,
          gstn_number: '',
          contact_email: '',
          contact_person: '',
          contact_number: '',
        };
        const result = customerCreateSchema.safeParse(data);
        expect(result.success).toBe(true);
      }),
      { numRuns: 100 },
    );
  });

  it('accepts valid customer data with optional fields omitted', () => {
    fc.assert(
      fc.property(validCustomerCode, validCustomerName, (code, name) => {
        const data = {
          customer_code: code,
          customer_name: name,
        };
        const result = customerCreateSchema.safeParse(data);
        expect(result.success).toBe(true);
      }),
      { numRuns: 100 },
    );
  });

  it('rejects empty customer_code', () => {
    fc.assert(
      fc.property(validCustomerName, (name) => {
        const data = {
          customer_code: '',
          customer_name: name,
        };
        const result = customerCreateSchema.safeParse(data);
        expect(result.success).toBe(false);
      }),
      { numRuns: 100 },
    );
  });

  it('rejects customer_code exceeding 50 characters', () => {
    fc.assert(
      fc.property(
        fc.string({ minLength: 51, maxLength: 100 }),
        validCustomerName,
        (code, name) => {
          const data = {
            customer_code: code,
            customer_name: name,
          };
          const result = customerCreateSchema.safeParse(data);
          expect(result.success).toBe(false);
        },
      ),
      { numRuns: 100 },
    );
  });

  it('rejects empty customer_name', () => {
    fc.assert(
      fc.property(validCustomerCode, (code) => {
        const data = {
          customer_code: code,
          customer_name: '',
        };
        const result = customerCreateSchema.safeParse(data);
        expect(result.success).toBe(false);
      }),
      { numRuns: 100 },
    );
  });

  it('rejects customer_name exceeding 255 characters', () => {
    fc.assert(
      fc.property(
        validCustomerCode,
        fc.string({ minLength: 256, maxLength: 300 }),
        (code, name) => {
          const data = {
            customer_code: code,
            customer_name: name,
          };
          const result = customerCreateSchema.safeParse(data);
          expect(result.success).toBe(false);
        },
      ),
      { numRuns: 100 },
    );
  });

  it('rejects invalid GSTN pattern (wrong length or lowercase)', () => {
    fc.assert(
      fc.property(
        validCustomerCode,
        validCustomerName,
        fc.oneof(
          // Too short
          fc.array(fc.constantFrom(...ALPHANUM_UPPER), { minLength: 1, maxLength: 14 }).map((a) => a.join('')),
          // Too long
          fc.array(fc.constantFrom(...ALPHANUM_UPPER), { minLength: 16, maxLength: 20 }).map((a) => a.join('')),
          // Correct length but contains lowercase
          fc.array(fc.constantFrom(...ALPHANUM_LOWER), { minLength: 15, maxLength: 15 }).map((a) => a.join('')),
        ),
        (code, name, gstn) => {
          const data = {
            customer_code: code,
            customer_name: name,
            gstn_number: gstn,
          };
          const result = customerCreateSchema.safeParse(data);
          expect(result.success).toBe(false);
        },
      ),
      { numRuns: 100 },
    );
  });

  it('rejects invalid email format when provided', () => {
    fc.assert(
      fc.property(
        validCustomerCode,
        validCustomerName,
        // Generate strings that are clearly not emails (no @ sign)
        fc.string({ minLength: 1, maxLength: 50 }).filter((s) => !s.includes('@') && s.length > 0),
        (code, name, email) => {
          const data = {
            customer_code: code,
            customer_name: name,
            contact_email: email,
          };
          const result = customerCreateSchema.safeParse(data);
          expect(result.success).toBe(false);
        },
      ),
      { numRuns: 100 },
    );
  });

  it('rejects contact_person exceeding 100 characters', () => {
    fc.assert(
      fc.property(
        validCustomerCode,
        validCustomerName,
        fc.string({ minLength: 101, maxLength: 150 }),
        (code, name, person) => {
          const data = {
            customer_code: code,
            customer_name: name,
            contact_person: person,
          };
          const result = customerCreateSchema.safeParse(data);
          expect(result.success).toBe(false);
        },
      ),
      { numRuns: 100 },
    );
  });

  it('rejects contact_number exceeding 20 characters', () => {
    fc.assert(
      fc.property(
        validCustomerCode,
        validCustomerName,
        fc.string({ minLength: 21, maxLength: 50 }),
        (code, name, number) => {
          const data = {
            customer_code: code,
            customer_name: name,
            contact_number: number,
          };
          const result = customerCreateSchema.safeParse(data);
          expect(result.success).toBe(false);
        },
      ),
      { numRuns: 100 },
    );
  });
});

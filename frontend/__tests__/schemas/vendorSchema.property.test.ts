/**
 * Vendor Schema — Property-Based Test
 *
 * Uses Vitest + fast-check to verify that the vendorCreateSchema Zod schema
 * accepts valid vendor form data and rejects invalid data, matching the defined
 * constraints for all fields.
 *
 * **Validates: Requirements 3.4**
 */

import * as fc from 'fast-check';
import { describe, it, expect } from 'vitest';
import { vendorCreateSchema } from '../../src/features/masters/schemas/vendorSchema';

/**
 * Arbitraries for generating valid data
 */

// Valid non-empty string up to maxLen
const nonEmptyString = (maxLen: number) =>
  fc.string({ minLength: 1, maxLength: maxLen }).filter((s) => s.trim().length > 0);

// Valid email arbitrary — generates structurally valid emails within max length
const validEmail = () =>
  fc
    .tuple(
      fc.stringMatching(/^[a-z][a-z0-9]{0,19}$/),
      fc.stringMatching(/^[a-z][a-z0-9]{0,9}$/),
      fc.constantFrom('com', 'org', 'net', 'io', 'co')
    )
    .map(([local, domain, tld]) => `${local}@${domain}.${tld}`)
    .filter((email) => email.length <= 254 && email.length >= 5);

// Valid GSTN: exactly 15 uppercase alphanumeric chars
const validGstn = () => fc.stringMatching(/^[A-Z0-9]{15}$/);

// Optional field: either empty string or valid string within max length
const optionalString = (maxLen: number) =>
  fc.oneof(fc.constant(''), fc.constant(undefined), fc.string({ minLength: 1, maxLength: maxLen }));

describe('Property 3: Vendor schema validation — patterns and format constraints', () => {
  /**
   * Sub-property 3a: Schema accepts all valid vendor form data
   *
   * For any generated data that satisfies all constraints, the schema must accept it.
   */
  it('accepts valid vendor form data with all fields within constraints', () => {
    fc.assert(
      fc.property(
        fc.record({
          vendor_code: nonEmptyString(50),
          vendor_name: nonEmptyString(200),
          vendor_email: validEmail(),
          vendor_contact: fc.oneof(fc.constant(''), fc.constant(undefined), fc.string({ minLength: 1, maxLength: 20 })),
          vendor_address: fc.oneof(fc.constant(''), fc.constant(undefined), fc.string({ minLength: 1, maxLength: 100 })),
          gstn_number: fc.oneof(fc.constant(''), fc.constant(undefined), validGstn()),
          pan_number: fc.oneof(fc.constant(''), fc.constant(undefined), fc.string({ minLength: 1, maxLength: 10 })),
          bank_account_no: fc.oneof(fc.constant(''), fc.constant(undefined), fc.string({ minLength: 1, maxLength: 30 })),
          bank_ifsc: fc.oneof(fc.constant(''), fc.constant(undefined), fc.string({ minLength: 1, maxLength: 11 })),
          bank_name: fc.oneof(fc.constant(''), fc.constant(undefined), fc.string({ minLength: 1, maxLength: 100 })),
        }),
        (data) => {
          const cleaned = Object.fromEntries(
            Object.entries(data).filter(([, v]) => v !== undefined)
          );
          const result = vendorCreateSchema.safeParse(cleaned);
          expect(result.success).toBe(true);
        }
      ),
      { numRuns: 100 }
    );
  });

  /**
   * Sub-property 3b: Schema rejects empty vendor_code
   */
  it('rejects when vendor_code is empty', () => {
    fc.assert(
      fc.property(
        validEmail(),
        nonEmptyString(200),
        (email, name) => {
          const data = {
            vendor_code: '',
            vendor_name: name,
            vendor_email: email,
          };
          const result = vendorCreateSchema.safeParse(data);
          expect(result.success).toBe(false);
        }
      ),
      { numRuns: 100 }
    );
  });

  /**
   * Sub-property 3c: Schema rejects vendor_name exceeding 200 characters
   */
  it('rejects when vendor_name exceeds 200 characters', () => {
    fc.assert(
      fc.property(
        nonEmptyString(50),
        validEmail(),
        fc.string({ minLength: 201, maxLength: 300 }),
        (code, email, longName) => {
          const data = {
            vendor_code: code,
            vendor_name: longName,
            vendor_email: email,
          };
          const result = vendorCreateSchema.safeParse(data);
          expect(result.success).toBe(false);
        }
      ),
      { numRuns: 100 }
    );
  });

  /**
   * Sub-property 3d: Schema rejects invalid email formats
   */
  it('rejects when vendor_email is not a valid email', () => {
    fc.assert(
      fc.property(
        nonEmptyString(50),
        nonEmptyString(200),
        fc.string({ minLength: 1, maxLength: 50 }).filter((s) => !s.includes('@') || !s.includes('.')),
        (code, name, invalidEmail) => {
          const data = {
            vendor_code: code,
            vendor_name: name,
            vendor_email: invalidEmail,
          };
          const result = vendorCreateSchema.safeParse(data);
          expect(result.success).toBe(false);
        }
      ),
      { numRuns: 100 }
    );
  });

  /**
   * Sub-property 3e: Schema rejects GSTN that doesn't match [A-Z0-9]{15}
   */
  it('rejects when gstn_number does not match [A-Z0-9]{15} pattern', () => {
    fc.assert(
      fc.property(
        nonEmptyString(50),
        nonEmptyString(200),
        validEmail(),
        fc.oneof(
          // Too short
          fc.stringMatching(/^[A-Z0-9]{1,14}$/),
          // Too long
          fc.stringMatching(/^[A-Z0-9]{16,20}$/),
          // Lowercase chars (invalid)
          fc.stringMatching(/^[a-z0-9]{15}$/)
        ),
        (code, name, email, invalidGstn) => {
          const data = {
            vendor_code: code,
            vendor_name: name,
            vendor_email: email,
            gstn_number: invalidGstn,
          };
          const result = vendorCreateSchema.safeParse(data);
          expect(result.success).toBe(false);
        }
      ),
      { numRuns: 100 }
    );
  });

  /**
   * Sub-property 3f: Schema accepts valid GSTN patterns
   */
  it('accepts when gstn_number matches [A-Z0-9]{15} exactly', () => {
    fc.assert(
      fc.property(
        nonEmptyString(50),
        nonEmptyString(200),
        validEmail(),
        validGstn(),
        (code, name, email, gstn) => {
          const data = {
            vendor_code: code,
            vendor_name: name,
            vendor_email: email,
            gstn_number: gstn,
          };
          const result = vendorCreateSchema.safeParse(data);
          expect(result.success).toBe(true);
        }
      ),
      { numRuns: 100 }
    );
  });

  /**
   * Sub-property 3g: Schema rejects vendor_contact exceeding 20 characters
   */
  it('rejects when vendor_contact exceeds 20 characters', () => {
    fc.assert(
      fc.property(
        nonEmptyString(50),
        nonEmptyString(200),
        validEmail(),
        fc.string({ minLength: 21, maxLength: 50 }),
        (code, name, email, longContact) => {
          const data = {
            vendor_code: code,
            vendor_name: name,
            vendor_email: email,
            vendor_contact: longContact,
          };
          const result = vendorCreateSchema.safeParse(data);
          expect(result.success).toBe(false);
        }
      ),
      { numRuns: 100 }
    );
  });

  /**
   * Sub-property 3h: Schema rejects fields exceeding their max lengths
   */
  it('rejects when optional fields exceed their max length constraints', () => {
    fc.assert(
      fc.property(
        nonEmptyString(50),
        nonEmptyString(200),
        validEmail(),
        fc.constantFrom('pan_number', 'bank_account_no', 'bank_ifsc', 'bank_name') as fc.Arbitrary<string>,
        (code, name, email, field) => {
          const maxLengths: Record<string, number> = {
            pan_number: 10,
            bank_account_no: 30,
            bank_ifsc: 11,
            bank_name: 100,
          };
          const maxLen = maxLengths[field]!;
          // Generate a string exceeding the max length
          const overLengthValue = 'A'.repeat(maxLen + 1);

          const data: Record<string, string> = {
            vendor_code: code,
            vendor_name: name,
            vendor_email: email,
            [field]: overLengthValue,
          };
          const result = vendorCreateSchema.safeParse(data);
          expect(result.success).toBe(false);
        }
      ),
      { numRuns: 100 }
    );
  });

  /**
   * Sub-property 3i: Schema rejects vendor_code exceeding 50 characters
   */
  it('rejects when vendor_code exceeds 50 characters', () => {
    fc.assert(
      fc.property(
        fc.string({ minLength: 51, maxLength: 100 }),
        nonEmptyString(200),
        validEmail(),
        (longCode, name, email) => {
          const data = {
            vendor_code: longCode,
            vendor_name: name,
            vendor_email: email,
          };
          const result = vendorCreateSchema.safeParse(data);
          expect(result.success).toBe(false);
        }
      ),
      { numRuns: 100 }
    );
  });

  /**
   * Sub-property 3j: Schema rejects empty vendor_name
   */
  it('rejects when vendor_name is empty', () => {
    fc.assert(
      fc.property(
        nonEmptyString(50),
        validEmail(),
        (code, email) => {
          const data = {
            vendor_code: code,
            vendor_name: '',
            vendor_email: email,
          };
          const result = vendorCreateSchema.safeParse(data);
          expect(result.success).toBe(false);
        }
      ),
      { numRuns: 100 }
    );
  });

  /**
   * Sub-property 3k: Schema rejects empty vendor_email
   */
  it('rejects when vendor_email is empty', () => {
    fc.assert(
      fc.property(
        nonEmptyString(50),
        nonEmptyString(200),
        (code, name) => {
          const data = {
            vendor_code: code,
            vendor_name: name,
            vendor_email: '',
          };
          const result = vendorCreateSchema.safeParse(data);
          expect(result.success).toBe(false);
        }
      ),
      { numRuns: 100 }
    );
  });
});

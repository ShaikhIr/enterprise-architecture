/**
 * User Create Form Schema — Property-Based Test
 *
 * Uses Vitest + fast-check to verify the createUserSchema Zod schema
 * enforces conditional password validation based on the is_validate_ad flag.
 *
 * Property 9: The schema SHALL require password (non-empty, ≥ 8 characters) if and only if
 * is_validate_ad is false. When is_validate_ad is true, the schema SHALL accept the form
 * regardless of password field content.
 *
 * **Validates: Requirements 10.4**
 */

import * as fc from 'fast-check';
import { describe, it, expect } from 'vitest';
import { createUserSchema } from '../../src/features/user-management/components/UserForm';

/**
 * Arbitraries
 */

// Valid non-empty string (at least 1 visible char) with max length
const nonEmptyString = (maxLen: number) =>
  fc.string({ minLength: 1, maxLength: maxLen }).filter((s) => s.trim().length > 0);

// Valid username: 3–255 characters
const validUsername = () =>
  fc.string({ minLength: 3, maxLength: 50 }).filter((s) => s.trim().length >= 3);

// Valid password: at least 8 characters
const validPassword = () =>
  fc.string({ minLength: 8, maxLength: 64 }).filter((s) => s.length >= 8);

// Short password: 0–7 characters (invalid when AD is off)
const shortPassword = () =>
  fc.string({ minLength: 0, maxLength: 7 });

// Base valid form data (all required fields satisfied, excluding password)
const validBaseData = () =>
  fc.record({
    employee_id: nonEmptyString(50),
    username: validUsername(),
    email: fc.constant(''),
    first_name: fc.constant(''),
    last_name: fc.constant(''),
    role_id: nonEmptyString(36),
    entity_id: fc.constant(''),
  });

describe('Property 9: User create form — conditional password validation', () => {
  /**
   * Sub-property 9a: When is_validate_ad is false, schema ACCEPTS valid passwords (≥ 8 chars)
   */
  it('accepts form when is_validate_ad=false and password is ≥ 8 characters', () => {
    fc.assert(
      fc.property(
        validBaseData(),
        validPassword(),
        (base, password) => {
          const data = {
            ...base,
            is_validate_ad: false,
            password,
          };
          const result = createUserSchema.safeParse(data);
          expect(result.success).toBe(true);
        }
      ),
      { numRuns: 100 }
    );
  });

  /**
   * Sub-property 9b: When is_validate_ad is false, schema REJECTS passwords shorter than 8 chars
   */
  it('rejects form when is_validate_ad=false and password is < 8 characters', () => {
    fc.assert(
      fc.property(
        validBaseData(),
        shortPassword(),
        (base, password) => {
          const data = {
            ...base,
            is_validate_ad: false,
            password,
          };
          const result = createUserSchema.safeParse(data);
          expect(result.success).toBe(false);
          if (!result.success) {
            const passwordErrors = result.error.issues.filter((i) =>
              i.path.includes('password')
            );
            expect(passwordErrors.length).toBeGreaterThan(0);
          }
        }
      ),
      { numRuns: 100 }
    );
  });

  /**
   * Sub-property 9c: When is_validate_ad is false, schema REJECTS empty/undefined password
   */
  it('rejects form when is_validate_ad=false and password is empty or undefined', () => {
    fc.assert(
      fc.property(
        validBaseData(),
        fc.constantFrom('', undefined),
        (base, password) => {
          const data = {
            ...base,
            is_validate_ad: false,
            password,
          };
          const result = createUserSchema.safeParse(data);
          expect(result.success).toBe(false);
          if (!result.success) {
            const passwordErrors = result.error.issues.filter((i) =>
              i.path.includes('password')
            );
            expect(passwordErrors.length).toBeGreaterThan(0);
          }
        }
      ),
      { numRuns: 100 }
    );
  });

  /**
   * Sub-property 9d: When is_validate_ad is true, schema ACCEPTS regardless of password content
   * (valid password, short password, empty, or undefined)
   */
  it('accepts form when is_validate_ad=true regardless of password content', () => {
    fc.assert(
      fc.property(
        validBaseData(),
        fc.oneof(
          validPassword(),
          shortPassword(),
          fc.constant(''),
          fc.constant(undefined)
        ),
        (base, password) => {
          const data = {
            ...base,
            is_validate_ad: true,
            password,
          };
          const result = createUserSchema.safeParse(data);
          expect(result.success).toBe(true);
        }
      ),
      { numRuns: 100 }
    );
  });

  /**
   * Sub-property 9e: When is_validate_ad is true, password at exactly 8 chars boundary is accepted
   * (boundary test — confirms no spurious rejection at exactly the min length)
   */
  it('accepts form when is_validate_ad=true and password is exactly 8 characters', () => {
    fc.assert(
      fc.property(
        validBaseData(),
        fc.string({ minLength: 8, maxLength: 8 }),
        (base, password) => {
          const data = {
            ...base,
            is_validate_ad: true,
            password,
          };
          const result = createUserSchema.safeParse(data);
          expect(result.success).toBe(true);
        }
      ),
      { numRuns: 100 }
    );
  });

  /**
   * Sub-property 9f: When is_validate_ad is false, password at exactly 8 chars boundary is accepted
   * (boundary test — confirms acceptance at exactly the min length)
   */
  it('accepts form when is_validate_ad=false and password is exactly 8 characters', () => {
    fc.assert(
      fc.property(
        validBaseData(),
        fc.string({ minLength: 8, maxLength: 8 }).filter((s) => s.length === 8),
        (base, password) => {
          const data = {
            ...base,
            is_validate_ad: false,
            password,
          };
          const result = createUserSchema.safeParse(data);
          expect(result.success).toBe(true);
        }
      ),
      { numRuns: 100 }
    );
  });

  /**
   * Sub-property 9g: When is_validate_ad is false, password at exactly 7 chars is rejected
   * (boundary test — confirms rejection just below the minimum)
   */
  it('rejects form when is_validate_ad=false and password is exactly 7 characters', () => {
    fc.assert(
      fc.property(
        validBaseData(),
        fc.string({ minLength: 7, maxLength: 7 }).filter((s) => s.length === 7),
        (base, password) => {
          const data = {
            ...base,
            is_validate_ad: false,
            password,
          };
          const result = createUserSchema.safeParse(data);
          expect(result.success).toBe(false);
        }
      ),
      { numRuns: 100 }
    );
  });
});

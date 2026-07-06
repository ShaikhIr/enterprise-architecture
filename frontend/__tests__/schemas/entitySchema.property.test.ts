/**
 * Entity Schema — Property-Based Tests
 *
 * Uses Vitest + fast-check to verify that the entityCreateSchema Zod schema
 * correctly validates Entity create form inputs according to the defined constraints:
 * - entity_name: required (non-empty) and max 255 characters
 * - short_code: optional, max 50 characters
 * - company_code: optional, max 50 characters
 *
 * **Validates: Requirements 2.5**
 */

import * as fc from 'fast-check';
import { describe, it, expect } from 'vitest';
import { entityCreateSchema } from '../../src/features/masters/schemas/entitySchema';
import { formatEntityDropdown } from '../../src/features/masters/pages/EntityListPage';

describe('Entity Schema — Property Tests', () => {
  /**
   * Property 2: Entity schema validation — required and length constraints
   *
   * For any string input for Entity create form fields, the Zod schema SHALL
   * accept the input if and only if: entity_name is non-empty and ≤ 255 characters,
   * short_code (if provided) is ≤ 50 characters, and company_code (if provided)
   * is ≤ 50 characters.
   *
   * **Validates: Requirements 2.5**
   */
  it('accepts valid inputs: entity_name non-empty ≤255, short_code ≤50, company_code ≤50', () => {
    fc.assert(
      fc.property(
        // entity_name: non-empty string with length 1–255
        fc.string({ minLength: 1, maxLength: 255 }),
        // short_code: optional string ≤50 or empty string or undefined
        fc.oneof(
          fc.constant(undefined),
          fc.constant(''),
          fc.string({ minLength: 1, maxLength: 50 })
        ),
        // company_code: optional string ≤50 or empty string or undefined
        fc.oneof(
          fc.constant(undefined),
          fc.constant(''),
          fc.string({ minLength: 1, maxLength: 50 })
        ),
        (entityName, shortCode, companyCode) => {
          const input: Record<string, unknown> = { entity_name: entityName };
          if (shortCode !== undefined) input.short_code = shortCode;
          if (companyCode !== undefined) input.company_code = companyCode;

          const result = entityCreateSchema.safeParse(input);
          expect(result.success).toBe(true);
        }
      ),
      { numRuns: 100 }
    );
  });

  it('rejects empty entity_name', () => {
    fc.assert(
      fc.property(
        // short_code and company_code valid
        fc.oneof(fc.constant(undefined), fc.string({ maxLength: 50 })),
        fc.oneof(fc.constant(undefined), fc.string({ maxLength: 50 })),
        (shortCode, companyCode) => {
          const input: Record<string, unknown> = { entity_name: '' };
          if (shortCode !== undefined) input.short_code = shortCode;
          if (companyCode !== undefined) input.company_code = companyCode;

          const result = entityCreateSchema.safeParse(input);
          expect(result.success).toBe(false);
        }
      ),
      { numRuns: 100 }
    );
  });

  it('rejects entity_name longer than 255 characters', () => {
    fc.assert(
      fc.property(
        // entity_name: string with length 256–500
        fc.string({ minLength: 256, maxLength: 500 }),
        fc.oneof(fc.constant(undefined), fc.string({ maxLength: 50 })),
        fc.oneof(fc.constant(undefined), fc.string({ maxLength: 50 })),
        (entityName, shortCode, companyCode) => {
          const input: Record<string, unknown> = { entity_name: entityName };
          if (shortCode !== undefined) input.short_code = shortCode;
          if (companyCode !== undefined) input.company_code = companyCode;

          const result = entityCreateSchema.safeParse(input);
          expect(result.success).toBe(false);
        }
      ),
      { numRuns: 100 }
    );
  });

  it('rejects short_code longer than 50 characters', () => {
    fc.assert(
      fc.property(
        // Valid entity_name
        fc.string({ minLength: 1, maxLength: 255 }),
        // Invalid short_code: length 51–100
        fc.string({ minLength: 51, maxLength: 100 }),
        fc.oneof(fc.constant(undefined), fc.string({ maxLength: 50 })),
        (entityName, shortCode, companyCode) => {
          const input: Record<string, unknown> = {
            entity_name: entityName,
            short_code: shortCode,
          };
          if (companyCode !== undefined) input.company_code = companyCode;

          const result = entityCreateSchema.safeParse(input);
          expect(result.success).toBe(false);
        }
      ),
      { numRuns: 100 }
    );
  });

  it('rejects company_code longer than 50 characters', () => {
    fc.assert(
      fc.property(
        // Valid entity_name
        fc.string({ minLength: 1, maxLength: 255 }),
        fc.oneof(fc.constant(undefined), fc.string({ maxLength: 50 })),
        // Invalid company_code: length 51–100
        fc.string({ minLength: 51, maxLength: 100 }),
        (entityName, shortCode, companyCode) => {
          const input: Record<string, unknown> = {
            entity_name: entityName,
            company_code: companyCode,
          };
          if (shortCode !== undefined) input.short_code = shortCode;

          const result = entityCreateSchema.safeParse(input);
          expect(result.success).toBe(false);
        }
      ),
      { numRuns: 100 }
    );
  });
});


describe('Entity Dropdown Formatting — Property Tests', () => {
  /**
   * Property 1: Entity dropdown formatting
   *
   * For any Entity object with any combination of short_code (null, empty string,
   * whitespace-only, or valid non-empty string) and entity_name, the formatter SHALL
   * produce:
   * - "{short_code.trim()} - {entity_name}" when short_code is non-empty after trim
   * - "Unknown - {entity_name}" when short_code is null, empty, or whitespace-only
   *
   * **Validates: Requirements 2.9, 10.10**
   */
  it('produces "{short_code} - {entity_name}" when short_code is non-empty after trim', () => {
    fc.assert(
      fc.property(
        // entity_name: non-empty string
        fc.string({ minLength: 1, maxLength: 200 }),
        // short_code: non-empty after trim (at least one non-whitespace character)
        fc.string({ minLength: 1, maxLength: 50 }).filter((s) => s.trim().length > 0),
        (entityName, shortCode) => {
          const entity = { short_code: shortCode, entity_name: entityName };
          const result = formatEntityDropdown(entity);
          expect(result).toBe(`${shortCode.trim()} - ${entityName}`);
        }
      ),
      { numRuns: 100 }
    );
  });

  it('produces "Unknown - {entity_name}" when short_code is null', () => {
    fc.assert(
      fc.property(
        // entity_name: non-empty string
        fc.string({ minLength: 1, maxLength: 200 }),
        (entityName) => {
          const entity = { short_code: null, entity_name: entityName };
          const result = formatEntityDropdown(entity);
          expect(result).toBe(`Unknown - ${entityName}`);
        }
      ),
      { numRuns: 100 }
    );
  });

  it('produces "Unknown - {entity_name}" when short_code is empty string', () => {
    fc.assert(
      fc.property(
        // entity_name: non-empty string
        fc.string({ minLength: 1, maxLength: 200 }),
        (entityName) => {
          const entity = { short_code: '', entity_name: entityName };
          const result = formatEntityDropdown(entity);
          expect(result).toBe(`Unknown - ${entityName}`);
        }
      ),
      { numRuns: 100 }
    );
  });

  it('produces "Unknown - {entity_name}" when short_code is whitespace-only', () => {
    fc.assert(
      fc.property(
        // entity_name: non-empty string
        fc.string({ minLength: 1, maxLength: 200 }),
        // whitespace-only short_code (spaces, tabs, newlines)
        fc.array(fc.constantFrom(' ', '\t', '\n', '\r'), { minLength: 1, maxLength: 20 }).map((arr) => arr.join('')),
        (entityName, shortCode) => {
          const entity = { short_code: shortCode, entity_name: entityName };
          const result = formatEntityDropdown(entity);
          expect(result).toBe(`Unknown - ${entityName}`);
        }
      ),
      { numRuns: 100 }
    );
  });

  it('always produces output matching pattern "{code} - {entity_name}" for any short_code variant', () => {
    // Combined property: covers all short_code variants in a single property
    const shortCodeArb = fc.oneof(
      fc.constant(null),
      fc.constant(''),
      fc.array(fc.constantFrom(' ', '\t', '\n'), { minLength: 1, maxLength: 10 }).map((arr) => arr.join('')),
      fc.string({ minLength: 1, maxLength: 50 }).filter((s) => s.trim().length > 0)
    );

    fc.assert(
      fc.property(
        fc.string({ minLength: 1, maxLength: 200 }),
        shortCodeArb,
        (entityName, shortCode) => {
          const entity = { short_code: shortCode, entity_name: entityName };
          const result = formatEntityDropdown(entity);

          const expectedCode = shortCode?.trim() ? shortCode.trim() : 'Unknown';
          expect(result).toBe(`${expectedCode} - ${entityName}`);
        }
      ),
      { numRuns: 100 }
    );
  });
});

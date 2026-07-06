/**
 * Mapping Schema — Property-Based Test
 *
 * Uses Vitest + fast-check to verify that the mappingCreateSchema Zod schema
 * accepts valid mapping form data when validity_from ≤ validity_to (date ordering)
 * and rejects when validity_from > validity_to.
 *
 * **Validates: Requirements 8.5**
 */

import * as fc from 'fast-check';
import { describe, it, expect } from 'vitest';
import { mappingCreateSchema, mappingUpdateSchema } from '../../src/features/masters/schemas/mappingSchema';

/**
 * Arbitraries for generating valid data
 */

// Valid non-empty string for IDs (vendor_id, customer_id)
const nonEmptyId = () =>
  fc.string({ minLength: 1, maxLength: 36 }).filter((s) => s.trim().length > 0);

// Helper to format year/month/day into YYYY-MM-DD
const toIsoDate = (year: number, month: number, day: number): string => {
  const y = String(year).padStart(4, '0');
  const m = String(month).padStart(2, '0');
  const d = String(day).padStart(2, '0');
  return `${y}-${m}-${d}`;
};

// Generate a valid ISO date string (YYYY-MM-DD) using integer components
const isoDateString = () =>
  fc
    .record({
      year: fc.integer({ min: 1970, max: 2099 }),
      month: fc.integer({ min: 1, max: 12 }),
      day: fc.integer({ min: 1, max: 28 }), // Use 28 to avoid invalid day-of-month
    })
    .map(({ year, month, day }) => toIsoDate(year, month, day));

// Generate an ordered date pair where from <= to
const orderedDatePair = () =>
  fc
    .tuple(isoDateString(), isoDateString())
    .map(([a, b]) => (a <= b ? [a, b] as const : [b, a] as const));

// Generate a reversed date pair where from > to (strictly)
const reversedDatePair = () =>
  fc
    .tuple(isoDateString(), isoDateString())
    .filter(([a, b]) => a !== b)
    .map(([a, b]) => (a > b ? [a, b] as const : [b, a] as const));

describe('Property 7: Mapping schema validation — date ordering constraint', () => {
  /**
   * Sub-property 7a: Schema accepts when validity_from ≤ validity_to
   *
   * For any generated date pair where from ≤ to, with valid vendor_id and customer_id,
   * the mappingCreateSchema must accept.
   */
  it('accepts mapping data when validity_from ≤ validity_to', () => {
    fc.assert(
      fc.property(
        nonEmptyId(),
        nonEmptyId(),
        orderedDatePair(),
        (vendorId, customerId, [fromDate, toDate]) => {
          const data = {
            vendor_id: vendorId,
            customer_id: customerId,
            validity_from: fromDate,
            validity_to: toDate,
          };
          const result = mappingCreateSchema.safeParse(data);
          expect(result.success).toBe(true);
        }
      ),
      { numRuns: 150 }
    );
  });

  /**
   * Sub-property 7b: Schema rejects when validity_from > validity_to
   *
   * For any generated date pair where from > to, with valid vendor_id and customer_id,
   * the mappingCreateSchema must reject.
   */
  it('rejects mapping data when validity_from > validity_to', () => {
    fc.assert(
      fc.property(
        nonEmptyId(),
        nonEmptyId(),
        reversedDatePair(),
        (vendorId, customerId, [fromDate, toDate]) => {
          const data = {
            vendor_id: vendorId,
            customer_id: customerId,
            validity_from: fromDate,
            validity_to: toDate,
          };
          const result = mappingCreateSchema.safeParse(data);
          expect(result.success).toBe(false);
        }
      ),
      { numRuns: 150 }
    );
  });

  /**
   * Sub-property 7c: Schema accepts when validity_from equals validity_to (same day)
   *
   * A mapping that starts and ends on the same date is valid.
   */
  it('accepts mapping data when validity_from equals validity_to', () => {
    fc.assert(
      fc.property(
        nonEmptyId(),
        nonEmptyId(),
        isoDateString(),
        (vendorId, customerId, sameDate) => {
          const data = {
            vendor_id: vendorId,
            customer_id: customerId,
            validity_from: sameDate,
            validity_to: sameDate,
          };
          const result = mappingCreateSchema.safeParse(data);
          expect(result.success).toBe(true);
        }
      ),
      { numRuns: 100 }
    );
  });

  /**
   * Sub-property 7d: Update schema also enforces validity_from ≤ validity_to
   *
   * The mappingUpdateSchema applies the same date ordering constraint.
   */
  it('update schema accepts when validity_from ≤ validity_to', () => {
    fc.assert(
      fc.property(
        orderedDatePair(),
        ([fromDate, toDate]) => {
          const data = {
            validity_from: fromDate,
            validity_to: toDate,
          };
          const result = mappingUpdateSchema.safeParse(data);
          expect(result.success).toBe(true);
        }
      ),
      { numRuns: 100 }
    );
  });

  /**
   * Sub-property 7e: Update schema rejects when validity_from > validity_to
   */
  it('update schema rejects when validity_from > validity_to', () => {
    fc.assert(
      fc.property(
        reversedDatePair(),
        ([fromDate, toDate]) => {
          const data = {
            validity_from: fromDate,
            validity_to: toDate,
          };
          const result = mappingUpdateSchema.safeParse(data);
          expect(result.success).toBe(false);
        }
      ),
      { numRuns: 100 }
    );
  });
});

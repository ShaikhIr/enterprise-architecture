/**
 * Agreement Schema — Property-Based Test
 *
 * Uses Vitest + fast-check to verify that the agreementCreateSchema Zod schema
 * correctly enforces cross-field date and commission constraints:
 * - from_date ≤ to_date
 * - min_commission_percent ≤ max_commission_percent
 * - slab_in_days is an integer > 0
 * - reduction_percent is between 0 and 100
 * - max_commission_percent is between 0 and 100
 * - min_commission_percent is between 0 and 100
 * - credit_days is an integer ≥ 0
 *
 * **Validates: Requirements 7.5**
 */

import * as fc from 'fast-check';
import { describe, it, expect } from 'vitest';
import { agreementCreateSchema } from '../../src/features/masters/schemas/agreementSchema';

/**
 * Arbitraries for generating valid data
 */

// Valid non-empty string (for IDs)
const nonEmptyId = () =>
  fc.string({ minLength: 1, maxLength: 36 }).filter((s) => s.trim().length > 0);

// Helper to format year/month/day into ISO date string (YYYY-MM-DD)
const toIsoDate = (year: number, month: number, day: number): string => {
  const y = String(year).padStart(4, '0');
  const m = String(month).padStart(2, '0');
  const d = String(day).padStart(2, '0');
  return `${y}-${m}-${d}`;
};

// Generate an ISO date string (YYYY-MM-DD) using integer components
const isoDateString = () =>
  fc
    .tuple(
      fc.integer({ min: 2000, max: 2099 }),
      fc.integer({ min: 1, max: 12 }),
      fc.integer({ min: 1, max: 28 }) // use 28 to avoid invalid day-of-month issues
    )
    .map(([y, m, d]) => toIsoDate(y, m, d));

// Generate an ordered pair of date strings where from_date <= to_date
const orderedDatePair = () =>
  fc.tuple(isoDateString(), isoDateString()).map(([d1, d2]) => {
    return d1 <= d2
      ? { from_date: d1, to_date: d2 }
      : { from_date: d2, to_date: d1 };
  });

// Generate a reversed pair of date strings where from_date > to_date
const reversedDatePair = () =>
  fc
    .tuple(isoDateString(), isoDateString())
    .filter(([d1, d2]) => d1 !== d2)
    .map(([d1, d2]) => {
      // Intentionally reversed: from_date > to_date
      return d1 > d2
        ? { from_date: d1, to_date: d2 }
        : { from_date: d2, to_date: d1 };
    });

// Valid commission percent: number between 0 and 100 inclusive
const validPercent = () => fc.double({ min: 0, max: 100, noNaN: true, noDefaultInfinity: true });

// Ordered commission pair where min <= max
const orderedCommissionPair = () =>
  fc.tuple(validPercent(), validPercent()).map(([a, b]) => {
    const sorted = a <= b ? [a, b] : [b, a];
    return { min_commission_percent: sorted[0], max_commission_percent: sorted[1] };
  });

// Reversed commission pair where min > max
const reversedCommissionPair = () =>
  fc
    .tuple(validPercent(), validPercent())
    .filter(([a, b]) => a !== b)
    .map(([a, b]) => {
      const sorted = a <= b ? [a, b] : [b, a];
      return { min_commission_percent: sorted[1], max_commission_percent: sorted[0] };
    })
    .filter((pair) => pair.min_commission_percent > pair.max_commission_percent);

// Valid slab_in_days: positive integer
const validSlabInDays = () => fc.integer({ min: 1, max: 365 });

// Invalid slab_in_days: zero or negative integer
const invalidSlabInDays = () => fc.integer({ min: -100, max: 0 });

// Non-integer slab (float)
const nonIntegerSlab = () =>
  fc.double({ min: 0.01, max: 365, noNaN: true, noDefaultInfinity: true }).filter(
    (n) => !Number.isInteger(n)
  );

// Valid credit_days: non-negative integer
const validCreditDays = () => fc.integer({ min: 0, max: 365 });

// Invalid credit_days: negative integer
const negativeCreditDays = () => fc.integer({ min: -100, max: -1 });

// Percent out of range (below 0)
const belowZeroPercent = () => fc.double({ min: -100, max: -0.01, noNaN: true, noDefaultInfinity: true });

// Percent out of range (above 100)
const aboveHundredPercent = () => fc.double({ min: 100.01, max: 500, noNaN: true, noDefaultInfinity: true });

/**
 * Helper to build a fully valid agreement form data object
 */
const buildValidData = (overrides: Record<string, unknown> = {}) => ({
  vendor_id: 'vendor-001',
  product_detail_id: 'product-detail-001',
  from_date: '2024-01-01',
  to_date: '2024-12-31',
  slab_in_days: 30,
  reduction_percent: 5,
  max_commission_percent: 20,
  min_commission_percent: 10,
  credit_days: 30,
  ...overrides,
});

describe('Property 6: Agreement schema validation — cross-field date and commission constraints', () => {
  /**
   * Sub-property 6a: Schema accepts valid agreement data with all constraints satisfied
   *
   * For any data where from_date ≤ to_date, min_commission ≤ max_commission,
   * slab_in_days integer > 0, reduction_percent [0, 100], commissions [0, 100],
   * credit_days integer ≥ 0, the schema must accept.
   */
  it('accepts valid agreement form data with all cross-field constraints satisfied', () => {
    fc.assert(
      fc.property(
        nonEmptyId(),
        nonEmptyId(),
        orderedDatePair(),
        orderedCommissionPair(),
        validSlabInDays(),
        validPercent(),
        validCreditDays(),
        (vendorId, productDetailId, dates, commissions, slabInDays, reductionPercent, creditDays) => {
          const data = {
            vendor_id: vendorId,
            product_detail_id: productDetailId,
            from_date: dates.from_date,
            to_date: dates.to_date,
            slab_in_days: slabInDays,
            reduction_percent: reductionPercent,
            max_commission_percent: commissions.max_commission_percent,
            min_commission_percent: commissions.min_commission_percent,
            credit_days: creditDays,
          };
          const result = agreementCreateSchema.safeParse(data);
          expect(result.success).toBe(true);
        }
      ),
      { numRuns: 150 }
    );
  });

  /**
   * Sub-property 6b: Schema rejects when from_date > to_date
   */
  it('rejects when from_date is after to_date', () => {
    fc.assert(
      fc.property(reversedDatePair(), (dates) => {
        const data = buildValidData({
          from_date: dates.from_date,
          to_date: dates.to_date,
        });
        const result = agreementCreateSchema.safeParse(data);
        expect(result.success).toBe(false);
        if (!result.success) {
          const paths = result.error.issues.map((i) => i.path.join('.'));
          expect(paths).toContain('to_date');
        }
      }),
      { numRuns: 100 }
    );
  });

  /**
   * Sub-property 6c: Schema rejects when min_commission_percent > max_commission_percent
   */
  it('rejects when min_commission_percent > max_commission_percent', () => {
    fc.assert(
      fc.property(reversedCommissionPair(), (commissions) => {
        const data = buildValidData({
          min_commission_percent: commissions.min_commission_percent,
          max_commission_percent: commissions.max_commission_percent,
        });
        const result = agreementCreateSchema.safeParse(data);
        expect(result.success).toBe(false);
        if (!result.success) {
          const paths = result.error.issues.map((i) => i.path.join('.'));
          expect(paths).toContain('min_commission_percent');
        }
      }),
      { numRuns: 100 }
    );
  });

  /**
   * Sub-property 6d: Schema rejects when slab_in_days is 0 or negative
   */
  it('rejects when slab_in_days is zero or negative', () => {
    fc.assert(
      fc.property(invalidSlabInDays(), (invalidSlab) => {
        const data = buildValidData({ slab_in_days: invalidSlab });
        const result = agreementCreateSchema.safeParse(data);
        expect(result.success).toBe(false);
      }),
      { numRuns: 100 }
    );
  });

  /**
   * Sub-property 6e: Schema rejects when slab_in_days is not an integer
   */
  it('rejects when slab_in_days is not an integer', () => {
    fc.assert(
      fc.property(nonIntegerSlab(), (nonIntSlab) => {
        const data = buildValidData({ slab_in_days: nonIntSlab });
        const result = agreementCreateSchema.safeParse(data);
        expect(result.success).toBe(false);
      }),
      { numRuns: 100 }
    );
  });

  /**
   * Sub-property 6f: Schema rejects when reduction_percent is below 0
   */
  it('rejects when reduction_percent is below 0', () => {
    fc.assert(
      fc.property(belowZeroPercent(), (negativePercent) => {
        const data = buildValidData({ reduction_percent: negativePercent });
        const result = agreementCreateSchema.safeParse(data);
        expect(result.success).toBe(false);
      }),
      { numRuns: 100 }
    );
  });

  /**
   * Sub-property 6g: Schema rejects when reduction_percent exceeds 100
   */
  it('rejects when reduction_percent exceeds 100', () => {
    fc.assert(
      fc.property(aboveHundredPercent(), (overPercent) => {
        const data = buildValidData({ reduction_percent: overPercent });
        const result = agreementCreateSchema.safeParse(data);
        expect(result.success).toBe(false);
      }),
      { numRuns: 100 }
    );
  });

  /**
   * Sub-property 6h: Schema rejects when max_commission_percent is below 0
   */
  it('rejects when max_commission_percent is below 0', () => {
    fc.assert(
      fc.property(belowZeroPercent(), (negativePercent) => {
        const data = buildValidData({
          max_commission_percent: negativePercent,
          min_commission_percent: 0,
        });
        const result = agreementCreateSchema.safeParse(data);
        expect(result.success).toBe(false);
      }),
      { numRuns: 100 }
    );
  });

  /**
   * Sub-property 6i: Schema rejects when max_commission_percent exceeds 100
   */
  it('rejects when max_commission_percent exceeds 100', () => {
    fc.assert(
      fc.property(aboveHundredPercent(), (overPercent) => {
        const data = buildValidData({
          max_commission_percent: overPercent,
          min_commission_percent: 0,
        });
        const result = agreementCreateSchema.safeParse(data);
        expect(result.success).toBe(false);
      }),
      { numRuns: 100 }
    );
  });

  /**
   * Sub-property 6j: Schema rejects when min_commission_percent is below 0
   */
  it('rejects when min_commission_percent is below 0', () => {
    fc.assert(
      fc.property(belowZeroPercent(), (negativePercent) => {
        const data = buildValidData({
          min_commission_percent: negativePercent,
          max_commission_percent: 100,
        });
        const result = agreementCreateSchema.safeParse(data);
        expect(result.success).toBe(false);
      }),
      { numRuns: 100 }
    );
  });

  /**
   * Sub-property 6k: Schema rejects when min_commission_percent exceeds 100
   */
  it('rejects when min_commission_percent exceeds 100', () => {
    fc.assert(
      fc.property(aboveHundredPercent(), (overPercent) => {
        const data = buildValidData({
          min_commission_percent: overPercent,
          max_commission_percent: 100,
        });
        const result = agreementCreateSchema.safeParse(data);
        expect(result.success).toBe(false);
      }),
      { numRuns: 100 }
    );
  });

  /**
   * Sub-property 6l: Schema rejects when credit_days is negative
   */
  it('rejects when credit_days is negative', () => {
    fc.assert(
      fc.property(negativeCreditDays(), (negativeDays) => {
        const data = buildValidData({ credit_days: negativeDays });
        const result = agreementCreateSchema.safeParse(data);
        expect(result.success).toBe(false);
      }),
      { numRuns: 100 }
    );
  });

  /**
   * Sub-property 6m: Schema accepts boundary values — same from_date and to_date,
   * equal min and max commission, slab_in_days = 1, credit_days = 0,
   * reduction_percent = 0 and 100
   */
  it('accepts boundary values: same dates, equal commissions, slab=1, credit=0, reduction=0', () => {
    fc.assert(
      fc.property(isoDateString(), validPercent(), (date, commission) => {
        const data = {
          vendor_id: 'vendor-001',
          product_detail_id: 'product-001',
          from_date: date,
          to_date: date, // same date
          slab_in_days: 1, // minimum valid
          reduction_percent: 0, // lower boundary
          max_commission_percent: commission,
          min_commission_percent: commission, // equal to max
          credit_days: 0, // minimum valid
        };
        const result = agreementCreateSchema.safeParse(data);
        expect(result.success).toBe(true);
      }),
      { numRuns: 100 }
    );
  });

  /**
   * Sub-property 6n: Schema rejects when credit_days is not an integer (float)
   */
  it('rejects when credit_days is not an integer', () => {
    fc.assert(
      fc.property(
        fc.double({ min: 0.01, max: 365, noNaN: true, noDefaultInfinity: true }).filter(
          (n) => !Number.isInteger(n)
        ),
        (nonIntCreditDays) => {
          const data = buildValidData({ credit_days: nonIntCreditDays });
          const result = agreementCreateSchema.safeParse(data);
          expect(result.success).toBe(false);
        }
      ),
      { numRuns: 100 }
    );
  });
});

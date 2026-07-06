/**
 * Product Master Schema — Property-Based Test
 *
 * Uses Vitest + fast-check to verify that the productMasterCreateSchema Zod schema
 * accepts valid product master form data and rejects invalid data, specifically
 * focusing on numeric range constraints for MRP, Rate, and GST %.
 *
 * Previously this tested a separate productDetailCreateSchema; that schema has
 * been merged into productMasterCreateSchema as part of collapsing the two-level
 * product hierarchy into a single entity.
 *
 * **Validates: Requirements 6.5**
 */

import * as fc from 'fast-check';
import { describe, it, expect } from 'vitest';
import { productMasterCreateSchema } from '../../src/features/masters/schemas/productMasterSchema';

/**
 * Arbitraries for generating valid data
 */

// Valid non-empty string up to maxLen
const nonEmptyString = (maxLen: number) =>
  fc.string({ minLength: 1, maxLength: maxLen }).filter((s) => s.trim().length > 0);

// Valid MRP/Rate: number between 0 and 999999999.99 inclusive
const validMrpRate = () => fc.double({ min: 0, max: 999999999.99, noNaN: true, noDefaultInfinity: true });

// Valid GST percent: number between 0 and 100 inclusive
const validGstPercent = () => fc.double({ min: 0, max: 100, noNaN: true, noDefaultInfinity: true });

// Negative number arbitrary
const negativeNumber = () => fc.double({ min: -1000000, max: -0.01, noNaN: true, noDefaultInfinity: true });

// Number exceeding MRP/Rate max (> 999999999.99)
const overMaxMrpRate = () => fc.double({ min: 999999999.995, max: 9999999999, noNaN: true, noDefaultInfinity: true });

// Number exceeding GST max (> 100)
const overMaxGst = () => fc.double({ min: 100.01, max: 1000, noNaN: true, noDefaultInfinity: true });

describe('Product Master schema validation — numeric range constraints', () => {
  /**
   * Sub-property 5a: Schema accepts valid numeric values within ranges
   */
  it('accepts valid product master form data with numeric fields within valid ranges', () => {
    fc.assert(
      fc.property(
        fc.record({
          basic_material_code: nonEmptyString(50),
          product_name: nonEmptyString(255),
          child_code: nonEmptyString(50),
          mrp: validMrpRate(),
          rate: validMrpRate(),
          gst_percent: validGstPercent(),
        }),
        (data) => {
          const result = productMasterCreateSchema.safeParse(data);
          expect(result.success).toBe(true);
        }
      ),
      { numRuns: 100 }
    );
  });

  /**
   * Sub-property 5b: Schema accepts when numeric fields are omitted (optional)
   */
  it('accepts valid product master form data when numeric fields are omitted', () => {
    fc.assert(
      fc.property(
        fc.record({
          basic_material_code: nonEmptyString(50),
          product_name: nonEmptyString(255),
          child_code: nonEmptyString(50),
        }),
        (data) => {
          const result = productMasterCreateSchema.safeParse(data);
          expect(result.success).toBe(true);
        }
      ),
      { numRuns: 100 }
    );
  });

  /**
   * Sub-property 5c: Schema rejects negative MRP values
   */
  it('rejects when MRP is negative', () => {
    fc.assert(
      fc.property(
        nonEmptyString(50),
        nonEmptyString(255),
        nonEmptyString(50),
        negativeNumber(),
        (basicMaterialCode, productName, childCode, negativeMrp) => {
          const data = {
            basic_material_code: basicMaterialCode,
            product_name: productName,
            child_code: childCode,
            mrp: negativeMrp,
          };
          const result = productMasterCreateSchema.safeParse(data);
          expect(result.success).toBe(false);
        }
      ),
      { numRuns: 100 }
    );
  });

  /**
   * Sub-property 5d: Schema rejects negative Rate values
   */
  it('rejects when Rate is negative', () => {
    fc.assert(
      fc.property(
        nonEmptyString(50),
        nonEmptyString(255),
        nonEmptyString(50),
        negativeNumber(),
        (basicMaterialCode, productName, childCode, negativeRate) => {
          const data = {
            basic_material_code: basicMaterialCode,
            product_name: productName,
            child_code: childCode,
            rate: negativeRate,
          };
          const result = productMasterCreateSchema.safeParse(data);
          expect(result.success).toBe(false);
        }
      ),
      { numRuns: 100 }
    );
  });

  /**
   * Sub-property 5e: Schema rejects negative GST % values
   */
  it('rejects when GST % is negative', () => {
    fc.assert(
      fc.property(
        nonEmptyString(50),
        nonEmptyString(255),
        nonEmptyString(50),
        negativeNumber(),
        (basicMaterialCode, productName, childCode, negativeGst) => {
          const data = {
            basic_material_code: basicMaterialCode,
            product_name: productName,
            child_code: childCode,
            gst_percent: negativeGst,
          };
          const result = productMasterCreateSchema.safeParse(data);
          expect(result.success).toBe(false);
        }
      ),
      { numRuns: 100 }
    );
  });

  /**
   * Sub-property 5f: Schema rejects MRP exceeding 999999999.99
   */
  it('rejects when MRP exceeds 999999999.99', () => {
    fc.assert(
      fc.property(
        nonEmptyString(50),
        nonEmptyString(255),
        nonEmptyString(50),
        overMaxMrpRate(),
        (basicMaterialCode, productName, childCode, overMrp) => {
          const data = {
            basic_material_code: basicMaterialCode,
            product_name: productName,
            child_code: childCode,
            mrp: overMrp,
          };
          const result = productMasterCreateSchema.safeParse(data);
          expect(result.success).toBe(false);
        }
      ),
      { numRuns: 100 }
    );
  });

  /**
   * Sub-property 5g: Schema rejects Rate exceeding 999999999.99
   */
  it('rejects when Rate exceeds 999999999.99', () => {
    fc.assert(
      fc.property(
        nonEmptyString(50),
        nonEmptyString(255),
        nonEmptyString(50),
        overMaxMrpRate(),
        (basicMaterialCode, productName, childCode, overRate) => {
          const data = {
            basic_material_code: basicMaterialCode,
            product_name: productName,
            child_code: childCode,
            rate: overRate,
          };
          const result = productMasterCreateSchema.safeParse(data);
          expect(result.success).toBe(false);
        }
      ),
      { numRuns: 100 }
    );
  });

  /**
   * Sub-property 5h: Schema rejects GST % exceeding 100
   */
  it('rejects when GST % exceeds 100', () => {
    fc.assert(
      fc.property(
        nonEmptyString(50),
        nonEmptyString(255),
        nonEmptyString(50),
        overMaxGst(),
        (basicMaterialCode, productName, childCode, overGst) => {
          const data = {
            basic_material_code: basicMaterialCode,
            product_name: productName,
            child_code: childCode,
            gst_percent: overGst,
          };
          const result = productMasterCreateSchema.safeParse(data);
          expect(result.success).toBe(false);
        }
      ),
      { numRuns: 100 }
    );
  });

  /**
   * Sub-property 5i: Schema accepts boundary values (0 for all numeric fields)
   */
  it('accepts zero as a valid boundary for MRP, Rate, and GST %', () => {
    fc.assert(
      fc.property(
        nonEmptyString(50),
        nonEmptyString(255),
        nonEmptyString(50),
        (basicMaterialCode, productName, childCode) => {
          const data = {
            basic_material_code: basicMaterialCode,
            product_name: productName,
            child_code: childCode,
            mrp: 0,
            rate: 0,
            gst_percent: 0,
          };
          const result = productMasterCreateSchema.safeParse(data);
          expect(result.success).toBe(true);
        }
      ),
      { numRuns: 100 }
    );
  });

  /**
   * Sub-property 5j: Schema accepts upper boundary values
   */
  it('accepts upper boundary values (999999999.99 for MRP/Rate, 100 for GST %)', () => {
    fc.assert(
      fc.property(
        nonEmptyString(50),
        nonEmptyString(255),
        nonEmptyString(50),
        (basicMaterialCode, productName, childCode) => {
          const data = {
            basic_material_code: basicMaterialCode,
            product_name: productName,
            child_code: childCode,
            mrp: 999999999.99,
            rate: 999999999.99,
            gst_percent: 100,
          };
          const result = productMasterCreateSchema.safeParse(data);
          expect(result.success).toBe(true);
        }
      ),
      { numRuns: 100 }
    );
  });

  /**
   * Sub-property 5k: Schema rejects when required child_code is empty
   */
  it('rejects when child_code is empty', () => {
    fc.assert(
      fc.property(
        nonEmptyString(50),
        nonEmptyString(255),
        validMrpRate(),
        validGstPercent(),
        (basicMaterialCode, productName, mrp, gst) => {
          const data = {
            basic_material_code: basicMaterialCode,
            product_name: productName,
            child_code: '',
            mrp,
            gst_percent: gst,
          };
          const result = productMasterCreateSchema.safeParse(data);
          expect(result.success).toBe(false);
        }
      ),
      { numRuns: 100 }
    );
  });

  /**
   * Sub-property 5l: Schema rejects when required basic_material_code is empty
   */
  it('rejects when basic_material_code is empty', () => {
    fc.assert(
      fc.property(
        nonEmptyString(255),
        nonEmptyString(50),
        validMrpRate(),
        validGstPercent(),
        (productName, childCode, rate, gst) => {
          const data = {
            basic_material_code: '',
            product_name: productName,
            child_code: childCode,
            rate,
            gst_percent: gst,
          };
          const result = productMasterCreateSchema.safeParse(data);
          expect(result.success).toBe(false);
        }
      ),
      { numRuns: 100 }
    );
  });
});

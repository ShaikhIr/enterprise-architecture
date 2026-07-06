/**
 * Invoice Schema — Property-Based Test
 *
 * Uses Vitest + fast-check to verify that the invoiceCreateSchema Zod schema
 * accepts valid invoice form data and rejects invalid data, focusing on:
 * - invoice_number must be non-empty
 * - invoice_date must be provided
 * - vendor_id must be provided
 * - customer_id must be provided
 * - bill_amount_excl_gst must be a positive number
 * - lines must have at least 1 item with product_detail_id specified
 *
 * **Validates: Requirements 9.5**
 */

import * as fc from 'fast-check';
import { describe, it, expect } from 'vitest';
import { invoiceCreateSchema } from '../../src/features/masters/schemas/invoiceSchema';

/**
 * Arbitraries for generating valid data
 */

// Valid non-empty string up to maxLen (trimmed non-empty)
const nonEmptyString = (maxLen: number) =>
  fc.string({ minLength: 1, maxLength: maxLen }).filter((s) => s.trim().length > 0);

// Positive number (bill_amount_excl_gst must be positive)
const positiveNumber = () =>
  fc.double({ min: 0.01, max: 999999999.99, noNaN: true, noDefaultInfinity: true });

// Non-positive number (zero or negative)
const nonPositiveNumber = () =>
  fc.double({ min: -999999999, max: 0, noNaN: true, noDefaultInfinity: true });

// Valid invoice line with product_detail_id specified
const validInvoiceLine = () =>
  fc.record({
    product_detail_id: nonEmptyString(36),
    quantity: fc.option(fc.nat({ max: 10000 }), { nil: undefined }),
    line_amount: fc.option(fc.double({ min: 0, max: 999999, noNaN: true, noDefaultInfinity: true }), { nil: undefined }),
    vat_gst_amount: fc.option(fc.double({ min: 0, max: 999999, noNaN: true, noDefaultInfinity: true }), { nil: undefined }),
  });

// Non-empty array of valid invoice lines (at least 1)
const validLines = () => fc.array(validInvoiceLine(), { minLength: 1, maxLength: 5 });

// Valid complete invoice form data
const validInvoiceData = () =>
  fc.record({
    invoice_number: nonEmptyString(100),
    invoice_date: nonEmptyString(20),
    vendor_id: nonEmptyString(36),
    customer_id: nonEmptyString(36),
    bill_amount_excl_gst: positiveNumber(),
    lines: validLines(),
  });

describe('Property 8: Invoice schema validation — positive amounts and non-empty lines', () => {
  /**
   * Sub-property 8a: Schema accepts valid invoice form data
   *
   * For any generated data with non-empty invoice_number, invoice_date, vendor_id,
   * customer_id, positive bill_amount_excl_gst, and at least 1 line item with
   * product_detail_id, the schema must accept.
   */
  it('accepts valid invoice form data with all required fields', () => {
    fc.assert(
      fc.property(validInvoiceData(), (data) => {
        const result = invoiceCreateSchema.safeParse(data);
        expect(result.success).toBe(true);
      }),
      { numRuns: 100 }
    );
  });

  /**
   * Sub-property 8b: Schema rejects when invoice_number is empty
   */
  it('rejects when invoice_number is empty', () => {
    fc.assert(
      fc.property(
        nonEmptyString(20),
        nonEmptyString(36),
        nonEmptyString(36),
        positiveNumber(),
        validLines(),
        (invoiceDate, vendorId, customerId, amount, lines) => {
          const data = {
            invoice_number: '',
            invoice_date: invoiceDate,
            vendor_id: vendorId,
            customer_id: customerId,
            bill_amount_excl_gst: amount,
            lines,
          };
          const result = invoiceCreateSchema.safeParse(data);
          expect(result.success).toBe(false);
        }
      ),
      { numRuns: 100 }
    );
  });

  /**
   * Sub-property 8c: Schema rejects when invoice_date is empty
   */
  it('rejects when invoice_date is empty', () => {
    fc.assert(
      fc.property(
        nonEmptyString(100),
        nonEmptyString(36),
        nonEmptyString(36),
        positiveNumber(),
        validLines(),
        (invoiceNumber, vendorId, customerId, amount, lines) => {
          const data = {
            invoice_number: invoiceNumber,
            invoice_date: '',
            vendor_id: vendorId,
            customer_id: customerId,
            bill_amount_excl_gst: amount,
            lines,
          };
          const result = invoiceCreateSchema.safeParse(data);
          expect(result.success).toBe(false);
        }
      ),
      { numRuns: 100 }
    );
  });

  /**
   * Sub-property 8d: Schema rejects when vendor_id is empty
   */
  it('rejects when vendor_id is empty', () => {
    fc.assert(
      fc.property(
        nonEmptyString(100),
        nonEmptyString(20),
        nonEmptyString(36),
        positiveNumber(),
        validLines(),
        (invoiceNumber, invoiceDate, customerId, amount, lines) => {
          const data = {
            invoice_number: invoiceNumber,
            invoice_date: invoiceDate,
            vendor_id: '',
            customer_id: customerId,
            bill_amount_excl_gst: amount,
            lines,
          };
          const result = invoiceCreateSchema.safeParse(data);
          expect(result.success).toBe(false);
        }
      ),
      { numRuns: 100 }
    );
  });

  /**
   * Sub-property 8e: Schema rejects when customer_id is empty
   */
  it('rejects when customer_id is empty', () => {
    fc.assert(
      fc.property(
        nonEmptyString(100),
        nonEmptyString(20),
        nonEmptyString(36),
        positiveNumber(),
        validLines(),
        (invoiceNumber, invoiceDate, vendorId, amount, lines) => {
          const data = {
            invoice_number: invoiceNumber,
            invoice_date: invoiceDate,
            vendor_id: vendorId,
            customer_id: '',
            bill_amount_excl_gst: amount,
            lines,
          };
          const result = invoiceCreateSchema.safeParse(data);
          expect(result.success).toBe(false);
        }
      ),
      { numRuns: 100 }
    );
  });

  /**
   * Sub-property 8f: Schema rejects when bill_amount_excl_gst is zero or negative
   */
  it('rejects when bill_amount_excl_gst is zero or negative', () => {
    fc.assert(
      fc.property(
        nonEmptyString(100),
        nonEmptyString(20),
        nonEmptyString(36),
        nonEmptyString(36),
        nonPositiveNumber(),
        validLines(),
        (invoiceNumber, invoiceDate, vendorId, customerId, badAmount, lines) => {
          const data = {
            invoice_number: invoiceNumber,
            invoice_date: invoiceDate,
            vendor_id: vendorId,
            customer_id: customerId,
            bill_amount_excl_gst: badAmount,
            lines,
          };
          const result = invoiceCreateSchema.safeParse(data);
          expect(result.success).toBe(false);
        }
      ),
      { numRuns: 100 }
    );
  });

  /**
   * Sub-property 8g: Schema rejects when lines array is empty
   */
  it('rejects when lines array is empty', () => {
    fc.assert(
      fc.property(
        nonEmptyString(100),
        nonEmptyString(20),
        nonEmptyString(36),
        nonEmptyString(36),
        positiveNumber(),
        (invoiceNumber, invoiceDate, vendorId, customerId, amount) => {
          const data = {
            invoice_number: invoiceNumber,
            invoice_date: invoiceDate,
            vendor_id: vendorId,
            customer_id: customerId,
            bill_amount_excl_gst: amount,
            lines: [],
          };
          const result = invoiceCreateSchema.safeParse(data);
          expect(result.success).toBe(false);
        }
      ),
      { numRuns: 100 }
    );
  });

  /**
   * Sub-property 8h: Schema rejects when line item has empty product_detail_id
   */
  it('rejects when a line item has empty product_detail_id', () => {
    fc.assert(
      fc.property(
        nonEmptyString(100),
        nonEmptyString(20),
        nonEmptyString(36),
        nonEmptyString(36),
        positiveNumber(),
        (invoiceNumber, invoiceDate, vendorId, customerId, amount) => {
          const data = {
            invoice_number: invoiceNumber,
            invoice_date: invoiceDate,
            vendor_id: vendorId,
            customer_id: customerId,
            bill_amount_excl_gst: amount,
            lines: [{ product_detail_id: '' }],
          };
          const result = invoiceCreateSchema.safeParse(data);
          expect(result.success).toBe(false);
        }
      ),
      { numRuns: 100 }
    );
  });

  /**
   * Sub-property 8i: Schema accepts with optional fields included
   *
   * Verifies that optional fields (bill_amount_incl_tax, amount_deducted, tds_value,
   * line quantity, line_amount, vat_gst_amount) do not affect acceptance when
   * all required constraints are met.
   */
  it('accepts valid data with optional fields included', () => {
    fc.assert(
      fc.property(
        fc.record({
          invoice_number: nonEmptyString(100),
          invoice_date: nonEmptyString(20),
          vendor_id: nonEmptyString(36),
          customer_id: nonEmptyString(36),
          bill_amount_excl_gst: positiveNumber(),
          bill_amount_incl_tax: fc.double({ min: 0, max: 999999, noNaN: true, noDefaultInfinity: true }),
          amount_deducted: fc.double({ min: 0, max: 999999, noNaN: true, noDefaultInfinity: true }),
          tds_value: fc.double({ min: 0, max: 999999, noNaN: true, noDefaultInfinity: true }),
          lines: fc.array(
            fc.record({
              product_detail_id: nonEmptyString(36),
              quantity: fc.nat({ max: 10000 }),
              line_amount: fc.double({ min: 0, max: 999999, noNaN: true, noDefaultInfinity: true }),
              vat_gst_amount: fc.double({ min: 0, max: 999999, noNaN: true, noDefaultInfinity: true }),
            }),
            { minLength: 1, maxLength: 5 }
          ),
        }),
        (data) => {
          const result = invoiceCreateSchema.safeParse(data);
          expect(result.success).toBe(true);
        }
      ),
      { numRuns: 100 }
    );
  });
});

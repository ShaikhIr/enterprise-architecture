/**
 * Emcure Design System — Property-Based Tests
 *
 * Uses Vitest + @testing-library/react + fast-check to verify universal
 * correctness invariants that must hold across all valid inputs.
 *
 * Each property references the design document acceptance criterion it validates.
 */

import React from 'react';
import * as fc from 'fast-check';
import { render, fireEvent, cleanup } from '@testing-library/react';
import { vi, describe, it, expect, afterEach } from 'vitest';
import Button, { type ButtonVariant } from '../../src/shared/components/ui/Button/Button';
import KpiCard from '../../src/shared/components/ui/KpiCard/KpiCard';
import DataGrid from '../../src/shared/components/ui/DataGrid/DataGrid';

afterEach(() => {
  cleanup();
});

describe('Emcure Design System — Property Tests', () => {
  /**
   * Property 1: Disabled Button Blocks All Click Events
   *
   * For any non-`sm` Button variant, when `disabled` is `true`, clicking the
   * rendered button must never invoke the `onClick` handler — regardless of
   * which colour variant is active.
   *
   * Validates: Requirements 4.11
   */
  it('Property 1: disabled button blocks all click events for any variant', () => {
    // Feature: emcure-design-system, Property 1: Disabled button blocks all click events
    fc.assert(
      fc.property(
        fc.constantFrom('primary', 'secondary', 'ghost', 'danger', 'save', 'delete'),
        (variant) => {
          const onClick = vi.fn();
          const { getByRole } = render(
            <Button variant={variant as ButtonVariant} disabled onClick={onClick}>
              Click me
            </Button>
          );
          fireEvent.click(getByRole('button'));
          expect(onClick).not.toHaveBeenCalled();
          cleanup();
        }
      ),
      { numRuns: 100 }
    );
  });

  /**
   * Property 2: KpiCard Delta Chip Color Tracks Sign
   *
   * For any non-zero numeric delta value passed to a KpiCard, the rendered
   * delta chip must apply a green-tinted style when delta > 0 and a red-tinted
   * style when delta < 0. The sign of the delta uniquely determines the chip
   * color class.
   *
   * Validates: Requirements 10.6
   */
  it('Property 2: KpiCard delta chip color tracks sign', () => {
    // Feature: emcure-design-system, Property 2: KpiCard delta chip color tracks sign
    fc.assert(
      fc.property(
        fc.integer({ min: 1, max: 100_000 }),    // positive delta
        fc.integer({ min: -100_000, max: -1 }),  // negative delta
        (posDelta, negDelta) => {
          // Positive delta → green chip class
          const { container: posContainer } = render(
            <KpiCard icon={<span />} value={42} label="Test" delta={posDelta} />
          );
          expect(posContainer.querySelector('.deltaPositive')).toBeTruthy();
          expect(posContainer.querySelector('.deltaNegative')).toBeNull();

          // Negative delta → red chip class
          const { container: negContainer } = render(
            <KpiCard icon={<span />} value={42} label="Test" delta={negDelta} />
          );
          expect(negContainer.querySelector('.deltaNegative')).toBeTruthy();
          expect(negContainer.querySelector('.deltaPositive')).toBeNull();
        }
      ),
      { numRuns: 100 }
    );
  });

  /**
   * Property 3: DataGrid Even-Row Striping Invariant
   *
   * For any non-empty array of row data passed to a DataGrid, every row at an
   * even index (0, 2, 4, …) must carry the `rowEven` CSS module class, and
   * every row at an odd index must NOT carry that class — regardless of the
   * data content or row count.
   *
   * **Validates: Requirements 11.5**
   */
  it('Property 3: DataGrid even-row striping invariant', () => {
    // Feature: emcure-design-system, Property 3: DataGrid even-row striping invariant
    fc.assert(
      fc.property(
        fc.array(fc.record({ id: fc.nat(), name: fc.string() }), { minLength: 1, maxLength: 50 }),
        (rows) => {
          const columns = [
            { header: 'ID', field: 'id' as const },
            { header: 'Name', field: 'name' as const },
          ];
          const { container } = render(<DataGrid columns={columns} data={rows} />);
          const tableRows = container.querySelectorAll('tbody tr');

          tableRows.forEach((row, index) => {
            if (index % 2 === 0) {
              expect(row.classList.contains('rowEven')).toBe(true);
            } else {
              expect(row.classList.contains('rowEven')).toBe(false);
            }
          });

          cleanup();
        }
      ),
      { numRuns: 100 }
    );
  });
});

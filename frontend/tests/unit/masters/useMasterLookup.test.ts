import { describe, expect, it } from 'vitest';

import { buildMasterLookup } from '@features/masters/hooks/useMasterLookup';
import type { LabelledMaster } from '@features/masters/models/common';

const record = (overrides: Partial<LabelledMaster>): LabelledMaster => ({
  id: 1,
  code: 'IN',
  name: 'India',
  is_active: true,
  created_by: 'system',
  created_date: '2024-01-01T00:00:00Z',
  modified_by: 'system',
  modified_date: '2024-01-01T00:00:00Z',
  ...overrides,
});

describe('buildMasterLookup', () => {
  it('builds dropdown options only from the active list, labelled as "name (code)"', () => {
    const active = [record({ id: 1, code: 'IN', name: 'India' })];
    const all = [
      record({ id: 1, code: 'IN', name: 'India' }),
      record({ id: 2, code: 'US', name: 'United States', is_active: false }),
    ];

    const lookup = buildMasterLookup(active, all, false);

    expect(lookup.options).toEqual([{ label: 'India (IN)', value: 1 }]);
  });

  it('resolves a stored id to its label even when the parent is no longer active', () => {
    const active: LabelledMaster[] = [];
    const all = [record({ id: 2, code: 'US', name: 'United States', is_active: false })];

    const lookup = buildMasterLookup(active, all, false);

    // Not offered as an option (retired), but a row that still points at it
    // must render its label rather than a bare id.
    expect(lookup.options).toEqual([]);
    expect(lookup.labelFor(2)).toBe('United States (US)');
  });

  it('returns an em dash for a null or undefined id', () => {
    const lookup = buildMasterLookup([], [], false);

    expect(lookup.labelFor(null)).toBe('—');
    expect(lookup.labelFor(undefined)).toBe('—');
  });

  it('returns "Unknown" for an id that exists in neither list', () => {
    const lookup = buildMasterLookup([], [], false);

    expect(lookup.labelFor(999)).toBe('Unknown');
  });

  it('passes the loading flag straight through', () => {
    expect(buildMasterLookup([], [], true).loading).toBe(true);
    expect(buildMasterLookup([], [], false).loading).toBe(false);
  });
});

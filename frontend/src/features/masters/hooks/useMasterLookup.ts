/**
 * Helper for building a parent-picker lookup.
 *
 * Two lists rather than one, on purpose: a picker must only offer *active*
 * parents, because pointing a new rule at a retired legislation is never
 * intended. But existing rows keep whatever parent they were given, so resolving
 * a stored id needs the *unfiltered* list — otherwise a record whose parent was
 * later deactivated would render as a bare UUID.
 */

import type { LabelledMaster } from '../models/common';

export interface SelectOption {
  label: string;
  value: string;
}

export interface MasterLookup {
  /** Active parents, for a Dropdown. */
  options: SelectOption[];
  loading: boolean;
  /** Resolve any stored id to a label, active or not. */
  labelFor: (id: string | null | undefined) => string;
}

/** How many parents a picker loads. Masters are reference data, not transactional. */
export const OPTION_LIMIT = 500;

export const buildMasterLookup = (
  active: LabelledMaster[],
  all: LabelledMaster[],
  loading: boolean,
): MasterLookup => {
  const labels = new Map(all.map((row) => [row.id, `${row.name} (${row.code})`]));
  return {
    options: active.map((row) => ({
      label: `${row.name} (${row.code})`,
      value: row.id,
    })),
    loading,
    labelFor: (id) => {
      if (!id) return '—';
      return labels.get(id) ?? 'Unknown';
    },
  };
};

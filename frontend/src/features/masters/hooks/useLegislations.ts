/**
 * Legislation master query hooks.
 *
 * A legislation's label appears on the Rules screen, so an edit here invalidates
 * that cache too.
 */

import { useMemo } from 'react';

import { legislationApi } from '../api/legislationApi';
import type {
  CreateLegislationRequest,
  Legislation,
  LegislationListParams,
  UpdateLegislationRequest,
} from '../models/Legislation';

import { createMasterHooks } from './createMasterHooks';
import { MASTER_KEYS } from './masterQueryKeys';
import { buildMasterLookup, OPTION_LIMIT, type MasterLookup } from './useMasterLookup';

const hooks = createMasterHooks<
  Legislation,
  CreateLegislationRequest,
  UpdateLegislationRequest,
  LegislationListParams
>(legislationApi, MASTER_KEYS.legislations, [MASTER_KEYS.rules]);

export const useLegislations = hooks.useList;
export const useCreateLegislation = hooks.useCreate;
export const useUpdateLegislation = hooks.useUpdate;
export const useDeleteLegislation = hooks.useDelete;

/** Options for a legislation picker, plus a resolver for already-stored ids. */
export const useLegislationLookup = (): MasterLookup => {
  const active = useLegislations({ limit: OPTION_LIMIT, is_active: true });
  const all = useLegislations({ limit: OPTION_LIMIT });
  return useMemo(
    () => buildMasterLookup(active.data?.items ?? [], all.data?.items ?? [], active.isLoading),
    [active.data, all.data, active.isLoading],
  );
};

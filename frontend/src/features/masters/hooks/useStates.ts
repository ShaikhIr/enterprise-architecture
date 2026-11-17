/**
 * State master query hooks.
 *
 * A state's label appears on the Categories of Law, Legislations and Rules
 * screens, so an edit here invalidates all three.
 */

import { useMemo } from 'react';

import { stateApi } from '../api/stateApi';
import type {
  CreateStateRequest,
  State,
  StateListParams,
  UpdateStateRequest,
} from '../models/State';

import { createMasterHooks } from './createMasterHooks';
import { MASTER_KEYS } from './masterQueryKeys';
import { buildMasterLookup, OPTION_LIMIT, type MasterLookup } from './useMasterLookup';

const hooks = createMasterHooks<State, CreateStateRequest, UpdateStateRequest, StateListParams>(
  stateApi,
  MASTER_KEYS.states,
  [MASTER_KEYS.categoriesOfLaw, MASTER_KEYS.legislations, MASTER_KEYS.rules],
);

export const useStates = hooks.useList;
export const useCreateState = hooks.useCreate;
export const useUpdateState = hooks.useUpdate;
export const useDeleteState = hooks.useDelete;

/**
 * Options for a state picker, plus a resolver for already-stored ids.
 *
 * @param countryId Narrows the options to one country. Pass the form's current
 *                  country so a state from a different country cannot be chosen.
 */
export const useStateLookup = (countryId?: number): MasterLookup => {
  const active = useStates({
    limit: OPTION_LIMIT,
    is_active: true,
    country_id: countryId,
  });
  const all = useStates({ limit: OPTION_LIMIT });
  return useMemo(
    () => buildMasterLookup(active.data?.items ?? [], all.data?.items ?? [], active.isLoading),
    [active.data, all.data, active.isLoading],
  );
};

/**
 * Country master query hooks.
 *
 * A country's label appears on the States, Legislations and Rules screens, so an
 * edit here invalidates all three.
 */

import { useMemo } from 'react';

import { countryApi } from '../api/countryApi';
import type {
  Country,
  CountryListParams,
  CreateCountryRequest,
  UpdateCountryRequest,
} from '../models/Country';

import { createMasterHooks } from './createMasterHooks';
import { MASTER_KEYS } from './masterQueryKeys';
import { buildMasterLookup, OPTION_LIMIT, type MasterLookup } from './useMasterLookup';

const hooks = createMasterHooks<
  Country,
  CreateCountryRequest,
  UpdateCountryRequest,
  CountryListParams
>(countryApi, MASTER_KEYS.countries, [
  MASTER_KEYS.states,
  MASTER_KEYS.legislations,
  MASTER_KEYS.rules,
]);

export const useCountries = hooks.useList;
export const useCreateCountry = hooks.useCreate;
export const useUpdateCountry = hooks.useUpdate;
export const useDeleteCountry = hooks.useDelete;

/** Options for a country picker, plus a resolver for already-stored ids. */
export const useCountryLookup = (): MasterLookup => {
  const active = useCountries({ limit: OPTION_LIMIT, is_active: true });
  const all = useCountries({ limit: OPTION_LIMIT });
  return useMemo(
    () => buildMasterLookup(active.data?.items ?? [], all.data?.items ?? [], active.isLoading),
    [active.data, all.data, active.isLoading],
  );
};

/**
 * Category of law master query hooks.
 *
 * A category's label appears on the Legislations screen, so an edit here
 * invalidates that cache too.
 */

import { useMemo } from 'react';

import { categoryOfLawApi } from '../api/categoryOfLawApi';
import type {
  CategoryOfLaw,
  CategoryOfLawListParams,
  CreateCategoryOfLawRequest,
  UpdateCategoryOfLawRequest,
} from '../models/CategoryOfLaw';

import { createMasterHooks } from './createMasterHooks';
import { MASTER_KEYS } from './masterQueryKeys';
import { buildMasterLookup, OPTION_LIMIT, type MasterLookup } from './useMasterLookup';

const hooks = createMasterHooks<
  CategoryOfLaw,
  CreateCategoryOfLawRequest,
  UpdateCategoryOfLawRequest,
  CategoryOfLawListParams
>(categoryOfLawApi, MASTER_KEYS.categoriesOfLaw, [MASTER_KEYS.legislations]);

export const useCategoriesOfLaw = hooks.useList;
export const useCreateCategoryOfLaw = hooks.useCreate;
export const useUpdateCategoryOfLaw = hooks.useUpdate;
export const useDeleteCategoryOfLaw = hooks.useDelete;

/** Options for a category picker, plus a resolver for already-stored ids. */
export const useCategoryOfLawLookup = (): MasterLookup => {
  const active = useCategoriesOfLaw({ limit: OPTION_LIMIT, is_active: true });
  const all = useCategoriesOfLaw({ limit: OPTION_LIMIT });
  return useMemo(
    () => buildMasterLookup(active.data?.items ?? [], all.data?.items ?? [], active.isLoading),
    [active.data, all.data, active.isLoading],
  );
};

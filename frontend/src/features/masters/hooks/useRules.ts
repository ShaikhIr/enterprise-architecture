/**
 * Rule master query hooks.
 *
 * Rules are the leaf of the hierarchy — nothing displays a rule's label, so there
 * are no dependent caches to invalidate.
 */

import { useMemo } from 'react';

import { ruleApi } from '../api/ruleApi';
import type { CreateRuleRequest, Rule, RuleListParams, UpdateRuleRequest } from '../models/Rule';

import { createMasterHooks } from './createMasterHooks';
import { MASTER_KEYS } from './masterQueryKeys';
import { buildMasterLookup, OPTION_LIMIT, type MasterLookup } from './useMasterLookup';

const hooks = createMasterHooks<Rule, CreateRuleRequest, UpdateRuleRequest, RuleListParams>(
  ruleApi,
  MASTER_KEYS.rules,
);

export const useRules = hooks.useList;
export const useCreateRule = hooks.useCreate;
export const useUpdateRule = hooks.useUpdate;
export const useDeleteRule = hooks.useDelete;

/**
 * Options for a rule picker, plus a resolver for already-stored ids.
 *
 * @param legislationId Narrows the options to one legislation. Pass the form's
 *                      current legislation so a rule framed under a different
 *                      act cannot be chosen — the backend rejects that
 *                      combination anyway.
 */
export const useRuleLookup = (legislationId?: number): MasterLookup => {
  const active = useRules({
    limit: OPTION_LIMIT,
    is_active: true,
    legislation_id: legislationId,
  });
  const all = useRules({ limit: OPTION_LIMIT });
  return useMemo(
    () => buildMasterLookup(active.data?.items ?? [], all.data?.items ?? [], active.isLoading),
    [active.data, all.data, active.isLoading],
  );
};

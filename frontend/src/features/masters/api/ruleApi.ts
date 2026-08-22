/**
 * Rule master API calls.
 * Maps to backend: /api/v1/masters/rules
 */

import type { CreateRuleRequest, Rule, RuleListParams, UpdateRuleRequest } from '../models/Rule';

import { createMasterApi } from './createMasterApi';

export const ruleApi = createMasterApi<Rule, CreateRuleRequest, UpdateRuleRequest, RuleListParams>(
  '/masters/rules',
  'rules',
);

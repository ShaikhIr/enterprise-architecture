/**
 * Rule master types.
 * Mirrors backend RuleResponse / RuleCreate / RuleUpdate.
 */

import type { MasterListParams, MasterRecord } from './common';

export interface Rule extends MasterRecord {
  code: string;
  name: string;
  description: string;
  legislation_id: string;
  country_id: string;
  /** null means the rule is central (country-wide). */
  state_id: string | null;
  rule_number: string | null;
  /** ISO date (yyyy-MM-dd), not a timestamp. */
  effective_date: string | null;
}

export interface CreateRuleRequest {
  code: string;
  name: string;
  description: string;
  legislation_id: string;
  country_id: string;
  state_id: string | null;
  rule_number: string | null;
  effective_date: string | null;
  is_active: boolean;
}

export type UpdateRuleRequest = Partial<CreateRuleRequest>;

export interface RuleListParams extends MasterListParams {
  country_id?: string;
  state_id?: string;
  legislation_id?: string;
}

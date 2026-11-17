/**
 * Legislation master types.
 * Mirrors backend LegislationResponse / LegislationCreate / LegislationUpdate.
 */

import type { MasterListParams, MasterRecord } from './common';

export interface Legislation extends MasterRecord {
  code: string;
  name: string;
  description: string;
  category_of_law_id: number;
  country_id: number;
  /** null means central (country-wide) legislation. */
  state_id: number | null;
  legislation_number: string | null;
  /** ISO date (yyyy-MM-dd), not a timestamp. */
  effective_date: string | null;
}

export interface CreateLegislationRequest {
  code: string;
  name: string;
  description: string;
  category_of_law_id: number;
  country_id: number;
  state_id: number | null;
  legislation_number: string | null;
  effective_date: string | null;
  is_active: boolean;
}

export type UpdateLegislationRequest = Partial<CreateLegislationRequest>;

export interface LegislationListParams extends MasterListParams {
  country_id?: number;
  state_id?: number;
  category_of_law_id?: number;
}

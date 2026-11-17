/**
 * Category of law master types.
 * Mirrors backend CategoryOfLawResponse / CategoryOfLawCreate / CategoryOfLawUpdate.
 */

import type { MasterListParams, MasterRecord } from './common';

export interface CategoryOfLaw extends MasterRecord {
  code: string;
  name: string;
  description: string;
  /** null means the category applies country-wide rather than to one state. */
  state_id: number | null;
}

export interface CreateCategoryOfLawRequest {
  code: string;
  name: string;
  description: string;
  state_id: number | null;
  is_active: boolean;
}

export type UpdateCategoryOfLawRequest = Partial<CreateCategoryOfLawRequest>;

export interface CategoryOfLawListParams extends MasterListParams {
  state_id?: number;
}

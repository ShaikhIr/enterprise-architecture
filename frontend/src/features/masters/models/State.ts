/**
 * State master types.
 * Mirrors backend StateResponse / StateCreate / StateUpdate.
 */

import type { MasterListParams, MasterRecord } from './common';

export interface State extends MasterRecord {
  code: string;
  name: string;
  country_id: number;
  is_union_territory: boolean;
}

export interface CreateStateRequest {
  code: string;
  name: string;
  country_id: number;
  is_union_territory: boolean;
  is_active: boolean;
}

export type UpdateStateRequest = Partial<CreateStateRequest>;

export interface StateListParams extends MasterListParams {
  country_id?: number;
}

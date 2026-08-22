/**
 * Task type master types.
 * Mirrors backend TaskTypeResponse / TaskTypeCreate / TaskTypeUpdate.
 *
 * Independent of the country/state hierarchy — task types are a flat lookup.
 */

import type { MasterListParams, MasterRecord } from './common';

export interface TaskType extends MasterRecord {
  code: string;
  name: string;
  description: string;
}

export interface CreateTaskTypeRequest {
  code: string;
  name: string;
  description: string;
  is_active: boolean;
}

export type UpdateTaskTypeRequest = Partial<CreateTaskTypeRequest>;

export type TaskTypeListParams = MasterListParams;

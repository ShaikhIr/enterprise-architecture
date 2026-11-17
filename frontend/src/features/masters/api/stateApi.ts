/**
 * State master API calls.
 * Maps to backend: /api/v1/masters/states
 */

import type {
  CreateStateRequest,
  State,
  StateListParams,
  UpdateStateRequest,
} from '../models/State';

import { createMasterApi } from './createMasterApi';

export const stateApi = createMasterApi<
  State,
  CreateStateRequest,
  UpdateStateRequest,
  StateListParams
>('/masters/states', 'states');

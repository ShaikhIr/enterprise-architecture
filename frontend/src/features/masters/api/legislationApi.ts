/**
 * Legislation master API calls.
 * Maps to backend: /api/v1/masters/legislations
 */

import type {
  CreateLegislationRequest,
  Legislation,
  LegislationListParams,
  UpdateLegislationRequest,
} from '../models/Legislation';

import { createMasterApi } from './createMasterApi';

export const legislationApi = createMasterApi<
  Legislation,
  CreateLegislationRequest,
  UpdateLegislationRequest,
  LegislationListParams
>('/masters/legislations', 'legislations');

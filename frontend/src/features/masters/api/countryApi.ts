/**
 * Country master API calls.
 * Maps to backend: /api/v1/masters/countries
 */

import type {
  Country,
  CountryListParams,
  CreateCountryRequest,
  UpdateCountryRequest,
} from '../models/Country';

import { createMasterApi } from './createMasterApi';

export const countryApi = createMasterApi<
  Country,
  CreateCountryRequest,
  UpdateCountryRequest,
  CountryListParams
>('/masters/countries', 'countries');

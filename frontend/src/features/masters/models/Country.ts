/**
 * Country master types.
 * Mirrors backend CountryResponse / CountryCreate / CountryUpdate.
 */

import type { MasterListParams, MasterRecord } from './common';

export interface Country extends MasterRecord {
  code: string;
  name: string;
  iso3_code: string | null;
  dial_code: string | null;
  currency_code: string | null;
}

export interface CreateCountryRequest {
  code: string;
  name: string;
  iso3_code: string | null;
  dial_code: string | null;
  currency_code: string | null;
  is_active: boolean;
}

export type UpdateCountryRequest = Partial<CreateCountryRequest>;

/** Backend search matches code, name or ISO3. */
export type CountryListParams = MasterListParams;

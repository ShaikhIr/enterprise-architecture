/**
 * Country Master API service.
 * Provides CRUD operations and Excel import/template download for countries.
 */

import { apiClient } from '@shared/services/apiClient';

export interface Country {
  id: string;
  country_code: string;
  country_name: string;
  region_id: string | null;
  region_name: string | null;
  is_active: boolean;
}

export interface CountryCreatePayload {
  country_code: string;
  country_name: string;
  region_id?: string | null;
}

export interface CountryUpdatePayload {
  country_code?: string;
  country_name?: string;
  region_id?: string | null;
  is_active?: boolean;
}

export interface ImportResult {
  created: number;
  skipped: number;
}

export const countryApi = {
  /** List countries. Pass includeInactive=true to include deactivated ones. */
  async getCountries(includeInactive = false): Promise<Country[]> {
    const params = includeInactive ? { include_inactive: 'true' } : {};
    const { data } = await apiClient.get<Country[]>('/masters/countries', { params });
    return data;
  },

  /** Create a new country. */
  async createCountry(payload: CountryCreatePayload): Promise<Country> {
    const { data } = await apiClient.post<Country>('/masters/countries', payload);
    return data;
  },

  /** Update an existing country by ID. */
  async updateCountry(id: string, payload: CountryUpdatePayload): Promise<Country> {
    const { data } = await apiClient.put<Country>(`/masters/countries/${id}`, payload);
    return data;
  },

  /** Soft-delete (deactivate) a country by ID. */
  async deleteCountry(id: string): Promise<void> {
    await apiClient.delete(`/masters/countries/${id}`);
  },

  /** Download Excel template for bulk import. */
  async downloadTemplate(): Promise<void> {
    const { data } = await apiClient.get('/masters/countries-template', {
      responseType: 'blob',
    });
    const url = window.URL.createObjectURL(data);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'countries_template.xlsx';
    a.click();
    window.URL.revokeObjectURL(url);
  },

  /** Import countries from an Excel file. */
  async importExcel(file: File): Promise<ImportResult> {
    const formData = new FormData();
    formData.append('file', file);
    const { data } = await apiClient.post<ImportResult>('/masters/countries-import', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return data;
  },
};

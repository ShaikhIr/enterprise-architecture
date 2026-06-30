/**
 * City Master API service.
 */

import { apiClient } from '@shared/services/apiClient';

export interface City {
  id: string;
  city_name: string;
  state_id: string;
  state_name: string | null;
  is_active: boolean;
}

export interface CityCreatePayload {
  state_id: string;
  city_name: string;
}

export interface CityUpdatePayload {
  state_id?: string;
  city_name?: string;
  is_active?: boolean;
}

export interface ImportResult {
  created: number;
  skipped: number;
}

export const cityApi = {
  async getCities(includeInactive = false): Promise<City[]> {
    const params = includeInactive ? { include_inactive: 'true' } : {};
    const { data } = await apiClient.get<City[]>('/masters/cities', { params });
    return data;
  },

  async createCity(payload: CityCreatePayload): Promise<City> {
    const { data } = await apiClient.post<City>('/masters/cities', payload);
    return data;
  },

  async updateCity(id: string, payload: CityUpdatePayload): Promise<City> {
    const { data } = await apiClient.put<City>(`/masters/cities/${id}`, payload);
    return data;
  },

  async deleteCity(id: string): Promise<void> {
    await apiClient.delete(`/masters/cities/${id}`);
  },

  async downloadTemplate(): Promise<void> {
    const { data } = await apiClient.get('/masters/cities-template', { responseType: 'blob' });
    const url = window.URL.createObjectURL(data);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'cities_template.xlsx';
    a.click();
    window.URL.revokeObjectURL(url);
  },

  async importExcel(file: File): Promise<ImportResult> {
    const formData = new FormData();
    formData.append('file', file);
    const { data } = await apiClient.post<ImportResult>('/masters/cities-import', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return data;
  },
};

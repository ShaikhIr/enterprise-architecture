/**
 * State Master API service.
 * Provides CRUD operations and Excel import/template download for states.
 */

import { apiClient } from '@shared/services/apiClient';

export interface State {
  id: string;
  country_id: string;
  country_name: string | null;
  language_key: string;
  state_name: string;
  is_active: boolean;
}

export interface StateCreatePayload {
  country_id: string;
  language_key: string;
  state_name: string;
}

export interface StateUpdatePayload {
  country_id?: string;
  language_key?: string;
  state_name?: string;
  is_active?: boolean;
}

export interface ImportResult {
  created: number;
  skipped: number;
}

export const stateApi = {
  async getStates(includeInactive = false): Promise<State[]> {
    const params = includeInactive ? { include_inactive: 'true' } : {};
    const { data } = await apiClient.get<State[]>('/masters/states', { params });
    return data;
  },

  async createState(payload: StateCreatePayload): Promise<State> {
    const { data } = await apiClient.post<State>('/masters/states', payload);
    return data;
  },

  async updateState(id: string, payload: StateUpdatePayload): Promise<State> {
    const { data } = await apiClient.put<State>(`/masters/states/${id}`, payload);
    return data;
  },

  async deleteState(id: string): Promise<void> {
    await apiClient.delete(`/masters/states/${id}`);
  },

  async downloadTemplate(): Promise<void> {
    const { data } = await apiClient.get('/masters/states-template', {
      responseType: 'blob',
    });
    const url = window.URL.createObjectURL(data);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'states_template.xlsx';
    a.click();
    window.URL.revokeObjectURL(url);
  },

  async importExcel(file: File): Promise<ImportResult> {
    const formData = new FormData();
    formData.append('file', file);
    const { data } = await apiClient.post<ImportResult>('/masters/states-import', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return data;
  },
};

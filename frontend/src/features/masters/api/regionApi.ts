/**
 * Region Master API service.
 * Provides CRUD operations and Excel import/template download for regions.
 */

import { apiClient } from '@shared/services/apiClient';

export interface Region {
  id: string;
  region_id: string | null;
  region_name: string;
  is_active: boolean;
}

export interface RegionCreatePayload {
  region_name: string;
  region_id?: string;
}

export interface RegionUpdatePayload {
  region_name?: string;
  region_id?: string;
  is_active?: boolean;
}

export interface ImportResult {
  created: number;
  skipped: number;
}

export const regionApi = {
  /** List regions. Pass includeInactive=true to include deactivated regions. */
  async getRegions(includeInactive = false): Promise<Region[]> {
    const params = includeInactive ? { include_inactive: 'true' } : {};
    const { data } = await apiClient.get<Region[]>('/masters/regions', { params });
    return data;
  },

  /** Create a new region. */
  async createRegion(payload: RegionCreatePayload): Promise<Region> {
    const { data } = await apiClient.post<Region>('/masters/regions', payload);
    return data;
  },

  /** Update an existing region by ID. */
  async updateRegion(id: string, payload: RegionUpdatePayload): Promise<Region> {
    const { data } = await apiClient.put<Region>(`/masters/regions/${id}`, payload);
    return data;
  },

  /** Soft-delete (deactivate) a region by ID. */
  async deleteRegion(id: string): Promise<void> {
    await apiClient.delete(`/masters/regions/${id}`);
  },

  /** Download Excel template for bulk import. */
  async downloadTemplate(): Promise<void> {
    const { data } = await apiClient.get('/masters/regions-template', {
      responseType: 'blob',
    });
    const url = window.URL.createObjectURL(data);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'regions_template.xlsx';
    a.click();
    window.URL.revokeObjectURL(url);
  },

  /** Import regions from an Excel file. */
  async importExcel(file: File): Promise<ImportResult> {
    const formData = new FormData();
    formData.append('file', file);
    const { data } = await apiClient.post<ImportResult>('/masters/regions-import', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return data;
  },
};

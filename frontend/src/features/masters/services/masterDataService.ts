/**
 * Master Data API service.
 * Centralized service for all master data CRUD operations.
 */

import { apiClient } from '@shared/services/apiClient';

// ============================================================
// Types
// ============================================================

export interface ProductType {
  id: string;
  product_type_name: string;
  is_active: boolean;
}

export interface PackStyle {
  id: string;
  pack_style: string;
  is_active: boolean;
}

export interface Pallet {
  id: string;
  name: string;
  length: number | null;
  width: number | null;
  height: number | null;
  gross_weight_per_pack_type: number | null;
  volumetric_weight: number | null;
  is_active: boolean;
}

// ============================================================
// Product Type Master
// ============================================================

export const productTypeService = {
  list: (includeInactive = false) =>
    apiClient.get<ProductType[]>('/masters/product-types', {
      params: { include_inactive: includeInactive },
    }),

  create: (data: { product_type_name: string }) =>
    apiClient.post<ProductType>('/masters/product-types', data),

  update: (id: string, data: { product_type_name?: string; is_active?: boolean }) =>
    apiClient.put<ProductType>(`/masters/product-types/${id}`, data),

  delete: (id: string) =>
    apiClient.delete(`/masters/product-types/${id}`),
};

// ============================================================
// Pack Style Master
// ============================================================

export const packStyleService = {
  list: (includeInactive = false) =>
    apiClient.get<PackStyle[]>('/masters/pack-styles', {
      params: { include_inactive: includeInactive },
    }),

  create: (data: { pack_style: string }) =>
    apiClient.post<PackStyle>('/masters/pack-styles', data),

  update: (id: string, data: { pack_style?: string; is_active?: boolean }) =>
    apiClient.put<PackStyle>(`/masters/pack-styles/${id}`, data),

  delete: (id: string) =>
    apiClient.delete(`/masters/pack-styles/${id}`),
};

// ============================================================
// Type of Pallet Master
// ============================================================

export const palletService = {
  list: (includeInactive = false) =>
    apiClient.get<Pallet[]>('/masters/pallets', {
      params: { include_inactive: includeInactive },
    }),

  create: (data: Omit<Pallet, 'id' | 'is_active'>) =>
    apiClient.post<Pallet>('/masters/pallets', data),

  update: (id: string, data: Partial<Omit<Pallet, 'id'>>) =>
    apiClient.put<Pallet>(`/masters/pallets/${id}`, data),

  delete: (id: string) =>
    apiClient.delete(`/masters/pallets/${id}`),

  importExcel: (file: File) => {
    const formData = new FormData();
    formData.append('file', file);
    return apiClient.post<{ created: number; skipped: number }>(
      '/masters/pallets-import',
      formData,
    );
  },

  downloadTemplate: () =>
    apiClient.get('/masters/pallets-template', { responseType: 'blob' }),
};

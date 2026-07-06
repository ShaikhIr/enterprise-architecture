import { apiClient } from '@shared/services/apiClient';
import type { Vendor, VendorListResponse, CreateVendorRequest, UpdateVendorRequest } from '../models/vendor';
import type { PaginatedParams } from '../models/common';

export const vendorApi = {
  list: async (params: PaginatedParams): Promise<VendorListResponse> => {
    const { data } = await apiClient.get<VendorListResponse>('/vendors', { params });
    return data;
  },

  getById: async (id: string): Promise<Vendor> => {
    const { data } = await apiClient.get<Vendor>(`/vendors/${id}`);
    return data;
  },

  create: async (request: CreateVendorRequest): Promise<Vendor> => {
    const { data } = await apiClient.post<Vendor>('/vendors', request);
    return data;
  },

  update: async (id: string, request: UpdateVendorRequest): Promise<Vendor> => {
    const { data } = await apiClient.patch<Vendor>(`/vendors/${id}`, request);
    return data;
  },

  deactivate: async (id: string): Promise<void> => {
    await apiClient.post(`/vendors/${id}/deactivate`);
  },
};

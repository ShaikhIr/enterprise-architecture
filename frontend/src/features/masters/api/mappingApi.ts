import { apiClient } from '@shared/services/apiClient';
import type { VendorCustomerMapping, MappingListResponse, CreateMappingRequest, UpdateMappingRequest } from '../models/mapping';
import type { PaginatedParams } from '../models/common';

export const mappingApi = {
  list: async (params: PaginatedParams): Promise<MappingListResponse> => {
    const { data } = await apiClient.get<MappingListResponse>('/mappings', { params });
    return data;
  },

  getById: async (id: string): Promise<VendorCustomerMapping> => {
    const { data } = await apiClient.get<VendorCustomerMapping>(`/mappings/${id}`);
    return data;
  },

  create: async (request: CreateMappingRequest): Promise<VendorCustomerMapping> => {
    const { data } = await apiClient.post<VendorCustomerMapping>('/mappings', request);
    return data;
  },

  update: async (id: string, request: UpdateMappingRequest): Promise<VendorCustomerMapping> => {
    const { data } = await apiClient.patch<VendorCustomerMapping>(`/mappings/${id}`, request);
    return data;
  },

  delete: async (id: string): Promise<void> => {
    await apiClient.delete(`/mappings/${id}`);
  },
};

import { apiClient } from '@shared/services/apiClient';
import type {
  ProductMaster,
  ProductMasterListResponse,
  CreateProductMasterRequest,
  UpdateProductMasterRequest,
} from '../models/productMaster';
import type { PaginatedParams } from '../models/common';

export const productMasterApi = {
  list: async (params: PaginatedParams): Promise<ProductMasterListResponse> => {
    const { data } = await apiClient.get<ProductMasterListResponse>('/product-masters', { params });
    return data;
  },

  getById: async (id: string): Promise<ProductMaster> => {
    const { data } = await apiClient.get<ProductMaster>(`/product-masters/${id}`);
    return data;
  },

  create: async (request: CreateProductMasterRequest): Promise<ProductMaster> => {
    const { data } = await apiClient.post<ProductMaster>('/product-masters', request);
    return data;
  },

  update: async (id: string, request: UpdateProductMasterRequest): Promise<ProductMaster> => {
    const { data } = await apiClient.patch<ProductMaster>(`/product-masters/${id}`, request);
    return data;
  },
};

import { apiClient } from '@shared/services/apiClient';
import type { Customer, CustomerListResponse, CreateCustomerRequest, UpdateCustomerRequest } from '../models/customer';
import type { PaginatedParams } from '../models/common';

export const customerApi = {
  list: async (params: PaginatedParams): Promise<CustomerListResponse> => {
    const { data } = await apiClient.get<CustomerListResponse>('/customers', { params });
    return data;
  },

  getById: async (id: string): Promise<Customer> => {
    const { data } = await apiClient.get<Customer>(`/customers/${id}`);
    return data;
  },

  create: async (request: CreateCustomerRequest): Promise<Customer> => {
    const { data } = await apiClient.post<Customer>('/customers', request);
    return data;
  },

  update: async (id: string, request: UpdateCustomerRequest): Promise<Customer> => {
    const { data } = await apiClient.patch<Customer>(`/customers/${id}`, request);
    return data;
  },

  delete: async (id: string): Promise<void> => {
    await apiClient.delete(`/customers/${id}`);
  },
};

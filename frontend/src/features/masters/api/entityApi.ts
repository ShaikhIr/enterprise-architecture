import { apiClient } from '@shared/services/apiClient';
import type { Entity, EntityListResponse, CreateEntityRequest, UpdateEntityRequest, EntityDropdownItem } from '../models/entity';
import type { PaginatedParams } from '../models/common';

export const entityApi = {
  list: async (params: PaginatedParams): Promise<EntityListResponse> => {
    const { data } = await apiClient.get<EntityListResponse>('/entities', { params });
    return data;
  },

  dropdown: async (): Promise<EntityDropdownItem[]> => {
    const { data } = await apiClient.get<EntityDropdownItem[]>('/entities/dropdown');
    return data;
  },

  getById: async (id: string): Promise<Entity> => {
    const { data } = await apiClient.get<Entity>(`/entities/${id}`);
    return data;
  },

  create: async (request: CreateEntityRequest): Promise<Entity> => {
    const { data } = await apiClient.post<Entity>('/entities', request);
    return data;
  },

  update: async (id: string, request: UpdateEntityRequest): Promise<Entity> => {
    const { data } = await apiClient.patch<Entity>(`/entities/${id}`, request);
    return data;
  },
};

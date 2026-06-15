/**
 * User Management API calls.
 * Maps to backend: GET/POST /api/v1/users, GET/PATCH /api/v1/users/{id}
 */

import { apiClient } from '@shared/services/apiClient';
import type {
  CreateUserRequest,
  UpdateUserRequest,
  User,
  UserListResponse,
} from '../models/User';

export const userApi = {
  listUsers: async (skip = 0, limit = 100): Promise<UserListResponse> => {
    const { data } = await apiClient.get<UserListResponse>('/users', {
      params: { skip, limit },
    });
    return data;
  },

  getUserById: async (userId: string): Promise<User> => {
    const { data } = await apiClient.get<User>(`/users/${userId}`);
    return data;
  },

  createUser: async (request: CreateUserRequest): Promise<User> => {
    const { data } = await apiClient.post<User>('/users', request);
    return data;
  },

  updateUser: async (userId: string, request: UpdateUserRequest): Promise<User> => {
    const { data } = await apiClient.patch<User>(`/users/${userId}`, request);
    return data;
  },
};

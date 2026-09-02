/**
 * User Management API calls.
 * Maps to backend: GET/POST /api/v1/users, GET/PATCH /api/v1/users/{id}
 */

import { apiClient } from '@shared/services/apiClient';
import { fetchAllPages } from '@shared/utils/fetchAllPages';

import type {
  CreateUserRequest,
  ImportEmployeesResponse,
  UpdateUserRequest,
  User,
  UserListResponse,
  UserRolesResponse,
} from '../models/User';

export const userApi = {
  listUsers: async (skip = 0, limit = 100): Promise<UserListResponse> => {
    const { data } = await apiClient.get<UserListResponse>('/users', {
      params: { skip, limit },
    });
    return data;
  },

  /**
   * The whole directory, for resolving ids to names.
   *
   * There are more users than the endpoint's 500-row page, so a lookup built from a
   * single request would fail to name anyone past the first page — and would do it
   * silently, showing an empty dropdown rather than an error.
   */
  listAllUsers: async (): Promise<User[]> =>
    fetchAllPages<User>(async (skip, limit) => {
      const page = await userApi.listUsers(skip, limit);
      return { items: page.users, total: page.total };
    }),

  getUserById: async (userId: number): Promise<User> => {
    const { data } = await apiClient.get<User>(`/users/${userId}`);
    return data;
  },

  createUser: async (request: CreateUserRequest): Promise<User> => {
    const { data } = await apiClient.post<User>('/users', request);
    return data;
  },

  updateUser: async (userId: number, request: UpdateUserRequest): Promise<User> => {
    const { data } = await apiClient.patch<User>(`/users/${userId}`, request);
    return data;
  },

  getUserRoles: async (userId: number): Promise<UserRolesResponse> => {
    const { data } = await apiClient.get<UserRolesResponse>(`/users/${userId}/roles`);
    return data;
  },

  importEmployees: async (employeeIds: string[]): Promise<ImportEmployeesResponse> => {
    const { data } = await apiClient.post<ImportEmployeesResponse>('/users/import-employees', {
      employee_ids: employeeIds,
    });
    return data;
  },
};

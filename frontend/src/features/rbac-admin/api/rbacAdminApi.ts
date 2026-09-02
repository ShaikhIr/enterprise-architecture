/**
 * RBAC Admin API client.
 * Provides CRUD operations for roles, permissions, and audit logs.
 */

import { apiClient } from '@shared/services/apiClient';

import type {
  AuditLogListResponse,
  CreateRoleRequest,
  Permission,
  PermissionGrantRequest,
  RbacAck,
  Role,
  RoleAssignRequest,
  RoleAssignment,
  RoleListResponse,
  UpdateRoleRequest,
} from '../models/rbac-admin.types';

const BASE = '/rbac';

export const rbacAdminApi = {
  // ─── Roles ───

  async listRoles(tenantId?: number): Promise<RoleListResponse> {
    const params = tenantId ? { tenant_id: tenantId } : {};
    const response = await apiClient.get<RoleListResponse>(`${BASE}/roles`, { params });
    return response.data;
  },

  async createRole(data: CreateRoleRequest): Promise<Role> {
    const response = await apiClient.post<Role>(`${BASE}/roles`, data);
    return response.data;
  },

  async updateRole(roleId: number, data: UpdateRoleRequest): Promise<Role> {
    const response = await apiClient.patch<Role>(`${BASE}/roles/${roleId}`, data);
    return response.data;
  },

  // ─── Permissions ───

  async listPermissions(scope?: string): Promise<Permission[]> {
    const params = scope ? { scope } : {};
    const response = await apiClient.get<Permission[]>(`${BASE}/permissions`, { params });
    return response.data;
  },

  /*
    Grant and revoke answer with an acknowledgement dictionary rather than a schema, so
    the return type is deliberately open. What matters to the caller is that no error was
    thrown.
  */
  async grantPermission(data: PermissionGrantRequest): Promise<RbacAck> {
    const response = await apiClient.post<RbacAck>(`${BASE}/roles/grant-permission`, data);
    return response.data;
  },

  async revokePermission(data: PermissionGrantRequest): Promise<RbacAck> {
    const response = await apiClient.post<RbacAck>(`${BASE}/roles/revoke-permission`, data);
    return response.data;
  },

  // ─── Role Assignments ───

  async assignRole(data: RoleAssignRequest): Promise<RoleAssignment> {
    const response = await apiClient.post<RoleAssignment>(`${BASE}/assignments`, data);
    return response.data;
  },

  async revokeRole(data: RoleAssignRequest): Promise<RbacAck> {
    const response = await apiClient.post<RbacAck>(`${BASE}/assignments/revoke`, data);
    return response.data;
  },

  // ─── Audit Logs ───

  async listAuditLogs(params?: {
    action?: string;
    actor_username?: string;
    resource_type?: string;
    skip?: number;
    limit?: number;
  }): Promise<AuditLogListResponse> {
    const response = await apiClient.get<AuditLogListResponse>(`${BASE}/audit-logs`, { params });
    return response.data;
  },
};

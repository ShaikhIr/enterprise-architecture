/** User domain types matching backend UserResponse */

export interface User {
  id: string;
  username: string;
  is_active: boolean;
  is_blocked: boolean;
  is_validate_ad: boolean;
  employee_id: string | null;
  employee_name: string | null;
  email: string | null;
  last_login: string | null;
  created_by: string;
  created_date: string;
  modified_by: string;
  modified_date: string;
}

export interface UserDetails {
  id: string;
  username: string;
  is_active: boolean;
  is_blocked: boolean;
  is_validate_ad: boolean;
  employee_id: string | null;
  employee_name: string | null;
  first_name: string | null;
  middle_name: string | null;
  last_name: string | null;
  email: string | null;
  entity_id: string | null;
  designation_title: string | null;
  department: string | null;
  created_by: string;
  created_date: string;
  modified_by: string;
  modified_date: string;
}

export interface UserListResponse {
  users: User[];
  total: number;
  skip: number;
  limit: number;
}

export interface CreateUserRequest {
  employee_id: string;
  username: string;
  password?: string;
  email?: string;
  first_name?: string;
  last_name?: string;
  is_validate_ad: boolean;
  role_id: string | null;
  entity_id?: string;
}

export interface UpdateUserRequest {
  is_active?: boolean;
  is_blocked?: boolean;
  is_validate_ad?: boolean;
  /** Replaces all existing role assignments when supplied */
  role_ids?: string[] | null;
  email?: string;
  first_name?: string;
  last_name?: string;
  /** Non-empty (≥ 8 chars) sets a new password when AD is disabled */
  change_password?: string;
  entity_id?: string;
}

export interface RolePermission {
  code: string;
  name: string;
  scope: string;
  resource: string;
  action: string;
}

export interface UserRole {
  id: string;
  code: string;
  name: string;
  permissions: RolePermission[];
}

export interface UserRolesResponse {
  user_id: string;
  roles: UserRole[];
}

export interface ImportResult {
  employee_id: string;
  status: 'created' | 'updated' | 'failed';
  message?: string;
}

export interface ImportEmployeesResponse {
  total: number;
  created: number;
  updated: number;
  failed: number;
  results: ImportResult[];
}

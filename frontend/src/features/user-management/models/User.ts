/** User domain types matching backend UserResponse */

export interface User {
  id: string;
  username: string;
  is_active: boolean;
  is_blocked: boolean;
  role: string;
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
  username: string;
  password: string;
  role: string;
}

export interface UpdateUserRequest {
  is_active?: boolean;
  is_blocked?: boolean;
  role?: string;
}

export type UserRole = 'ADMIN' | 'MANAGER' | 'USER';

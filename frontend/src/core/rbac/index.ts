/**
 * RBAC module public API.
 */

// Components
export { ActionGate, FieldGate, MenuGate, PermissionGate } from './PermissionGate';

// Hooks
export {
  useApiPermissions,
  useCan,
  useFieldPermissions,
  useHasPermission,
  useMenuPermission,
  useMenuPermissions,
} from './usePermissions';

// Redux
export {
  clearRbac,
  fetchApiPermissions,
  fetchFieldPermissions,
  fetchMenuPermissions,
} from './rbacSlice';
export { default as rbacReducer } from './rbacSlice';

// Types
export type {
  ApiPermissionsResponse,
  AuditLogEntry,
  AuditLogListResponse,
  FieldPermissionsResponse,
  MenuPermissionsResponse,
  Permission,
  PermissionAction,
  PermissionScope,
  Role,
  RoleAssignment,
} from './types';

// API
export { rbacApi } from './rbacApi';

/**
 * The caller's CRUD permissions for one master resource.
 *
 * Resolved from the API-scope grants, so it matches exactly what
 * `require_api_permission(resource, action)` enforces on the endpoint. Screens use
 * it to hide controls that would only produce a 403 — the guard on the server is
 * still what enforces it; this only avoids offering a dead button.
 */

import { useCan } from '@core/rbac';

export interface MasterPermissions {
  canCreate: boolean;
  canUpdate: boolean;
  canDelete: boolean;
  /** True when at least one row-level action is available. */
  canModifyRows: boolean;
}

/**
 * @param resource Resource name as the backend authorises it, e.g. "countries".
 */
export const useMasterPermissions = (resource: string): MasterPermissions => {
  const canCreate = useCan(resource, 'CREATE');
  const canUpdate = useCan(resource, 'UPDATE');
  const canDelete = useCan(resource, 'DELETE');

  return {
    canCreate,
    canUpdate,
    canDelete,
    canModifyRows: canUpdate || canDelete,
  };
};

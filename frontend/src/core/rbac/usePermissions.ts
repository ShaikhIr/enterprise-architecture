/**
 * Permission hooks for components.
 * Provides declarative access to RBAC checks throughout the app.
 */

import { useCallback, useEffect } from 'react';

import { useAppDispatch, useAppSelector } from '@app/store';

import { fetchApiPermissions, fetchFieldPermissions, fetchMenuPermissions } from './rbacSlice';
import type { PermissionAction } from './types';

/**
 * Hook to check if the current user has access to a specific menu item.
 *
 * @example
 * const { canAccess } = useMenuPermission('users');
 * if (canAccess) { ... }
 */
export const useMenuPermission = (menuKey: string) => {
  const { menuKeys, isLoaded } = useAppSelector((state) => state.rbac);

  return {
    canAccess: isLoaded && menuKeys.includes(menuKey),
    isLoaded,
  };
};

/**
 * Hook to get all menu keys the user can access.
 * Used by navigation components to filter visible items.
 *
 * @example
 * const { menuKeys, isLoaded } = useMenuPermissions();
 */
export const useMenuPermissions = () => {
  const dispatch = useAppDispatch();
  const { menuKeys, isLoaded, isLoading } = useAppSelector((state) => state.rbac);

  useEffect(() => {
    if (!isLoaded && !isLoading) {
      dispatch(fetchMenuPermissions());
    }
  }, [dispatch, isLoaded, isLoading]);

  return { menuKeys, isLoaded, isLoading };
};

/**
 * Hook to check field-level permissions for a resource.
 * Lazy-loads field permissions on first access.
 *
 * @example
 * const { canReadField, canWriteField } = useFieldPermissions('users');
 * const showSalary = canReadField('salary');
 * const canEditEmail = canWriteField('email');
 */
export const useFieldPermissions = (resource: string) => {
  const dispatch = useAppDispatch();
  const fieldPermissions = useAppSelector((state) => state.rbac.fieldPermissions[resource]);
  const status = useAppSelector((state) => state.rbac.fieldPermissionStatus[resource]);

  useEffect(() => {
    // Only when nothing has been tried yet. Retrying on 'error' from here would loop,
    // since the failure is what re-runs the effect.
    if (!status) {
      dispatch(fetchFieldPermissions(resource));
    }
  }, [dispatch, resource, status]);

  const retry = useCallback(() => {
    dispatch(fetchFieldPermissions(resource));
  }, [dispatch, resource]);

  const canReadField = useCallback(
    (fieldName: string): boolean => {
      if (!fieldPermissions) return false;
      const actions = fieldPermissions[fieldName];
      return actions ? actions.includes('READ') : false;
    },
    [fieldPermissions],
  );

  const canWriteField = useCallback(
    (fieldName: string): boolean => {
      if (!fieldPermissions) return false;
      const actions = fieldPermissions[fieldName];
      return actions ? actions.includes('UPDATE') : false;
    },
    [fieldPermissions],
  );

  const getFieldActions = useCallback(
    (fieldName: string): PermissionAction[] => {
      if (!fieldPermissions) return [];
      return fieldPermissions[fieldName] || [];
    },
    [fieldPermissions],
  );

  return {
    canReadField,
    canWriteField,
    getFieldActions,
    /** Grants are in hand. */
    isLoaded: !!fieldPermissions,
    isLoading: status === 'loading' || !status,
    failed: status === 'error',
    /**
     * The question has been answered one way or the other.
     *
     * What a spinner should watch, rather than `isLoaded`: a failed fetch is never going
     * to become loaded, and a control that waits for that waits forever.
     */
    isSettled: !!fieldPermissions || status === 'error',
    retry,
  };
};

/**
 * Loads the caller's API-scope permissions once, and reports readiness.
 *
 * Kept separate from `useMenuPermissions` so navigation is never blocked on this
 * request: menu keys decide what you can reach, API grants only decide which
 * buttons are worth showing.
 *
 * @example
 * const { isLoaded } = useApiPermissions();
 */
export const useApiPermissions = () => {
  const dispatch = useAppDispatch();
  const { apiCodes, apiResourceActions, isApiLoaded } = useAppSelector((state) => state.rbac);

  useEffect(() => {
    if (!isApiLoaded) {
      dispatch(fetchApiPermissions());
    }
  }, [dispatch, isApiLoaded]);

  return { apiCodes, apiResourceActions, isLoaded: isApiLoaded };
};

/**
 * Hook to check a specific permission code.
 *
 * Checks the API-scope grants as well as the menu ones. It previously looked only
 * at `menuPermissions`, which meant any check against an API code such as
 * `countries.create` was always false — hiding the control from every user,
 * administrators included.
 *
 * @example
 * const hasPermission = useHasPermission('reports.export');
 */
export const useHasPermission = (permissionCode: string): boolean => {
  const { menuPermissions, apiCodes, isLoaded, isApiLoaded } = useAppSelector(
    (state) => state.rbac,
  );
  const dispatch = useAppDispatch();

  // Self-loading: a gate can be rendered anywhere, so it cannot rely on an
  // ancestor having asked for the API grants first.
  useEffect(() => {
    if (!isApiLoaded) {
      dispatch(fetchApiPermissions());
    }
  }, [dispatch, isApiLoaded]);

  if (apiCodes.includes(permissionCode)) return true;
  if (!isLoaded) return false;
  return menuPermissions.some((p) => p.code === permissionCode);
};

/**
 * Hook to check an API permission by the (resource, action) pair the backend
 * authorises on — the same pair `require_api_permission` compares against.
 *
 * Preferred over `useHasPermission` for CRUD controls, because it does not assume
 * the permission code follows a `resource.action` naming convention.
 *
 * @example
 * const canCreate = useCan('countries', 'CREATE');
 */
export const useCan = (resource: string, action: PermissionAction): boolean => {
  const { apiResourceActions, isApiLoaded } = useAppSelector((state) => state.rbac);
  const dispatch = useAppDispatch();

  useEffect(() => {
    if (!isApiLoaded) {
      dispatch(fetchApiPermissions());
    }
  }, [dispatch, isApiLoaded]);

  // Closed until the grants are known, so a control never flashes into view and
  // then disappears.
  if (!isApiLoaded) return false;
  return apiResourceActions[resource]?.includes(action) ?? false;
};

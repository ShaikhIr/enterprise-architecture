/**
 * Hook to fetch roles from the RBAC roles table.
 * Used in user create/edit forms to populate the role dropdown dynamically.
 */

import { useEffect, useState } from 'react';
import { apiClient } from '@shared/services/apiClient';

interface RoleOption {
  label: string;
  value: string;
}

interface RoleFromApi {
  id: string;
  code: string;
  name: string;
  is_active: boolean;
}

interface RoleListResponse {
  roles: RoleFromApi[];
  total: number;
}

export const useRoles = () => {
  const [roleOptions, setRoleOptions] = useState<RoleOption[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchRoles = async () => {
      try {
        const response = await apiClient.get<RoleListResponse>('/rbac/roles');
        const options = response.data.roles
          .filter((r) => r.is_active)
          .map((r) => ({
            label: r.name,
            value: r.code,
          }));
        setRoleOptions(options);
      } catch {
        // Fallback to defaults if RBAC endpoint is unavailable
        setRoleOptions([
          { label: 'Admin', value: 'ADMIN' },
          { label: 'Manager', value: 'MANAGER' },
          { label: 'User', value: 'USER' },
        ]);
      } finally {
        setLoading(false);
      }
    };

    fetchRoles();
  }, []);

  return { roleOptions, loading };
};

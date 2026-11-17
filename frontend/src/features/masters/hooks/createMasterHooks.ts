/**
 * Query-hook factory for master data.
 *
 * Shares the caching mechanics — key derivation, invalidation on write — across
 * the six masters. Each master re-exports these under its own names so call sites
 * read as `useCountries()` rather than a generic lookup.
 */

import { useMutation, useQuery, useQueryClient, type QueryKey } from '@tanstack/react-query';

import type { MasterApi } from '../api/createMasterApi';
import type { MasterListParams } from '../models/common';

export const createMasterHooks = <TEntity, TCreate, TUpdate, TParams extends MasterListParams>(
  api: MasterApi<TEntity, TCreate, TUpdate, TParams>,
  key: QueryKey,
  /**
   * Caches that display this master's labels and so go stale when it changes.
   * Renaming a country changes the Country column on the States screen, so that
   * cache cannot be left holding the old label.
   */
  dependentKeys: QueryKey[] = [],
) => {
  /**
   * @param options.enabled Hold the request back until the caller is ready. Screens
   *                        whose filters are mandatory use it so nothing is fetched
   *                        until a valid combination has been chosen — the default
   *                        stays `true` so ordinary list screens are unaffected.
   */
  const useList = (params?: TParams, options?: { enabled?: boolean }) =>
    useQuery({
      queryKey: [...key, params ?? {}],
      queryFn: () => api.list(params),
      staleTime: 30_000,
      enabled: options?.enabled ?? true,
    });

  const useInvalidate = () => {
    const queryClient = useQueryClient();
    return () => {
      queryClient.invalidateQueries({ queryKey: key });
      for (const dependent of dependentKeys) {
        queryClient.invalidateQueries({ queryKey: dependent });
      }
    };
  };

  const useCreate = () => {
    const invalidate = useInvalidate();
    return useMutation({
      mutationFn: (request: TCreate) => api.create(request),
      onSuccess: invalidate,
    });
  };

  const useUpdate = () => {
    const invalidate = useInvalidate();
    return useMutation({
      mutationFn: ({ id, request }: { id: number; request: TUpdate }) => api.update(id, request),
      onSuccess: invalidate,
    });
  };

  const useDelete = () => {
    const invalidate = useInvalidate();
    return useMutation({
      mutationFn: (id: number) => api.remove(id),
      onSuccess: invalidate,
    });
  };

  return { useList, useCreate, useUpdate, useDelete };
};

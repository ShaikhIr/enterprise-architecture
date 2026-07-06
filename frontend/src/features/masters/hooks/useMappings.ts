import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { mappingApi } from '../api/mappingApi';
import type { PaginatedParams } from '../models/common';
import type { UpdateMappingRequest } from '../models/mapping';
import { useAppSelector } from '@app/store';

const MAPPINGS_KEY = ['mappings'];

/**
 * Fetches paginated mappings list.
 * If the current user is a vendor agent (has vendor_id), automatically applies vendor_id filter.
 */
export const useMappings = (params: PaginatedParams) => {
  const user = useAppSelector((state) => state.auth.user);
  const vendorId = user?.vendor_id ?? undefined;

  const effectiveParams: PaginatedParams = vendorId
    ? { ...params, vendor_id: vendorId }
    : params;

  return useQuery({
    queryKey: [...MAPPINGS_KEY, effectiveParams],
    queryFn: () => mappingApi.list(effectiveParams),
    staleTime: 30_000,
  });
};

export const useCreateMapping = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: mappingApi.create,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: MAPPINGS_KEY }),
  });
};

export const useUpdateMapping = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, request }: { id: string; request: UpdateMappingRequest }) =>
      mappingApi.update(id, request),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: MAPPINGS_KEY }),
  });
};

export const useDeleteMapping = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: mappingApi.delete,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: MAPPINGS_KEY }),
  });
};

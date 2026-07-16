import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { vendorApi } from '../api/vendorApi';
import type { CreateVendorRequest, UpdateVendorRequest } from '../models/vendor';
import type { PaginatedParams } from '../models/common';

const VENDORS_KEY = ['vendors'];

export const useVendors = (params: PaginatedParams, options?: { enabled?: boolean }) => {
  return useQuery({
    queryKey: [...VENDORS_KEY, params],
    queryFn: () => vendorApi.list(params),
    staleTime: 30_000,
    enabled: options?.enabled ?? true,
  });
};

export const useCreateVendor = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (request: CreateVendorRequest) => vendorApi.create(request),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: VENDORS_KEY }),
  });
};

export const useUpdateVendor = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, request }: { id: string; request: UpdateVendorRequest }) =>
      vendorApi.update(id, request),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: VENDORS_KEY }),
  });
};

export const useDeactivateVendor = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => vendorApi.deactivate(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: VENDORS_KEY }),
  });
};

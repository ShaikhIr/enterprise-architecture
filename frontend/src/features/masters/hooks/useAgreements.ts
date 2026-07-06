import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { agreementApi } from '../api/agreementApi';
import type { CreateAgreementRequest, UpdateAgreementRequest, RenewAgreementRequest } from '../models/agreement';
import type { PaginatedParams } from '../models/common';
import { useAppSelector } from '@app/store';

const AGREEMENTS_KEY = ['agreements'];

/**
 * Fetches a paginated list of agreements.
 * When the logged-in user has the vendor agent role, a vendor_id filter is
 * automatically applied so that only agreements belonging to their associated
 * vendor are returned.
 */
export const useAgreements = (params: PaginatedParams) => {
  const user = useAppSelector((state) => state.auth.user);

  // If the authenticated user is a vendor agent, inject their vendor_id filter
  const effectiveParams: PaginatedParams = user && user.vendor_id
    ? { ...params, vendor_id: user.vendor_id }
    : params;

  return useQuery({
    queryKey: [...AGREEMENTS_KEY, effectiveParams],
    queryFn: () => agreementApi.list(effectiveParams),
    staleTime: 30_000,
  });
};

export const useCreateAgreement = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (request: CreateAgreementRequest) => agreementApi.create(request),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: AGREEMENTS_KEY }),
  });
};

export const useUpdateAgreement = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, request }: { id: string; request: UpdateAgreementRequest }) =>
      agreementApi.update(id, request),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: AGREEMENTS_KEY }),
  });
};

export const useRenewAgreement = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, request }: { id: string; request: RenewAgreementRequest }) =>
      agreementApi.renew(id, request),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: AGREEMENTS_KEY }),
  });
};

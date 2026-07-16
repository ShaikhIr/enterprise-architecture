import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { claimApi } from '../api/claimApi';
import type { ClaimListParams } from '../api/claimApi';

const CLAIMS_KEY = ['claims'];
const CLAIMS_TAB_DRAFT_KEY = ['claims', 'tab', 'draft'];
const CLAIMS_TAB_PENDING_KEY = ['claims', 'tab', 'pending'];
const CLAIMS_TAB_CLOSED_KEY = ['claims', 'tab', 'closed'];

export const useClaims = (params?: ClaimListParams) => {
  return useQuery({
    queryKey: [...CLAIMS_KEY, params],
    queryFn: () => claimApi.list(params),
    staleTime: 30_000,
  });
};

export const useClaimsTabDraft = (params?: ClaimListParams, options?: { enabled?: boolean }) => {
  return useQuery({
    queryKey: [...CLAIMS_TAB_DRAFT_KEY, params],
    queryFn: () => claimApi.getTabDraft(params),
    staleTime: 30_000,
    enabled: options?.enabled !== false,
  });
};

export const useClaimsTabPending = (params?: ClaimListParams, options?: { enabled?: boolean }) => {
  return useQuery({
    queryKey: [...CLAIMS_TAB_PENDING_KEY, params],
    queryFn: () => claimApi.getTabPending(params),
    staleTime: 30_000,
    enabled: options?.enabled !== false,
  });
};

export const useClaimsTabClosed = (params?: ClaimListParams, options?: { enabled?: boolean }) => {
  return useQuery({
    queryKey: [...CLAIMS_TAB_CLOSED_KEY, params],
    queryFn: () => claimApi.getTabClosed(params),
    staleTime: 30_000,
    enabled: options?.enabled !== false,
  });
};

export const useCreateClaim = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ vendor_id, entity_id }: { vendor_id: string; entity_id?: string | null }) =>
      claimApi.create(vendor_id, entity_id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: CLAIMS_KEY });
      queryClient.invalidateQueries({ queryKey: CLAIMS_TAB_DRAFT_KEY });
    },
  });
};

export const useSubmitClaim = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (claimId: string) => claimApi.submit(claimId),
    onSuccess: (_data, claimId) => {
      queryClient.invalidateQueries({ queryKey: CLAIMS_KEY });
      queryClient.invalidateQueries({ queryKey: CLAIMS_TAB_DRAFT_KEY });
      queryClient.invalidateQueries({ queryKey: CLAIMS_TAB_PENDING_KEY });
      queryClient.invalidateQueries({ queryKey: ['claims', claimId] });
      queryClient.invalidateQueries({ queryKey: ['claims', 'approval-queue'] });
    },
  });
};

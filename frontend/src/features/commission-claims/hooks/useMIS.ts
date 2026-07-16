import { useQuery, useMutation } from '@tanstack/react-query';
import { claimApi } from '../api/claimApi';
import type { ClaimListParams } from '../api/claimApi';

const MIS_PENDING_KEY = ['claims', 'mis', 'pending'];
const MIS_HISTORY_KEY = ['claims', 'mis', 'history'];

export const useMISPending = (params?: ClaimListParams) => {
  return useQuery({
    queryKey: [...MIS_PENDING_KEY, params],
    queryFn: () => claimApi.getMisPending(params),
    staleTime: 30_000,
  });
};

export const useMISHistory = (params?: ClaimListParams) => {
  return useQuery({
    queryKey: [...MIS_HISTORY_KEY, params],
    queryFn: () => claimApi.getMisHistory(params),
    staleTime: 30_000,
  });
};

export const useExportMIS = () => {
  return useMutation({
    mutationFn: ({ view, params }: { view: 'pending' | 'history'; params?: ClaimListParams }) =>
      view === 'pending'
        ? claimApi.exportMisPending(params)
        : claimApi.exportMisHistory(params),
  });
};

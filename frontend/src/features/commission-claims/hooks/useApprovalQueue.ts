import { useQuery } from '@tanstack/react-query';
import { claimApi } from '../api/claimApi';

const APPROVAL_QUEUE_KEY = ['claims', 'approval-queue'];

export const useApprovalQueue = () => {
  return useQuery({
    queryKey: APPROVAL_QUEUE_KEY,
    queryFn: () => claimApi.getApprovalQueue(),
    staleTime: 10_000, // Short stale time for approval queue to reflect changes quickly
  });
};

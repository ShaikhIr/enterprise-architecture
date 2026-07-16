import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { claimApi } from '../api/claimApi';
import type { AddLineRequest, LineUpdateRequest, WorkflowActionRequest, PaymentClearingDateRequest } from '../api/claimApi';

export const useClaimDetail = (claimId: string) => {
  return useQuery({
    queryKey: ['claims', claimId],
    queryFn: () => claimApi.getDetail(claimId),
    staleTime: 30_000,
    enabled: !!claimId,
  });
};

export const useUpdateClaimEntity = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ claimId, entityId }: { claimId: string; entityId: string | null }) =>
      claimApi.updateEntity(claimId, entityId),
    onSuccess: (_data, { claimId }) => {
      queryClient.invalidateQueries({ queryKey: ['claims', claimId] });
    },
  });
};

export const useClaimAudit = (claimId: string) => {
  return useQuery({
    queryKey: ['claims', claimId, 'audit'],
    queryFn: () => claimApi.getAudit(claimId),
    staleTime: 30_000,
    enabled: !!claimId,
  });
};

export const useWorkflowAction = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ claimId, action, request }: {
      claimId: string;
      action: 'approve' | 'referBack' | 'reject';
      request: WorkflowActionRequest;
    }) => claimApi[action](claimId, request),
    onSuccess: (_data, { claimId }) => {
      queryClient.invalidateQueries({ queryKey: ['claims', claimId] });
      queryClient.invalidateQueries({ queryKey: ['claims'] });
      queryClient.invalidateQueries({ queryKey: ['claims', 'approval-queue'] });
      queryClient.invalidateQueries({ queryKey: ['claims', 'tab', 'draft'] });
      queryClient.invalidateQueries({ queryKey: ['claims', 'tab', 'pending'] });
      queryClient.invalidateQueries({ queryKey: ['claims', 'tab', 'closed'] });
    },
  });
};

export const useAddLine = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ claimId, request }: { claimId: string; request: AddLineRequest }) =>
      claimApi.addLine(claimId, request),
    onSuccess: (_data, { claimId }) => {
      queryClient.invalidateQueries({ queryKey: ['claims', claimId] });
    },
  });
};

export const useUpdateLine = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ claimId, lineId, request }: {
      claimId: string;
      lineId: string;
      request: LineUpdateRequest;
    }) => claimApi.updateLine(claimId, lineId, request),
    onSuccess: (_data, { claimId }) => {
      queryClient.invalidateQueries({ queryKey: ['claims', claimId] });
    },
  });
};

export const useRemoveLine = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ claimId, lineId }: { claimId: string; lineId: string }) =>
      claimApi.removeLine(claimId, lineId),
    onSuccess: (_data, { claimId }) => {
      queryClient.invalidateQueries({ queryKey: ['claims', claimId] });
    },
  });
};

export const useUploadPod = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ claimId, lineId, documentId }: {
      claimId: string;
      lineId: string;
      documentId: string;
    }) => claimApi.uploadPod(claimId, lineId, documentId),
    onSuccess: (_data, { claimId }) => {
      queryClient.invalidateQueries({ queryKey: ['claims', claimId] });
    },
  });
};

export const useUpdatePaymentClearingDate = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ claimId, lineId, request }: {
      claimId: string;
      lineId: string;
      request: PaymentClearingDateRequest;
    }) => claimApi.updatePaymentClearingDate(claimId, lineId, request),
    onSuccess: (_data, { claimId }) => {
      queryClient.invalidateQueries({ queryKey: ['claims', claimId] });
    },
  });
};

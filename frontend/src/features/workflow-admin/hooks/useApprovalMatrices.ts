/**
 * TanStack Query hooks for approval matrices.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { approvalMatrixApi, type ListMatricesParams } from '../api/approvalMatrixApi';
import type {
  ApprovalResolveRequest,
  CreateApprovalMatrixRequest,
  UpdateApprovalMatrixRequest,
} from '../models/ApprovalMatrix';

const MATRICES_KEY = ['approval-matrices'];

export const useApprovalMatrices = (params: ListMatricesParams = {}) =>
  useQuery({
    queryKey: [...MATRICES_KEY, params],
    queryFn: () => approvalMatrixApi.listMatrices(params),
    staleTime: 30_000,
  });

export const useCreateApprovalMatrix = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (request: CreateApprovalMatrixRequest) => approvalMatrixApi.createMatrix(request),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: MATRICES_KEY });
    },
  });
};

export const useUpdateApprovalMatrix = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      matrixId,
      request,
    }: {
      matrixId: number;
      request: UpdateApprovalMatrixRequest;
    }) => approvalMatrixApi.updateMatrix(matrixId, request),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: MATRICES_KEY });
    },
  });
};

export const useDeleteApprovalMatrix = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (matrixId: number) => approvalMatrixApi.deleteMatrix(matrixId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: MATRICES_KEY });
    },
  });
};

/**
 * Resolution preview is a mutation rather than a query: it is a POST, it is only
 * ever run on demand, and its result should not be cached against a key.
 */
export const useResolveApprovalMatrix = () =>
  useMutation({
    mutationFn: (request: ApprovalResolveRequest) => approvalMatrixApi.resolveMatrix(request),
  });

export const useMyApprovalTasks = () =>
  useQuery({
    queryKey: ['my-approval-tasks'],
    queryFn: () => approvalMatrixApi.listMyTasks(),
    staleTime: 30_000,
  });

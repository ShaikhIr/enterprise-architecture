/**
 * Approval matrix API calls.
 * Maps to backend: /api/v1/workflow/approval-matrices
 */

import { apiClient } from '@shared/services/apiClient';

import type {
  ApprovalMatrix,
  ApprovalMatrixListResponse,
  ApprovalResolveRequest,
  ApprovalResolveResponse,
  ApprovalTask,
  CreateApprovalMatrixRequest,
  UpdateApprovalMatrixRequest,
} from '../models/ApprovalMatrix';

const BASE = '/workflow/approval-matrices';

export interface ListMatricesParams {
  skip?: number;
  limit?: number;
  search?: string;
  is_active?: boolean;
  entity_type?: string;
}

export const approvalMatrixApi = {
  listMatrices: async (params: ListMatricesParams = {}): Promise<ApprovalMatrixListResponse> => {
    const { data } = await apiClient.get<ApprovalMatrixListResponse>(BASE, {
      params: { skip: 0, limit: 100, ...params },
    });
    return data;
  },

  getMatrix: async (matrixId: number): Promise<ApprovalMatrix> => {
    const { data } = await apiClient.get<ApprovalMatrix>(`${BASE}/${matrixId}`);
    return data;
  },

  createMatrix: async (request: CreateApprovalMatrixRequest): Promise<ApprovalMatrix> => {
    const { data } = await apiClient.post<ApprovalMatrix>(BASE, request);
    return data;
  },

  updateMatrix: async (
    matrixId: number,
    request: UpdateApprovalMatrixRequest,
  ): Promise<ApprovalMatrix> => {
    const { data } = await apiClient.patch<ApprovalMatrix>(`${BASE}/${matrixId}`, request);
    return data;
  },

  deleteMatrix: async (matrixId: number): Promise<void> => {
    await apiClient.delete(`${BASE}/${matrixId}`);
  },

  /** Dry run: which matrix would route this record, and to whom. Writes nothing. */
  resolveMatrix: async (request: ApprovalResolveRequest): Promise<ApprovalResolveResponse> => {
    const { data } = await apiClient.post<ApprovalResolveResponse>(`${BASE}/resolve`, request);
    return data;
  },

  listMyTasks: async (): Promise<ApprovalTask[]> => {
    const { data } = await apiClient.get<ApprovalTask[]>('/workflow/my-tasks');
    return data;
  },
};

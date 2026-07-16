import { apiClient } from '@shared/services/apiClient';
import type {
  ClaimHeader,
  ClaimLine,
  ClaimDetail,
  ClaimListResponse,
  ApprovalQueueItem,
  ClaimAuditEntry,
} from '../models/claim.types';

// ── Query param types ───────────────────────────────────────────────────────

export interface ClaimListParams {
  skip?: number;
  limit?: number;
  vendor_id?: string;
  claim_number?: string;
  start_date?: string;
  end_date?: string;
}

export interface AddLineRequest {
  invoice_id: string;
  due_date_override?: string | null;
  ld_charges?: number;
  retention_amount?: number;
  remarks?: string;
}

export interface LineUpdateRequest {
  amount_deducted?: number | null;
  tds_value?: number | null;
  payment_clearing_date?: string | null;
  ld_charges?: number | null;
  retention_amount?: number | null;
  due_date?: string | null;
  remarks?: string | null;
}

export interface WorkflowActionRequest {
  remarks: string;
}

export interface PaymentClearingDateRequest {
  payment_clearing_date: string;
}

export interface SAPBookingRequest {
  sap_p2p_booking_reference: string;
}

export interface GSTInvoiceRequest {
  gst_invoice_number: string;
}

export interface PODUploadRequest {
  document_id: string;
}

export interface MISListResponse {
  items: { header: ClaimHeader; status_label: string }[];
  total: number;
  skip: number;
  limit: number;
}

// ── API client ──────────────────────────────────────────────────────────────

export const claimApi = {
  // Claim lifecycle
  create: async (vendor_id: string, entity_id?: string | null): Promise<ClaimHeader> => {
    const { data } = await apiClient.post<ClaimHeader>('/claims', { vendor_id, entity_id: entity_id || null });
    return data;
  },

  list: async (params?: ClaimListParams): Promise<ClaimListResponse> => {
    const { data } = await apiClient.get<ClaimListResponse>('/claims', { params });
    return data;
  },

  getDetail: async (id: string): Promise<ClaimDetail> => {
    const { data } = await apiClient.get<ClaimDetail>(`/claims/${id}`);
    return data;
  },

  getAudit: async (id: string): Promise<ClaimAuditEntry[]> => {
    const { data } = await apiClient.get<ClaimAuditEntry[]>(`/claims/${id}/audit`);
    return data;
  },

  // Line management
  addLine: async (claimId: string, request: AddLineRequest): Promise<ClaimLine> => {
    const { data } = await apiClient.post<ClaimLine>(`/claims/${claimId}/lines`, request);
    return data;
  },

  updateLine: async (claimId: string, lineId: string, request: LineUpdateRequest): Promise<ClaimLine> => {
    const { data } = await apiClient.patch<ClaimLine>(`/claims/${claimId}/lines/${lineId}`, request);
    return data;
  },

  removeLine: async (claimId: string, lineId: string): Promise<void> => {
    await apiClient.delete(`/claims/${claimId}/lines/${lineId}`);
  },

  uploadPod: async (claimId: string, lineId: string, documentId: string): Promise<ClaimLine> => {
    const { data } = await apiClient.post<ClaimLine>(
      `/claims/${claimId}/lines/${lineId}/pod`,
      { document_id: documentId },
    );
    return data;
  },

  // Workflow actions
  submit: async (id: string): Promise<ClaimHeader> => {
    const { data } = await apiClient.post<ClaimHeader>(`/claims/${id}/submit`);
    return data;
  },

  // Claim entity update
  updateEntity: async (id: string, entity_id: string | null): Promise<ClaimHeader> => {
    const { data } = await apiClient.patch<ClaimHeader>(`/claims/${id}/entity`, { entity_id });
    return data;
  },

  approve: async (id: string, request: WorkflowActionRequest): Promise<ClaimHeader> => {
    const { data } = await apiClient.post<ClaimHeader>(`/claims/${id}/approve`, request);
    return data;
  },

  referBack: async (id: string, request: WorkflowActionRequest): Promise<ClaimHeader> => {
    const { data } = await apiClient.post<ClaimHeader>(`/claims/${id}/refer-back`, request);
    return data;
  },

  reject: async (id: string, request: WorkflowActionRequest): Promise<ClaimHeader> => {
    const { data } = await apiClient.post<ClaimHeader>(`/claims/${id}/reject`, request);
    return data;
  },

  // Post-closure operations
  updatePaymentClearingDate: async (
    claimId: string,
    lineId: string,
    request: PaymentClearingDateRequest,
  ): Promise<ClaimLine> => {
    const { data } = await apiClient.patch<ClaimLine>(
      `/claims/${claimId}/lines/${lineId}/payment-clearing-date`,
      request,
    );
    return data;
  },

  recordSapBooking: async (id: string, request: SAPBookingRequest): Promise<ClaimHeader> => {
    const { data } = await apiClient.patch<ClaimHeader>(`/claims/${id}/sap-booking`, request);
    return data;
  },

  uploadGstInvoice: async (id: string, request: GSTInvoiceRequest): Promise<ClaimHeader> => {
    const { data } = await apiClient.post<ClaimHeader>(`/claims/${id}/gst-invoice`, request);
    return data;
  },

  // Approval queue and MIS views
  getApprovalQueue: async (): Promise<ApprovalQueueItem[]> => {
    const { data } = await apiClient.get<ApprovalQueueItem[]>('/claims/approval-queue');
    return data;
  },

  // Tab-based listing
  getTabDraft: async (params?: ClaimListParams): Promise<ClaimListResponse> => {
    const { data } = await apiClient.get<ClaimListResponse>('/claims/tab/draft', { params });
    return data;
  },

  getTabPending: async (params?: ClaimListParams): Promise<ClaimListResponse> => {
    const { data } = await apiClient.get<ClaimListResponse>('/claims/tab/pending', { params });
    return data;
  },

  getTabClosed: async (params?: ClaimListParams): Promise<ClaimListResponse> => {
    const { data } = await apiClient.get<ClaimListResponse>('/claims/tab/closed', { params });
    return data;
  },

  getMisPending: async (params?: ClaimListParams): Promise<MISListResponse> => {
    const { data } = await apiClient.get<MISListResponse>('/claims/mis/pending', { params });
    return data;
  },

  getMisHistory: async (params?: ClaimListParams): Promise<MISListResponse> => {
    const { data } = await apiClient.get<MISListResponse>('/claims/mis/history', { params });
    return data;
  },

  exportMisPending: async (params?: ClaimListParams): Promise<Blob> => {
    const { data } = await apiClient.get<Blob>('/claims/mis/pending/export', {
      params,
      responseType: 'blob',
    });
    return data;
  },

  exportMisHistory: async (params?: ClaimListParams): Promise<Blob> => {
    const { data } = await apiClient.get<Blob>('/claims/mis/history/export', {
      params,
      responseType: 'blob',
    });
    return data;
  },
};

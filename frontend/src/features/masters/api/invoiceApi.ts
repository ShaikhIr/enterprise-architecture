import { apiClient } from '@shared/services/apiClient';
import type {
  Invoice,
  InvoiceListResponse,
  CreateInvoiceRequest,
  PaymentUpdateRequest,
  EligibilityCheck,
} from '../models/invoice';
import type { PaginatedParams } from '../models/common';

export const invoiceApi = {
  list: async (params: PaginatedParams): Promise<InvoiceListResponse> => {
    const { data } = await apiClient.get<InvoiceListResponse>('/invoices', { params });
    return data;
  },

  getById: async (id: string): Promise<Invoice> => {
    const { data } = await apiClient.get<Invoice>(`/invoices/${id}`);
    return data;
  },

  create: async (request: CreateInvoiceRequest): Promise<Invoice> => {
    const { data } = await apiClient.post<Invoice>('/invoices', request);
    return data;
  },

  /**
   * POST /invoices/{id}/sap-payment — records SAP payment and sets status
   * to "Payment Cleared".
   * Backend field: sap_clearing_document_no (not sap_clearing_doc_no).
   */
  updatePayment: async (id: string, request: PaymentUpdateRequest): Promise<Invoice> => {
    const { data } = await apiClient.post<Invoice>(`/invoices/${id}/sap-payment`, {
      payment_clearing_date: request.payment_clearing_date,
      sap_clearing_document_no: request.sap_clearing_doc_no ?? '',
    });
    return data;
  },

  /**
   * POST /invoices/{id}/settle — marks invoice as Settled.
   */
  markSettled: async (id: string): Promise<Invoice> => {
    const { data } = await apiClient.post<Invoice>(`/invoices/${id}/settle`);
    return data;
  },

  checkEligibility: async (id: string): Promise<EligibilityCheck> => {
    const { data } = await apiClient.get<EligibilityCheck>(`/invoices/${id}/eligibility`);
    return data;
  },
};

import { apiClient } from '@shared/services/apiClient';
import type {
  Agreement,
  AgreementListResponse,
  CreateAgreementRequest,
  UpdateAgreementRequest,
  RenewAgreementRequest,
} from '../models/agreement';
import type { PaginatedParams } from '../models/common';

/**
 * Convert any plain-object request to FormData.
 *
 * The Agreement backend uses FastAPI's `Form(...)` dependencies (multipart/form-data)
 * for create, update, and renew — even when no file is attached.  Sending a JSON
 * body to a Form-only endpoint causes FastAPI to return 422 because it cannot
 * parse a JSON payload as form fields.  We therefore always send FormData.
 *
 * File fields (File / Blob instances) are appended directly; all other values are
 * coerced to strings. Undefined and null values are omitted so optional fields
 * stay absent. Note: numeric zero (0) and boolean false are intentionally
 * included because they are valid field values.
 */
function toFormData(request: Record<string, unknown>): FormData {
  const formData = new FormData();
  Object.entries(request).forEach(([key, value]) => {
    if (value === undefined || value === null) return;
    if (value instanceof File || value instanceof Blob) {
      formData.append(key, value);
    } else {
      formData.append(key, String(value));
    }
  });
  return formData;
}

/**
 * Axios config for multipart/form-data requests.
 *
 * The apiClient instance sets `Content-Type: application/json` as a default
 * header. When sending FormData, we must delete that default so Axios (and the
 * underlying XMLHttpRequest / fetch) can automatically set
 * `Content-Type: multipart/form-data; boundary=<generated>`. Without the
 * boundary, FastAPI's Form() parameters cannot parse the body and returns a
 * 422 "field required" error for every field.
 */
const MULTIPART_CONFIG = {
  headers: { 'Content-Type': undefined as unknown as string },
};

export const agreementApi = {
  list: async (params: PaginatedParams): Promise<AgreementListResponse> => {
    const { data } = await apiClient.get<AgreementListResponse>('/agreements', { params });
    return data;
  },

  getById: async (id: string): Promise<Agreement> => {
    const { data } = await apiClient.get<Agreement>(`/agreements/${id}`);
    return data;
  },

  /**
   * POST /agreements — always multipart/form-data (backend uses FastAPI Form deps).
   */
  create: async (request: CreateAgreementRequest): Promise<Agreement> => {
    const formData = toFormData(request as unknown as Record<string, unknown>);
    const { data } = await apiClient.post<Agreement>('/agreements', formData, MULTIPART_CONFIG);
    return data;
  },

  /**
   * PATCH /agreements/:id — always multipart/form-data.
   * Note: backend registers PATCH, not PUT.
   */
  update: async (id: string, request: UpdateAgreementRequest): Promise<Agreement> => {
    const formData = toFormData(request as unknown as Record<string, unknown>);
    const { data } = await apiClient.patch<Agreement>(`/agreements/${id}`, formData, MULTIPART_CONFIG);
    return data;
  },

  /**
   * POST /agreements/:id/renew — always multipart/form-data.
   */
  renew: async (id: string, request: RenewAgreementRequest): Promise<Agreement> => {
    const formData = toFormData(request as unknown as Record<string, unknown>);
    const { data } = await apiClient.post<Agreement>(`/agreements/${id}/renew`, formData, MULTIPART_CONFIG);
    return data;
  },
};

import type { PaginatedResponse } from './common';

export type AgreementType = 'Original' | 'Renewal';
export type AgreementStatus = 'Active' | 'Expired' | 'Renewed';

export interface Agreement {
  id: string;
  vendor_id: string;
  vendor_name: string;
  product_master_id: string;
  product_detail_child_code: string;
  product_detail_name: string;
  from_date: string;
  to_date: string;
  slab_in_days: number;
  reduction_percent: number;
  max_commission_percent: number;
  min_commission_percent: number;
  credit_days: number;
  agreement_type: AgreementType;
  prior_agreement_id: string | null;
  agreement_document_url: string | null;
  status: AgreementStatus;
  created_at: string;
  modified_at: string;
  created_by: string | null;
  modified_by: string | null;
}

export interface AgreementListResponse extends PaginatedResponse<Agreement> {}

export interface CreateAgreementRequest {
  vendor_id: string;
  product_master_id: string;
  from_date: string;
  to_date: string;
  slab_in_days: number;
  reduction_percent: number;
  max_commission_percent: number;
  min_commission_percent: number;
  credit_days: number;
  agreement_document?: File;
}

export interface UpdateAgreementRequest extends Partial<CreateAgreementRequest> {}

export interface RenewAgreementRequest {
  from_date: string;
  to_date: string;
  slab_in_days: number;
  reduction_percent: number;
  max_commission_percent: number;
  min_commission_percent: number;
  credit_days: number;
  agreement_document?: File;
}

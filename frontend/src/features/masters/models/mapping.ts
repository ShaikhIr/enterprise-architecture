import type { PaginatedResponse } from './common';

export type MappingStatus = 'Active' | 'Expired';

export interface VendorCustomerMapping {
  id: string;
  vendor_id: string;
  vendor_name: string;
  customer_id: string;
  customer_name: string;
  validity_from: string;
  validity_to: string;
  status: MappingStatus;
  created_at: string;
  modified_at: string;
  created_by: string | null;
  modified_by: string | null;
}

export interface MappingListResponse extends PaginatedResponse<VendorCustomerMapping> {}

export interface CreateMappingRequest {
  vendor_id: string;
  customer_id: string;
  validity_from: string;
  validity_to: string;
}

export interface UpdateMappingRequest {
  validity_from: string;
  validity_to: string;
}

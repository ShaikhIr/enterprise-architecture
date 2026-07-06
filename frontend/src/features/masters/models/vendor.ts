import type { PaginatedResponse } from './common';

export type VendorStatus = 'Active' | 'Inactive';

export interface Vendor {
  id: string;
  vendor_code: string;
  vendor_name: string;
  vendor_email: string;
  vendor_contact: string | null;
  vendor_address: string | null;
  city: string | null;
  gstn_number: string | null;
  pan_number: string | null;
  bank_account_no: string | null;
  bank_ifsc: string | null;
  bank_name: string | null;
  portal_user_id: string | null;
  status: VendorStatus;
  created_at: string;
  modified_at: string;
  created_by: string | null;
  modified_by: string | null;
}

export interface VendorListResponse extends PaginatedResponse<Vendor> {}

export interface CreateVendorRequest {
  vendor_code: string;
  vendor_name: string;
  vendor_email: string;
  vendor_contact?: string;
  vendor_address?: string;
  city?: string;
  gstn_number?: string;
  pan_number?: string;
  bank_account_no?: string;
  bank_ifsc?: string;
  bank_name?: string;
}

export interface UpdateVendorRequest extends Partial<CreateVendorRequest> {
  status?: VendorStatus;
}

import type { PaginatedResponse } from './common';

export type CustomerStatus = 'Active' | 'Inactive';

export interface Customer {
  id: string;
  customer_code: string;
  customer_name: string;
  address: string | null;
  gstn_number: string | null;
  contact_person: string | null;
  contact_number: string | null;
  contact_email: string | null;
  status: CustomerStatus;
  created_at: string;
  modified_at: string;
  created_by: string | null;
  modified_by: string | null;
}

export interface CustomerListResponse extends PaginatedResponse<Customer> {}

export interface CreateCustomerRequest {
  customer_code: string;
  customer_name: string;
  address?: string;
  gstn_number?: string;
  contact_person?: string;
  contact_number?: string;
  contact_email?: string;
}

export interface UpdateCustomerRequest extends Partial<CreateCustomerRequest> {
  status?: CustomerStatus;
}

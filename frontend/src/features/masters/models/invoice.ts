import type { PaginatedResponse } from './common';

export type InvoiceStatus = 'Open' | 'Payment Cleared' | 'Settled';

export interface InvoiceLine {
  id: string;
  product_detail_id: string;
  product_child_code: string | null;
  product_name: string | null;
  quantity: number | null;
  line_amount: number | null;
  vat_gst_amount: number | null;
}

export interface Invoice {
  id: string;
  invoice_number: string;
  invoice_date: string;
  vendor_id: string;
  vendor_name: string;
  customer_id: string | null;
  customer_name: string | null;
  bill_amount_excl_gst: number;
  bill_amount_incl_tax: number | null;
  amount_deducted: number;
  tds_value: number;
  due_date: string | null;
  payment_clearing_date: string | null;
  sap_clearing_doc_no: string | null;
  /** invoice_status is the canonical field returned by the backend */
  invoice_status: InvoiceStatus;
  /** status mirrors invoice_status for frontend convenience */
  status: InvoiceStatus;
  lines: InvoiceLine[];
  created_at: string;
  modified_at: string;
  created_by: string | null;
  modified_by: string | null;
}

export interface InvoiceListResponse extends PaginatedResponse<Invoice> {}

export interface CreateInvoiceLineRequest {
  product_detail_id: string;
  quantity?: number;
  line_amount?: number;
  vat_gst_amount?: number;
}

export interface CreateInvoiceRequest {
  invoice_number: string;
  invoice_date: string;
  vendor_id: string;
  customer_id: string;
  bill_amount_excl_gst: number;
  bill_amount_incl_tax?: number;
  amount_deducted?: number;
  tds_value?: number;
  lines: CreateInvoiceLineRequest[];
}

export interface PaymentUpdateRequest {
  payment_clearing_date: string;
  sap_clearing_doc_no?: string;
}

export interface EligibilityCheck {
  agreement_valid: boolean;
  agreement_message: string;
  mapping_valid: boolean;
  mapping_message: string;
  status_valid: boolean;
  status_message: string;
  overall_eligible: boolean;
}

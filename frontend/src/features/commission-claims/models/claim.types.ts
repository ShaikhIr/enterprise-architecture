// All monetary/decimal fields from the Python API come as strings (FastAPI serialises Decimal as string)

export type ClaimStatus = 'Draft' | 'Pending' | 'Referred Back' | 'Rejected' | 'Closed';

export const STATUS_SEVERITY: Record<ClaimStatus, 'info' | 'warning' | 'success' | 'danger'> = {
  Draft: 'info',
  Pending: 'warning',
  'Referred Back': 'warning',
  Closed: 'success',
  Rejected: 'danger',
};

export interface ClaimLine {
  id: string;
  claim_header_id: string;
  invoice_header_id: string;
  invoice_number: string | null;
  product_master_id: string;
  customer_id: string;
  bill_amount_excl_gst: string;
  amount_deducted: string;
  tds_value: string;
  ld_charges: string;
  retention_amount: string;
  net_amount: string;
  commission_payable_base: string;
  due_date: string;          // ISO date
  payment_clearing_date: string;
  delay_days: number;
  applicable_commission_percent: string;
  commission_amount: string;
  gst_on_commission: string;
  final_line_claim_amount: string;
  pod_document_id: string | null;
  remarks: string;
  created_by: string;
  created_date: string;
}

export interface ClaimHeader {
  id: string;
  vendor_id: string;
  entity_id: string | null;
  claim_number: string | null;
  claim_date: string;
  status: ClaimStatus;
  workflow_status_name: string | null;
  workflow_instance_id: string | null;
  total_claim_amount: string;
  total_commission_amount: string;
  total_gst_amount: string;
  total_tds_amount: string;
  total_ld_amount: string;
  total_retention_amount: string;
  gstn_verification_status: string;
  gst_invoice_number: string | null;
  gst_invoice_upload_date: string | null;
  sap_p2p_booking_reference: string | null;
  created_by: string;
  created_date: string;
  modified_date: string;
}

export interface ClaimDetail {
  header: ClaimHeader;
  lines: ClaimLine[];
  workflow_status: Record<string, unknown> | null;
  available_actions: string[];
}

export interface ClaimListResponse {
  items: ClaimHeader[];
  total: number;
  skip: number;
  limit: number;
}

export interface ApprovalQueueItem {
  id: string;
  claim_number: string | null;
  vendor_id: string;
  claim_date: string;
  total_claim_amount: string;
  status: ClaimStatus;
  workflow_step_name: string | null;
  submitted_date: string | null;
}

export interface MISItem {
  id: string;
  claim_number: string | null;
  vendor_id: string;
  claim_date: string;
  status: ClaimStatus;
  status_label: string;
  total_claim_amount: string;
  total_commission_amount: string;
  created_date: string;
}

export interface ClaimAuditEntry {
  id: string;
  claim_header_id: string;
  action: string;
  actor_username: string;
  actor_user_id: string;
  timestamp_utc: string;
  from_status: string | null;
  to_status: string | null;
  workflow_step_name: string | null;
  remarks: string | null;
  field_changes: Record<string, { old: unknown; new: unknown }> | null;
}

// ── Request types ──────────────────────────────────────────────────────────────

export interface MISFilterParams {
  vendor_id?: string;
  claim_number?: string;
  start_date?: string;
  end_date?: string;
}

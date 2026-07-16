/**
 * ClaimLineTable — Read-only DataTable showing all claim lines.
 * Columns per Req 19.2: Invoice Number, Bill Amount, Amount Deducted, TDS Value,
 * LD Charges, Retention Amount, Net Amount, Commission Payable Base,
 * Due Date, Payment Clearing Date, Delay Days, Applicable Commission %,
 * Commission Amount, GST on Commission, Final Line Claim Amount, POD Document, Remarks.
 */
import { DataTable } from 'primereact/datatable';
import { Column } from 'primereact/column';
import type { ClaimLine } from '../models/claim.types';

interface ClaimLineTableProps {
  lines: ClaimLine[];
  loading?: boolean;
  podSlot?: (line: ClaimLine) => React.ReactNode;
}

const formatCurrency = (value: string | number) =>
  Number(value).toLocaleString('en-IN', { style: 'currency', currency: 'INR', minimumFractionDigits: 2 });

const formatPercent = (value: string | number) => `${Number(value).toFixed(4)}%`;

export const ClaimLineTable = ({ lines, loading = false, podSlot }: ClaimLineTableProps) => {
  return (
    <DataTable
      value={lines}
      loading={loading}
      stripedRows
      paginator
      rows={10}
      rowsPerPageOptions={[5, 10, 20]}
      emptyMessage="No lines added yet."
      scrollable
      scrollHeight="400px"
      className="p-datatable-sm"
      aria-label="Claim line items table"
    >
      <Column
        field="invoice_number"
        header="Invoice Number"
        style={{ minWidth: '140px' }}
        body={(row: ClaimLine) => row.invoice_number || row.invoice_header_id?.slice(0, 8) + '...'}
      />
      <Column
        field="bill_amount_excl_gst"
        header="Bill Amount"
        body={(row: ClaimLine) => formatCurrency(row.bill_amount_excl_gst)}
        style={{ minWidth: '120px' }}
      />
      <Column
        field="amount_deducted"
        header="Amt Deducted"
        body={(row: ClaimLine) => formatCurrency(row.amount_deducted)}
        style={{ minWidth: '120px' }}
      />
      <Column
        field="tds_value"
        header="TDS Value"
        body={(row: ClaimLine) => formatCurrency(row.tds_value)}
        style={{ minWidth: '110px' }}
      />
      <Column
        field="ld_charges"
        header="LD Charges"
        body={(row: ClaimLine) => formatCurrency(row.ld_charges)}
        style={{ minWidth: '110px' }}
      />
      <Column
        field="retention_amount"
        header="Retention"
        body={(row: ClaimLine) => formatCurrency(row.retention_amount)}
        style={{ minWidth: '110px' }}
      />
      <Column
        field="net_amount"
        header="Net Amount"
        body={(row: ClaimLine) => formatCurrency(row.net_amount)}
        style={{ minWidth: '120px' }}
      />
      <Column
        field="commission_payable_base"
        header="Comm. Base"
        body={(row: ClaimLine) => formatCurrency(row.commission_payable_base)}
        style={{ minWidth: '120px' }}
      />
      <Column field="due_date" header="Due Date" style={{ minWidth: '100px' }} />
      <Column field="payment_clearing_date" header="Clearing Date" style={{ minWidth: '110px' }} />
      <Column field="delay_days" header="Delay Days" style={{ minWidth: '90px' }} />
      <Column
        field="applicable_commission_percent"
        header="Comm. %"
        body={(row: ClaimLine) => formatPercent(row.applicable_commission_percent)}
        style={{ minWidth: '90px' }}
      />
      <Column
        field="commission_amount"
        header="Commission Amt"
        body={(row: ClaimLine) => formatCurrency(row.commission_amount)}
        style={{ minWidth: '130px' }}
      />
      <Column
        field="gst_on_commission"
        header="GST on Comm."
        body={(row: ClaimLine) => formatCurrency(row.gst_on_commission)}
        style={{ minWidth: '120px' }}
      />
      <Column
        field="final_line_claim_amount"
        header="Final Claim Amt"
        body={(row: ClaimLine) => formatCurrency(row.final_line_claim_amount)}
        style={{ minWidth: '130px' }}
      />
      {podSlot && (
        <Column header="POD Document" body={podSlot} style={{ minWidth: '140px' }} />
      )}
      <Column field="remarks" header="Remarks" style={{ minWidth: '150px' }} />
    </DataTable>
  );
};

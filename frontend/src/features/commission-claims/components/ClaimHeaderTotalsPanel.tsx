/**
 * ClaimHeaderTotalsPanel — Summary panel showing all 6 header totals.
 * Displays live values from the ClaimHeader, formatted as INR currency (Req 19.3).
 */
import type { ClaimHeader } from '../models/claim.types';

interface ClaimHeaderTotalsPanelProps {
  header: Pick<ClaimHeader,
    'total_claim_amount' | 'total_commission_amount' | 'total_gst_amount' |
    'total_tds_amount' | 'total_ld_amount' | 'total_retention_amount'>;
}

const formatCurrency = (value: string | number) =>
  Number(value).toLocaleString('en-IN', { style: 'currency', currency: 'INR', minimumFractionDigits: 2 });

const TotalCard = ({ label, value }: { label: string; value: string | number }) => (
  <div className="flex flex-column gap-1 p-3 surface-card border-round border-1 border-200 flex-1">
    <span className="text-500 text-sm font-medium">{label}</span>
    <span className="text-900 font-bold text-xl">{formatCurrency(value)}</span>
  </div>
);

export const ClaimHeaderTotalsPanel = ({ header }: ClaimHeaderTotalsPanelProps) => {
  return (
    <div
      className="flex flex-wrap gap-3 p-3 surface-50 border-round border-1 border-200"
      role="region"
      aria-label="Claim header totals"
    >
      <TotalCard label="Total Claim Amount" value={header.total_claim_amount} />
      <TotalCard label="Total Commission" value={header.total_commission_amount} />
      <TotalCard label="Total GST" value={header.total_gst_amount} />
      <TotalCard label="Total TDS" value={header.total_tds_amount} />
      <TotalCard label="Total LD" value={header.total_ld_amount} />
      <TotalCard label="Total Retention" value={header.total_retention_amount} />
    </div>
  );
};

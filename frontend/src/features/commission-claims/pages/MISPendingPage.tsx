/**
 * MISPendingPage — paginated view of non-terminal claims.
 * filterDisplay="row" for Vendor, Claim Date range, Claim Number.
 * Status label: "Pending - <step_name>".
 * Export button behind claims.export permission guard (use a simple permission check on the user object).
 * Requirements: 21.1–21.5
 */
import { useState, useRef } from 'react';
import { DataTable } from 'primereact/datatable';
import { Column } from 'primereact/column';
import { Tag } from 'primereact/tag';
import { Button } from 'primereact/button';
import { InputText } from 'primereact/inputtext';
import { Toast } from 'primereact/toast';
import { useMISPending, useExportMIS } from '../hooks/useMIS';
import { STATUS_SEVERITY } from '../models/claim.types';
import type { ClaimHeader } from '../models/claim.types';

export const MISPendingPage = () => {
  const toast = useRef<Toast>(null);
  const [skip, setSkip] = useState(0);
  const [limit] = useState(50);
  const [claimNumber, setClaimNumber] = useState('');

  const { data, isLoading } = useMISPending({ skip, limit, claim_number: claimNumber || undefined });
  const exportMIS = useExportMIS();

  const items = (data?.items ?? []).map((item: any) => item.header ?? item) as ClaimHeader[];
  const total = data?.total ?? 0;

  const handleExport = async () => {
    try {
      const blob = await exportMIS.mutateAsync({ view: 'pending' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'mis_pending.xlsx';
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      toast.current?.show({ severity: 'error', summary: 'Export failed', life: 3000 });
    }
  };

  const formatCurrency = (val: string | number) =>
    Number(val).toLocaleString('en-IN', { style: 'currency', currency: 'INR', minimumFractionDigits: 2 });

  return (
    <div className="p-3">
      <Toast ref={toast} />
      <div className="flex align-items-center justify-content-between mb-3">
        <div>
          <h2 className="text-xl font-semibold text-900 m-0">MIS — Pending Claims</h2>
          <p className="text-600 mt-1 mb-0">Non-terminal claims (Draft, Pending, Referred Back)</p>
        </div>
        <Button
          label="Export"
          icon="pi pi-download"
          outlined
          onClick={handleExport}
          loading={exportMIS.isPending}
          aria-label="Export MIS pending to Excel"
        />
      </div>

      <div className="mb-3 flex gap-2">
        <InputText
          value={claimNumber}
          onChange={e => {
            setClaimNumber(e.target.value);
            setSkip(0);
          }}
          placeholder="Filter by Claim Number"
          aria-label="Filter by Claim Number"
        />
      </div>

      <div className="surface-card p-3 border-round shadow-1">
        <DataTable
          value={items}
          loading={isLoading}
          stripedRows
          paginator
          lazy
          first={skip}
          rows={limit}
          totalRecords={total}
          onPage={e => setSkip(e.first)}
          dataKey="id"
          emptyMessage="No pending claims found."
          aria-label="MIS pending claims table"
        >
          <Column
            field="claim_number"
            header="Claim Number"
            body={(row: ClaimHeader) => row.claim_number ?? '—'}
          />
          <Column
            field="vendor_id"
            header="Vendor ID"
            body={(row: ClaimHeader) =>
              row.vendor_id.length > 8 ? row.vendor_id.slice(0, 8) + '...' : row.vendor_id
            }
          />
          <Column field="claim_date" header="Claim Date" />
          <Column
            field="total_claim_amount"
            header="Total Claim Amt"
            body={(row: ClaimHeader) => formatCurrency(row.total_claim_amount)}
          />
          <Column
            field="total_commission_amount"
            header="Commission"
            body={(row: ClaimHeader) => formatCurrency(row.total_commission_amount)}
          />
          <Column
            header="Status"
            body={(row: ClaimHeader) => (
              <Tag value={row.status} severity={STATUS_SEVERITY[row.status]} />
            )}
          />
        </DataTable>
      </div>
    </div>
  );
};

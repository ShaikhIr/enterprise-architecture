/**
 * ApprovalQueuePage — shows claims pending the current user's approval.
 * DataTable: stripedRows, paginator, rows=10.
 * Columns per Req 20.2: Claim Number, Vendor Name, Claim Date, Total Claim Amount,
 * Step Name, Submission Date.
 * Row click navigates to ClaimDetailPage.
 * Status Tag: warning for Pending, success for Closed, danger for Rejected.
 * Requirements: 20.1, 20.2, 20.4
 */
import { useNavigate } from 'react-router-dom';
import { DataTable } from 'primereact/datatable';
import { Column } from 'primereact/column';
import { Tag } from 'primereact/tag';
import { useApprovalQueue } from '../hooks/useApprovalQueue';
import { STATUS_SEVERITY } from '../models/claim.types';
import type { ApprovalQueueItem } from '../models/claim.types';

export const ApprovalQueuePage = () => {
  const navigate = useNavigate();
  const { data: items = [], isLoading } = useApprovalQueue();

  const formatCurrency = (val: string | number) =>
    Number(val).toLocaleString('en-IN', { style: 'currency', currency: 'INR', minimumFractionDigits: 2 });

  return (
    <div className="p-3">
      <div className="mb-3">
        <h2 className="text-xl font-semibold text-900 m-0">Approval Queue</h2>
        <p className="text-600 mt-1 mb-0">Claims pending your action</p>
      </div>
      <div className="surface-card p-3 border-round shadow-1">
        <DataTable
          value={items}
          loading={isLoading}
          stripedRows
          paginator
          rows={10}
          rowsPerPageOptions={[10, 25, 50]}
          dataKey="id"
          emptyMessage="No claims pending your approval."
          onRowClick={(e) => navigate(`/claims/${(e.data as ApprovalQueueItem).id}`)}
          rowClassName={() => 'cursor-pointer'}
          aria-label="Approval queue table"
        >
          <Column
            field="claim_number"
            header="Claim Number"
            body={(row: ApprovalQueueItem) => row.claim_number ?? '—'}
          />
          <Column
            field="vendor_id"
            header="Vendor ID"
            body={(row: ApprovalQueueItem) =>
              row.vendor_id.length > 8 ? row.vendor_id.slice(0, 8) + '...' : row.vendor_id
            }
          />
          <Column field="claim_date" header="Claim Date" />
          <Column
            field="total_claim_amount"
            header="Total Claim Amount"
            body={(row: ApprovalQueueItem) => formatCurrency(row.total_claim_amount)}
          />
          <Column
            field="workflow_step_name"
            header="Step Name"
            body={(row: ApprovalQueueItem) => row.workflow_step_name ?? '—'}
          />
          <Column
            field="submitted_date"
            header="Submission Date"
            body={(row: ApprovalQueueItem) => row.submitted_date ?? '—'}
          />
          <Column
            header="Status"
            body={(row: ApprovalQueueItem) => (
              <Tag value={row.status} severity={STATUS_SEVERITY[row.status]} />
            )}
          />
        </DataTable>
      </div>
    </div>
  );
};

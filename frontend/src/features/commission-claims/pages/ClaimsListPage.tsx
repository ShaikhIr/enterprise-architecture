/**
 * ClaimsListPage — landing page for /claims with Draft, Pending, and Closed tabs.
 *
 * Tab visibility is controlled by RBAC permissions:
 * - menu.claims_draft → Draft tab
 * - menu.claims_pending → Pending tab
 * - menu.claims_closed → Closed tab
 *
 * The page auto-lands on the first permitted tab.
 */

import { useRef, useCallback, useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { DataTable } from 'primereact/datatable';
import { Column } from 'primereact/column';
import { Button } from 'primereact/button';
import { Tag } from 'primereact/tag';
import { Toast } from 'primereact/toast';
import { Dialog } from 'primereact/dialog';
import { Dropdown } from 'primereact/dropdown';
import { useAppSelector } from '@app/store';
import { useHasPermission } from '@core/rbac';
import {
  useClaimsTabDraft,
  useClaimsTabPending,
  useClaimsTabClosed,
  useCreateClaim,
} from '../hooks/useClaims';
import { useVendors } from '@features/masters/hooks/useVendors';
import { useEntityDropdown } from '@features/masters/hooks/useEntities';
import { STATUS_SEVERITY } from '../models/claim.types';
import type { ClaimHeader } from '../models/claim.types';

const formatCurrency = (val: string | number) =>
  Number(val).toLocaleString('en-IN', {
    style: 'currency',
    currency: 'INR',
    minimumFractionDigits: 2,
  });

type TabKey = 'draft' | 'pending' | 'closed';

export const ClaimsListPage = () => {
  const navigate = useNavigate();
  const toast = useRef<Toast>(null);

  const user = useAppSelector((state) => state.auth.user);

  // ─── Tab visibility based on RBAC permissions ──────────────────────────────
  const canSeeDraft = useHasPermission('menu.claims_draft');
  const canSeePending = useHasPermission('menu.claims_pending');
  const canSeeClosed = useHasPermission('menu.claims_closed');

  // Build ordered list of visible tabs — determines which tab to land on
  const visibleTabs = useMemo<TabKey[]>(() => {
    const tabs: TabKey[] = [];
    if (canSeeDraft) tabs.push('draft');
    if (canSeePending) tabs.push('pending');
    if (canSeeClosed) tabs.push('closed');
    return tabs;
  }, [canSeeDraft, canSeePending, canSeeClosed]);

  const [activeTab, setActiveTab] = useState<TabKey>(visibleTabs[0] ?? 'draft');

  // Tab data hooks — only fetch if the tab is visible
  const { data: draftData, isLoading: draftLoading } = useClaimsTabDraft(
    undefined, { enabled: canSeeDraft }
  );
  const { data: pendingData, isLoading: pendingLoading } = useClaimsTabPending(
    undefined, { enabled: canSeePending }
  );
  const { data: closedData, isLoading: closedLoading } = useClaimsTabClosed(
    undefined, { enabled: canSeeClosed }
  );

  const createClaim = useCreateClaim();

  // Vendor picker
  const [showVendorPicker, setShowVendorPicker] = useState(false);
  const [selectedVendorId, setSelectedVendorId] = useState<string>('');
  const [selectedEntityId, setSelectedEntityId] = useState<string>('');
  const { data: vendorData } = useVendors(
    { skip: 0, limit: 500 },
    { enabled: showVendorPicker },
  );
  const vendorOptions = (vendorData?.items ?? []).map((v: any) => ({
    label: `${v.vendor_code} — ${v.vendor_name}`,
    value: v.id,
  }));

  const { data: entityDropdownData } = useEntityDropdown();
  const entityOptions = (entityDropdownData ?? []).map((e: any) => ({
    label: e.label,
    value: e.id,
  }));

  const draftItems: ClaimHeader[] = draftData?.items ?? [];
  const pendingItems: ClaimHeader[] = pendingData?.items ?? [];
  const closedItems: ClaimHeader[] = closedData?.items ?? [];

  const doCreateClaim = useCallback(
    async (vendorId: string, entityId?: string) => {
      try {
        const newClaim = await createClaim.mutateAsync({ vendor_id: vendorId, entity_id: entityId || null });
        setShowVendorPicker(false);
        setSelectedVendorId('');
        setSelectedEntityId('');
        navigate(`/claims/${newClaim.id}/edit`);
      } catch (e: any) {
        toast.current?.show({
          severity: 'error',
          summary: 'Failed to create claim',
          detail: e.response?.data?.detail ?? String(e),
          life: 5000,
        });
      }
    },
    [createClaim, navigate],
  );

  const handleNewClaim = useCallback(async () => {
    const vendorId = user?.vendor_id;
    if (vendorId) {
      // Vendor user — create claim directly and navigate to claim page
      // Entity will be selected on the claim page itself
      await doCreateClaim(vendorId);
    } else {
      // Admin user — show picker for vendor + entity
      setShowVendorPicker(true);
    }
  }, [user?.vendor_id, doCreateClaim]);

  const handleVendorPickerConfirm = useCallback(async () => {
    if (!selectedVendorId) return;
    await doCreateClaim(selectedVendorId, selectedEntityId || undefined);
  }, [selectedVendorId, selectedEntityId, doCreateClaim]);

  // ─── Tab button config ─────────────────────────────────────────────────────
  const tabConfig: Record<TabKey, { label: string; icon: string; count: number }> = {
    draft: { label: 'Draft', icon: 'pi pi-file-edit', count: draftData?.total ?? 0 },
    pending: { label: 'Pending', icon: 'pi pi-clock', count: pendingData?.total ?? 0 },
    closed: { label: 'Closed', icon: 'pi pi-check-circle', count: closedData?.total ?? 0 },
  };

  return (
    <div className="p-3">
      <Toast ref={toast} />

      <div className="flex align-items-center justify-content-between mb-3">
        <div>
          <h2 className="text-xl font-semibold text-900 m-0">Commission Claims</h2>
          <p className="text-600 mt-1 mb-0">Manage your commission claim requests</p>
        </div>
        {canSeeDraft && (
          <Button
            label="New Claim"
            icon="pi pi-plus"
            onClick={handleNewClaim}
            loading={createClaim.isPending}
            aria-label="Create new commission claim"
          />
        )}
      </div>

      <div className="surface-card border-round shadow-1">
        {/* ── Custom Tab Bar ────────────────────────────────────────────────── */}
        <div className="flex border-bottom-1 surface-border px-3 pt-2 gap-1">
          {visibleTabs.map((tabKey) => {
            const cfg = tabConfig[tabKey];
            const isActive = activeTab === tabKey;
            return (
              <button
                key={tabKey}
                type="button"
                onClick={() => setActiveTab(tabKey)}
                className={`
                  flex align-items-center gap-2 px-3 py-2 border-noround
                  cursor-pointer transition-colors transition-duration-150
                  border-none bg-transparent
                  ${isActive
                    ? 'font-semibold border-bottom-2'
                    : 'text-600 hover:text-900 hover:surface-hover border-bottom-2 border-transparent'
                  }
                `}
                style={{
                  marginBottom: '-1px',
                  outline: 'none',
                  color: isActive ? '#ED1C24' : undefined,
                  borderBottomColor: isActive ? '#ED1C24' : undefined,
                }}
                aria-label={`${cfg.label} tab`}
                aria-selected={isActive}
                role="tab"
              >
                <i className={cfg.icon} style={{ fontSize: '0.85rem' }} />
                <span style={{ fontSize: '0.813rem' }}>{cfg.label}</span>
                {cfg.count > 0 && (
                  <span
                    className={`
                      flex align-items-center justify-content-center border-circle
                      text-xs font-bold
                      ${isActive ? 'text-white' : 'surface-200 text-700'}
                    `}
                    style={{
                      minWidth: '20px',
                      height: '20px',
                      padding: '0 5px',
                      fontSize: '0.7rem',
                      backgroundColor: isActive ? '#ED1C24' : undefined,
                    }}
                  >
                    {cfg.count}
                  </span>
                )}
              </button>
            );
          })}
        </div>

        {/* ── Tab Content ──────────────────────────────────────────────────── */}
        <div className="p-3" style={{ minHeight: '400px' }}>
          {/* Draft */}
          {activeTab === 'draft' && canSeeDraft && (
            <DataTable
              value={draftItems}
              loading={draftLoading}
              stripedRows
              paginator
              rows={10}
              rowsPerPageOptions={[10, 25, 50]}
              dataKey="id"
              emptyMessage="No draft claims."
              onRowClick={(e) => navigate(`/claims/${(e.data as ClaimHeader).id}/edit`)}
              rowClassName={() => 'cursor-pointer'}
              aria-label="Draft claims list"
            >
              <Column
                field="claim_number"
                header="Claim Number"
                body={(row: ClaimHeader) => row.claim_number ?? '(Not assigned)'}
                style={{ minWidth: '140px' }}
              />
              <Column field="claim_date" header="Claim Date" style={{ minWidth: '120px' }} />
              <Column
                field="total_claim_amount"
                header="Total Claim Amount"
                body={(row: ClaimHeader) => formatCurrency(row.total_claim_amount)}
                style={{ minWidth: '160px' }}
              />
              <Column
                header="Status"
                body={(row: ClaimHeader) => (
                  <Tag value={row.status} severity={STATUS_SEVERITY[row.status] ?? 'info'} />
                )}
                style={{ minWidth: '100px' }}
              />
              <Column field="modified_date" header="Last Updated" style={{ minWidth: '130px' }} />
            </DataTable>
          )}

          {/* Pending */}
          {activeTab === 'pending' && canSeePending && (
            <DataTable
              value={pendingItems}
              loading={pendingLoading}
              stripedRows
              paginator
              rows={10}
              rowsPerPageOptions={[10, 25, 50]}
              dataKey="id"
              emptyMessage="No pending claims."
              onRowClick={(e) => navigate(`/claims/${(e.data as ClaimHeader).id}`)}
              rowClassName={() => 'cursor-pointer'}
              aria-label="Pending claims list"
            >
              <Column
                field="claim_number"
                header="Claim Number"
                body={(row: ClaimHeader) => row.claim_number ?? '—'}
                style={{ minWidth: '140px' }}
              />
              <Column field="claim_date" header="Claim Date" style={{ minWidth: '120px' }} />
              <Column
                field="total_claim_amount"
                header="Total Claim Amount"
                body={(row: ClaimHeader) => formatCurrency(row.total_claim_amount)}
                style={{ minWidth: '160px' }}
              />
              <Column
                field="total_commission_amount"
                header="Commission"
                body={(row: ClaimHeader) => formatCurrency(row.total_commission_amount)}
                style={{ minWidth: '130px' }}
              />
              <Column
                header="Status"
                body={(row: ClaimHeader) => (
                  <Tag
                    value={row.workflow_status_name || row.status}
                    severity={STATUS_SEVERITY[row.status] ?? 'info'}
                  />
                )}
                style={{ minWidth: '160px' }}
              />
              <Column field="modified_date" header="Last Updated" style={{ minWidth: '130px' }} />
            </DataTable>
          )}

          {/* Closed */}
          {activeTab === 'closed' && canSeeClosed && (
            <DataTable
              value={closedItems}
              loading={closedLoading}
              stripedRows
              paginator
              rows={10}
              rowsPerPageOptions={[10, 25, 50]}
              dataKey="id"
              emptyMessage="No closed claims."
              onRowClick={(e) => navigate(`/claims/${(e.data as ClaimHeader).id}`)}
              rowClassName={() => 'cursor-pointer'}
              aria-label="Closed claims list"
            >
              <Column
                field="claim_number"
                header="Claim Number"
                body={(row: ClaimHeader) => row.claim_number ?? '—'}
                style={{ minWidth: '140px' }}
              />
              <Column field="claim_date" header="Claim Date" style={{ minWidth: '120px' }} />
              <Column
                field="total_claim_amount"
                header="Total Claim Amount"
                body={(row: ClaimHeader) => formatCurrency(row.total_claim_amount)}
                style={{ minWidth: '160px' }}
              />
              <Column
                field="total_commission_amount"
                header="Commission"
                body={(row: ClaimHeader) => formatCurrency(row.total_commission_amount)}
                style={{ minWidth: '130px' }}
              />
              <Column
                header="Status"
                body={(row: ClaimHeader) => (
                  <Tag
                    value={row.workflow_status_name || row.status}
                    severity={STATUS_SEVERITY[row.status] ?? 'info'}
                  />
                )}
                style={{ minWidth: '160px' }}
              />
              <Column field="modified_date" header="Last Updated" style={{ minWidth: '130px' }} />
            </DataTable>
          )}
        </div>
      </div>

      {/* Vendor & Entity picker dialog */}
      <Dialog
        header="Create New Claim"
        visible={showVendorPicker}
        onHide={() => {
          setShowVendorPicker(false);
          setSelectedVendorId('');
          setSelectedEntityId('');
        }}
        style={{ width: '420px' }}
        modal
        footer={
          <div className="flex justify-content-end gap-2">
            <Button
              label="Cancel"
              severity="secondary"
              outlined
              onClick={() => {
                setShowVendorPicker(false);
                setSelectedVendorId('');
                setSelectedEntityId('');
              }}
            />
            <Button
              label="Create Claim"
              icon="pi pi-plus"
              onClick={handleVendorPickerConfirm}
              disabled={!selectedVendorId || !selectedEntityId}
              loading={createClaim.isPending}
            />
          </div>
        }
      >
        <div className="flex flex-column gap-3 pt-2">
          <div className="flex flex-column gap-2">
            <label className="font-medium">
              Entity <span className="text-red-500">*</span>
            </label>
            <Dropdown
              value={selectedEntityId}
              options={entityOptions}
              onChange={(e) => setSelectedEntityId(e.value)}
              placeholder="Select an entity..."
              filter
              filterPlaceholder="Search entities..."
              className="w-full"
              aria-label="Select entity for claim"
            />
          </div>
          {!user?.vendor_id && (
            <div className="flex flex-column gap-2">
              <label className="font-medium">
                Vendor <span className="text-red-500">*</span>
              </label>
              <Dropdown
                value={selectedVendorId}
                options={vendorOptions}
                onChange={(e) => setSelectedVendorId(e.value)}
                placeholder="Select a vendor..."
                filter
                filterPlaceholder="Search vendors..."
                className="w-full"
                aria-label="Select vendor for claim"
              />
            </div>
          )}
        </div>
      </Dialog>
    </div>
  );
};

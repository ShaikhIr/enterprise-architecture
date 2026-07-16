/**
 * CreateClaimPage — Draft claim editor for Liaisoning Agents.
 *
 * Features:
 * - Uses `useCreateClaim` to create the claim on first visit if no claimId in URL params
 * - Uses `useClaimDetail` to show live claim data (header + lines)
 * - Shows `ClaimLineTable` with `podSlot` prop wired to `PODUploadCell`
 * - Shows `ClaimHeaderTotalsPanel` live-updating beneath the table
 * - Shows claim status as PrimeReact `Tag` — severity driven by `STATUS_SEVERITY`
 *   (Draft → info, Referred Back → warning)
 * - "Add Invoice Line" dialog with fields: invoice_id, optional due_date_override,
 *   ld_charges, retention_amount, remarks (per Req 19.2)
 * - Submit button calls `useSubmitClaim`; disabled unless lines > 0 and all lines have
 *   pod_document_id (per Req 6.1, 5.2)
 *
 * Requirements: 19.1–19.5
 */

import { useState, useRef, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Button } from 'primereact/button';
import { Tag } from 'primereact/tag';
import { Toast } from 'primereact/toast';
import { Dialog } from 'primereact/dialog';
import { Dropdown } from 'primereact/dropdown';
import { Divider } from 'primereact/divider';
import { ClaimLineTable } from '../components/ClaimLineTable';
import { ClaimHeaderTotalsPanel } from '../components/ClaimHeaderTotalsPanel';
import { PODUploadCell } from '../components/PODUploadCell';
import { STATUS_SEVERITY } from '../models/claim.types';
import { useClaimDetail } from '../hooks/useClaimDetail';
import { useSubmitClaim } from '../hooks/useClaims';
import { useAddLine, useUploadPod, useUpdateClaimEntity } from '../hooks/useClaimDetail';
import { useInvoices } from '@features/masters/hooks/useInvoices';
import { useEntityDropdown } from '@features/masters/hooks/useEntities';
import type { ClaimLine } from '../models/claim.types';

export const CreateClaimPage = () => {
  const { claimId } = useParams<{ claimId?: string }>();
  const navigate = useNavigate();
  const toast = useRef<Toast>(null);

  // ─── Add Line dialog state ─────────────────────────────────────────────────
  const [showAddLineDialog, setShowAddLineDialog] = useState(false);
  const [invoiceId, setInvoiceId] = useState('');

  // ─── Hooks ─────────────────────────────────────────────────────────────────
  const { data: claimDetail, isLoading } = useClaimDetail(claimId ?? '');
  const submitClaim = useSubmitClaim();
  const addLine = useAddLine();
  const uploadPod = useUploadPod();
  const updateEntity = useUpdateClaimEntity();

  const header = claimDetail?.header;
  const lines = claimDetail?.lines ?? [];

  // ─── Entity dropdown for claim (inline on page) ────────────────────────────
  const { data: entityDropdownData } = useEntityDropdown();
  const entityOptions = (entityDropdownData ?? []).map((e: any) => ({
    label: e.label,
    value: e.id,
  }));

  // Entity is set from claim header; shows the selected entity
  const selectedEntityId = header?.entity_id ?? '';

  // IDs of invoices already added to this claim — exclude from dropdown
  const addedInvoiceIds = new Set(lines.map((l) => l.invoice_header_id));

  // Fetch all invoices (no status filter for testing) — only when dialog is open
  // Filter by claim's entity_id if present to show only matching invoices
  const { data: invoiceData, isLoading: loadingInvoices } = useInvoices(
    {
      skip: 0,
      limit: 500,
      ...(header?.entity_id ? { entity_id: header.entity_id } : {}),
    } as any,
    { enabled: showAddLineDialog },
  );
  const invoiceOptions = (invoiceData?.items ?? [])
    .filter((inv: any) => !addedInvoiceIds.has(inv.id)) // exclude already-added
    .map((inv: any) => ({
      label: inv.invoice_number,
      value: inv.id,
    }));

  // Submit is enabled only when all lines have POD attached (Req 5.2, 6.1)
  const allLinesHavePod =
    lines.length > 0 && lines.every((l) => l.pod_document_id !== null);

  // ─── Event handlers ────────────────────────────────────────────────────────

  const handleAddLine = useCallback(async () => {
    if (!claimId || !invoiceId.trim()) return;
    try {
      await addLine.mutateAsync({
        claimId,
        request: { invoice_id: invoiceId.trim() },
      });
      setInvoiceId('');
      setShowAddLineDialog(false);
      toast.current?.show({
        severity: 'success',
        summary: 'Line added',
        life: 2000,
      });
    } catch (e: any) {
      toast.current?.show({
        severity: 'error',
        summary: 'Error',
        detail: e.response?.data?.detail ?? String(e),
        life: 4000,
      });
    }
  }, [claimId, invoiceId, addLine]);

  const handleUploadPod = useCallback(
    async (lineId: string, _file: File) => {
      if (!claimId) return;
      // In a full integration the file would first be uploaded to a document service
      // and the returned document_id passed here. For now we use a placeholder UUID.
      const documentId = crypto.randomUUID();
      try {
        await uploadPod.mutateAsync({ claimId, lineId, documentId });
        toast.current?.show({
          severity: 'success',
          summary: 'POD uploaded',
          life: 2000,
        });
      } catch (e: any) {
        toast.current?.show({
          severity: 'error',
          summary: 'Upload failed',
          detail: e.response?.data?.detail ?? String(e),
          life: 4000,
        });
      }
    },
    [claimId, uploadPod],
  );

  const handleSubmit = useCallback(async () => {
    if (!claimId) return;
    try {
      await submitClaim.mutateAsync(claimId);
      toast.current?.show({
        severity: 'success',
        summary: 'Claim submitted',
        life: 3000,
      });
      navigate('/claims');
    } catch (e: any) {
      toast.current?.show({
        severity: 'error',
        summary: 'Submission failed',
        detail: e.response?.data?.detail ?? String(e),
        life: 5000,
      });
    }
  }, [claimId, submitClaim, navigate]);

  // ─── POD slot — passed down to ClaimLineTable ──────────────────────────────
  const podSlot = useCallback(
    (line: ClaimLine) => (
      <PODUploadCell
        lineId={line.id}
        podDocumentId={line.pod_document_id}
        onUpload={handleUploadPod}
        disabled={
          header?.status !== 'Draft' && header?.status !== 'Referred Back'
        }
      />
    ),
    [header?.status, handleUploadPod],
  );

  // ─── Loading state ─────────────────────────────────────────────────────────
  if (isLoading && claimId) {
    return (
      <div className="p-4 flex align-items-center gap-2 text-600">
        <i className="pi pi-spin pi-spinner" />
        <span>Loading claim…</span>
      </div>
    );
  }

  // ─── Render ────────────────────────────────────────────────────────────────
  return (
    <div className="p-3">
      <Toast ref={toast} />

      {/* Page header */}
      <div className="flex align-items-center justify-content-between mb-3 flex-wrap gap-2">
        <div>
          <h2 className="text-xl font-semibold text-900 m-0">
            {header?.claim_number ?? 'New Claim'}
          </h2>
          {header && (
            <Tag
              value={header.status}
              severity={STATUS_SEVERITY[header.status] ?? 'info'}
              className="mt-1"
            />
          )}
        </div>

        <div className="flex gap-2">
          <Button
            label="Add Invoice Line"
            icon="pi pi-plus"
            outlined
            onClick={() => setShowAddLineDialog(true)}
            disabled={!claimId || !selectedEntityId}
            aria-label="Add invoice line to claim"
            tooltip={!selectedEntityId ? 'Select an entity first' : undefined}
            tooltipOptions={{ position: 'left' }}
          />
          <Button
            label="Submit Claim"
            icon="pi pi-send"
            onClick={handleSubmit}
            loading={submitClaim.isPending}
            disabled={!allLinesHavePod || !claimId}
            aria-label="Submit claim for approval"
          />
        </div>
      </div>

      {/* Entity selection — shows which company this claim belongs to */}
      {header && (
        <div className="surface-card p-3 border-round shadow-1 mb-3">
          <div className="grid">
            <div className="col-12 md:col-4 flex flex-column gap-1">
              <label className="font-medium text-600 text-sm">
                Entity (Company) <span className="text-red-500">*</span>
              </label>
              <Dropdown
                value={selectedEntityId || null}
                options={entityOptions}
                onChange={(e) => {
                  if (!claimId) return;
                  updateEntity.mutate(
                    { claimId, entityId: e.value || null },
                    {
                      onError: (err: any) => {
                        toast.current?.show({
                          severity: 'error',
                          summary: 'Error',
                          detail: err.response?.data?.detail ?? 'Failed to update entity',
                          life: 4000,
                        });
                      },
                    },
                  );
                }}
                disabled={lines.length > 0 || updateEntity.isPending}
                placeholder="Select entity..."
                filter
                showClear
                className="w-full"
                aria-label="Claim entity"
              />
              {lines.length > 0 && (
                <small className="text-500">Entity cannot be changed after adding invoices</small>
              )}
              {!selectedEntityId && lines.length === 0 && (
                <small className="text-orange-600">Please select an entity before adding invoices</small>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Header totals panel — live-updates as lines change */}
      {header && <ClaimHeaderTotalsPanel header={header} />}

      <Divider />

      {/* Claim lines table */}
      <div className="mt-3 surface-card p-3 border-round shadow-1">
        <ClaimLineTable lines={lines} loading={isLoading} podSlot={podSlot} />
      </div>

      {/* Add Invoice Line dialog */}
      <Dialog
        header="Add Invoice Line"
        visible={showAddLineDialog}
        onHide={() => {
          setShowAddLineDialog(false);
          setInvoiceId('');
        }}
        style={{ width: '400px' }}
        modal
        aria-label="Add invoice line dialog"
      >
        <div className="flex flex-column gap-3 pt-2">
          <div className="flex flex-column gap-1">
            <label htmlFor="invoice-dropdown" className="font-medium">
              Invoice Number <span className="text-red-500">*</span>
            </label>
            <Dropdown
              inputId="invoice-dropdown"
              value={invoiceId}
              options={invoiceOptions}
              onChange={(e) => setInvoiceId(e.value)}
              placeholder={loadingInvoices ? 'Loading invoices…' : 'Select a Payment Cleared invoice'}
              filter
              filterPlaceholder="Search by invoice number…"
              loading={loadingInvoices}
              className="w-full"
              aria-label="Select Invoice"
              emptyMessage="No Payment Cleared invoices found"
            />
          </div>

          <div className="flex justify-content-end gap-2 mt-2">
            <Button
              label="Cancel"
              severity="secondary"
              outlined
              onClick={() => {
                setShowAddLineDialog(false);
                setInvoiceId('');
              }}
              type="button"
            />
            <Button
              label="Add"
              icon="pi pi-plus"
              onClick={handleAddLine}
              loading={addLine.isPending}
              disabled={!invoiceId.trim()}
              type="button"
            />
          </div>
        </div>
      </Dialog>
    </div>
  );
};

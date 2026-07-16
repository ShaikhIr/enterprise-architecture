/**
 * ClaimDetailPage — Read/action page for approvers to view a pending claim and take
 * workflow actions.
 *
 * Features:
 * - Shows claim detail with `ClaimLineTable` and `ClaimHeaderTotalsPanel`
 * - Workflow actions (Approve, Refer Back, Reject) via `ClaimActionDialog`
 *   shown when `available_actions` is non-empty
 * - Finance step: renders `payment_clearing_date` as editable Calendar when
 *   `workflow_status.step_code === 'FINANCE_REVIEW'` and user has `claims.approve`
 *   permission — otherwise read-only (Req 20.5)
 * - Uses `useClaimDetail` for data, `useWorkflowAction` for mutations
 *
 * Requirements: 20.3, 20.5
 */

import { useState, useRef, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Button } from 'primereact/button';
import { Tag } from 'primereact/tag';
import { Toast } from 'primereact/toast';
import { Calendar } from 'primereact/calendar';
import { Divider } from 'primereact/divider';
import { useHasPermission } from '@core/rbac';
import { useEntityDropdown } from '@features/masters/hooks/useEntities';
import { ClaimLineTable } from '../components/ClaimLineTable';
import { ClaimHeaderTotalsPanel } from '../components/ClaimHeaderTotalsPanel';
import { ClaimActionDialog, type WorkflowActionType } from '../components/ClaimActionDialog';
import { PODUploadCell } from '../components/PODUploadCell';
import { STATUS_SEVERITY, type ClaimLine } from '../models/claim.types';
import {
  useClaimDetail,
  useWorkflowAction,
  useUpdatePaymentClearingDate,
} from '../hooks/useClaimDetail';

export const ClaimDetailPage = () => {
  const { claimId } = useParams<{ claimId: string }>();
  const navigate = useNavigate();
  const toast = useRef<Toast>(null);

  // ─── Dialog state ─────────────────────────────────────────────────────────
  const [actionDialog, setActionDialog] = useState<{
    visible: boolean;
    action: WorkflowActionType;
  }>({ visible: false, action: 'approve' });

  // ─── Permission check ─────────────────────────────────────────────────────
  const canApprove = useHasPermission('claims.approve');
  const canReferBack = useHasPermission('claims.refer_back');
  const canReject = useHasPermission('claims.reject');

  // ─── Hooks ────────────────────────────────────────────────────────────────
  const { data: claimDetail, isLoading } = useClaimDetail(claimId ?? '');
  const workflowAction = useWorkflowAction();
  const updatePaymentDate = useUpdatePaymentClearingDate();

  // Entity name lookup
  const { data: entityDropdownData } = useEntityDropdown();

  // ─── All useCallback hooks MUST be before any early returns ────────────────
  const openAction = (action: WorkflowActionType) =>
    setActionDialog({ visible: true, action });

  const closeAction = () =>
    setActionDialog((prev) => ({ ...prev, visible: false }));

  const handleConfirmAction = useCallback(
    async (remarks: string) => {
      if (!claimId) return;
      try {
        await workflowAction.mutateAsync({
          claimId,
          action: actionDialog.action,
          request: { remarks },
        });
        setActionDialog((prev) => ({ ...prev, visible: false }));
        toast.current?.show({ severity: 'success', summary: 'Action completed', life: 3000 });
        // Navigate back to claims list after successful action
        // The query invalidation in the hook will ensure all tabs refresh
        setTimeout(() => navigate('/claims'), 1500);
      } catch (e: any) {
        toast.current?.show({ severity: 'error', summary: 'Action failed', detail: e.response?.data?.detail ?? String(e), life: 5000 });
      }
    },
    [claimId, actionDialog.action, workflowAction, navigate],
  );

  const handlePodUpload = useCallback(
    (_lineId: string, _file: File) => { /* no-op on detail page */ },
    [],
  );

  const handlePaymentDateChange = useCallback(
    (lineId: string, newDate: Date | null) => {
      if (!newDate || !claimId) return;
      const isoDate = newDate.toISOString().split('T')[0] ?? '';
      updatePaymentDate.mutate(
        { claimId, lineId, request: { payment_clearing_date: isoDate } },
        {
          onSuccess: () => toast.current?.show({ severity: 'success', summary: 'Payment date updated', life: 3000 }),
          onError: (err: any) => toast.current?.show({ severity: 'error', summary: 'Update failed', detail: err.response?.data?.detail ?? 'Failed', life: 5000 }),
        },
      );
    },
    [claimId, updatePaymentDate],
  );

  // ─── Guards (after all hooks) ──────────────────────────────────────────────
  if (!claimId) return null;

  if (isLoading) {
    return (
      <div className="p-4 flex align-items-center gap-2 text-600">
        <i className="pi pi-spin pi-spinner" />
        <span>Loading claim…</span>
      </div>
    );
  }

  if (!claimDetail) {
    return <div className="p-4 text-red-500">Claim not found.</div>;
  }

  const header = claimDetail.header;
  const lines = claimDetail.lines ?? [];
  const available_actions = claimDetail.available_actions ?? [];
  const workflow_status = claimDetail.workflow_status;

  // ─── Finance step detection (Req 20.5) ────────────────────────────────────
  const isFinanceStep = (workflow_status as any)?.step_code === 'FINANCE_REVIEW';
  const showEditablePaymentDate = isFinanceStep && canApprove;

  // Extract action codes from available_actions (may be strings or {action_code} objects)
  const actionCodes: string[] = available_actions.map((a: any) =>
    typeof a === 'string' ? a : (a?.action_code ?? '')
  );

  // ─── Column slot: POD (read-only on detail page) + editable payment date ──
  const podSlot = (line: ClaimLine) => (
    <div className="flex flex-column gap-2">
      {/* POD display — read-only on detail/approver page */}
      <PODUploadCell
        lineId={line.id}
        podDocumentId={line.pod_document_id}
        onUpload={handlePodUpload}
        disabled={true}
      />

      {/* Editable payment clearing date for Finance step only (Req 20.5) */}
      {showEditablePaymentDate && (
        <div className="flex flex-column gap-1">
          <label
            htmlFor={`pcd-${line.id}`}
            className="text-xs text-500 font-medium"
          >
            Payment Clearing Date
          </label>
          <Calendar
            inputId={`pcd-${line.id}`}
            value={
              line.payment_clearing_date
                ? new Date(line.payment_clearing_date)
                : null
            }
            onChange={(e) =>
              handlePaymentDateChange(line.id, e.value as Date | null)
            }
            dateFormat="yy-mm-dd"
            showIcon
            style={{ width: '170px' }}
            aria-label={`Edit payment clearing date for line ${line.id}`}
            disabled={updatePaymentDate.isPending}
          />
        </div>
      )}
    </div>
  );

  // ─── Render ────────────────────────────────────────────────────────────────
  return (
    <div className="p-3">
      <Toast ref={toast} />

      {/* Header bar */}
      <div className="flex align-items-center justify-content-between mb-3 flex-wrap gap-2">
        <div className="flex align-items-center gap-2">
          <Button
            icon="pi pi-arrow-left"
            text
            rounded
            size="small"
            onClick={() => navigate(-1)}
            aria-label="Go back"
          />
          <h2 className="text-xl font-semibold text-900 m-0">
            {header.claim_number ?? 'Claim'}
          </h2>
          <Tag
            value={header.status}
            severity={STATUS_SEVERITY[header.status] ?? 'info'}
          />
        </div>

        {/* Workflow action buttons — shown only when user has RBAC permission AND available_actions is non-empty */}
        <div className="flex gap-2 flex-wrap">
          {canApprove && (actionCodes.includes('APPROVE') || actionCodes.includes('approve') ||
            actionCodes.includes('final_approve') || actionCodes.includes('FINAL_APPROVE')) && (
            <Button
              label="Approve"
              icon="pi pi-check"
              severity="success"
              onClick={() => openAction('approve')}
              aria-label="Approve claim"
            />
          )}
          {canReferBack && (actionCodes.includes('REFER_BACK') || actionCodes.includes('refer_back')) && (
            <Button
              label="Refer Back"
              icon="pi pi-arrow-left"
              severity="warning"
              onClick={() => openAction('referBack')}
              aria-label="Refer back claim"
            />
          )}
          {canReject && (actionCodes.includes('REJECT') || actionCodes.includes('reject')) && (
            <Button
              label="Reject"
              icon="pi pi-times"
              severity="danger"
              onClick={() => openAction('reject')}
              aria-label="Reject claim"
            />
          )}
        </div>
      </div>

      {/* Entity (Company) — read-only display */}
      {header.entity_id && (
        <div className="surface-card p-3 border-round shadow-1 mb-3">
          <div className="flex align-items-center gap-2">
            <i className="pi pi-building text-600" />
            <span className="font-medium text-600 text-sm">Entity:</span>
            <span className="font-semibold text-900">
              {entityDropdownData?.find((e) => e.id === header.entity_id)?.label ?? header.entity_id}
            </span>
          </div>
        </div>
      )}

      {/* Header totals */}
      <ClaimHeaderTotalsPanel header={header} />

      <Divider />

      {/* Finance step notice */}
      {showEditablePaymentDate && (
        <p className="text-sm text-orange-600 m-0 mb-2">
          <i className="pi pi-info-circle mr-1" />
          You are at the Finance Review step — payment clearing dates are
          editable below.
        </p>
      )}

      {/* Claim lines */}
      <div className="surface-card p-3 border-round shadow-1">
        <ClaimLineTable lines={lines} loading={isLoading} podSlot={podSlot} />
      </div>

      {/* Workflow action dialog */}
      <ClaimActionDialog
        visible={actionDialog.visible}
        action={actionDialog.action}
        onHide={closeAction}
        onConfirm={handleConfirmAction}
        loading={workflowAction.isPending}
      />
    </div>
  );
};

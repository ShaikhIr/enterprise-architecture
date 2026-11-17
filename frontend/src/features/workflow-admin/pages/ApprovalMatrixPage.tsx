/**
 * Approval matrix configuration.
 * Manage the routing tables, and preview how a sample record would route through
 * them before relying on the rules.
 */

import { useRef, useState } from 'react';

import { Button } from 'primereact/button';
import { ConfirmDialog, confirmDialog } from 'primereact/confirmdialog';
import { Toast } from 'primereact/toast';
import { useNavigate } from 'react-router-dom';

import { useCan } from '@core/rbac';

import { extractApiError } from '@shared/utils/apiError';

import { ApprovalMatrixForm } from '../components/ApprovalMatrixForm';
import { ApprovalMatrixResolveDialog } from '../components/ApprovalMatrixResolveDialog';
import { ApprovalMatrixTable } from '../components/ApprovalMatrixTable';
import {
  useApprovalMatrices,
  useCreateApprovalMatrix,
  useDeleteApprovalMatrix,
  useResolveApprovalMatrix,
  useUpdateApprovalMatrix,
} from '../hooks/useApprovalMatrices';
import type { ApprovalMatrix, CreateApprovalMatrixRequest } from '../models/ApprovalMatrix';

export const ApprovalMatrixPage = () => {
  const navigate = useNavigate();
  const toast = useRef<Toast>(null);
  const [showDialog, setShowDialog] = useState(false);
  const [editing, setEditing] = useState<ApprovalMatrix | null>(null);
  const [showResolve, setShowResolve] = useState(false);

  const canCreate = useCan('approval_matrices', 'CREATE');
  const canUpdate = useCan('approval_matrices', 'UPDATE');
  const canDelete = useCan('approval_matrices', 'DELETE');
  const canViewWorkflows = useCan('workflows', 'READ');

  const { data, isLoading, refetch, isRefetching } = useApprovalMatrices();
  const createMutation = useCreateApprovalMatrix();
  const updateMutation = useUpdateApprovalMatrix();
  const deleteMutation = useDeleteApprovalMatrix();
  const resolveMutation = useResolveApprovalMatrix();

  const notifyError = (error: unknown, fallback: string) => {
    toast.current?.show({
      severity: 'error',
      summary: 'Error',
      detail: extractApiError(error, fallback),
      life: 6000,
    });
  };

  const notifySuccess = (summary: string, detail: string) => {
    toast.current?.show({ severity: 'success', summary, detail, life: 3000 });
  };

  const handleSubmit = async (formData: CreateApprovalMatrixRequest) => {
    try {
      if (editing) {
        // `code` is immutable after creation, so it is not sent on update.
        const { code: _code, ...changes } = formData;
        await updateMutation.mutateAsync({ matrixId: editing.id, request: changes });
        notifySuccess('Updated', `Matrix '${editing.code}' updated`);
      } else {
        await createMutation.mutateAsync(formData);
        notifySuccess('Created', `Matrix '${formData.code}' created`);
      }
      setShowDialog(false);
      setEditing(null);
    } catch (error) {
      notifyError(error, 'Failed to save the approval matrix');
    }
  };

  const handleDelete = (matrix: ApprovalMatrix) => {
    confirmDialog({
      header: 'Delete approval matrix',
      message: `Delete '${matrix.name}'? Its conditions and approval levels go with it.`,
      icon: 'pi pi-exclamation-triangle',
      acceptLabel: 'Delete',
      acceptClassName: 'p-button-danger',
      rejectLabel: 'Cancel',
      accept: async () => {
        try {
          await deleteMutation.mutateAsync(matrix.id);
          notifySuccess('Deleted', `Matrix '${matrix.code}' deleted`);
        } catch (error) {
          notifyError(error, 'Failed to delete the approval matrix');
        }
      },
    });
  };

  const handleResolve = async (entityType: string, entityData: Record<string, unknown>) => {
    try {
      await resolveMutation.mutateAsync({
        entity_type: entityType,
        entity_data: entityData,
      });
    } catch (error) {
      notifyError(error, 'Failed to resolve the routing');
    }
  };

  return (
    <div className="p-4">
      <Toast ref={toast} />
      <ConfirmDialog />

      <div className="flex align-items-center justify-content-between mb-4 flex-wrap gap-3">
        <div>
          <h2 className="text-2xl font-semibold text-900 m-0">Approval Matrix</h2>
          <p className="text-600 mt-1 mb-0">
            Route records to approvers by condition. The lowest-priority matrix whose conditions
            match wins.
          </p>
        </div>
        <div className="flex gap-2">
          {canViewWorkflows && (
            <Button
              label="Workflows"
              icon="pi pi-sitemap"
              severity="secondary"
              outlined
              onClick={() => navigate('/workflows')}
              aria-label="Go to workflows"
            />
          )}
          <Button
            label="Preview Routing"
            icon="pi pi-play"
            severity="secondary"
            outlined
            onClick={() => {
              resolveMutation.reset();
              setShowResolve(true);
            }}
            aria-label="Preview approval routing"
          />
          <Button
            label="Refresh"
            icon="pi pi-refresh"
            severity="secondary"
            outlined
            loading={isRefetching}
            onClick={() => refetch()}
            aria-label="Refresh approval matrices"
          />
          {canCreate && (
            <Button
              label="New Matrix"
              icon="pi pi-plus"
              onClick={() => {
                setEditing(null);
                setShowDialog(true);
              }}
              aria-label="Create new approval matrix"
            />
          )}
        </div>
      </div>

      <div className="surface-card p-4 border-round shadow-1">
        <ApprovalMatrixTable
          matrices={data?.matrices ?? []}
          loading={isLoading}
          canUpdate={canUpdate}
          canDelete={canDelete}
          onEdit={(matrix) => {
            setEditing(matrix);
            setShowDialog(true);
          }}
          onDelete={handleDelete}
        />
      </div>

      <ApprovalMatrixForm
        visible={showDialog}
        matrix={editing}
        loading={createMutation.isPending || updateMutation.isPending}
        onHide={() => {
          setShowDialog(false);
          setEditing(null);
        }}
        onSubmit={handleSubmit}
      />

      <ApprovalMatrixResolveDialog
        visible={showResolve}
        loading={resolveMutation.isPending}
        result={resolveMutation.data ?? null}
        onHide={() => setShowResolve(false)}
        onResolve={handleResolve}
      />
    </div>
  );
};

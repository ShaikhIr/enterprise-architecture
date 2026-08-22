/**
 * Workflow definitions list.
 * Create and manage workflows; the builder for a single workflow lives on its own
 * route so the state machine has room to breathe.
 */

import { useRef, useState } from 'react';

import { Button } from 'primereact/button';
import { ConfirmDialog, confirmDialog } from 'primereact/confirmdialog';
import { Toast } from 'primereact/toast';
import { useNavigate } from 'react-router-dom';

import { useCan } from '@core/rbac';

import { extractApiError } from '@shared/utils/apiError';

import { WorkflowDefinitionForm } from '../components/WorkflowDefinitionForm';
import { WorkflowDefinitionTable } from '../components/WorkflowDefinitionTable';
import {
  useCreateWorkflowDefinition,
  useDeleteWorkflowDefinition,
  useUpdateWorkflowDefinition,
  useWorkflowDefinitions,
} from '../hooks/useWorkflows';
import type { CreateWorkflowDefinitionRequest, WorkflowDefinition } from '../models/Workflow';

export const WorkflowDefinitionsPage = () => {
  const navigate = useNavigate();
  const toast = useRef<Toast>(null);
  const [showDialog, setShowDialog] = useState(false);
  const [editing, setEditing] = useState<WorkflowDefinition | null>(null);

  // Designing a workflow is a different grant from running one, so the buttons are
  // gated on the same (resource, action) pairs the endpoints authorise on.
  const canCreate = useCan('workflows', 'CREATE');
  const canUpdate = useCan('workflows', 'UPDATE');
  const canDelete = useCan('workflows', 'DELETE');
  const canViewMatrices = useCan('approval_matrices', 'READ');

  const { data, isLoading, refetch, isRefetching } = useWorkflowDefinitions();
  const createMutation = useCreateWorkflowDefinition();
  const updateMutation = useUpdateWorkflowDefinition();
  const deleteMutation = useDeleteWorkflowDefinition();

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

  const openCreate = () => {
    setEditing(null);
    setShowDialog(true);
  };

  const openEdit = (definition: WorkflowDefinition) => {
    setEditing(definition);
    setShowDialog(true);
  };

  const handleSubmit = async (formData: CreateWorkflowDefinitionRequest) => {
    try {
      if (editing) {
        // `code` is immutable after creation, so it is not sent on update.
        const { code: _code, ...changes } = formData;
        await updateMutation.mutateAsync({
          definitionId: editing.id,
          request: changes,
        });
        notifySuccess('Updated', `Workflow '${editing.code}' updated`);
      } else {
        await createMutation.mutateAsync(formData);
        notifySuccess('Created', `Workflow '${formData.code}' created`);
      }
      setShowDialog(false);
      setEditing(null);
    } catch (error) {
      notifyError(error, 'Failed to save the workflow');
    }
  };

  const handleDelete = (definition: WorkflowDefinition) => {
    confirmDialog({
      header: 'Delete workflow',
      message: `Delete '${definition.name}'? Its states and transitions go with it. Workflows with instances cannot be deleted — deactivate them instead.`,
      icon: 'pi pi-exclamation-triangle',
      acceptLabel: 'Delete',
      acceptClassName: 'p-button-danger',
      rejectLabel: 'Cancel',
      accept: async () => {
        try {
          await deleteMutation.mutateAsync(definition.id);
          notifySuccess('Deleted', `Workflow '${definition.code}' deleted`);
        } catch (error) {
          notifyError(error, 'Failed to delete the workflow');
        }
      },
    });
  };

  return (
    <div className="p-4">
      <Toast ref={toast} />
      <ConfirmDialog />

      <div className="flex align-items-center justify-content-between mb-4 flex-wrap gap-3">
        <div>
          <h2 className="text-2xl font-semibold text-900 m-0">Workflows</h2>
          <p className="text-600 mt-1 mb-0">
            Define the approval flows that govern compliance records
          </p>
        </div>
        <div className="flex gap-2">
          {canViewMatrices && (
            <Button
              label="Approval Matrix"
              icon="pi pi-check-square"
              severity="secondary"
              outlined
              onClick={() => navigate('/approval-matrix')}
              aria-label="Go to approval matrix"
            />
          )}
          <Button
            label="Refresh"
            icon="pi pi-refresh"
            severity="secondary"
            outlined
            loading={isRefetching}
            onClick={() => refetch()}
            aria-label="Refresh workflows"
          />
          {canCreate && (
            <Button
              label="New Workflow"
              icon="pi pi-plus"
              onClick={openCreate}
              aria-label="Create new workflow"
            />
          )}
        </div>
      </div>

      <div className="surface-card p-4 border-round shadow-1">
        <WorkflowDefinitionTable
          definitions={data?.definitions ?? []}
          loading={isLoading}
          canUpdate={canUpdate}
          canDelete={canDelete}
          onConfigure={(definition) => navigate(`/workflows/${definition.id}`)}
          onEdit={openEdit}
          onDelete={handleDelete}
        />
      </div>

      <WorkflowDefinitionForm
        visible={showDialog}
        definition={editing}
        loading={createMutation.isPending || updateMutation.isPending}
        onHide={() => {
          setShowDialog(false);
          setEditing(null);
        }}
        onSubmit={handleSubmit}
      />
    </div>
  );
};

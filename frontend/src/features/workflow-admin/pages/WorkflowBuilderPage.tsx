/**
 * Workflow builder — states and transitions for one definition.
 *
 * Both tables read from the single definition-detail response, so every mutation
 * invalidates that one query and the two views can never disagree about which
 * states exist.
 */

import { useMemo, useRef, useState } from 'react';

import { Button } from 'primereact/button';
import { ConfirmDialog, confirmDialog } from 'primereact/confirmdialog';
import { Message } from 'primereact/message';
import { ProgressSpinner } from 'primereact/progressspinner';
import { Tag } from 'primereact/tag';
import { Toast } from 'primereact/toast';
import { useNavigate, useParams } from 'react-router-dom';

import { useCan } from '@core/rbac';

import { extractApiError } from '@shared/utils/apiError';

import { WorkflowStatusForm } from '../components/WorkflowStatusForm';
import { WorkflowStatusTable } from '../components/WorkflowStatusTable';
import { WorkflowTransitionForm } from '../components/WorkflowTransitionForm';
import { WorkflowTransitionTable } from '../components/WorkflowTransitionTable';
import {
  useCreateWorkflowStatus,
  useCreateWorkflowTransition,
  useDeleteWorkflowStatus,
  useDeleteWorkflowTransition,
  useUpdateWorkflowStatus,
  useWorkflowDefinition,
} from '../hooks/useWorkflows';
import type {
  CreateWorkflowStatusRequest,
  CreateWorkflowTransitionRequest,
  WorkflowStatus,
  WorkflowTransition,
} from '../models/Workflow';

export const WorkflowBuilderPage = () => {
  const { definitionId } = useParams<{ definitionId: string }>();
  const navigate = useNavigate();
  const toast = useRef<Toast>(null);

  const [showStatusDialog, setShowStatusDialog] = useState(false);
  const [editingStatus, setEditingStatus] = useState<WorkflowStatus | null>(null);
  const [showTransitionDialog, setShowTransitionDialog] = useState(false);

  // States and transitions are part of the workflow definition, so they are gated
  // on the same resource rather than one of their own.
  const canCreate = useCan('workflows', 'CREATE');
  const canUpdate = useCan('workflows', 'UPDATE');
  const canDelete = useCan('workflows', 'DELETE');

  const { data, isLoading, isError, error } = useWorkflowDefinition(definitionId);
  const createStatus = useCreateWorkflowStatus(definitionId);
  const updateStatus = useUpdateWorkflowStatus(definitionId);
  const deleteStatus = useDeleteWorkflowStatus(definitionId);
  const createTransition = useCreateWorkflowTransition(definitionId);
  const deleteTransition = useDeleteWorkflowTransition(definitionId);

  /*
    Memoised because the three useMemos below depend on them. `?? []` builds a fresh array
    every render while the query is loading, which would defeat the memoisation it feeds.
  */
  const statuses = useMemo(() => data?.statuses ?? [], [data?.statuses]);
  const transitions = useMemo(() => data?.transitions ?? [], [data?.transitions]);

  const hasInitialState = useMemo(() => statuses.some((status) => status.is_initial), [statuses]);
  const hasTerminalState = useMemo(() => statuses.some((status) => status.is_terminal), [statuses]);
  const nextSequence = useMemo(
    () => (statuses.length === 0 ? 0 : Math.max(...statuses.map((status) => status.sequence)) + 10),
    [statuses],
  );

  const notifyError = (err: unknown, fallback: string) => {
    toast.current?.show({
      severity: 'error',
      summary: 'Error',
      detail: extractApiError(err, fallback),
      life: 6000,
    });
  };

  const notifySuccess = (summary: string, detail: string) => {
    toast.current?.show({ severity: 'success', summary, detail, life: 3000 });
  };

  const handleStatusSubmit = async (formData: CreateWorkflowStatusRequest) => {
    try {
      if (editingStatus) {
        await updateStatus.mutateAsync({
          statusId: editingStatus.id,
          request: formData,
        });
        notifySuccess('Updated', `State '${formData.code}' updated`);
      } else {
        await createStatus.mutateAsync(formData);
        notifySuccess('Added', `State '${formData.code}' added`);
      }
      setShowStatusDialog(false);
      setEditingStatus(null);
    } catch (err) {
      notifyError(err, 'Failed to save the state');
    }
  };

  const handleStatusDelete = (status: WorkflowStatus) => {
    confirmDialog({
      header: 'Delete state',
      message: `Delete state '${status.name}'? States referenced by a transition or holding live instances cannot be deleted.`,
      icon: 'pi pi-exclamation-triangle',
      acceptLabel: 'Delete',
      acceptClassName: 'p-button-danger',
      rejectLabel: 'Cancel',
      accept: async () => {
        try {
          await deleteStatus.mutateAsync(status.id);
          notifySuccess('Deleted', `State '${status.code}' deleted`);
        } catch (err) {
          notifyError(err, 'Failed to delete the state');
        }
      },
    });
  };

  const handleTransitionSubmit = async (formData: CreateWorkflowTransitionRequest) => {
    try {
      await createTransition.mutateAsync(formData);
      notifySuccess('Added', `Action '${formData.action_code}' wired up`);
      setShowTransitionDialog(false);
    } catch (err) {
      notifyError(err, 'Failed to add the transition');
    }
  };

  const handleTransitionDelete = (transition: WorkflowTransition) => {
    confirmDialog({
      header: 'Delete transition',
      message: `Remove the '${transition.action_code}' transition?`,
      icon: 'pi pi-exclamation-triangle',
      acceptLabel: 'Delete',
      acceptClassName: 'p-button-danger',
      rejectLabel: 'Cancel',
      accept: async () => {
        try {
          await deleteTransition.mutateAsync(transition.id);
          notifySuccess('Deleted', 'Transition removed');
        } catch (err) {
          notifyError(err, 'Failed to delete the transition');
        }
      },
    });
  };

  if (isLoading) {
    return (
      <div className="flex align-items-center justify-content-center p-6">
        <ProgressSpinner style={{ width: '3rem', height: '3rem' }} />
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div className="p-4">
        <Message
          severity="error"
          text={extractApiError(error, 'This workflow could not be loaded.')}
        />
        <div className="mt-3">
          <Button
            label="Back to Workflows"
            icon="pi pi-arrow-left"
            outlined
            onClick={() => navigate('/workflows')}
          />
        </div>
      </div>
    );
  }

  const { definition } = data;

  return (
    <div className="p-4">
      <Toast ref={toast} />
      <ConfirmDialog />

      <div className="flex align-items-start justify-content-between mb-4 flex-wrap gap-3">
        <div>
          <div className="flex align-items-center gap-2">
            <Button
              icon="pi pi-arrow-left"
              rounded
              text
              onClick={() => navigate('/workflows')}
              aria-label="Back to workflows"
            />
            <h2 className="text-2xl font-semibold text-900 m-0">{definition.name}</h2>
            <Tag
              value={definition.is_active ? 'Active' : 'Inactive'}
              severity={definition.is_active ? 'success' : 'warning'}
            />
          </div>
          <p className="text-600 mt-1 mb-0 ml-5">
            {definition.code} · governs <code>{definition.entity_type}</code> · version{' '}
            {definition.version}
          </p>
        </div>
      </div>

      {!hasInitialState && (
        <Message
          className="mb-3 w-full justify-content-start"
          severity="warn"
          text="This workflow has no initial state, so it cannot be started. Add one to begin."
        />
      )}
      {hasInitialState && !hasTerminalState && (
        <Message
          className="mb-3 w-full justify-content-start"
          severity="info"
          text="No terminal state yet — instances of this workflow would never complete."
        />
      )}

      <div className="surface-card p-4 border-round shadow-1 mb-4">
        <div className="flex align-items-center justify-content-between mb-3 flex-wrap gap-2">
          <div>
            <h3 className="text-lg font-semibold text-900 m-0">States</h3>
            <p className="text-600 text-sm mt-1 mb-0">
              The positions a record can occupy in this workflow
            </p>
          </div>
          {canCreate && (
            <Button
              label="Add State"
              icon="pi pi-plus"
              size="small"
              onClick={() => {
                setEditingStatus(null);
                setShowStatusDialog(true);
              }}
              aria-label="Add state"
            />
          )}
        </div>
        <WorkflowStatusTable
          statuses={statuses}
          loading={deleteStatus.isPending}
          canUpdate={canUpdate}
          canDelete={canDelete}
          onEdit={(status) => {
            setEditingStatus(status);
            setShowStatusDialog(true);
          }}
          onDelete={handleStatusDelete}
        />
      </div>

      <div className="surface-card p-4 border-round shadow-1">
        <div className="flex align-items-center justify-content-between mb-3 flex-wrap gap-2">
          <div>
            <h3 className="text-lg font-semibold text-900 m-0">Transitions</h3>
            <p className="text-600 text-sm mt-1 mb-0">
              The actions that move a record between states
            </p>
          </div>
          {canCreate && (
            <Button
              label="Add Transition"
              icon="pi pi-plus"
              size="small"
              disabled={statuses.length < 2}
              onClick={() => setShowTransitionDialog(true)}
              aria-label="Add transition"
            />
          )}
        </div>
        <WorkflowTransitionTable
          transitions={transitions}
          statuses={statuses}
          loading={deleteTransition.isPending}
          canDelete={canDelete}
          onDelete={handleTransitionDelete}
        />
      </div>

      <WorkflowStatusForm
        visible={showStatusDialog}
        status={editingStatus}
        nextSequence={nextSequence}
        loading={createStatus.isPending || updateStatus.isPending}
        onHide={() => {
          setShowStatusDialog(false);
          setEditingStatus(null);
        }}
        onSubmit={handleStatusSubmit}
      />

      <WorkflowTransitionForm
        visible={showTransitionDialog}
        statuses={statuses}
        loading={createTransition.isPending}
        onHide={() => setShowTransitionDialog(false)}
        onSubmit={handleTransitionSubmit}
      />
    </div>
  );
};

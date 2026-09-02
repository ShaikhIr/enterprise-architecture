/**
 * TanStack Query hooks for the workflow engine.
 * Server state lives here, not in Redux — matching the rest of the app.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { workflowApi, type ListDefinitionsParams } from '../api/workflowApi';
import type {
  CreateWorkflowDefinitionRequest,
  CreateWorkflowStatusRequest,
  CreateWorkflowTransitionRequest,
  UpdateWorkflowDefinitionRequest,
  UpdateWorkflowStatusRequest,
  WorkflowActionRequest,
} from '../models/Workflow';

const DEFINITIONS_KEY = ['workflow-definitions'];

const definitionKey = (definitionId: number) => ['workflow-definition', definitionId];

export const useWorkflowDefinitions = (params: ListDefinitionsParams = {}) =>
  useQuery({
    queryKey: [...DEFINITIONS_KEY, params],
    queryFn: () => workflowApi.listDefinitions(params),
    staleTime: 30_000,
  });

export const useWorkflowDefinition = (definitionId: number | undefined) =>
  useQuery({
    queryKey: definitionKey(definitionId ?? 0),
    queryFn: () => workflowApi.getDefinition(definitionId as number),
    enabled: Boolean(definitionId),
    staleTime: 30_000,
  });

export const useCreateWorkflowDefinition = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (request: CreateWorkflowDefinitionRequest) => workflowApi.createDefinition(request),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: DEFINITIONS_KEY });
    },
  });
};

export const useUpdateWorkflowDefinition = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      definitionId,
      request,
    }: {
      definitionId: number;
      request: UpdateWorkflowDefinitionRequest;
    }) => workflowApi.updateDefinition(definitionId, request),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: DEFINITIONS_KEY });
      queryClient.invalidateQueries({
        queryKey: definitionKey(variables.definitionId),
      });
    },
  });
};

export const useDeleteWorkflowDefinition = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (definitionId: number) => workflowApi.deleteDefinition(definitionId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: DEFINITIONS_KEY });
    },
  });
};

/**
 * State and transition mutations all invalidate the parent definition query,
 * because the builder screen reads statuses and transitions from that one
 * detail response rather than fetching them separately.
 */
const useDefinitionChildMutation = <TVariables>(
  definitionId: number | undefined,
  mutationFn: (variables: TVariables) => Promise<unknown>,
) => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: definitionKey(definitionId ?? 0) });
    },
  });
};

export const useCreateWorkflowStatus = (definitionId: number | undefined) =>
  useDefinitionChildMutation(definitionId, (request: CreateWorkflowStatusRequest) =>
    workflowApi.createStatus(definitionId as number, request),
  );

export const useUpdateWorkflowStatus = (definitionId: number | undefined) =>
  useDefinitionChildMutation(
    definitionId,
    ({ statusId, request }: { statusId: number; request: UpdateWorkflowStatusRequest }) =>
      workflowApi.updateStatus(statusId, request),
  );

export const useDeleteWorkflowStatus = (definitionId: number | undefined) =>
  useDefinitionChildMutation(definitionId, (statusId: number) =>
    workflowApi.deleteStatus(statusId),
  );

export const useCreateWorkflowTransition = (definitionId: number | undefined) =>
  useDefinitionChildMutation(definitionId, (request: CreateWorkflowTransitionRequest) =>
    workflowApi.createTransition(definitionId as number, request),
  );

export const useDeleteWorkflowTransition = (definitionId: number | undefined) =>
  useDefinitionChildMutation(definitionId, (transitionId: number) =>
    workflowApi.deleteTransition(transitionId),
  );

// ─── Runtime ───

export const useWorkflowInstance = (instanceId: number | undefined) =>
  useQuery({
    queryKey: ['workflow-instance', instanceId],
    queryFn: () => workflowApi.getInstance(instanceId as number),
    enabled: Boolean(instanceId),
  });

export const useWorkflowInstanceActions = (instanceId: number | undefined) =>
  useQuery({
    queryKey: ['workflow-instance-actions', instanceId],
    queryFn: () => workflowApi.listAvailableActions(instanceId as number),
    enabled: Boolean(instanceId),
  });

export const useWorkflowInstanceHistory = (instanceId: number | undefined) =>
  useQuery({
    queryKey: ['workflow-instance-history', instanceId],
    queryFn: () => workflowApi.listHistory(instanceId as number),
    enabled: Boolean(instanceId),
  });

export const useExecuteWorkflowAction = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ instanceId, request }: { instanceId: number; request: WorkflowActionRequest }) =>
      workflowApi.executeAction(instanceId, request),
    onSuccess: (_data, variables) => {
      // The action changes the state, the available actions and the history, so
      // all three views of the instance are refetched.
      queryClient.invalidateQueries({
        queryKey: ['workflow-instance', variables.instanceId],
      });
      queryClient.invalidateQueries({
        queryKey: ['workflow-instance-actions', variables.instanceId],
      });
      queryClient.invalidateQueries({
        queryKey: ['workflow-instance-history', variables.instanceId],
      });
    },
  });
};

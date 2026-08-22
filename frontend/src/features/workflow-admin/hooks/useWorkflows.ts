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

const definitionKey = (definitionId: string) => ['workflow-definition', definitionId];

export const useWorkflowDefinitions = (params: ListDefinitionsParams = {}) =>
  useQuery({
    queryKey: [...DEFINITIONS_KEY, params],
    queryFn: () => workflowApi.listDefinitions(params),
    staleTime: 30_000,
  });

export const useWorkflowDefinition = (definitionId: string | undefined) =>
  useQuery({
    queryKey: definitionKey(definitionId ?? ''),
    queryFn: () => workflowApi.getDefinition(definitionId as string),
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
      definitionId: string;
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
    mutationFn: (definitionId: string) => workflowApi.deleteDefinition(definitionId),
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
  definitionId: string | undefined,
  mutationFn: (variables: TVariables) => Promise<unknown>,
) => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: definitionKey(definitionId ?? '') });
    },
  });
};

export const useCreateWorkflowStatus = (definitionId: string | undefined) =>
  useDefinitionChildMutation(definitionId, (request: CreateWorkflowStatusRequest) =>
    workflowApi.createStatus(definitionId as string, request),
  );

export const useUpdateWorkflowStatus = (definitionId: string | undefined) =>
  useDefinitionChildMutation(
    definitionId,
    ({ statusId, request }: { statusId: string; request: UpdateWorkflowStatusRequest }) =>
      workflowApi.updateStatus(statusId, request),
  );

export const useDeleteWorkflowStatus = (definitionId: string | undefined) =>
  useDefinitionChildMutation(definitionId, (statusId: string) =>
    workflowApi.deleteStatus(statusId),
  );

export const useCreateWorkflowTransition = (definitionId: string | undefined) =>
  useDefinitionChildMutation(definitionId, (request: CreateWorkflowTransitionRequest) =>
    workflowApi.createTransition(definitionId as string, request),
  );

export const useDeleteWorkflowTransition = (definitionId: string | undefined) =>
  useDefinitionChildMutation(definitionId, (transitionId: string) =>
    workflowApi.deleteTransition(transitionId),
  );

// ─── Runtime ───

export const useWorkflowInstance = (instanceId: string | undefined) =>
  useQuery({
    queryKey: ['workflow-instance', instanceId],
    queryFn: () => workflowApi.getInstance(instanceId as string),
    enabled: Boolean(instanceId),
  });

export const useWorkflowInstanceActions = (instanceId: string | undefined) =>
  useQuery({
    queryKey: ['workflow-instance-actions', instanceId],
    queryFn: () => workflowApi.listAvailableActions(instanceId as string),
    enabled: Boolean(instanceId),
  });

export const useWorkflowInstanceHistory = (instanceId: string | undefined) =>
  useQuery({
    queryKey: ['workflow-instance-history', instanceId],
    queryFn: () => workflowApi.listHistory(instanceId as string),
    enabled: Boolean(instanceId),
  });

export const useExecuteWorkflowAction = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ instanceId, request }: { instanceId: string; request: WorkflowActionRequest }) =>
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

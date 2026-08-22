/**
 * Workflow engine API calls.
 * Maps to backend: /api/v1/workflow/definitions, /statuses, /transitions, /instances
 */

import { apiClient } from '@shared/services/apiClient';

import type {
  CreateWorkflowDefinitionRequest,
  CreateWorkflowStatusRequest,
  CreateWorkflowTransitionRequest,
  StartWorkflowRequest,
  UpdateWorkflowDefinitionRequest,
  UpdateWorkflowStatusRequest,
  WorkflowActionRequest,
  WorkflowAvailableAction,
  WorkflowDefinition,
  WorkflowDefinitionDetail,
  WorkflowDefinitionListResponse,
  WorkflowHistoryEntry,
  WorkflowInstance,
  WorkflowInstanceListResponse,
  WorkflowStatus,
  WorkflowTransition,
} from '../models/Workflow';

export interface ListDefinitionsParams {
  skip?: number;
  limit?: number;
  search?: string;
  is_active?: boolean;
  entity_type?: string;
}

export interface ListInstancesParams {
  skip?: number;
  limit?: number;
  entity_type?: string;
  entity_id?: string;
  definition_id?: string;
  status_id?: string;
  is_completed?: boolean;
}

export const workflowApi = {
  // ─── Definitions ───

  listDefinitions: async (
    params: ListDefinitionsParams = {},
  ): Promise<WorkflowDefinitionListResponse> => {
    const { data } = await apiClient.get<WorkflowDefinitionListResponse>('/workflow/definitions', {
      params: { skip: 0, limit: 100, ...params },
    });
    return data;
  },

  getDefinition: async (definitionId: string): Promise<WorkflowDefinitionDetail> => {
    const { data } = await apiClient.get<WorkflowDefinitionDetail>(
      `/workflow/definitions/${definitionId}`,
    );
    return data;
  },

  createDefinition: async (
    request: CreateWorkflowDefinitionRequest,
  ): Promise<WorkflowDefinition> => {
    const { data } = await apiClient.post<WorkflowDefinition>('/workflow/definitions', request);
    return data;
  },

  updateDefinition: async (
    definitionId: string,
    request: UpdateWorkflowDefinitionRequest,
  ): Promise<WorkflowDefinition> => {
    const { data } = await apiClient.patch<WorkflowDefinition>(
      `/workflow/definitions/${definitionId}`,
      request,
    );
    return data;
  },

  deleteDefinition: async (definitionId: string): Promise<void> => {
    await apiClient.delete(`/workflow/definitions/${definitionId}`);
  },

  // ─── States ───

  listStatuses: async (definitionId: string): Promise<WorkflowStatus[]> => {
    const { data } = await apiClient.get<WorkflowStatus[]>(
      `/workflow/definitions/${definitionId}/statuses`,
    );
    return data;
  },

  createStatus: async (
    definitionId: string,
    request: CreateWorkflowStatusRequest,
  ): Promise<WorkflowStatus> => {
    const { data } = await apiClient.post<WorkflowStatus>(
      `/workflow/definitions/${definitionId}/statuses`,
      request,
    );
    return data;
  },

  updateStatus: async (
    statusId: string,
    request: UpdateWorkflowStatusRequest,
  ): Promise<WorkflowStatus> => {
    const { data } = await apiClient.patch<WorkflowStatus>(
      `/workflow/statuses/${statusId}`,
      request,
    );
    return data;
  },

  deleteStatus: async (statusId: string): Promise<void> => {
    await apiClient.delete(`/workflow/statuses/${statusId}`);
  },

  // ─── Transitions ───

  listTransitions: async (definitionId: string): Promise<WorkflowTransition[]> => {
    const { data } = await apiClient.get<WorkflowTransition[]>(
      `/workflow/definitions/${definitionId}/transitions`,
    );
    return data;
  },

  createTransition: async (
    definitionId: string,
    request: CreateWorkflowTransitionRequest,
  ): Promise<WorkflowTransition> => {
    const { data } = await apiClient.post<WorkflowTransition>(
      `/workflow/definitions/${definitionId}/transitions`,
      request,
    );
    return data;
  },

  deleteTransition: async (transitionId: string): Promise<void> => {
    await apiClient.delete(`/workflow/transitions/${transitionId}`);
  },

  // ─── Runtime ───

  listInstances: async (
    params: ListInstancesParams = {},
  ): Promise<WorkflowInstanceListResponse> => {
    const { data } = await apiClient.get<WorkflowInstanceListResponse>('/workflow/instances', {
      params: { skip: 0, limit: 100, ...params },
    });
    return data;
  },

  getInstance: async (instanceId: string): Promise<WorkflowInstance> => {
    const { data } = await apiClient.get<WorkflowInstance>(`/workflow/instances/${instanceId}`);
    return data;
  },

  startWorkflow: async (request: StartWorkflowRequest): Promise<WorkflowInstance> => {
    const { data } = await apiClient.post<WorkflowInstance>('/workflow/instances', request);
    return data;
  },

  executeAction: async (
    instanceId: string,
    request: WorkflowActionRequest,
  ): Promise<WorkflowInstance> => {
    const { data } = await apiClient.post<WorkflowInstance>(
      `/workflow/instances/${instanceId}/actions`,
      request,
    );
    return data;
  },

  listAvailableActions: async (instanceId: string): Promise<WorkflowAvailableAction[]> => {
    const { data } = await apiClient.get<WorkflowAvailableAction[]>(
      `/workflow/instances/${instanceId}/actions`,
    );
    return data;
  },

  listHistory: async (instanceId: string): Promise<WorkflowHistoryEntry[]> => {
    const { data } = await apiClient.get<WorkflowHistoryEntry[]>(
      `/workflow/instances/${instanceId}/history`,
    );
    return data;
  },
};

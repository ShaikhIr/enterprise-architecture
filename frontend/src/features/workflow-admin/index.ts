// Workflow Admin feature barrel export
export { WorkflowDefinitionsPage } from './pages/WorkflowDefinitionsPage';
export { WorkflowBuilderPage } from './pages/WorkflowBuilderPage';
export { ApprovalMatrixPage } from './pages/ApprovalMatrixPage';

export { WorkflowDefinitionTable } from './components/WorkflowDefinitionTable';
export { WorkflowDefinitionForm } from './components/WorkflowDefinitionForm';
export { WorkflowStatusTable } from './components/WorkflowStatusTable';
export { WorkflowStatusForm } from './components/WorkflowStatusForm';
export { WorkflowTransitionTable } from './components/WorkflowTransitionTable';
export { WorkflowTransitionForm } from './components/WorkflowTransitionForm';
export { ApprovalMatrixTable } from './components/ApprovalMatrixTable';
export { ApprovalMatrixForm } from './components/ApprovalMatrixForm';
export { ApprovalMatrixResolveDialog } from './components/ApprovalMatrixResolveDialog';

export { workflowApi } from './api/workflowApi';
export { approvalMatrixApi } from './api/approvalMatrixApi';

export {
  useWorkflowDefinitions,
  useWorkflowDefinition,
  useCreateWorkflowDefinition,
  useUpdateWorkflowDefinition,
  useDeleteWorkflowDefinition,
  useCreateWorkflowStatus,
  useUpdateWorkflowStatus,
  useDeleteWorkflowStatus,
  useCreateWorkflowTransition,
  useDeleteWorkflowTransition,
  useWorkflowInstance,
  useWorkflowInstanceActions,
  useWorkflowInstanceHistory,
  useExecuteWorkflowAction,
} from './hooks/useWorkflows';

export {
  useApprovalMatrices,
  useCreateApprovalMatrix,
  useUpdateApprovalMatrix,
  useDeleteApprovalMatrix,
  useResolveApprovalMatrix,
  useMyApprovalTasks,
} from './hooks/useApprovalMatrices';

export { WORKFLOW_ACTION_TYPES, WORKFLOW_ACTION_TYPE_EFFECTS } from './models/Workflow';

export type {
  WorkflowActionType,
  WorkflowDefinition,
  WorkflowDefinitionDetail,
  WorkflowStatus,
  WorkflowTransition,
  WorkflowInstance,
  WorkflowAvailableAction,
  WorkflowHistoryEntry,
  CreateWorkflowDefinitionRequest,
  UpdateWorkflowDefinitionRequest,
  CreateWorkflowStatusRequest,
  UpdateWorkflowStatusRequest,
  CreateWorkflowTransitionRequest,
  StartWorkflowRequest,
  WorkflowActionRequest,
} from './models/Workflow';

export type {
  ApprovalMatrix,
  ApprovalRule,
  ApprovalAssignment,
  ApprovalTask,
  RuleOperator,
  RuleDataType,
  AssignmentType,
  CreateApprovalMatrixRequest,
  UpdateApprovalMatrixRequest,
  ApprovalResolveRequest,
  ApprovalResolveResponse,
} from './models/ApprovalMatrix';

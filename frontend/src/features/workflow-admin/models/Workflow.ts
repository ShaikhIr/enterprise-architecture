/**
 * Workflow engine types.
 * Field names mirror the backend responses (snake_case) so no mapping layer is
 * needed between the API client and the components.
 */

export interface WorkflowDefinition {
  id: string;
  code: string;
  name: string;
  description: string;
  entity_type: string;
  version: number;
  is_active: boolean;
  created_by: string;
  created_date: string;
  modified_by: string;
  modified_date: string;
}

export interface WorkflowDefinitionListResponse {
  definitions: WorkflowDefinition[];
  total: number;
  skip: number;
  limit: number;
}

export interface WorkflowStatus {
  id: string;
  workflow_definition_id: string;
  code: string;
  name: string;
  is_initial: boolean;
  is_terminal: boolean;
  sequence: number;
}

/**
 * What a transition means for the approval chain.
 *
 * `action_code` is free text, so it cannot tell the engine whether "SIGN_OFF"
 * approves or rejects. This is the designer's explicit declaration, and it is the
 * only signal the approval coordinator reads.
 */
export const WORKFLOW_ACTION_TYPES = [
  'SUBMIT',
  'APPROVE',
  'REJECT',
  'REFER_BACK',
  'CANCEL',
  'CLOSE',
  'ESCALATE',
  'CUSTOM',
] as const;

export type WorkflowActionType = (typeof WORKFLOW_ACTION_TYPES)[number];

/** How each action type affects the approval chain, for display in the builder. */
export const WORKFLOW_ACTION_TYPE_EFFECTS: Record<WorkflowActionType, string> = {
  SUBMIT: 'Opens approval level 1',
  APPROVE: 'Settles this level, opens the next',
  REJECT: 'Settles this level, ends the chain',
  REFER_BACK: 'Ends the chain; a later Submit restarts it at level 1',
  CANCEL: 'Ends the chain',
  CLOSE: 'No effect on approvals',
  ESCALATE: 'No effect on approvals',
  CUSTOM: 'No effect on approvals',
};

export interface WorkflowTransition {
  id: string;
  workflow_definition_id: string;
  from_status_id: string;
  to_status_id: string;
  action_code: string;
  action_type: WorkflowActionType;
  guard_expression: string | null;
  requires_comment: boolean;
  auto_execute: boolean;
  priority: number;
}

/** A definition together with its full state machine, as the builder screen needs. */
export interface WorkflowDefinitionDetail {
  definition: WorkflowDefinition;
  statuses: WorkflowStatus[];
  transitions: WorkflowTransition[];
}

export interface CreateWorkflowDefinitionRequest {
  code: string;
  name: string;
  entity_type: string;
  description: string;
  is_active: boolean;
}

export type UpdateWorkflowDefinitionRequest = Partial<CreateWorkflowDefinitionRequest>;

export interface CreateWorkflowStatusRequest {
  code: string;
  name: string;
  is_initial: boolean;
  is_terminal: boolean;
  sequence: number;
}

export type UpdateWorkflowStatusRequest = Partial<CreateWorkflowStatusRequest>;

export interface CreateWorkflowTransitionRequest {
  from_status_id: string;
  to_status_id: string;
  action_code: string;
  action_type: WorkflowActionType;
  guard_expression?: string | null;
  requires_comment: boolean;
  auto_execute: boolean;
  priority: number;
}

// ─── Runtime ───

export interface WorkflowInstance {
  id: string;
  workflow_definition_id: string;
  definition_code: string;
  definition_name: string;
  entity_type: string;
  entity_id: string;
  current_status_id: string;
  current_status_code: string;
  current_status_name: string;
  is_terminal: boolean;
  initiated_by: string;
  priority: number;
  due_date: string | null;
  started_at: string;
  completed_at: string | null;
  is_completed: boolean;
  /** Approval level currently open; 0 means none. */
  approval_level: number;
  is_awaiting_approval: boolean;
  metadata: Record<string, unknown>;
}

export interface WorkflowInstanceListResponse {
  instances: WorkflowInstance[];
  total: number;
  skip: number;
  limit: number;
}

export interface WorkflowAvailableAction {
  action_code: string;
  action_type: WorkflowActionType;
  to_status_id: string;
  to_status_code: string;
  to_status_name: string;
  requires_comment: boolean;
  is_terminal: boolean;
}

export interface WorkflowHistoryEntry {
  id: string;
  instance_id: string;
  from_status_id: string | null;
  from_status_code: string | null;
  to_status_id: string;
  to_status_code: string | null;
  action_code: string;
  actor_id: string | null;
  actor_username: string;
  comments: string;
  ip_address: string;
  created_at: string;
}

export interface StartWorkflowRequest {
  definition_code: string;
  entity_type: string;
  entity_id: string;
  priority?: number;
  metadata?: Record<string, unknown>;
}

export interface WorkflowActionRequest {
  action_code: string;
  comments: string;
}

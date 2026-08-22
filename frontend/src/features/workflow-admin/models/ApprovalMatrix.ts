/**
 * Approval matrix types.
 * Operator and data-type unions mirror the backend enums, so an invalid rule
 * cannot be constructed in the UI in the first place.
 */

export const RULE_OPERATORS = [
  'EQ',
  'NEQ',
  'GT',
  'GTE',
  'LT',
  'LTE',
  'IN',
  'NOT_IN',
  'CONTAINS',
  'STARTS_WITH',
] as const;

export type RuleOperator = (typeof RULE_OPERATORS)[number];

export const RULE_DATA_TYPES = ['STRING', 'NUMBER', 'BOOLEAN', 'LIST'] as const;

export type RuleDataType = (typeof RULE_DATA_TYPES)[number];

export const ASSIGNMENT_TYPES = ['ROLE', 'USER'] as const;

export type AssignmentType = (typeof ASSIGNMENT_TYPES)[number];

export type ApprovalTaskStatus = 'PENDING' | 'COMPLETED' | 'CANCELLED' | 'ESCALATED';

export interface ApprovalRule {
  id: string;
  field: string;
  operator: RuleOperator;
  value: string;
  data_type: RuleDataType;
  logical_group: string;
}

export interface ApprovalAssignment {
  id: string;
  level: number;
  assignment_type: AssignmentType;
  user_id: string | null;
  role_id: string | null;
}

export interface ApprovalMatrix {
  id: string;
  code: string;
  name: string;
  entity_type: string;
  priority: number;
  is_active: boolean;
  rules: ApprovalRule[];
  assignments: ApprovalAssignment[];
  created_by: string;
  created_date: string;
  modified_by: string;
  modified_date: string;
}

export interface ApprovalMatrixListResponse {
  matrices: ApprovalMatrix[];
  total: number;
  skip: number;
  limit: number;
}

/** Rule as submitted — no id, because the backend replaces the whole rule set. */
export interface ApprovalRuleInput {
  field: string;
  operator: RuleOperator;
  value: string;
  data_type: RuleDataType;
  logical_group: string;
}

export interface ApprovalAssignmentInput {
  level: number;
  assignment_type: AssignmentType;
  user_id: string | null;
  role_id: string | null;
}

export interface CreateApprovalMatrixRequest {
  code: string;
  name: string;
  entity_type: string;
  priority: number;
  is_active: boolean;
  rules: ApprovalRuleInput[];
  assignments: ApprovalAssignmentInput[];
}

export type UpdateApprovalMatrixRequest = Partial<Omit<CreateApprovalMatrixRequest, 'code'>>;

export interface ApprovalResolveRequest {
  entity_type: string;
  entity_data: Record<string, unknown>;
}

export interface ApprovalResolveResponse {
  matched: boolean;
  matrix: ApprovalMatrix | null;
  levels: number[];
  assignments: ApprovalAssignment[];
}

export interface ApprovalTask {
  id: string;
  instance_id: string;
  matrix_id: string | null;
  assignee_id: string;
  level: number;
  status: ApprovalTaskStatus;
  action_taken: string | null;
  due_date: string | null;
  comments: string | null;
  created_date: string;
}

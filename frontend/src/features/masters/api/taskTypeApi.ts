/**
 * Task type master API calls.
 * Maps to backend: /api/v1/masters/task-types
 */

import type {
  CreateTaskTypeRequest,
  TaskType,
  TaskTypeListParams,
  UpdateTaskTypeRequest,
} from '../models/TaskType';

import { createMasterApi } from './createMasterApi';

export const taskTypeApi = createMasterApi<
  TaskType,
  CreateTaskTypeRequest,
  UpdateTaskTypeRequest,
  TaskTypeListParams
>('/masters/task-types', 'task_types');

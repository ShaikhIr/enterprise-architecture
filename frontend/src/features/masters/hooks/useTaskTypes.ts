/**
 * Task type master query hooks.
 *
 * Independent of the country/state hierarchy, so there are no dependent caches.
 */

import { useMemo } from 'react';

import { taskTypeApi } from '../api/taskTypeApi';
import type {
  CreateTaskTypeRequest,
  TaskType,
  TaskTypeListParams,
  UpdateTaskTypeRequest,
} from '../models/TaskType';

import { createMasterHooks } from './createMasterHooks';
import { MASTER_KEYS } from './masterQueryKeys';
import { buildMasterLookup, OPTION_LIMIT, type MasterLookup } from './useMasterLookup';

const hooks = createMasterHooks<
  TaskType,
  CreateTaskTypeRequest,
  UpdateTaskTypeRequest,
  TaskTypeListParams
>(taskTypeApi, MASTER_KEYS.taskTypes);

export const useTaskTypes = hooks.useList;
export const useCreateTaskType = hooks.useCreate;
export const useUpdateTaskType = hooks.useUpdate;
export const useDeleteTaskType = hooks.useDelete;

/** Options for a task type picker, plus a resolver for already-stored ids. */
export const useTaskTypeLookup = (): MasterLookup => {
  const active = useTaskTypes({ limit: OPTION_LIMIT, is_active: true });
  const all = useTaskTypes({ limit: OPTION_LIMIT });
  return useMemo(
    () => buildMasterLookup(active.data?.items ?? [], all.data?.items ?? [], active.isLoading),
    [active.data, all.data, active.isLoading],
  );
};

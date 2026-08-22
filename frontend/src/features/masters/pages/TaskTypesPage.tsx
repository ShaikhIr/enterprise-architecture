/**
 * Task type master screen.
 * A flat lookup, independent of the country/state hierarchy.
 */

import { useState } from 'react';

import { FilterMatchMode } from 'primereact/api';
import { Column } from 'primereact/column';
import type { DataTableFilterMeta } from 'primereact/datatable';

import { MasterCrudPage } from '../components/MasterCrudPage';
import { MasterRowActions } from '../components/MasterRowActions';
import { MasterStatusTag } from '../components/MasterStatusTag';
import { TaskTypeForm } from '../components/TaskTypeForm';
import { useMasterCrudController } from '../hooks/useMasterCrudController';
import { useMasterPermissions } from '../hooks/useMasterPermissions';
import {
  useCreateTaskType,
  useDeleteTaskType,
  useTaskTypes,
  useUpdateTaskType,
} from '../hooks/useTaskTypes';
import type { CreateTaskTypeRequest, TaskType } from '../models/TaskType';

const defaultFilters: DataTableFilterMeta = {
  code: { value: null, matchMode: FilterMatchMode.CONTAINS },
  name: { value: null, matchMode: FilterMatchMode.CONTAINS },
};

export const TaskTypesPage = () => {
  const [filters, setFilters] = useState<DataTableFilterMeta>(defaultFilters);

  const { data, isLoading, refetch, isRefetching } = useTaskTypes();
  const createMutation = useCreateTaskType();
  const updateMutation = useUpdateTaskType();
  const deleteMutation = useDeleteTaskType();

  const permissions = useMasterPermissions('task_types');

  const crud = useMasterCrudController<TaskType, CreateTaskTypeRequest>({
    entityLabel: 'Task type',
    labelOf: (row) => row.name,
    onCreate: (request) => createMutation.mutateAsync(request),
    onUpdate: (id, request) => updateMutation.mutateAsync({ id, request }),
    onDelete: (id) => deleteMutation.mutateAsync(id),
  });

  return (
    <MasterCrudPage<TaskType>
      title="Task Types"
      subtitle="Kinds of compliance task that can be scheduled"
      newLabel="New Task Type"
      rows={data?.items ?? []}
      loading={isLoading}
      refreshing={isRefetching}
      onRefresh={() => refetch()}
      onNew={crud.openCreate}
      canCreate={permissions.canCreate}
      filters={filters}
      onFilterChange={setFilters}
      emptyMessage="No task types defined yet."
      toastRef={crud.toast}
      columns={
        <>
          <Column
            field="code"
            header="Code"
            sortable
            filter
            filterPlaceholder="Search..."
            style={{ width: '14rem' }}
          />
          <Column field="name" header="Name" sortable filter filterPlaceholder="Search..." />
          <Column
            field="description"
            header="Description"
            body={(row: TaskType) => row.description || '—'}
          />
          <Column
            header="Status"
            body={(row: TaskType) => <MasterStatusTag isActive={row.is_active} />}
            style={{ width: '7rem' }}
          />
          {permissions.canModifyRows && (
            <Column
              header="Actions"
              body={(row: TaskType) => (
                <MasterRowActions
                  label={row.name}
                  canUpdate={permissions.canUpdate}
                  canDelete={permissions.canDelete}
                  onEdit={() => crud.openEdit(row)}
                  onDelete={() => crud.requestDelete(row)}
                />
              )}
              style={{ width: '7rem' }}
            />
          )}
        </>
      }
    >
      <TaskTypeForm
        visible={crud.dialogVisible}
        taskType={crud.editing}
        saving={createMutation.isPending || updateMutation.isPending}
        onHide={crud.closeDialog}
        onSubmit={crud.submit}
      />
    </MasterCrudPage>
  );
};

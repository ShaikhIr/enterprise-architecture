/**
 * Category of law master screen.
 *
 * A category with no state is country-wide, which the State column shows
 * explicitly rather than as a blank cell.
 */

import { useState } from 'react';

import { FilterMatchMode } from 'primereact/api';
import { Column } from 'primereact/column';
import type { DataTableFilterMeta } from 'primereact/datatable';
import { Dropdown } from 'primereact/dropdown';
import { Tag } from 'primereact/tag';

import { CategoryOfLawForm } from '../components/CategoryOfLawForm';
import { MasterCrudPage } from '../components/MasterCrudPage';
import { MasterRowActions } from '../components/MasterRowActions';
import { MasterStatusTag } from '../components/MasterStatusTag';
import {
  useCategoriesOfLaw,
  useCreateCategoryOfLaw,
  useDeleteCategoryOfLaw,
  useUpdateCategoryOfLaw,
} from '../hooks/useCategoriesOfLaw';
import { useMasterCrudController } from '../hooks/useMasterCrudController';
import { useMasterPermissions } from '../hooks/useMasterPermissions';
import { useStateLookup } from '../hooks/useStates';
import type { CategoryOfLaw, CreateCategoryOfLawRequest } from '../models/CategoryOfLaw';

const defaultFilters: DataTableFilterMeta = {
  code: { value: null, matchMode: FilterMatchMode.CONTAINS },
  name: { value: null, matchMode: FilterMatchMode.CONTAINS },
};

export const CategoriesOfLawPage = () => {
  const [filters, setFilters] = useState<DataTableFilterMeta>(defaultFilters);
  const [stateId, setStateId] = useState<string | null>(null);

  const states = useStateLookup();
  const { data, isLoading, refetch, isRefetching } = useCategoriesOfLaw({
    state_id: stateId ?? undefined,
  });
  const createMutation = useCreateCategoryOfLaw();
  const updateMutation = useUpdateCategoryOfLaw();
  const deleteMutation = useDeleteCategoryOfLaw();

  const permissions = useMasterPermissions('categories_of_law');

  const crud = useMasterCrudController<CategoryOfLaw, CreateCategoryOfLawRequest>({
    entityLabel: 'Category of law',
    labelOf: (row) => row.name,
    onCreate: (request) => createMutation.mutateAsync(request),
    onUpdate: (id, request) => updateMutation.mutateAsync({ id, request }),
    onDelete: (id) => deleteMutation.mutateAsync(id),
  });

  return (
    <MasterCrudPage<CategoryOfLaw>
      title="Categories of Law"
      subtitle="Branches of law that legislations are grouped under"
      newLabel="New Category"
      rows={data?.items ?? []}
      loading={isLoading}
      refreshing={isRefetching}
      onRefresh={() => refetch()}
      onNew={crud.openCreate}
      canCreate={permissions.canCreate}
      filters={filters}
      onFilterChange={setFilters}
      emptyMessage="No categories of law found."
      toastRef={crud.toast}
      toolbarEnd={
        <Dropdown
          value={stateId}
          options={states.options}
          onChange={(e) => setStateId(e.value ?? null)}
          placeholder="All states"
          showClear
          filter
          className="w-14rem"
          aria-label="Filter by state"
        />
      }
      columns={
        <>
          <Column
            field="code"
            header="Code"
            sortable
            filter
            filterPlaceholder="Search..."
            style={{ width: '12rem' }}
          />
          <Column field="name" header="Name" sortable filter filterPlaceholder="Search..." />
          <Column
            header="Scope"
            body={(row: CategoryOfLaw) =>
              row.state_id ? (
                states.labelFor(row.state_id)
              ) : (
                <Tag value="Country-wide" severity="info" />
              )
            }
          />
          <Column
            header="Status"
            body={(row: CategoryOfLaw) => <MasterStatusTag isActive={row.is_active} />}
            style={{ width: '7rem' }}
          />
          {permissions.canModifyRows && (
            <Column
              header="Actions"
              body={(row: CategoryOfLaw) => (
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
      <CategoryOfLawForm
        visible={crud.dialogVisible}
        category={crud.editing}
        saving={createMutation.isPending || updateMutation.isPending}
        onHide={crud.closeDialog}
        onSubmit={crud.submit}
      />
    </MasterCrudPage>
  );
};

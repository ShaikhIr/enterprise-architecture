/**
 * State master screen.
 *
 * Carries a country filter in the toolbar, because states are the first level
 * where the list gets long enough that browsing all countries at once is useless.
 * The filter is applied server-side via the `country_id` query parameter rather
 * than in the table, so it narrows the fetch too.
 */

import { useState } from 'react';

import { FilterMatchMode } from 'primereact/api';
import { Column } from 'primereact/column';
import type { DataTableFilterMeta } from 'primereact/datatable';
import { Dropdown } from 'primereact/dropdown';
import { Tag } from 'primereact/tag';

import { MasterCrudPage } from '../components/MasterCrudPage';
import { MasterRowActions } from '../components/MasterRowActions';
import { MasterStatusTag } from '../components/MasterStatusTag';
import { StateForm } from '../components/StateForm';
import { useCountryLookup } from '../hooks/useCountries';
import { useMasterCrudController } from '../hooks/useMasterCrudController';
import { useMasterPermissions } from '../hooks/useMasterPermissions';
import { useCreateState, useDeleteState, useStates, useUpdateState } from '../hooks/useStates';
import type { CreateStateRequest, State } from '../models/State';

const defaultFilters: DataTableFilterMeta = {
  code: { value: null, matchMode: FilterMatchMode.CONTAINS },
  name: { value: null, matchMode: FilterMatchMode.CONTAINS },
};

export const StatesPage = () => {
  const [filters, setFilters] = useState<DataTableFilterMeta>(defaultFilters);
  const [countryId, setCountryId] = useState<number | null>(null);

  const countries = useCountryLookup();
  const { data, isLoading, refetch, isRefetching } = useStates({
    country_id: countryId ?? undefined,
  });
  const createMutation = useCreateState();
  const updateMutation = useUpdateState();
  const deleteMutation = useDeleteState();

  const permissions = useMasterPermissions('states');

  const crud = useMasterCrudController<State, CreateStateRequest>({
    entityLabel: 'State',
    labelOf: (row) => row.name,
    onCreate: (request) => createMutation.mutateAsync(request),
    onUpdate: (id, request) => updateMutation.mutateAsync({ id, request }),
    onDelete: (id) => deleteMutation.mutateAsync(id),
  });

  return (
    <MasterCrudPage<State>
      title="States"
      subtitle="States, provinces and union territories within a country"
      newLabel="New State"
      rows={data?.items ?? []}
      loading={isLoading}
      refreshing={isRefetching}
      onRefresh={() => refetch()}
      onNew={crud.openCreate}
      canCreate={permissions.canCreate}
      filters={filters}
      onFilterChange={setFilters}
      emptyMessage="No states found."
      toastRef={crud.toast}
      toolbarEnd={
        <Dropdown
          value={countryId}
          options={countries.options}
          onChange={(e) => setCountryId(e.value ?? null)}
          placeholder="All countries"
          showClear
          filter
          className="w-14rem"
          aria-label="Filter by country"
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
            style={{ width: '10rem' }}
          />
          <Column field="name" header="Name" sortable filter filterPlaceholder="Search..." />
          <Column
            header="Country"
            body={(row: State) => countries.labelFor(row.country_id)}
            sortable
            field="country_id"
          />
          <Column
            header="Type"
            body={(row: State) =>
              row.is_union_territory ? (
                <Tag value="Union Territory" severity="info" />
              ) : (
                <span className="text-600">State</span>
              )
            }
            style={{ width: '10rem' }}
          />
          <Column
            header="Status"
            body={(row: State) => <MasterStatusTag isActive={row.is_active} />}
            style={{ width: '7rem' }}
          />
          {permissions.canModifyRows && (
            <Column
              header="Actions"
              body={(row: State) => (
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
      <StateForm
        visible={crud.dialogVisible}
        state={crud.editing}
        saving={createMutation.isPending || updateMutation.isPending}
        onHide={crud.closeDialog}
        onSubmit={crud.submit}
      />
    </MasterCrudPage>
  );
};

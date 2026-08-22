/**
 * Country master screen.
 * Root of the compliance hierarchy — states, legislations and rules all hang off it.
 */

import { useState } from 'react';

import { FilterMatchMode } from 'primereact/api';
import { Column } from 'primereact/column';
import type { DataTableFilterMeta } from 'primereact/datatable';

import { CountryForm } from '../components/CountryForm';
import { MasterCrudPage } from '../components/MasterCrudPage';
import { MasterRowActions } from '../components/MasterRowActions';
import { MasterStatusTag } from '../components/MasterStatusTag';
import {
  useCountries,
  useCreateCountry,
  useDeleteCountry,
  useUpdateCountry,
} from '../hooks/useCountries';
import { useMasterCrudController } from '../hooks/useMasterCrudController';
import { useMasterPermissions } from '../hooks/useMasterPermissions';
import type { Country, CreateCountryRequest } from '../models/Country';

const defaultFilters: DataTableFilterMeta = {
  code: { value: null, matchMode: FilterMatchMode.CONTAINS },
  name: { value: null, matchMode: FilterMatchMode.CONTAINS },
};

export const CountriesPage = () => {
  const [filters, setFilters] = useState<DataTableFilterMeta>(defaultFilters);

  const { data, isLoading, refetch, isRefetching } = useCountries();
  const createMutation = useCreateCountry();
  const updateMutation = useUpdateCountry();
  const deleteMutation = useDeleteCountry();

  const permissions = useMasterPermissions('countries');

  const crud = useMasterCrudController<Country, CreateCountryRequest>({
    entityLabel: 'Country',
    labelOf: (row) => row.name,
    onCreate: (request) => createMutation.mutateAsync(request),
    onUpdate: (id, request) => updateMutation.mutateAsync({ id, request }),
    onDelete: (id) => deleteMutation.mutateAsync(id),
  });

  return (
    <MasterCrudPage<Country>
      title="Countries"
      subtitle="Root of the compliance hierarchy"
      newLabel="New Country"
      rows={data?.items ?? []}
      loading={isLoading}
      refreshing={isRefetching}
      onRefresh={() => refetch()}
      onNew={crud.openCreate}
      canCreate={permissions.canCreate}
      filters={filters}
      onFilterChange={setFilters}
      emptyMessage="No countries defined yet."
      toastRef={crud.toast}
      columns={
        <>
          <Column
            field="code"
            header="Code"
            sortable
            filter
            filterPlaceholder="Search..."
            style={{ width: '8rem' }}
          />
          <Column field="name" header="Name" sortable filter filterPlaceholder="Search..." />
          <Column
            field="iso3_code"
            header="ISO3"
            body={(row: Country) => row.iso3_code ?? '—'}
            style={{ width: '7rem' }}
          />
          <Column
            field="dial_code"
            header="Dial"
            body={(row: Country) => row.dial_code ?? '—'}
            style={{ width: '7rem' }}
          />
          <Column
            field="currency_code"
            header="Currency"
            body={(row: Country) => row.currency_code ?? '—'}
            style={{ width: '8rem' }}
          />
          <Column
            header="Status"
            body={(row: Country) => <MasterStatusTag isActive={row.is_active} />}
            style={{ width: '7rem' }}
          />
          {permissions.canModifyRows && (
            <Column
              header="Actions"
              body={(row: Country) => (
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
      <CountryForm
        visible={crud.dialogVisible}
        country={crud.editing}
        saving={createMutation.isPending || updateMutation.isPending}
        onHide={crud.closeDialog}
        onSubmit={crud.submit}
      />
    </MasterCrudPage>
  );
};

/**
 * Legislation master screen.
 *
 * Filters by country and category server-side, since a mature compliance database
 * holds far more legislations than one page can show.
 */

import { useState } from 'react';

import { FilterMatchMode } from 'primereact/api';
import { Column } from 'primereact/column';
import type { DataTableFilterMeta } from 'primereact/datatable';
import { Dropdown } from 'primereact/dropdown';
import { Tag } from 'primereact/tag';

import { LegislationForm } from '../components/LegislationForm';
import { MasterCrudPage } from '../components/MasterCrudPage';
import { MasterRowActions } from '../components/MasterRowActions';
import { MasterStatusTag } from '../components/MasterStatusTag';
import { useCategoryOfLawLookup } from '../hooks/useCategoriesOfLaw';
import { useCountryLookup } from '../hooks/useCountries';
import {
  useCreateLegislation,
  useDeleteLegislation,
  useLegislations,
  useUpdateLegislation,
} from '../hooks/useLegislations';
import { useMasterCrudController } from '../hooks/useMasterCrudController';
import { useMasterPermissions } from '../hooks/useMasterPermissions';
import { useStateLookup } from '../hooks/useStates';
import type { CreateLegislationRequest, Legislation } from '../models/Legislation';
import { formatIsoDate } from '../utils/isoDate';

const defaultFilters: DataTableFilterMeta = {
  code: { value: null, matchMode: FilterMatchMode.CONTAINS },
  name: { value: null, matchMode: FilterMatchMode.CONTAINS },
};

export const LegislationsPage = () => {
  const [filters, setFilters] = useState<DataTableFilterMeta>(defaultFilters);
  const [countryId, setCountryId] = useState<number | null>(null);
  const [categoryId, setCategoryId] = useState<number | null>(null);

  const countries = useCountryLookup();
  const states = useStateLookup();
  const categories = useCategoryOfLawLookup();

  const { data, isLoading, refetch, isRefetching } = useLegislations({
    country_id: countryId ?? undefined,
    category_of_law_id: categoryId ?? undefined,
  });
  const createMutation = useCreateLegislation();
  const updateMutation = useUpdateLegislation();
  const deleteMutation = useDeleteLegislation();

  const permissions = useMasterPermissions('legislations');

  const crud = useMasterCrudController<Legislation, CreateLegislationRequest>({
    entityLabel: 'Legislation',
    labelOf: (row) => row.name,
    onCreate: (request) => createMutation.mutateAsync(request),
    onUpdate: (id, request) => updateMutation.mutateAsync({ id, request }),
    onDelete: (id) => deleteMutation.mutateAsync(id),
  });

  return (
    <MasterCrudPage<Legislation>
      title="Legislations"
      subtitle="Acts and statutes that compliance obligations derive from"
      newLabel="New Legislation"
      rows={data?.items ?? []}
      loading={isLoading}
      refreshing={isRefetching}
      onRefresh={() => refetch()}
      onNew={crud.openCreate}
      canCreate={permissions.canCreate}
      filters={filters}
      onFilterChange={setFilters}
      emptyMessage="No legislations found."
      toastRef={crud.toast}
      toolbarEnd={
        <>
          <Dropdown
            value={countryId}
            options={countries.options}
            onChange={(e) => setCountryId(e.value ?? null)}
            placeholder="All countries"
            showClear
            filter
            className="w-12rem"
            aria-label="Filter by country"
          />
          <Dropdown
            value={categoryId}
            options={categories.options}
            onChange={(e) => setCategoryId(e.value ?? null)}
            placeholder="All categories"
            showClear
            filter
            className="w-12rem"
            aria-label="Filter by category of law"
          />
        </>
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
            header="Category"
            body={(row: Legislation) => categories.labelFor(row.category_of_law_id)}
          />
          <Column
            header="Scope"
            body={(row: Legislation) =>
              row.state_id ? states.labelFor(row.state_id) : <Tag value="Central" severity="info" />
            }
          />
          <Column
            header="Effective"
            body={(row: Legislation) => formatIsoDate(row.effective_date)}
            sortable
            field="effective_date"
            style={{ width: '9rem' }}
          />
          <Column
            header="Status"
            body={(row: Legislation) => <MasterStatusTag isActive={row.is_active} />}
            style={{ width: '7rem' }}
          />
          {permissions.canModifyRows && (
            <Column
              header="Actions"
              body={(row: Legislation) => (
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
      <LegislationForm
        visible={crud.dialogVisible}
        legislation={crud.editing}
        saving={createMutation.isPending || updateMutation.isPending}
        onHide={crud.closeDialog}
        onSubmit={crud.submit}
      />
    </MasterCrudPage>
  );
};
